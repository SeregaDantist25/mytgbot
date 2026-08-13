# -*- coding: utf-8 -*-
"""
Обработчики команд и сообщений.

Содержит регистрацию всех message-обработчиков: /start, /login, /approve,
/users, /set_role, /scan, /stats, /gosts, /search, /approve_contract,
/reject_contract, загрузку ремонтной ведомости и главный обработчик
сообщений (NLP через Алису).

Все глобальные объекты (bot, gost_checker, alisa_router и т.д.) читаются
из bot_context, который заполняется в bot.py при инициализации.
"""

import re
import traceback
import logging

import telebot
from telebot import types

import db
import bot_context
import navigation
import document_commands
import services.user_service as us

from services.extra import (
    load_ships,
    add_ship,
    get_chat_state,
    set_chat_state,
    detect_ship,
    detect_pump_type,
    detect_equipment_type,
    extract_clearances_from_text,
    parse_works_for_avr,
    analyze_query_local,
    generate_work_volume,
    generate_base_work_volume,
    get_user_role,
    find_employee_role,
    can_upload_repair_list,
    save_repair_items_to_db,
)
from services.document_builder import create_defect_document, create_avr_document
from models import SessionLocal, Ship

from utils import NAVIGATION_BUTTONS

logger = logging.getLogger(__name__)


