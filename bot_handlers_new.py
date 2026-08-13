# -*- coding: utf-8 -*-
"""
Новые обработчики для bot.py:
1. Загрузка ремонтных ведомостей (Excel)
2. Навигация по пунктам
3. Версионирование документов
4. Проверка ролей в handle_message
"""

import logging
from telebot import types
from telebot.handler_backends import State, StatesGroup
import os
import tempfile
from datetime import datetime

import document_manager as dm
from models import SessionLocal, Ship, RepairStatement, StatementItem
from file_storage import storage

logger = logging.getLogger(__name__)

# ============================================================
#  STATES ДЛЯ МНОГОШАГОВЫХ СЦЕНАРИЕВ
# ============================================================

class DocumentStates(StatesGroup):
    """Состояния для работы с документами."""
    waiting_delete_confirm = State()  # подтверждение удаления старого draft
    waiting_approve_confirm = State()  # подтверждение утверждения
    waiting_ship_select = State()      # выбор судна для загрузки ведомости


# ============================================================
#  ПЛАН 1: ЗАГРУЗКА РЕМОНТНОЙ ВЕДОМОСТИ
# ============================================================

def register_upload_handlers(bot):
    """Регистрирует обработчики загрузки ремонтной ведомости."""
    
    @bot.message_handler(commands=['upload_repair_list'])
    def cmd_upload_repair_list(message):
        """Команда для загрузки ремонтной ведомости (Excel)."""
        user_role = dm.get_user_role(message.chat.id)
        
        if not dm.can_upload_repair_list(user_role):
            bot.reply_to(message, "🚫 У вас нет прав на загрузку ремонтных ведомостей.")
            return
        
        # Получить список судов
        session = SessionLocal()
        try:
            ships = session.query(Ship).all()
            if not ships:
                bot.reply_to(message, "❌ Нет судов в системе. Добавьте судно сначала.")
                return
            
            # Показать меню выбора судна
            markup = types.InlineKeyboardMarkup()
            for ship in ships:
                btn = types.InlineKeyboardButton(
                    text=ship.name,
                    callback_data=f"upload_ship_{ship.id}"
                )
                markup.add(btn)
            
            bot.send_message(
                message.chat.id,
                "📋 Выберите судно для загрузки ремонтной ведомости:",
                reply_markup=markup
            )
        finally:
            session.close()
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("upload_ship_"))
    def handle_upload_ship_select(call):
        """Обработчик выбора судна для загрузки."""
        try:
            ship_id = int(call.data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка в данных", show_alert=True)
            return
        
        # Сохраняем ship_id в состояние пользователя
        bot.set_state(call.from_user.id, DocumentStates.waiting_ship_select, call.message.chat.id)
        bot.add_data(call.from_user.id, call.message.chat.id, ship_id=ship_id)
        
        bot.edit_message_text(
            "📁 Отправьте Excel-файл ремонтной ведомости (формат .xlsx или .xls):",
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id)
    
    @bot.message_handler(state=DocumentStates.waiting_ship_select, content_types=['document'])
    def handle_repair_list_upload(message):
        """Обработчик загрузки Excel-файла ремонтной ведомости."""
        user_role = dm.get_user_role(message.chat.id)
        
        if not dm.can_upload_repair_list(user_role):
            bot.reply_to(message, "🚫 У вас нет прав на загрузку ремонтных ведомостей.")
            return
        
        # Получить ship_id из состояния
        data = bot.get_data(message.from_user.id, message.chat.id)
        ship_id = data.get("ship_id")
        
        if not ship_id:
            bot.reply_to(message, "❌ Ошибка: судно не выбрано. Попробуйте снова.")
            return
        
        # Скачать файл
        file_info = bot.get_file(message.document.file_id)
        file_path = file_info.file_path
        
        # Проверить расширение
        if not file_path.lower().endswith(('.xlsx', '.xls')):
            bot.reply_to(message, "❌ Файл должен быть в формате Excel (.xlsx или .xls)")
            return
        
        try:
            # Скачать файл во временную папку
            downloaded_file = bot.download_file(file_path)
            temp_file = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            temp_file.write(downloaded_file)
            temp_file.close()
            
            # Парсить файл
            import scanner
            items = scanner.parse_repair_list(temp_file.name)
            
            if not items:
                bot.reply_to(message, "⚠️ В файле не найдено пунктов ремонтной ведомости.")
                os.unlink(temp_file.name)
                return
            
            # Сохранить в БД
            result = dm.save_repair_items_to_db(ship_id, items)
            
            # Очистить состояние
            bot.delete_state(message.from_user.id, message.chat.id)
            
            # Отправить результат
            if result["success"]:
                msg = f"✅ Ремонтная ведомость загружена!\n"
                msg += f"📌 Добавлено пунктов: {result['created']}\n"
                if result['skipped'] > 0:
                    msg += f"⏭️ Пропущено дубликатов: {result['skipped']}\n"
                if result['errors']:
                    msg += f"⚠️ Ошибок: {len(result['errors'])}\n"
                    for err in result['errors'][:3]:  # показать первые 3 ошибки
                        msg += f"  • {err}\n"
                bot.reply_to(message, msg)
            else:
                msg = "❌ Ошибка при загрузке ведомости:\n"
                for err in result['errors']:
                    msg += f"  • {err}\n"
                bot.reply_to(message, msg)
            
            # Удалить временный файл
            os.unlink(temp_file.name)
        
        except Exception as e:
            logger.error(f"Error processing repair list file: {e}", exc_info=True)
            bot.reply_to(message, f"❌ Ошибка при обработке файла: {str(e)}")
            try:
                os.unlink(temp_file.name)
            except Exception as cleanup_error:
                logger.warning(f"Failed to delete temp file: {cleanup_error}")
                pass


# ============================================================
#  ПЛАН 2: НАВИГАЦИЯ ПО ПУНКТАМ
# ============================================================

def _show_ships_menu(bot, chat_id):
    """Показать список судов для навигации по ремонтной ведомости.
    
    Если судов нет в БД, попытается синхронизировать из ships.json.
    Если всё равно нет — предложит добавить судно.
    """
    session = SessionLocal()
    try:
        ships = session.query(Ship).all()
        if not ships:
            # Попытаться синхронизировать суда из ships.json
            added = dm.sync_ships_from_json()
            if added:
                # Перезагрузить список судов
                ships = session.query(Ship).all()
            else:
                # Нет судов ни в БД, ни в ships.json
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(
                    text="➕ Добавить судно",
                    callback_data="add_ship"
                ))
                bot.send_message(
                    chat_id,
                    "❌ Нет судов в системе.\n\n"
                    "Нажмите кнопку ниже, чтобы добавить первое судно.",
                    reply_markup=markup
                )
                return

        # Показать меню выбора судна
        markup = types.InlineKeyboardMarkup()
        for ship in ships:
            btn = types.InlineKeyboardButton(
                text=ship.name,
                callback_data=f"ship_{ship.id}"
            )
            markup.add(btn)

        bot.send_message(
            chat_id,
            "🚢 Выберите судно:",
            reply_markup=markup
        )
    finally:
        session.close()


