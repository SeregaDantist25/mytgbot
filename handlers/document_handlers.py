# -*- coding: utf-8 -*-
"""
Обработчики документов: загрузка, утверждение, архивирование, удаление, замена.

Содержит функции-обработчики, которые вызываются из callback-обработчиков
и команд. Логика работы с БД делегируется services.document_service.
"""

from typing import Optional

import bot_context

from services.document_service import (
    create_document,
    get_document,
    get_documents,
    approve_document,
    archive_document,
    delete_document,
    replace_document,
    count_drafts_for_item,
    get_oldest_draft,
)


def handle_document_upload(item_id: int, category: str, file_data: bytes, user_id: int, file_type: Optional[str] = None):
    """Обрабатывает загрузку документа.

    Args:
        item_id: ID пункта ремонтной ведомости.
        category: Категория документа.
        file_data: Содержимое файла (bytes).
        user_id: Telegram ID пользователя.
        file_type: Тип файла (расширение).

    Returns:
        Созданный объект Document.
    """
    return create_document(item_id, category, file_data, user_id, file_type)


def handle_document_approve(document_id: int, user_id: int):
    """Обрабатывает утверждение документа.

    Args:
        document_id: ID документа.
        user_id: Telegram ID пользователя.

    Returns:
        Кортеж (success, message).
    """
    return approve_document(document_id, user_id)


def handle_document_archive(document_id: int, user_id: int):
    """Обрабатывает архивирование документа.

    Args:
        document_id: ID документа.
        user_id: Telegram ID пользователя.

    Returns:
        Кортеж (success, message).
    """
    return archive_document(document_id, user_id, bot_context.ADMIN_IDS)


def handle_document_delete(document_id: int, user_id: int):
    """Обрабатывает удаление документа.

    Args:
        document_id: ID документа.
        user_id: Telegram ID пользователя.

    Returns:
        Кортеж (success, message).
    """
    return delete_document(document_id, user_id, bot_context.ADMIN_IDS)


def handle_document_replace(document_id: int, file_data: bytes, user_id: int, file_type: Optional[str] = None):
    """Обрабатывает замену документа.

    Args:
        document_id: ID документа.
        file_data: Новое содержимое файла (bytes).
        user_id: Telegram ID пользователя.
        file_type: Тип файла (расширение).

    Returns:
        Кортеж (success, message).
    """
    return replace_document(document_id, file_data, user_id, file_type)


# -*- coding: utf-8 -*-
"""
Обработчики для работы с документами через StatesGroup.
Включает загрузку, замену и удаление документов.
"""

import logging
from telebot import types
from document_states import DocumentStates
from models import SessionLocal, Document, StatementItem
from file_storage import storage
from services.document_service import delete_document
from services.user_service import get_user
import bot_context
import os

logger = logging.getLogger(__name__)

DOCUMENT_MANAGER_ROLES = {
    "engineer",
    "engineer_technologist",
    "director",
    "builder",
}


def _can_manage_documents(user_id):
    """Проверить доступ к загрузке, замене и удалению документов."""
    if user_id in bot_context.ADMIN_IDS:
        return True
    user = get_user(user_id)
    return bool(user and user.approved and user.role in DOCUMENT_MANAGER_ROLES)