def register_message_handlers(bot: telebot.TeleBot) -> None:
    """Регистрирует все message-обработчики в боте.

    Args:
        bot: Экземпляр TeleBot.
    """
    bot_context.bot = bot

    # ============================================================
    #  КНОПКИ НАВИГАЦИИ
    # ============================================================

    def show_navigation_menu(chat_id, text="👋 Используйте кнопки для навигации."):
        """Показать ReplyKeyboardMarkup с кнопками навигации."""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for btn in NAVIGATION_BUTTONS:
            markup.add(btn)
        bot.send_message(chat_id, text, reply_markup=markup)

    # ============================================================
    #  КОМАНДА /START
    # ============================================================

    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        """Приветственное сообщение и кнопки навигации."""
        bot.reply_to(
            message,
            "👋 Привет! Я — твой инженерный ассистент.\n\n"
            "📌 Что я умею:\n"
            "• Создавать Акты дефектации (скажи 'сделай акт')\n"
            "• Создавать Акты выполненных работ (скажи 'сделай АВР')\n"
            "• Проверять зазоры по ТУ (скажи 'проверь зазор')\n"
            "• Проверять параметры по ГОСТам (скажи 'проверь по ГОСТ')\n"
            "• Показывать частые дефекты (спроси 'какие дефекты')\n"
            "• Показывать чек-лист деталей (спроси 'чек-лист насоса')\n\n"
            "📌 Типы оборудования в базе:\n"
            "• Насосы: центробежные, шестерёнчатые, поршневые\n"
            "• Двигатели (MAN, Caterpillar и др.)\n\n"
            "📌 Доступные команды:\n"
            "• /gosts — список всех ГОСТов\n"
            "• /search — поиск по ГОСТам\n"
            "• /stats — статистика AI\n\n"
            "🧠 Я использую Яндекс.Алису и базу знаний для анализа запросов!\n\n"
            "📝 Примеры:\n"
            "• 'Судно Славянская, пожарный насос, повреждена крылатка. Сделай акт'\n"
            "• 'Судно Аргака, главный двигатель MAN, износ поршневых колец. Сделай акт'\n"
            "• 'проверь по ГОСТ 520-2011 диаметр=50'\n"
            "• 'проверь по ГОСТ 3325-85 зазор=0.15'"
        )
        show_navigation_menu(message.chat.id)

    # ============================================================
    #  АВТОРИЗАЦИЯ И РОЛИ
    # ============================================================

    @bot.message_handler(commands=['login'])
    def cmd_login(message):
        """Регистрация/вход пользователя."""
        user = us.get_user(message.chat.id)
        if user and user.approved:
            bot.reply_to(
                message,
                f"✅ Вы уже авторизованы как {user.name} "
                f"({us.ROLE_LABELS.get(user.role, user.role)})."
            )
            show_navigation_menu(message.chat.id)
            return
        if user and not user.approved:
            bot.reply_to(message, "⏳ Ваша заявка ещё на рассмотрении. Ожидайте одобрения.")
            return
        set_chat_state(message.chat.id, "reg_step", "name")
        bot.reply_to(message, "📝 Регистрация. Введите ваше ФИО:")

    @bot.message_handler(commands=['approve'])
    def cmd_approve(message):
        """Одобрение/отклонение заявок на регистрацию."""
        user = us.get_user(message.chat.id)
        if not us.can_approve_users(user):
            bot.reply_to(message, "🚫 У вас нет прав на одобрение пользователей.")
            return
        pending = us.get_pending_users()
        if not pending:
            bot.reply_to(message, "📭 Нет заявок на одобрение.")
            return
        lines = ["📋 Заявки на регистрацию:"]
        for p in pending:
            lines.append(
                f"{p['user_id']}: {p['name']} — {us.ROLE_LABELS.get(p['role_requested'], p['role_requested'])}"
            )
        lines.append("\nОтветьте: /approve_yes <id> или /approve_no <id>")
        bot.reply_to(message, "\n".join(lines))

    @bot.message_handler(commands=['approve_yes'])
    def cmd_approve_yes(message):
        """Одобрение заявки на регистрацию."""
        user = us.get_user(message.chat.id)
        if not us.can_approve_users(user):
            bot.reply_to(message, "🚫 Нет прав.")
            return
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Укажите id: /approve_yes <id>")
            return
        try:
            uid = int(parts[1])
        except ValueError:
            bot.reply_to(message, "Неверный id.")
            return
        pending = us.get_pending_users()
        target = next((p for p in pending if p['user_id'] == uid), None)
        if not target:
            bot.reply_to(message, "Заявка не найдена.")
            return
        us.create_user(uid, target['name'], target['role_requested'], target.get('phone'), approved=1)
        us.remove_pending_user(uid)
        us.log_action(user.telegram_id, "approve_user", details=f"Одобрен пользователь {target['name']} ({uid})")
        bot.reply_to(message, f"✅ Пользователь {target['name']} одобрен.")
        try:
            bot.send_message(uid, f"✅ Ваша регистрация одобрена. Добро пожаловать, {target['name']}!")
        except Exception:
            pass

    @bot.message_handler(commands=['approve_no'])
    def cmd_approve_no(message):
        """Отклонение заявки на регистрацию."""
        user = us.get_user(message.chat.id)
        if not us.can_approve_users(user):
            bot.reply_to(message, "🚫 Нет прав.")
            return
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Укажите id: /approve_no <id>")
            return
        try:
            uid = int(parts[1])
        except ValueError:
            bot.reply_to(message, "Неверный id.")
            return
        us.remove_pending_user(uid)
        bot.reply_to(message, f"❌ Заявка {uid} отклонена.")
        try:
            bot.send_message(uid, "❌ Ваша заявка на регистрацию отклонена.")
        except Exception:
            pass

    @bot.message_handler(commands=['users'])
    def cmd_users(message):
        """Список пользователей (для инженера-технолога)."""
        user = us.get_user(message.chat.id)
        if not us.is_engineer(user):
            bot.reply_to(message, "🚫 Только для инженера-технолога.")
            return
        rows = us.get_users()
        if not rows:
            bot.reply_to(message, "Пользователей пока нет.")
            return
        lines = ["👥 Пользователи:"]
        for r in rows:
            status = "✅" if r.approved else "⏳"
            lines.append(f"{status} {r.name} — {us.ROLE_LABELS.get(r.role, r.role)}")
        bot.reply_to(message, "\n".join(lines))

    # ============================================================
    #  УСТАНОВКА РОЛИ (ADMIN)
    # ============================================================

    @bot.message_handler(commands=['set_role'])
    def cmd_set_role(message):
        """Устанавливает роль пользователю: /set_role <telegram_id> <role>."""
        if message.chat.id not in bot_context.ADMIN_IDS:
            bot.reply_to(message, "🚫 Команда доступна только администраторам.")
            return
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "📝 Использование: /set_role <telegram_id> <role>\nРоли: technologist, user")
            return
        try:
            tg_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ telegram_id должен быть числом.")
            return
        role = parts[2].strip().lower()
        if role not in ("technologist", "user"):
            bot.reply_to(message, "❌ Неизвестная роль. Допустимые: technologist, user")
            return
        from models import SessionLocal, User
        session = SessionLocal()
        try:
            user = session.query(User).filter(User.telegram_id == tg_id).first()
            if user:
                user.role = role
            else:
                session.add(User(telegram_id=tg_id, role=role))
            session.commit()
            bot.reply_to(message, f"✅ Роль пользователя {tg_id} установлена: {role}")
        except Exception as e:
            session.rollback()
            bot.reply_to(message, f"❌ Ошибка при сохранении роли: {e}")
        finally:
            session.close()

    # ============================================================
    #  СКАНИРОВАНИЕ ПАПКИ repair_docs
    # ============================================================

    @bot.message_handler(commands=['scan'])
    def cmd_scan(message):
        """Сканирует папку repair_docs и обрабатывает новые файлы."""
        user = db.get_user(message.chat.id)
        if not user or not user.get("approved"):
            bot.reply_to(message, "🔒 Сначала авторизуйтесь: /login")
            return
        bot.reply_to(message, "🔍 Сканирую папку repair_docs...")
        import scanner
        messages = scanner.scan_repair_docs(uploaded_by=user["user_id"])
        for m in messages:
            bot.send_message(message.chat.id, m)
        notify_contracts_for_approval()

    @bot.message_handler(content_types=['document'])
    def handle_repair_list_upload(message):
        """Обработчик загрузки Excel-файла с ремонтной ведомостью."""
        if not can_upload_repair_list(message.chat.id):
            bot.reply_to(message, "🚫 У вас нет прав на загрузку ремонтной ведомости.")
            return

        file_info = bot.get_file(message.document.file_id)
        file_path = file_info.file_path
        downloaded_file = bot.download_file(file_path)

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(downloaded_file)
            tmp_path = tmp.name

        try:
            import scanner
            items = scanner.parse_repair_list(tmp_path)
            if not items:
                bot.reply_to(message, "⚠️ В файле не найдено пунктов ремонтной ведомости.")
                return

            filename = message.document.file_name or "unknown"
            ship_name = scanner.detect_ship_from_filename(filename)

            if not ship_name:
                bot.reply_to(
                    message,
                    "❌ Не удалось определить судно из имени файла. "
                    "Используйте формат: Ремведомость_<Судно>.xlsx",
                )
                return

            session = SessionLocal()
            try:
                ship = session.query(Ship).filter_by(name=ship_name).first()
                if not ship:
                    bot.reply_to(message, f"❌ Судно '{ship_name}' не найдено в базе. Добавьте его сначала.")
                    return

                inserted, skipped, stmt_id = save_repair_items_to_db(ship.id, items)
                bot.reply_to(
                    message,
                    f"✅ Ремонтная ведомость загружена для судна '{ship_name}'\n"
                    f"📝 Добавлено: {inserted} пунктов\n"
                    f"⏭️ Пропущено (дубликаты): {skipped}",
                )
            finally:
                session.close()
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка при обработке файла: {str(e)}")
        finally:
            import os
            os.unlink(tmp_path)

    @bot.message_handler(commands=['approve_contract'])
    def cmd_approve_contract(message):
        """Утверждение договора (инженер-технолог или директор)."""
        user = db.get_user(message.chat.id)
        if not db.can_approve_users(user):
            bot.reply_to(message, "🚫 Нет прав на утверждение договоров.")
            return
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Укажите id: /approve_contract <id>")
            return
        try:
            doc_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "Неверный id.")
            return
        doc = db.get_document(doc_id)
        if not doc or doc["doc_type"] != db.DOC_CONTRACT:
            bot.reply_to(message, "Договор не найден.")
            return
        db.approve_document(doc_id)
        db.log_action(user["user_id"], "approve_contract", ship_id=doc["ship_id"], doc_id=doc_id)
        bot.reply_to(message, f"✅ Договор (id={doc_id}) утверждён.")

    @bot.message_handler(commands=['reject_contract'])
    def cmd_reject_contract(message):
        """Отклонение договора (инженер-технолог или директор)."""
        user = db.get_user(message.chat.id)
        if not db.can_approve_users(user):
            bot.reply_to(message, "🚫 Нет прав.")
            return
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Укажите id: /reject_contract <id>")
            return
        try:
            doc_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "Неверный id.")
            return
        doc = db.get_document(doc_id)
        if not doc:
            bot.reply_to(message, "Договор не найден.")
            return
        db.delete_document(doc_id)
        db.log_action(user["user_id"], "reject_contract", ship_id=doc["ship_id"], doc_id=doc_id)
        bot.reply_to(message, f"❌ Договор (id={doc_id}) отклонён и удалён.")

    @bot.message_handler(commands=['stats'])
    def show_stats(message):
        """Показывает статистику использования AI."""
        if bot_context.alisa_router:
            try:
                stats = bot_context.alisa_router.get_stats()
                response = "📊 **Статистика Алисы (YandexGPT):**\n\n"
                response += f"✅ Вызовов: {stats['calls']}\n"
                response += f"❌ Ошибок: {stats['errors']}\n"
                bot.reply_to(message, response, parse_mode='Markdown')
                return
            except Exception as e:
                logger.warning(f"Ошибка при получении статистики: {e}")

        bot.reply_to(message, "❌ Статистика недоступна")

    # ============================================================
    #  КОМАНДА /GOSTS — СПИСОК ВСЕХ ГОСТОВ
    # ============================================================

    @bot.message_handler(commands=['gosts'])
    def show_gosts(message):
        """Показывает список всех доступных ГОСТов."""
        if not bot_context.gost_checker:
            bot.reply_to(message, "❌ ГОСТ чекер не загружен. Проверьте файл gost_checker.py")
            return

        gosts = bot_context.gost_checker.get_all_gosts()
        if not gosts:
            bot.reply_to(message, "❌ База ГОСТов не загружена. Запустите merge_gosts.py")
            return

        response = "📁 **Доступные ГОСТы:**\n\n"

        sections = {}
        for gost_id, data in gosts.items():
            section = data.get("section", "Общие")
            if section not in sections:
                sections[section] = []
            sections[section].append((gost_id, data.get("title", "")[:50]))

        for section, items in sections.items():
            response += f"**{section}** ({len(items)})\n"
            for gost_id, title in items[:5]:
                response += f"• {gost_id} — {title}...\n"
            if len(items) > 5:
                response += f"  _... и ещё {len(items)-5}_\n"
            response += "\n"

        response += "💡 Используйте `проверь по ГОСТ {номер} {параметр}={значение}`\n"
        response += "Пример: `проверь по ГОСТ 520-2011 диаметр=50`"

        bot.reply_to(message, response, parse_mode='Markdown')

    # ============================================================
    #  КОМАНДА /SEARCH — ПОИСК ПО ГОСТАМ
    # ============================================================

    @bot.message_handler(commands=['search'])
    def search_gosts(message):
        """Поиск по ГОСТам."""
        if not bot_context.gost_checker:
            bot.reply_to(message, "❌ ГОСТ чекер не загружен")
            return

        query = message.text.replace('/search', '').strip()
        if not query:
            bot.reply_to(message, "📝 Введите поисковый запрос: `/search подшипник`")
            return

        results = bot_context.gost_checker.search(query)
        if not results:
            bot.reply_to(message, f"❌ Ничего не найдено по запросу '{query}'")
            return

        response = f"📋 **Результаты поиска по '{query}':**\n\n"
        for gost_id, data in list(results.items())[:10]:
            response += f"• **{gost_id}** — {data.get('title', 'Без названия')[:60]}...\n"

        if len(results) > 10:
            response += f"\n_... и ещё {len(results)-10} результатов_"

        bot.reply_to(message, response, parse_mode='Markdown')

    # ============================================================
    #  ГЛАВНЫЙ ОБРАБОТЧИК (ЧЕРЕЗ АЛИСУ)
    # ============================================================

    @bot.message_handler(func=lambda message: True)
    def handle_message(message):
        """Главный обработчик всех сообщений (NLP через Алису)."""
        user_text = message.text
        text_lower = user_text.lower()

        if user_text.startswith('/'):
            return

        # --- ПРОПУСК КНОПОК НАВИГАЦИИ ---
        # Кнопки меню обрабатываются отдельными хендлерами (bot_handlers_new),
        # поэтому не должны уходить в NLP.
        if user_text in NAVIGATION_BUTTONS:
            return

        # --- РЕГИСТРАЦИЯ НОВОГО ПОЛЬЗОВАТЕЛЯ ---
        reg_step = get_chat_state(message.chat.id, "reg_step")
        if reg_step:
            if reg_step == "name":
                name = user_text.strip()
                if not name:
                    bot.reply_to(message, "Введите ФИО:")
                    return
                # Автоматическое назначение роли по ФИО из employees.json
                auto_role = find_employee_role(name)
                if auto_role:
                    us.create_user(message.chat.id, name, auto_role, approved=1)
                    set_chat_state(message.chat.id, "reg_step", None)
                    set_chat_state(message.chat.id, "reg_name", None)
                    bot.reply_to(
                        message,
                        f"✅ Вы зарегистрированы как {us.ROLE_LABELS.get(auto_role, auto_role)}, {name}!",
                    )
                    return
                set_chat_state(message.chat.id, "reg_name", name)
                set_chat_state(message.chat.id, "reg_step", "role")
                bot.reply_to(
                    message,
                    "Выберите роль:\n"
                    "1️⃣ Строитель\n"
                    "2️⃣ Директор\n"
                    "3️⃣ Заказчик\n\n"
                    "Напишите номер или название. Если вы инженер-технолог — введите секретный код.",
                )
                return
            if reg_step == "role":
                name = get_chat_state(message.chat.id, "reg_name")
                choice = user_text.strip().lower()
                if bot_context.ENGINEER_CODE and choice == bot_context.ENGINEER_CODE.lower():
                    us.create_user(message.chat.id, name, us.ROLE_ENGINEER, approved=1)
                    set_chat_state(message.chat.id, "reg_step", None)
                    set_chat_state(message.chat.id, "reg_name", None)
                    bot.reply_to(message, f"✅ Вы зарегистрированы как инженер-технолог, {name}!")
                    return
                role_map = {
                    "1": us.ROLE_BUILDER, "строитель": us.ROLE_BUILDER,
                    "2": us.ROLE_DIRECTOR, "директор": us.ROLE_DIRECTOR,
                    "3": us.ROLE_CUSTOMER, "заказчик": us.ROLE_CUSTOMER,
                }
                role = role_map.get(choice)
                if not role:
                    bot.reply_to(message, "Неверный выбор. Напишите номер (1/2/3) или название роли.")
                    return
                us.add_pending_user(message.chat.id, name, role)
                set_chat_state(message.chat.id, "reg_step", None)
                set_chat_state(message.chat.id, "reg_name", None)
                bot.reply_to(
                    message,
                    f"📝 Заявка на роль «{us.ROLE_LABELS.get(role, role)}» отправлена на одобрение.\n"
                    "Ожидайте подтверждения.",
                )
                approvers = [
                    u.telegram_id for u in us.get_users()
                    if u.approved and u.role in (us.ROLE_ENGINEER, us.ROLE_DIRECTOR)
                ]
                for uid in approvers:
                    try:
                        bot.send_message(uid, f"📋 Новая заявка: {name} ({us.ROLE_LABELS.get(role, role)}). /approve")
                    except Exception:
                        pass
                return

        # --- ПРОВЕРКА АВТОРИЗАЦИИ ---
        user = us.get_user(message.chat.id)
        if not user or not user.approved:
            bot.reply_to(
                message,
                "🔒 Для работы с ботом необходимо авторизоваться.\n"
                "Введите /login для регистрации или входа.",
            )
            return

        # --- ПРОВЕРКА РОЛИ (интеграция с NLP) ---
        role = get_user_role(message.chat.id)
        if message.chat.id not in bot_context.ADMIN_IDS and role not in ("engineer", "engineer_technologist"):
            bot.reply_to(message, "📄 Отправьте документы или используйте кнопки для навигации.")
            return

        # --- ПРОВЕРКА РОЛИ (НОВОЕ) ---
        if bot_context.DOCUMENT_MANAGER_AVAILABLE:
            import document_manager
            user_role = document_manager.get_user_role(message.chat.id)
            if user_role == document_manager.ROLE_CUSTOMER:
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.add("📋 Ремонтная ведомость")
                markup.add("📄 Документы")
                markup.add("🚢 Суда")
                bot.send_message(
                    message.chat.id,
                    "👋 Используйте кнопки для навигации.",
                    reply_markup=markup,
                )
                return

        # --- ОБРАБОТКА УТОЧНЕНИЯ ОСНОВАНИЯ АКТА ---
        pending = get_chat_state(message.chat.id, "pending_act")
        if pending:
            if text_lower.strip() in ("отмена", "отменить", "cancel", "стоп"):
                set_chat_state(message.chat.id, "pending_act", None)
                bot.reply_to(message, "Отменено. Акт не создан.")
                return
            basis = user_text.strip()
            if not basis:
                bot.reply_to(message, "Пожалуйста, укажите основание для акта.")
                return
            set_chat_state(message.chat.id, "pending_act", None)
            try:
                file_stream = create_defect_document(
                    pending["ship"], pending["equipment"], pending["defects"],
                    pending["work_volume"], pending["pump_type"], pending["repair_type"],
                    purpose=pending["purpose"], basis=basis,
                )
                bot.send_document(
                    message.chat.id,
                    file_stream,
                    visible_file_name=f'Акт_дефектации_{pending["ship"] or "судна"}.docx',
                )
                bot.send_message(message.chat.id, "📄 Акт дефектации в Word отправлен!")
            except Exception as e:
                logger.error(traceback.format_exc())
                bot.send_message(message.chat.id, f"❌ Ошибка при создании акта:\n\n{str(e)}")
            return

        # --- ОБРАБОТКА ВЫБОРА/ДОБАВЛЕНИЯ СУДНА ---
        if get_chat_state(message.chat.id, "awaiting_ship"):
            ships = load_ships()
            ship_names = list(ships.values())
            choice = user_text.strip()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(ship_names):
                    ship = ship_names[idx]
                    set_chat_state(message.chat.id, "awaiting_ship", None)
                    set_chat_state(message.chat.id, "pending_act", {
                        "ship": ship,
                        "equipment": get_chat_state(message.chat.id, "draft_equipment"),
                        "defects": get_chat_state(message.chat.id, "draft_defects"),
                        "work_volume": get_chat_state(message.chat.id, "draft_work_volume"),
                        "pump_type": get_chat_state(message.chat.id, "draft_pump_type"),
                        "repair_type": get_chat_state(message.chat.id, "draft_repair_type"),
                        "purpose": "Определение технического состояния и объема ремонта",
                    })
                    bot.send_message(
                        message.chat.id,
                        f"✅ Судно: {ship}. Укажите основание для акта, например:\n"
                        "«План-график ремонта на 2026 год» или «Заявка капитана»",
                    )
                    return
                else:
                    bot.reply_to(
                        message,
                        "❌ Неверный номер. Выберите из списка или напишите название нового судна.",
                    )
                    return
            if choice.lower() in ("новое", "добавить", "новое судно"):
                set_chat_state(message.chat.id, "awaiting_ship", "new")
                bot.reply_to(message, "✏️ Напишите название нового судна:")
                return
            if get_chat_state(message.chat.id, "awaiting_ship") == "new":
                ok, text = add_ship(choice)
                if ok:
                    set_chat_state(message.chat.id, "awaiting_ship", None)
                    set_chat_state(message.chat.id, "pending_act", {
                        "ship": choice.strip(),
                        "equipment": get_chat_state(message.chat.id, "draft_equipment"),
                        "defects": get_chat_state(message.chat.id, "draft_defects"),
                        "work_volume": get_chat_state(message.chat.id, "draft_work_volume"),
                        "pump_type": get_chat_state(message.chat.id, "draft_pump_type"),
                        "repair_type": get_chat_state(message.chat.id, "draft_repair_type"),
                        "purpose": "Определение технического состояния и объема ремонта",
                    })
                    bot.send_message(message.chat.id, text)
                    bot.send_message(
                        message.chat.id,
                        "Укажите основание для акта, например:\n"
                        "«План-график ремонта на 2026 год» или «Заявка капитана»",
                    )
                else:
                    bot.reply_to(message, text)
                return
            if choice:
                ok, text = add_ship(choice)
                if ok:
                    set_chat_state(message.chat.id, "awaiting_ship", None)
                    set_chat_state(message.chat.id, "pending_act", {
                        "ship": choice.strip(),
                        "equipment": get_chat_state(message.chat.id, "draft_equipment"),
                        "defects": get_chat_state(message.chat.id, "draft_defects"),
                        "work_volume": get_chat_state(message.chat.id, "draft_work_volume"),
                        "pump_type": get_chat_state(message.chat.id, "draft_pump_type"),
                        "repair_type": get_chat_state(message.chat.id, "draft_repair_type"),
                        "purpose": "Определение технического состояния и объема ремонта",
                    })
                    bot.send_message(message.chat.id, text)
                    bot.send_message(
                        message.chat.id,
                        "Укажите основание для акта, например:\n"
                        "«План-график ремонта на 2026 год» или «Заявка капитана»",
                    )
                else:
                    bot.reply_to(message, text)
                return

        # --- ОБРАБОТКА УТОЧНЕНИЙ ---
        if get_chat_state(message.chat.id, "clarification"):
            equipment_type = text_lower
            if "1" in equipment_type or "насос" in equipment_type:
                set_chat_state(message.chat.id, "clarification", "pump")
                bot.reply_to(message, "✅ Принято: насос")
                return
            elif "2" in equipment_type or "двигател" in equipment_type:
                set_chat_state(message.chat.id, "clarification", "engine")
                bot.reply_to(message, "✅ Принято: двигатель")
                return
            else:
                set_chat_state(message.chat.id, "clarification", "other")
                bot.reply_to(message, "✅ Принято: другое оборудование")
                return

        # --- ПРОПУСК ОТВЕТОВ НА КНОПКИ/СООБЩЕНИЯ БОТА ---
        # Ответы на callback-кнопки и reply на сообщения бота не должны
        # уходить в NLP. Активные сценарии (регистрация, основание акта,
        # выбор судна, уточнения) обработаны выше, поэтому здесь это
        # безопасно пропускаем.
        if message.reply_to_message:
            return

        # ---- 1. АКТ ДЕФЕКТАЦИИ (ЧЕРЕЗ АЛИСУ) ----
        if any(word in text_lower for word in ['сделай акт', 'акт дефектации', 'оформи акт', 'составь акт']):
            handle_act_creation(message, user_text)
            return

        # ---- 2. АВР ----
        if any(word in text_lower for word in ['авр', 'акт выполненных', 'сделай авр', 'оформи авр']):
            handle_avr_creation(message, user_text)
            return

        # ---- 3. ПРОВЕРКА ПО ГОСТАМ ----
        if any(word in text_lower for word in ['проверь по госту', 'по ГОСТ', 'по госту', 'гост']):
            gost_match = re.search(r'гост\s*([\d-]+)', user_text, re.IGNORECASE)
            if gost_match and bot_context.gost_checker:
                gost_id = gost_match.group(1)
                param_match = re.search(r'(\w+)\s*[=:]\s*([\d.]+)', user_text)
                if param_match:
                    param_name = param_match.group(1).strip()
                    value = float(param_match.group(2))
                    result = bot_context.gost_checker.check_parameter(gost_id, param_name, value)

                    response = f"📊 **Проверка по ГОСТ {gost_id}**\n\n"
                    response += f"🔹 Параметр: {param_name}\n"
                    response += f"🔹 Значение: {value}\n\n"
                    response += f"{result.get('message', '')}"
                    if result.get('action'):
                        response += f"\n\n🔧 **Рекомендация:** {result['action']}"

                    bot.reply_to(message, response, parse_mode='Markdown')
                    return

        # ---- 4. ВСЁ ОСТАЛЬНОЕ — ЧЕРЕЗ АЛИСУ ----
        if bot_context.alisa_router:
            user_id = message.chat.id
            if user_id not in bot_context.user_histories:
                bot_context.user_histories[user_id] = []

            history = bot_context.user_histories[user_id]

            try:
                bot.send_chat_action(message.chat.id, 'typing')
                result = bot_context.alisa_router.process_query(user_text, history)

                history.append(f"Пользователь: {user_text}")
                history.append(f"Бот: {result.get('response', '')[:200]}")
                if len(history) > 10:
                    history = history[-10:]
                bot_context.user_histories[user_id] = history

                if result.get('status') == 'ok':
                    bot.reply_to(message, result.get('response', 'Извините, не удалось получить ответ.'))
                else:
                    bot.reply_to(message, "🤔 Попробую ответить без Алисы...")
                    handle_local_fallback(message, user_text)

            except Exception as e:
                logger.warning(f"Ошибка при вызове Алисы: {e}")
                bot.reply_to(message, "⚠️ Произошла ошибка при обращении к Алисе. Отвечаю в локальном режиме.")
                handle_local_fallback(message, user_text)
        else:
            handle_local_fallback(message, user_text)

    # ============================================================
    #  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ОБРАБОТЧИКА
    # ============================================================

    def handle_act_creation(message, user_text):
        """Создание Акта дефектации через Алису."""
        try:
            bot.send_message(message.chat.id, "🧠 Анализирую запрос и генерирую акт через Алису...")

            if bot_context.alisa_act_creator:
                try:
                    act_data = bot_context.alisa_act_creator.generate_act_data(user_text)
                    logger.info(f"Акт сгенерирован через Алису: {act_data}")
                except Exception as e:
                    logger.warning(f"Ошибка при вызове Алисы для акта: {e}")
                    act_data = None
            else:
                act_data = None

            if not act_data:
                logger.warning("Использую локальный парсер для акта")
                analysis = analyze_query_local(user_text)
                act_data = {
                    "ship": analysis.get('ship') or "Не указано",
                    "equipment": analysis.get('equipment') or "Не указано",
                    "repair_type": "Текущий ремонт",
                    "defects": analysis.get('defects', ["Не указано"]),
                    "work_volume": generate_work_volume(
                        analysis.get('defects', []),
                        user_text,
                        analysis.get('pump_type'),
                        analysis.get('equipment_type'),
                    ),
                    "conclusion": "Детали подлежат замене/восстановлению согласно указанному объёму работ.",
                }

            ship = act_data.get('ship', "Не указано")
            equipment = act_data.get('equipment', "Не указано")
            defects = act_data.get('defects', ["Не указано"])
            work_volume = act_data.get('work_volume', generate_base_work_volume(["Не указано"]))

            if not ship or ship == "Не указано":
                set_chat_state(message.chat.id, "draft_equipment", equipment)
                set_chat_state(message.chat.id, "draft_defects", defects)
                set_chat_state(message.chat.id, "draft_work_volume", work_volume)
                set_chat_state(message.chat.id, "draft_pump_type", detect_pump_type(user_text))
                set_chat_state(message.chat.id, "draft_repair_type", act_data.get('repair_type'))
                ships = load_ships()
                ship_names = list(ships.values())
                list_text = "\n".join(f"{i+1}. {name}" for i, name in enumerate(ship_names))
                set_chat_state(message.chat.id, "awaiting_ship", "choose")
                bot.send_message(
                    message.chat.id,
                    "🚢 Не удалось определить судно. Выберите из списка или добавьте новое:\n\n"
                    f"{list_text}\n\n"
                    "Напишите номер судна, название нового судна, или «новое» для добавления.",
                )
                return

            if not equipment or equipment == "Не указано":
                bot.send_message(
                    message.chat.id,
                    "🚫 Не удалось определить оборудование. Укажите тип и модель явно.",
                )
                return

            equipment_type = detect_equipment_type(equipment or "")
            if equipment_type is None:
                equipment_type = "pump"

            pump_type = detect_pump_type(user_text)

            repair_type = act_data.get('repair_type')
            set_chat_state(message.chat.id, "pending_act", {
                "ship": ship,
                "equipment": equipment,
                "defects": defects,
                "work_volume": work_volume,
                "pump_type": pump_type,
                "repair_type": repair_type,
                "purpose": "Определение технического состояния и объема ремонта",
            })
            bot.send_message(
                message.chat.id,
                "📋 Данные акта определены. Укажите основание для акта, например:\n"
                "«План-график ремонта на 2026 год» или «Заявка капитана»",
            )

        except Exception as e:
            error_text = f"❌ Ошибка при создании акта:\n\n{str(e)}"
            bot.send_message(message.chat.id, error_text)
            logger.error(traceback.format_exc())

    def handle_avr_creation(message, user_text):
        """Создание Акта выполненных работ."""
        ship = detect_ship(user_text)
        works = parse_works_for_avr(user_text)

        if not works:
            bot.reply_to(
                message,
                "🤔 Для создания АВР опишите выполненные работы:\n"
                "Пример: 'АВР: Кабель-трасса: замена уголков 44 шт, болтов 194 шт.'",
            )
            return

        file_stream = create_avr_document(ship, works)
        bot.send_document(
            message.chat.id,
            file_stream,
            visible_file_name=f'АВР_{ship or "судна"}.docx',
        )
        bot.send_message(message.chat.id, "📄 Акт выполненных работ отправлен!")

    def handle_local_fallback(message, user_text):
        """Локальный режим работы (без Алисы)."""
        text_lower = user_text.lower()

        if any(word in text_lower for word in ['проверь зазор', 'проверка зазора', 'какой зазор', 'норма зазора']):
            clearances = extract_clearances_from_text(user_text)
            if clearances:
                responses = []
                for c in clearances:
                    if c['type'] != 'unknown':
                        pump_type = detect_pump_type(user_text)
                        if not pump_type:
                            if "шестерен" in text_lower or "ротан" in text_lower:
                                pump_type = "gear"
                            elif "поршн" in text_lower or "плунж" in text_lower or "паровой" in text_lower:
                                pump_type = "piston"
                            else:
                                pump_type = "centrifugal"

                        result = bot_context.pump_db.check_clearance(pump_type, c['type'], c['value'])
                        responses.append(f"🔹 {c['type']}: {c['value']} мм -> {result['message']}")

                        if bot_context.gost_checker:
                            if c['type'] == 'bearing':
                                gost_result = bot_context.gost_checker.check_parameter("3325-85", "clearance", c['value'])
                                if gost_result.get('status') != 'error':
                                    responses.append(f"   📌 ГОСТ 3325-85: {gost_result.get('message', '')}")
                            elif c['type'] == 'axial' or c['type'] == 'radial':
                                gost_result = bot_context.gost_checker.check_parameter("24643-81", "runout", c['value'])
                                if gost_result.get('status') != 'error':
                                    responses.append(f"   📌 ГОСТ 24643-81: {gost_result.get('message', '')}")

                if responses:
                    response = "📊 **Результаты проверки зазоров:**\n\n" + "\n".join(responses)
                    bot.reply_to(message, response, parse_mode='Markdown')
                    return

        if any(word in text_lower for word in ['чек-лист', 'перечень деталей', 'какие детали']):
            pump_type = detect_pump_type(user_text)
            if pump_type:
                items = bot_context.pump_db.get_checklist(pump_type)
                pump_name = bot_context.pump_db.get_pump_name(pump_type)
                response = f"📋 **Чек-лист для {pump_name} насоса:**\n\n"
                for i, item in enumerate(items, 1):
                    name = item.get("name") if isinstance(item, dict) else item
                    response += f"{i}. {name}\n"
                bot.reply_to(message, response, parse_mode='Markdown')
            else:
                bot.reply_to(message, "📌 Уточните тип насоса: центробежный, шестерёнчатый или поршневой")
            return

        if any(word in text_lower for word in ['какие дефекты', 'частые дефекты', 'список дефектов', 'дефекты бывают']):
            if any(word in text_lower for word in ["двигател", "дизель", "мотор"]):
                defects = bot_context.pump_db.get_common_defects("engine")
                response = f"📋 **Частые дефекты двигателей:**\n\n"
                for i, defect in enumerate(defects, 1):
                    response += f"{i}. {defect}\n"
                bot.reply_to(message, response, parse_mode='Markdown')
                return

            pump_type = detect_pump_type(user_text)
            if pump_type:
                pump_name = bot_context.pump_db.get_pump_name(pump_type)
                defects = bot_context.pump_db.get_common_defects(pump_type)
                response = f"📋 **Частые дефекты {pump_name} насоса:**\n\n"
                for i, defect in enumerate(defects, 1):
                    method = bot_context.pump_db.get_repair_method(pump_type, defect)
                    method_text = f" -> {method}" if method else ""
                    response += f"{i}. {defect}{method_text}\n"
                bot.reply_to(message, response, parse_mode='Markdown')
                return
            else:
                bot.reply_to(message, "📌 Уточните тип оборудования: насос или двигатель")
                return

        if any(word in text_lower for word in ['норматив', 'норма', 'ту', 'техническ']):
            response = "📐 **Нормативы зазоров по ТУ**\n\n"
            for pump_type in bot_context.pump_db.get_pump_types():
                pump_name = bot_context.pump_db.get_pump_name(pump_type)
                response += f"**{pump_name.capitalize()} насос:**\n"
                clearances = bot_context.pump_db.data.get(pump_type, {}).get("clearances", {})
                for ct, data in clearances.items():
                    min_val = data.get("min", 0)
                    max_val = data.get("max", 0)
                    unit = data.get("unit", "мм")
                    response += f"  • {ct}: {min_val}-{max_val} {unit}\n"
                response += "\n"
            bot.reply_to(message, response, parse_mode='Markdown')
            return

        bot.reply_to(
            message,
            "🤔 Я не совсем понял запрос.\n\n"
            "Что нужно?\n"
            "📄 Акт дефектации — 'сделай акт'\n"
            "📋 АВР — 'сделай АВР'\n"
            "🔧 Проверить зазор — 'проверь зазор'\n"
            "📋 Дефекты — 'какие дефекты у поршневого насоса'\n"
            "📐 Нормативы — 'нормативы зазоров'\n"
            "📋 Чек-лист — 'чек-лист центробежного насоса'\n"
            "📁 Проверка по ГОСТам — 'проверь по ГОСТ 520-2011 диаметр=50'\n"
            "📋 Список ГОСТов — '/gosts'\n"
            "🔎 Поиск по ГОСТам — '/search подшипник'",
        )


def notify_contracts_for_approval() -> None:
    """Уведомляет инженера-технолога и директоров о договорах на утверждение."""
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT d.doc_id, s.name AS ship_name FROM documents d "
        "JOIN ships s ON s.ship_id = d.ship_id "
        "WHERE d.doc_type = ? AND d.approved = 0",
        (db.DOC_CONTRACT,),
    )
    pending = cur.fetchall()
    cur.execute(
        "SELECT user_id FROM users WHERE role IN (?, ?) AND approved = 1",
        (db.ROLE_ENGINEER, db.ROLE_DIRECTOR),
    )
    approvers = [r["user_id"] for r in cur.fetchall()]
    conn.close()
    if not pending:
        return
    for uid in approvers:
        try:
            lines = ["📄 Договоры, ожидающие утверждения:"]
            for p in pending:
                lines.append(f"• {p['ship_name']} (id={p['doc_id']})")
            lines.append("\nОтветьте: /approve_contract <id> или /reject_contract <id>")
            bot_context.bot.send_message(uid, "\n".join(lines))
        except Exception:
            pass
