# -*- coding: utf-8 -*-
"""
Диалог создания акта дефектации через AI по пункту ремонтной ведомости.

Сценарий:
1. Пользователь (инженер-технолог или строитель) нажимает "🧠 Создать акт
   дефектации (AI)" у пункта ведомости.
2. Бот определяет оборудование по описанию пункта и подбирает применимые ГОСТы.
3. Бот задаёт уточняющие вопросы (дефекты, тип ремонта, доп. детали).
4. Бот генерирует акт дефектации (по шаблону templates/defect_act_template.xlsx
   + Алиса/YandexGPT) и отправляет файл.
5. Пользователь подтверждает/правит/удаляет акт. При правке бот уточняет,
   что именно исправить, и повторяет генерацию — не более MAX_EDITS раз,
   пока акт не будет подтверждён или отклонён.

Состояние диалога хранится персистентно в БД (models.ActDialogSession),
включая байты сгенерированного файла — это переживает перезапуск/передеплой
бота (например, на Railway). Диалог, неактивный дольше SESSION_TIMEOUT,
считается устаревшим и автоматически закрывается.
"""

import re
import json
import logging
from io import BytesIO
from datetime import datetime, timedelta

from telebot import types

import bot_context
from models import SessionLocal, Ship, RepairStatement, StatementItem, ActDialogSession
from file_storage import storage
from services.extra import (
    detect_equipment_type,
    detect_pump_type,
    generate_work_volume,
    get_user_role,
)
from services.defect_act_service import generate_defect_act
from services.defect_profiles import (
    PROFILE_LABELS,
    build_defect_rows,
    detect_defect_profile,
    get_profile_question,
)

logger = logging.getLogger(__name__)

# Роли, которым разрешено создавать акты дефектации через AI-диалог.
ALLOWED_ROLES = ("engineer", "builder")

# Максимальное число циклов правок акта, прежде чем диалог придётся завершить.
MAX_EDITS = 5

# Таймаут неактивности диалога: по истечении сессия считается устаревшей.
SESSION_TIMEOUT = timedelta(hours=2)


def _check_access(telegram_id):
    """Проверяет, разрешена ли пользователю работа с AI-диалогом акта.

    Доступ разрешён ролям из ALLOWED_ROLES и администраторам (ADMIN_IDS).
    """
    if telegram_id in (bot_context.ADMIN_IDS or []):
        return True
    role = get_user_role(telegram_id)
    return role in ALLOWED_ROLES


def _get_item_and_ship(item_id):
    """Возвращает (dict с данными пункта, название судна) или (None, None)."""
    session = SessionLocal()
    try:
        item = session.query(StatementItem).filter_by(id=item_id).first()
        if not item:
            return None, None
        statement = session.query(RepairStatement).filter_by(id=item.statement_id).first()
        ship = session.query(Ship).filter_by(id=statement.ship_id).first() if statement else None
        return (
            {
                "id": item.id,
                "item_number": item.item_number,
                "description": item.description,
                "section": item.section,
            },
            ship.name if ship else None,
        )
    finally:
        session.close()


def _find_relevant_gosts(query_text, limit=5):
    """Ищет применимые ГОСТы по названию оборудования."""
    if not bot_context.gost_checker or not query_text:
        return []
    try:
        results = bot_context.gost_checker.search(query_text)
        gosts = []
        for gost_id, data in list(results.items())[:limit]:
            gosts.append(f"{gost_id} — {data.get('title', '')}")
        return gosts
    except Exception as e:
        logger.warning(f"Ошибка поиска ГОСТов: {e}")
        return []


# ============================================================
#  ХРАНЕНИЕ СЕССИИ ДИАЛОГА В БД (персистентно, переживает передеплой)
# ============================================================