def _show_sections(bot, call, ship_id, page=0):
    """Показать список разделов ремонтной ведомости судна (с пагинацией)."""
    sections = dm.get_sections_for_ship(ship_id)

    if not sections:
        bot.edit_message_text(
            "❌ Нет пунктов в ремонтной ведомости этого судна.",
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id)
        return

    page_data = dm.paginate_list(sections, page=page, page_size=10)

    markup = types.InlineKeyboardMarkup()
    for section in page_data["items"]:
        section_hash = dm.section_hash(section)
        btn = types.InlineKeyboardButton(
            text=section or "Без раздела",
            callback_data=f"section_{ship_id}_{section_hash}"
        )
        markup.add(btn)

    # Кнопки пагинации разделов
    nav_buttons = []
    if page_data["has_prev"]:
        nav_buttons.append(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"sections_{ship_id}_{page_data['page'] - 1}"))
    if page_data["has_next"]:
        nav_buttons.append(types.InlineKeyboardButton("Далее ➡️", callback_data=f"sections_{ship_id}_{page_data['page'] + 1}"))
    if nav_buttons:
        markup.add(*nav_buttons)

    bot.edit_message_text(
        f"📋 Разделы ремонтной ведомости (судно: {ship_id}):\n"
        f"Страница {page_data['page'] + 1}/{page_data['total_pages']}",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)


