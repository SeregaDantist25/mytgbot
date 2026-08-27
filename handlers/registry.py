# -*- coding: utf-8 -*-
"""Единая точка регистрации Telegram-обработчиков приложения."""

from __future__ import annotations

import logging

from handlers.message_handlers import register_message_handlers
from handlers.document_handlers import register_document_handlers
from handlers.error_handlers import setup_error_handlers
from category_handlers import register_category_handlers


logger = logging.getLogger(__name__)


def register_all_handlers(bot, document_manager_available=True):
    """Зарегистрировать обработчики в безопасном и проверенном порядке.

    Возвращает кортеж имён подключённых групп. Он используется диагностикой и
    тестами, поэтому состав приложения виден без анализа внутренних списков
    pyTelegramBotAPI.
    """
    registered = []

    register_message_handlers(bot)
    registered.append("messages")

    register_document_handlers(bot)
    registered.append("documents")

    register_category_handlers(bot)
    registered.append("document_categories")

    if document_manager_available:
        import bot_handlers_new

        bot_handlers_new.register_upload_handlers(bot)
        bot_handlers_new.register_navigation_handlers(bot)
        registered.extend(("repair_upload", "repair_navigation"))

    try:
        from ai.act_dialog import register_act_dialog_handlers

        register_act_dialog_handlers(bot)
        registered.append("defect_act_dialog")
    except Exception as exc:
        logger.warning("Диалог создания акта не зарегистрирован: %s", exc)

    setup_error_handlers(bot)
    return tuple(registered)
