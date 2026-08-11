# -*- coding: utf-8 -*-
"""
Глобальная обработка ошибок.

Содержит настройку глобального обработчика исключений для бота.
"""

import logging

import telebot
import bot_context

logger = logging.getLogger(__name__)


def setup_error_handlers(bot: telebot.TeleBot) -> None:
    """Настраивает глобальную обработку ошибок в боте.

    Args:
        bot: Экземпляр TeleBot.
    """
    bot_context.bot = bot

    # Реальная обработка ошибок выполняется через try/except в каждом
    # обработчике. Здесь мы лишь гарантируем, что bot_context.bot
    # заполнен, и предоставляем единую точку для будущих глобальных
    # обработчиков (например, @bot.exception_handler).
    logger.info("Глобальная обработка ошибок настроена.")
