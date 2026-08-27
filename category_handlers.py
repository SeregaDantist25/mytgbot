# -*- coding: utf-8 -*-
"""
Обработчики для работы с категориями документов.
Включает навигацию по категориям и документам.
"""

import navigation


def _parse_documents_callback(callback_data):
    """Разобрать ``docs_<item_id>_<category>_<page>``.

    Категория может содержать подчёркивания (например, ``defect_act``),
    поэтому обычный split по всем подчёркиваниям использовать нельзя.
    """
    payload = callback_data.removeprefix("docs_")
    item_id_raw, category_and_page = payload.split("_", 1)
    category, page_raw = category_and_page.rsplit("_", 1)
    return int(item_id_raw), category, int(page_raw)


def register_category_handlers(bot):
    """Регистрирует обработчики категорий в боте."""
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("categories_"))
    def handle_categories_button(call):
        """Обработчик кнопки 'Категории' (показать категории для пункта)."""
        try:
            item_id = int(call.data.split("_")[1])
            
            # Получаем детали пункта
            item = navigation.get_item_details(item_id)
            if not item:
                bot.answer_callback_query(call.id, "❌ Пункт не найден", show_alert=True)
                return
            
            # Форматируем текст
            text = navigation.format_item_details(item)
            text += "\n\n📂 **Выберите категорию документов:**"
            
            # Строим клавиатуру с категориями
            keyboard = navigation.build_categories_keyboard(item_id)
            
            if not keyboard:
                text = "❌ Нет документов для этого пункта"
                keyboard = None
            
            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("docs_"))
    def handle_documents_button(call):
        """Обработчик кнопки 'Документы' (показать документы категории)."""
        try:
            item_id, category, page = _parse_documents_callback(call.data)
            
            # Получаем детали пункта
            item = navigation.get_item_details(item_id)
            if not item:
                bot.answer_callback_query(call.id, "❌ Пункт не найден", show_alert=True)
                return
            
            # Форматируем текст
            category_name = navigation.DOCUMENT_CATEGORIES.get(category, category)
            text = f"📋 **Пункт {item.item_number}**\n"
            text += f"📂 **Категория:** {category_name}\n\n"
            text += "**Документы:**\n"
            
            # Строим клавиатуру с документами
            keyboard = navigation.build_documents_keyboard(item_id, category, page)
            
            if not keyboard:
                text += "❌ Нет документов в этой категории"
                keyboard = None
            
            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("doc_"))
    def handle_document_details(call):
        """Обработчик кнопки документа (показать детали)."""
        try:
            doc_id = int(call.data.split("_")[1])
            
            # Форматируем текст
            text = navigation.format_document_details(doc_id)
            
            # Строим клавиатуру с действиями
            keyboard = _build_document_actions_keyboard(doc_id)
            
            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)


def _build_document_actions_keyboard(doc_id):
    """Построить клавиатуру с действиями над документом."""
    from models import SessionLocal, Document
    
    session = SessionLocal()
    try:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return None
        
        keyboard = None
        
        if doc.status == "draft":
            # Для черновиков: Заменить, Утвердить, Удалить
            keyboard = __import__('telebot').types.InlineKeyboardMarkup()
            keyboard.add(__import__('telebot').types.InlineKeyboardButton("🔄 Заменить", callback_data=f"replace_{doc_id}"))
            keyboard.add(__import__('telebot').types.InlineKeyboardButton("✅ Утвердить", callback_data=f"approve_{doc_id}"))
            keyboard.add(__import__('telebot').types.InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{doc_id}"))
        
        elif doc.status == "approved":
            # Для утверждённых: Архивировать
            keyboard = __import__('telebot').types.InlineKeyboardMarkup()
            keyboard.add(__import__('telebot').types.InlineKeyboardButton("📦 Архивировать", callback_data=f"archive_{doc_id}"))
        
        elif doc.status == "archived":
            # Для архивированных: только просмотр
            keyboard = __import__('telebot').types.InlineKeyboardMarkup()
        
        # Кнопка "Назад"
        if keyboard:
            keyboard.add(__import__('telebot').types.InlineKeyboardButton("◀ Назад", callback_data=f"docs_{doc.item_id}_{doc.category}_0"))
        
        return keyboard
    finally:
        session.close()
