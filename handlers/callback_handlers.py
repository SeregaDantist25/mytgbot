# -*- coding: utf-8 -*-
"""
Обработчики callback-запросов (кнопки меню и навигации).

Содержит обработчики section_ и item_ из монолитного bot.py.
"""

import telebot

import bot_context


def register_callback_handlers(bot: telebot.TeleBot) -> None:
    """Регистрирует callback-обработчики навигации в боте.

    Обработчики section_/item_ навигации по ремонтной ведомости
    зарегистрированы в bot_handlers_new.register_navigation_handlers().
    Здесь они не дублируются, чтобы не перехватывать callback раньше
    (порядок регистрации в pyTelegramBotAPI имеет значение).
    """
    bot_context.bot = bot