def _save_session(chat_id, data):
    """Сохраняет (создаёт или обновляет) сессию диалога в БД."""
    db = SessionLocal()
    try:
        row = db.query(ActDialogSession).filter_by(chat_id=chat_id).first()
        if not row:
            row = ActDialogSession(chat_id=chat_id)
            db.add(row)
        row.item_id = data["item_id"]
        row.item_number = data["item_number"]
        row.ship = data["ship"]
        row.equipment = data["equipment"]
        row.equipment_type = data.get("equipment_type")
        row.pump_type = data.get("pump_type")
        row.gosts_json = json.dumps(data.get("gosts") or [], ensure_ascii=False)
        row.defects_json = json.dumps(data.get("defects") or [], ensure_ascii=False)
        row.repair_type = data.get("repair_type")
        row.extra_info = data.get("extra_info") or ""
        row.corrections_json = json.dumps(data.get("corrections") or [], ensure_ascii=False)
        row.edit_count = data.get("edit_count", 0)
        row.work_volume = data.get("work_volume")
        row.last_file = data.get("last_file")
        row.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def _load_session(chat_id):
    """Загружает сессию диалога из БД. Возвращает dict или None.

    Возвращает None, если сессии нет или она истекла по таймауту
    (в этом случае запись также удаляется).
    """
    db = SessionLocal()
    try:
        row = db.query(ActDialogSession).filter_by(chat_id=chat_id).first()
        if not row:
            return None
        if row.updated_at and datetime.utcnow() - row.updated_at > SESSION_TIMEOUT:
            db.delete(row)
            db.commit()
            return None
        return {
            "item_id": row.item_id,
            "item_number": row.item_number,
            "ship": row.ship,
            "equipment": row.equipment,
            "equipment_type": row.equipment_type,
            "pump_type": row.pump_type,
            "gosts": json.loads(row.gosts_json) if row.gosts_json else [],
            "defects": json.loads(row.defects_json) if row.defects_json else [],
            "repair_type": row.repair_type,
            "extra_info": row.extra_info or "",
            "corrections": json.loads(row.corrections_json) if row.corrections_json else [],
            "edit_count": row.edit_count or 0,
            "work_volume": row.work_volume,
            "last_file": row.last_file,
        }
    finally:
        db.close()


def _delete_session(chat_id):
    """Удаляет сессию диалога из БД."""
    db = SessionLocal()
    try:
        db.query(ActDialogSession).filter_by(chat_id=chat_id).delete()
        db.commit()
    finally:
        db.close()