def register_document_handlers(bot):
    """Регистрирует обработчики документов в боте."""

    # ========================================================================
    # Загрузка документа
    # ========================================================================

    @bot.callback_query_handler(func=lambda call: call.data.startswith("upload_") and call.data.split("_")[1].isdigit())
    def handle_upload_button(call):
        """Обработчик кнопки 'Загрузить документ'."""
        try:
            if not _can_manage_documents(call.from_user.id):
                bot.answer_callback_query(call.id, "🚫 Недостаточно прав", show_alert=True)
                return
            item_id = int(call.data.split("_")[1])

            # Проверяем, что пункт существует
            session = SessionLocal()
            item = session.query(StatementItem).filter_by(id=item_id).first()
            session.close()

            if not item:
                bot.answer_callback_query(call.id, "❌ Пункт не найден", show_alert=True)
                return

            # Переходим в состояние выбора категории
            bot.set_state(call.from_user.id, DocumentStates.waiting_for_category)

            # Сохраняем item_id в данные пользователя
            with bot.retrieve_data(call.from_user.id) as data:
                data['item_id'] = item_id

            # Показываем клавиатуру с категориями
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("📋 Акты дефектации", callback_data="cat_defect_act"))
            keyboard.add(types.InlineKeyboardButton("⚙️ АВР", callback_data="cat_avr"))
            keyboard.add(types.InlineKeyboardButton("📄 Прочее", callback_data="cat_other"))

            bot.edit_message_text(
                "📤 Выберите категорию документа:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)


    @bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"), state=DocumentStates.waiting_for_category)
    def handle_category_selection(call):
        """Обработчик выбора категории."""
        try:
            category = call.data.split("_", 1)[1]

            with bot.retrieve_data(call.from_user.id) as data:
                data['category'] = category

            # Переходим в состояние ожидания файла
            bot.set_state(call.from_user.id, DocumentStates.waiting_for_file)

            bot.edit_message_text(
                "📤 Отправьте документ (DOCX, XLSX, PDF):",
                call.message.chat.id,
                call.message.message_id
            )

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)


    @bot.message_handler(state=DocumentStates.waiting_for_file, content_types=['document'])
    def handle_file_upload(message):
        """Обработчик загрузки файла."""
        try:
            if not _can_manage_documents(message.from_user.id):
                bot.reply_to(message, "🚫 Недостаточно прав для загрузки документов")
                bot.delete_state(message.from_user.id)
                return
            with bot.retrieve_data(message.from_user.id) as data:
                item_id = data.get('item_id')
                category = data.get('category')

            if not item_id or not category:
                bot.reply_to(message, "❌ Ошибка: потеряны данные сессии")
                return

            # Получаем информацию о файле
            file_info = bot.get_file(message.document.file_id)
            file_name = message.document.file_name
            file_type = os.path.splitext(file_name)[1].lower()

            # Проверяем расширение файла
            allowed_types = ['.docx', '.xlsx', '.pdf']
            if file_type not in allowed_types:
                bot.reply_to(message, f"❌ Недопустимый тип файла. Допустимые: {', '.join(allowed_types)}")
                return

            # Скачиваем файл
            downloaded_file = bot.download_file(file_info.file_path)

            # Сохраняем в хранилище
            result = storage.save_document(
                file_name=file_name,
                file_content=downloaded_file,
                item_id=item_id,
                category=category,
                user_id=message.from_user.id
            )

            # Выходим из состояния
            bot.delete_state(message.from_user.id)

            if result["success"]:
                bot.reply_to(message, f"✅ Документ загружен успешно!\n📁 {file_name}")
            else:
                bot.reply_to(message, f"❌ Ошибка: {result['message']}")


        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка при загрузке: {str(e)}")


    # ========================================================================
    # Замена документа
    # ========================================================================

    @bot.callback_query_handler(func=lambda call: call.data.startswith("replace_"))
    def handle_replace_button(call):
        """Обработчик кнопки 'Заменить'."""
        try:
            if not _can_manage_documents(call.from_user.id):
                bot.answer_callback_query(call.id, "🚫 Недостаточно прав", show_alert=True)
                return
            doc_id = int(call.data.split("_")[1])

            # Проверяем, что документ существует и это draft
            session = SessionLocal()
            doc = session.query(Document).filter_by(id=doc_id).first()
            session.close()

            if not doc:
                bot.answer_callback_query(call.id, "❌ Документ не найден", show_alert=True)
                return

            if doc.status != "draft":
                bot.answer_callback_query(call.id, "❌ Можно заменять только черновики", show_alert=True)
                return

            # Переходим в состояние ожидания замены
            bot.set_state(call.from_user.id, DocumentStates.waiting_for_replacement)

            with bot.retrieve_data(call.from_user.id) as data:
                data['doc_id'] = doc_id
                data['item_id'] = doc.item_id
                data['category'] = doc.category

            bot.edit_message_text(
                "📤 Отправьте новый документ для замены:",
                call.message.chat.id,
                call.message.message_id
            )

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)


    @bot.message_handler(state=DocumentStates.waiting_for_replacement, content_types=['document'])
    def handle_file_replacement(message):
        """Обработчик замены файла."""
        try:
            if not _can_manage_documents(message.from_user.id):
                bot.reply_to(message, "🚫 Недостаточно прав для замены документов")
                bot.delete_state(message.from_user.id)
                return
            with bot.retrieve_data(message.from_user.id) as data:
                doc_id = data.get('doc_id')
                item_id = data.get('item_id')
                category = data.get('category')

            if not doc_id or not item_id or not category:
                bot.reply_to(message, "❌ Ошибка: потеряны данные сессии")
                return

            # Получаем информацию о файле
            file_info = bot.get_file(message.document.file_id)
            file_name = message.document.file_name
            file_type = os.path.splitext(file_name)[1].lower()

            # Проверяем расширение файла
            allowed_types = ['.docx', '.xlsx', '.pdf']
            if file_type not in allowed_types:
                bot.reply_to(message, f"❌ Недопустимый тип файла. Допустимые: {', '.join(allowed_types)}")
                return

            # Скачиваем файл
            downloaded_file = bot.download_file(file_info.file_path)

            # Заменяем документ
            result = storage.replace_document(
                document_id=doc_id,
                new_file_content=downloaded_file,
                new_file_name=file_name
            )

            # Выходим из состояния
            bot.delete_state(message.from_user.id)

            if result["success"]:
                bot.reply_to(message, f"✅ Документ заменён успешно!\n📁 {file_name}")
            else:
                bot.reply_to(message, f"❌ Ошибка: {result['message']}")


        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка при замене: {str(e)}")


    # ========================================================================
    # Удаление документа
    # ========================================================================

    @bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
    def handle_delete_button(call):
        """Обработчик кнопки 'Удалить'."""
        try:
            if not _can_manage_documents(call.from_user.id):
                bot.answer_callback_query(call.id, "🚫 Недостаточно прав", show_alert=True)
                return
            doc_id = int(call.data.split("_")[1])

            # Проверяем, что документ существует
            session = SessionLocal()
            doc = session.query(Document).filter_by(id=doc_id).first()
            session.close()

            if not doc:
                bot.answer_callback_query(call.id, "❌ Документ не найден", show_alert=True)
                return

            # Переходим в состояние подтверждения
            bot.set_state(call.from_user.id, DocumentStates.confirming_delete)

            with bot.retrieve_data(call.from_user.id) as data:
                data['doc_id'] = doc_id

            # Показываем подтверждение
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{doc_id}"),
                types.InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_delete_{doc_id}")
            )

            bot.edit_message_text(
                f"⚠️ Вы уверены, что хотите удалить документ v{doc.version}?",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)


    @bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete_"), state=DocumentStates.confirming_delete)
    def handle_delete_confirmation(call):
        """Обработчик подтверждения удаления."""
        try:
            if not _can_manage_documents(call.from_user.id):
                bot.delete_state(call.from_user.id)
                bot.answer_callback_query(call.id, "🚫 Недостаточно прав", show_alert=True)
                return
            doc_id = int(call.data.split("_")[2])

            success, message = delete_document(
                doc_id,
                call.from_user.id,
                admin_ids=bot_context.ADMIN_IDS,
            )

            # Выходим из состояния
            bot.delete_state(call.from_user.id)

            bot.edit_message_text(
                message,
                call.message.chat.id,
                call.message.message_id
            )
            if success:
                bot.answer_callback_query(call.id)
            else:
                bot.answer_callback_query(call.id, message, show_alert=True)

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)


    @bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_delete_"), state=DocumentStates.confirming_delete)
    def handle_delete_cancellation(call):
        """Обработчик отмены удаления."""
        try:
            doc_id = int(call.data.split("_")[2])

            # Выходим из состояния
            bot.delete_state(call.from_user.id)

            bot.edit_message_text(
                "❌ Удаление отменено",
                call.message.chat.id,
                call.message.message_id
            )

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
