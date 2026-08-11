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


# Регистрация callback-обработчиков документов (загрузка, замена, удаление)
# делегируется существующему корневому модулю document_handlers.py, который
# регистрирует StatesGroup-сценарии.
from document_handlers import register_document_handlers  # noqa: E402,F401