def register_act_dialog_handlers(bot):
    """Регистрирует обработчики диалога создания акта дефектации через AI."""

    def _generate_and_send(chat_id):
        session = _load_session(chat_id)
        if not session:
            bot.send_message(chat_id, "⏳ Сессия создания акта истекла. Начните заново.")
            return
        try:
            full_text = " ".join(session["defects"]) + " " + session.get("extra_info", "")
            work_volume = generate_work_volume(
                session["defects"], full_text, session.get("pump_type"), session.get("equipment_type")
            )
            if session.get("gosts"):
                work_volume += "\n\nПрименимые ГОСТы: " + ", ".join(
                    g.split(" — ")[0] for g in session["gosts"]
                )

            basis = f"Ремонтная ведомость судна «{session['ship']}», пункт {session['item_number']}"

            profile = detect_defect_profile(session["equipment"])
            rows = build_defect_rows(
                session["equipment"], session["defects"], work_volume, profile
            )
            file_bytes = generate_defect_act({
                "act_number": session["item_number"],
                "act_date": datetime.now().strftime("%d.%m.%Y"),
                "ship": session["ship"],
                "repair_item": session["item_number"],
                "equipment": session["equipment"],
                "repair_category": session.get("repair_type") or "Текущий ремонт",
                "work_summary": f"Дефектация: {PROFILE_LABELS.get(profile, PROFILE_LABELS['general'])}",
                "basis": basis,
                "rows": rows,
                "conclusion": (
                    "Выявленные дефекты подлежат устранению согласно указанному "
                    "объёму ремонтных работ. После ремонта выполнить сборку, "
                    "регулировку и контрольные испытания."
                ),
            })
            session["last_file"] = file_bytes
            session["work_volume"] = work_volume
            _save_session(chat_id, session)

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Подтвердить и добавить", callback_data="aiact_confirm"))
            if session["edit_count"] < MAX_EDITS:
                markup.add(types.InlineKeyboardButton("✏️ Внести правки", callback_data="aiact_edit"))
            markup.add(types.InlineKeyboardButton("🗑 Удалить", callback_data="aiact_reject"))

            caption = "📄 Акт дефектации сгенерирован. Что делаем с документом?"
            if session["edit_count"] >= MAX_EDITS:
                caption += f"\n\n⚠️ Достигнут лимит правок ({MAX_EDITS}). Подтвердите или удалите акт."

            bot.send_document(
                chat_id,
                BytesIO(file_bytes),
                visible_file_name=f'Акт_дефектации_{session["item_number"]}_{session["ship"]}.xlsx',
                caption=caption,
                reply_markup=markup,
            )
        except Exception as e:
            logger.error(f"Ошибка генерации акта через AI: {e}", exc_info=True)
            bot.send_message(chat_id, f"❌ Ошибка при генерации акта: {e}")
            _delete_session(chat_id)

    # --- ШАГ 0: старт диалога с кнопки пункта ведомости ---

    @bot.callback_query_handler(func=lambda call: call.data.startswith("aiact_start_"))
    def handle_start(call):
        if not _check_access(call.from_user.id):
            bot.answer_callback_query(
                call.id,
                "❌ Создавать акты дефектации могут только инженер-технолог и строитель.",
                show_alert=True,
            )
            return

        try:
            item_id = int(call.data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка в данных", show_alert=True)
            return

        item, ship = _get_item_and_ship(item_id)
        if not item:
            bot.answer_callback_query(call.id, "❌ Пункт не найден", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        chat_id = call.message.chat.id

        equipment = item["description"] or f"Пункт {item['item_number']}"
        equipment_type = detect_equipment_type(equipment) or "pump"
        defect_profile = detect_defect_profile(equipment)
        pump_type = detect_pump_type(equipment)
        gosts = _find_relevant_gosts(equipment)

        _save_session(chat_id, {
            "item_id": item_id,
            "item_number": item["item_number"],
            "ship": ship or "Не указано",
            "equipment": equipment,
            "equipment_type": equipment_type,
            "pump_type": pump_type,
            "gosts": gosts,
            "defects": [],
            "repair_type": None,
            "extra_info": "",
            "corrections": [],
            "edit_count": 0,
            "work_volume": None,
            "last_file": None,
        })

        gost_text = ""
        if gosts:
            gost_text = "\n\n📚 Найдены применимые ГОСТы:\n" + "\n".join(f"• {g}" for g in gosts)

        msg = bot.send_message(
            chat_id,
            f"🧠 Готовлю акт дефектации по пункту {item['item_number']} «{equipment}» "
            f"(судно «{ship or 'не указано'}»).\n"
            f"Профиль: {PROFILE_LABELS.get(defect_profile, PROFILE_LABELS['general'])}."
            f"{gost_text}\n\n"
            "❓ Опишите обнаруженные дефекты/неисправности (можно списком через запятую "
            "или с новой строки):",
        )
        bot.register_next_step_handler(msg, _step_ask_defects)

    # --- ШАГ 1: дефекты ---

    def _step_ask_defects(message):
        chat_id = message.chat.id
        session = _load_session(chat_id)
        if not session:
            bot.send_message(chat_id, "⏳ Сессия создания акта истекла. Начните заново.")
            return
        text = message.text or ""
        defects = [d.strip() for d in re.split(r"[\n,;]+", text) if d.strip()]
        session["defects"] = defects or ["Не указано"]
        _save_session(chat_id, session)

        msg = bot.send_message(
            chat_id,
            "❓ Какой тип ремонта требуется? (текущий / средний / капитальный)",
        )
        bot.register_next_step_handler(msg, _step_ask_repair_type)

    # --- ШАГ 2: тип ремонта ---

    def _step_ask_repair_type(message):
        chat_id = message.chat.id
        session = _load_session(chat_id)
        if not session:
            bot.send_message(chat_id, "⏳ Сессия создания акта истекла. Начните заново.")
            return
        session["repair_type"] = (message.text or "Текущий ремонт").strip()
        _save_session(chat_id, session)

        profile = detect_defect_profile(session["equipment"])
        msg = bot.send_message(
            chat_id,
            "❓ Укажите дополнительные технические данные.\n\n"
            f"{get_profile_question(profile)}\n\n"
            "Если данных нет — напишите «нет».",
        )
        bot.register_next_step_handler(msg, _step_ask_extra)

    # --- ШАГ 3: доп. детали, затем генерация ---

    def _step_ask_extra(message):
        chat_id = message.chat.id
        session = _load_session(chat_id)
        if not session:
            bot.send_message(chat_id, "⏳ Сессия создания акта истекла. Начните заново.")
            return
        text = (message.text or "").strip()
        if text and text.lower() not in ("нет", "нету", "-"):
            session["extra_info"] = text
            pump_type = detect_pump_type(text)
            if pump_type:
                session["pump_type"] = pump_type
        _save_session(chat_id, session)

        bot.send_message(chat_id, "🧠 Генерирую акт дефектации...")
        _generate_and_send(chat_id)

    # --- ДЕЙСТВИЯ С ГОТОВЫМ АКТОМ ---

    @bot.callback_query_handler(func=lambda call: call.data == "aiact_confirm")
    def handle_confirm(call):
        chat_id = call.message.chat.id
        if not _check_access(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Нет прав доступа", show_alert=True)
            return
        session = _load_session(chat_id)
        if not session or not session.get("last_file"):
            bot.answer_callback_query(call.id, "❌ Нет активного акта", show_alert=True)
            return

        result = storage.save_document(
            file_name=f'Акт_дефектации_{session["item_number"]}.xlsx',
            file_content=session["last_file"],
            item_id=session["item_id"],
            category="defect_act",
            user_id=call.from_user.id,
            source="bot",
        )
        bot.answer_callback_query(call.id)
        if result["success"]:
            bot.send_message(
                chat_id,
                f"✅ Акт дефектации добавлен к пункту {session['item_number']} "
                f"(документ #{result['document_id']}).",
            )
        else:
            bot.send_message(chat_id, f"❌ Ошибка при сохранении акта: {result['message']}")
        _delete_session(chat_id)

    @bot.callback_query_handler(func=lambda call: call.data == "aiact_reject")
    def handle_reject(call):
        chat_id = call.message.chat.id
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "🗑 Акт дефектации удалён (не сохранён).")
        _delete_session(chat_id)

    @bot.callback_query_handler(func=lambda call: call.data == "aiact_edit")
    def handle_edit(call):
        chat_id = call.message.chat.id
        if not _check_access(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Нет прав доступа", show_alert=True)
            return
        session = _load_session(chat_id)
        if not session:
            bot.answer_callback_query(call.id, "❌ Нет активного акта", show_alert=True)
            return
        if session["edit_count"] >= MAX_EDITS:
            bot.answer_callback_query(
                call.id,
                f"❌ Достигнут лимит правок ({MAX_EDITS}). Подтвердите или удалите акт.",
                show_alert=True,
            )
            return
        bot.answer_callback_query(call.id)
        remaining = MAX_EDITS - session["edit_count"]
        msg = bot.send_message(
            chat_id,
            "✏️ Какие пункты акта нужно исправить и что именно не так? Опишите подробно "
            "(например: «в объёме работ добавь замену уплотнений, неверно указан тип "
            f"ремонта — капитальный»).\n\nОсталось правок: {remaining}.",
        )
        bot.register_next_step_handler(msg, _step_apply_correction)

    def _step_apply_correction(message):
        chat_id = message.chat.id
        session = _load_session(chat_id)
        if not session:
            bot.send_message(chat_id, "⏳ Сессия создания акта истекла. Начните заново.")
            return
        correction = (message.text or "").strip()
        if not correction:
            bot.send_message(chat_id, "Пожалуйста, опишите правки.")
            return
        session["corrections"].append(correction)
        session["defects"].append(correction)
        session["edit_count"] += 1
        _save_session(chat_id, session)
        bot.send_message(chat_id, "🧠 Учитываю правки и перегенерирую акт...")
        _generate_and_send(chat_id)
