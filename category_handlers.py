# -*- coding: utf-8 -*-
"""
Обработчики для работы с категориями документов.
Включает навигацию по категориям и документам.
"""

import os

import bot_context
import navigation
from document_handlers import _can_manage_documents
from file_storage import storage
from services.document_service import approve_document, archive_document


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
            keyboard = _build_document_actions_keyboard(doc_id, call.from_user.id)
            
            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("approve_") and call.data.split("_")[-1].isdigit())
    def handle_document_approve(call):
        """Утвердить draft-документ из кнопочного интерфейса."""
        if not _can_manage_documents(call.from_user.id):
            bot.answer_callback_query(call.id, "🚫 Недостаточно прав", show_alert=True)
            return
        doc_id = int(call.data.rsplit("_", 1)[1])
        success, message = approve_document(doc_id, call.from_user.id)
        bot.answer_callback_query(call.id, message, show_alert=not success)
        if success:
            bot.edit_message_text(
                navigation.format_document_details(doc_id),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=_build_document_actions_keyboard(doc_id, call.from_user.id),
                parse_mode="Markdown",
            )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("archive_") and call.data.split("_")[-1].isdigit())
    def handle_document_archive(call):
        """Архивировать approved-документ; операция доступна администраторам."""
        doc_id = int(call.data.rsplit("_", 1)[1])
        success, message = archive_document(
            doc_id,
            call.from_user.id,
            admin_ids=bot_context.ADMIN_IDS,
        )
        bot.answer_callback_query(call.id, message, show_alert=not success)
        if success:
            bot.edit_message_text(
                navigation.format_document_details(doc_id),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=_build_document_actions_keyboard(doc_id, call.from_user.id),
                parse_mode="Markdown",
            )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("download_doc_") and call.data.split("_")[-1].isdigit())
    def handle_document_download(call):
        """Скачать документ любой категории по его ID."""
        doc_id = int(call.data.rsplit("_", 1)[1])
        file_bytes = storage.get_file(document_id=doc_id)
        if not file_bytes:
            bot.answer_callback_query(call.id, "❌ Файл не найден", show_alert=True)
            return

        from models import Document, SessionLocal

        session = SessionLocal()
        try:
            doc = session.query(Document).filter_by(id=doc_id).first()
            file_name = os.path.basename(doc.file_ref) if doc and doc.file_ref else f"document_{doc_id}.bin"
        finally:
            session.close()
        bot.answer_callback_query(call.id)
        bot.send_document(call.message.chat.id, file_bytes, visible_file_name=file_name)


def _build_document_actions_keyboard(doc_id, user_id=None):
    """Построить клавиатуру с действиями над документом."""
    from models import SessionLocal, Document
    
    session = SessionLocal()
    try:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return None
        
        keyboard = __import__('telebot').types.InlineKeyboardMarkup()
        can_manage = user_id is not None and _can_manage_documents(user_id)
        is_admin = user_id in bot_context.ADMIN_IDS if user_id is not None else False

        keyboard.add(__import__('telebot').types.InlineKeyboardButton(
            "📥 Скачать", callback_data=f"download_doc_{doc_id}"
        ))
        
        if doc.status == "draft" and can_manage:
            # Для черновиков: Заменить, Утвердить, Удалить
            keyboard.add(__import__('telebot').types.InlineKeyboardButton("🔄 Заменить", callback_data=f"replace_{doc_id}"))
            keyboard.add(__import__('telebot').types.InlineKeyboardButton("✅ Утвердить", callback_data=f"approve_{doc_id}"))
            keyboard.add(__import__('telebot').types.InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{doc_id}"))
        
        elif doc.status == "approved" and is_admin:
            # Для утверждённых: Архивировать
            keyboard.add(__import__('telebot').types.InlineKeyboardButton("📦 Архивировать", callback_data=f"archive_{doc_id}"))
        
        # Кнопка "Назад"
        keyboard.add(__import__('telebot').types.InlineKeyboardButton("◀ Назад", callback_data=f"docs_{doc.item_id}_{doc.category}_0"))
        
        return keyboard
    finally:
        session.close()