def register_navigation_handlers(bot):
    """Регистрирует обработчики навигации по пунктам ремонтной ведомости."""

    @bot.message_handler(commands=['repair_list'])
    def cmd_repair_list(message):
        """Показать ремонтную ведомость судна."""
        user_role = dm.get_user_role(message.chat.id)

        if not user_role:
            bot.reply_to(message, "🔒 Сначала авторизуйтесь.")
            return

        _show_ships_menu(bot, message.chat.id)

    @bot.message_handler(commands=['scan_acts'])
    def cmd_scan_acts(message):
        """Импортировать готовые акты дефектации из папки acts/."""
        try:
            import act_importer
            messages = act_importer.import_acts()
            bot.reply_to(message, "\n".join(messages))
        except Exception as e:
            logger.error(f"Ошибка импорта актов: {e}", exc_info=True)
            bot.reply_to(message, f"❌ Ошибка при импорте актов: {e}")

    @bot.message_handler(func=lambda message: message.text in ("📋 Ремонтная ведомость", "🚢 Суда"))
    def handle_nav_repair_list(message):
        """Кнопки «Ремонтная ведомость» и «Суда» → список судов."""
        _show_ships_menu(bot, message.chat.id)

    @bot.message_handler(func=lambda message: message.text == "📄 Документы")
    def handle_nav_documents(message):
        """Кнопка «Документы» → подсказка."""
        bot.send_message(
            message.chat.id,
            "📄 Чтобы посмотреть документы, выберите судно и пункт в ремонтной ведомости "
            "(кнопка «📋 Ремонтная ведомость»)."
        )
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("ship_"))
    def handle_ship_select(call):
        """Обработчик выбора судна."""
        try:
            ship_id = int(call.data.split("_")[1])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка в данных", show_alert=True)
            return
        
        # Показать разделы
        sections = dm.get_sections_for_ship(ship_id)
        
        if not sections:
            bot.edit_message_text(
                "❌ Нет пунктов в ремонтной ведомости этого судна.",
                call.message.chat.id,
                call.message.message_id
            )
            bot.answer_callback_query(call.id)
            return

        _show_sections(bot, call, ship_id, page=0)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("sections_"))
    def handle_sections_page(call):
        """Пагинация списка разделов."""
        try:
            parts = call.data.split("_")
            ship_id = int(parts[1])
            page = int(parts[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка в данных", show_alert=True)
            return
        _show_sections(bot, call, ship_id, page=page)

    def _show_items(bot, call, ship_id, section, page=0):
        """Показать пункты раздела с пагинацией."""
        items = dm.get_items_for_section(ship_id, section)

        if not items:
            bot.edit_message_text(
                "❌ Нет пунктов в этом разделе.",
                call.message.chat.id,
                call.message.message_id
            )
            bot.answer_callback_query(call.id)
            return

        page_data = dm.paginate_list(items, page=page, page_size=10)

        markup = types.InlineKeyboardMarkup()
        for item in page_data["items"]:
            btn_text = f"{item['item_number']}. {item['description'][:30]}"
            btn = types.InlineKeyboardButton(
                text=btn_text,
                callback_data=f"item_{item['id']}"
            )
            markup.add(btn)

        # Кнопки пагинации
        section_hash = dm.section_hash(section)
        nav_buttons = []
        if page_data["has_prev"]:
            nav_buttons.append(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"items_{ship_id}_{section_hash}_{page_data['page'] - 1}"))
        if page_data["has_next"]:
            nav_buttons.append(types.InlineKeyboardButton("Далее ➡️", callback_data=f"items_{ship_id}_{section_hash}_{page_data['page'] + 1}"))
        if nav_buttons:
            markup.add(*nav_buttons)

        # Кнопка "Назад к разделам"
        markup.add(types.InlineKeyboardButton("🔙 К разделам", callback_data=f"ship_{ship_id}"))

        bot.edit_message_text(
            f"📌 Пункты раздела: {section}\n"
            f"Страница {page_data['page'] + 1}/{page_data['total_pages']}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("items_"))
    def handle_items_page(call):
        """Пагинация списка пунктов раздела."""
        try:
            parts = call.data.split("_")
            ship_id = int(parts[1])
            section_hash = parts[2]
            page = int(parts[3])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка в данных", show_alert=True)
            return

        # Найти раздел по хешу
        sections = dm.get_sections_for_ship(ship_id)
        section = None
        for s in sections:
            if dm.section_hash(s) == section_hash:
                section = s
                break
        if section is None:
            bot.answer_callback_query(call.id, "❌ Раздел не найден", show_alert=True)
            return

        _show_items(bot, call, ship_id, section, page=page)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("section_"))
    def handle_section_select(call):
        """Обработчик выбора раздела (по хешу названия)."""
        try:
            parts = call.data.split("_")
            ship_id = int(parts[1])
            section_hash = parts[2]
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка в данных", show_alert=True)
            return

        # Найти раздел по хешу
        sections = dm.get_sections_for_ship(ship_id)
        section = None
        for s in sections:
            if dm.section_hash(s) == section_hash:
                section = s
                break
        if section is None:
            bot.answer_callback_query(call.id, "❌ Раздел не найден", show_alert=True)
            return

        _show_items(bot, call, ship_id, section, page=0)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("item_"))
    def handle_item_select(call):
        """Обработчик выбора пункта."""
        try:
            item_id = int(call.data.split("_")[1])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка в данных", show_alert=True)
            return
        
        # Получить детали пункта
        item = dm.get_item_details(item_id)
        
        if not item:
            bot.answer_callback_query(call.id, "❌ Пункт не найден", show_alert=True)
            return
        
        # Построить сообщение
        msg = f"📝 Пункт {item['item_number']}\n"
        msg += f"Описание: {item['description']}\n"
        if item['quantity']:
            msg += f"Кол-во: {item['quantity']}\n"
        msg += f"Раздел: {item['section']}\n\n"
        
        if item['documents']:
            msg += "📄 Документы:\n"
            for doc in item['documents']:
                src = "📁 из папки" if doc.get('source') == "folder" else "📤 через бота"
                msg += f"  • {doc['category']} ({src}, статус: {doc['status']}, v{doc['version']})\n"
        else:
            msg += "📄 Документов нет\n"
        
        # Кнопки действий
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📤 Загрузить документ", callback_data=f"upload_{item_id}"))
        markup.add(types.InlineKeyboardButton("🧠 Создать акт дефектации (AI)", callback_data=f"aiact_start_{item_id}"))
        # Назад к списку пунктов раздела (с контекстом судна и раздела)
        ship_id = dm.get_ship_id_for_item(item_id)
        section_hash = dm.section_hash(item['section']) if item['section'] else ""
        back_data = f"back_to_items_{ship_id}_{section_hash}"
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data=back_data))
        
        bot.edit_message_text(
            msg,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_items_"))
    def handle_back_to_items(call):
        """Возврат к списку пунктов раздела из деталей пункта."""
        try:
            parts = call.data.split("_")
            ship_id = int(parts[3])
            section_hash = parts[4]
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка в данных", show_alert=True)
            return

        sections = dm.get_sections_for_ship(ship_id)
        section = None
        for s in sections:
            if dm.section_hash(s) == section_hash:
                section = s
                break
        if section is None:
            bot.answer_callback_query(call.id, "❌ Раздел не найден", show_alert=True)
            return

        _show_items(bot, call, ship_id, section, page=0)

    @bot.callback_query_handler(func=lambda call: call.data == "add_ship")
    def handle_add_ship(call):
        """Обработчик кнопки 'Добавить судно'."""
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            "📝 Введите название судна:"
        )
        
        def process_add_ship_inner(message):
            """Обработчик ввода названия судна."""
            ship_name = message.text.strip()
            if not ship_name:
                bot.send_message(message.chat.id, "❌ Название не может быть пустым.")
                return
            
            try:
                ship = dm.ensure_ship_exists(ship_name)
                bot.send_message(
                    message.chat.id,
                    f"✅ Судно '{ship.name}' добавлено в систему!"
                )
                # Показать меню судов
                _show_ships_menu(bot, message.chat.id)
            except Exception as e:
                bot.send_message(
                    message.chat.id,
                    f"❌ Ошибка при добавлении судна: {str(e)}"
                )
        
        bot.register_next_step_handler(call.message, process_add_ship_inner)


# ============================================================
#  ПЛАН 4: ПРОВЕРКА РОЛЕЙ В HANDLE_MESSAGE
# ============================================================

def add_role_check_to_handle_message(original_handle_message):
    """
    Обёртка для handle_message, которая проверяет роль пользователя.
    
    Если role == "customer" → показать меню, не обрабатывать NLP.
    Если role == "engineer" или "builder" → работает старый NLP-режим.
    """
    def handle_message_with_role_check(message):
        user_role = dm.get_user_role(message.chat.id)
        
        # Если пользователь не в системе, создать его как customer
        if not user_role:
            dm.ensure_user_exists(message.chat.id, role=dm.ROLE_CUSTOMER)
            user_role = dm.ROLE_CUSTOMER
        
        # Если customer → показать меню, не обрабатывать NLP
        if user_role == dm.ROLE_CUSTOMER:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("📋 Ремонтная ведомость")
            markup.add("📄 Документы")
            markup.add("🚢 Суда")
            bot.send_message(
                message.chat.id,
                "👋 Используйте кнопки для навигации.",
                reply_markup=markup
            )
            return
        
        # Для остальных ролей → работает старый NLP-режим
        return original_handle_message(message)
    
    return handle_message_with_role_check
