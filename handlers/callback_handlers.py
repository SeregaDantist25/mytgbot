# -*- coding: utf-8 -*-
"""
Обработчики callback-запросов (кнопки меню и навигации).

Содержит обработчики section_ и item_ из монолитного bot.py.
"""

import telebot
from telebot import types

import bot_context
import navigation


def register_callback_handlers(bot: telebot.TeleBot) -> None:
    """Регистрирует callback-обработчики навигации в боте.

    Args:
        bot: Экземпляр TeleBot.
    """
    bot_context.bot = bot

    @bot.callback_query_handler(func=lambda call: call.data.startswith('section_'))
    def handle_section_callback(call: types.CallbackQuery) -> None:
        """Обработчик выбора раздела."""
        parts = call.data.split('_')
        if len(parts) < 3:
            return

        ship_id = int(parts[1])
        section_hash = parts[2]

        sections = navigation.get_sections_for_ship(ship_id)
        section = None
        for s in sections:
            if str(hash(s) & 0x7fffffff) == section_hash:
                section = s
                break

        if not section:
            bot.answer_callback_query(call.id, "❌ Раздел не найден")
            return

        keyboard = navigation.build_items_keyboard(ship_id, section, page=0)
        if not keyboard:
            bot.answer_callback_query(call.id, "⚠️ В этом разделе нет пунктов")
            return

        text = f"📄 **Раздел:** {section}\n\nВыберите пункт:"
        bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            reply_markup=keyboard, parse_mode='Markdown',
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('item_'))
    def handle_item_callback(call: types.CallbackQuery) -> None:
        """Обработчик выбора пункта."""
        parts = call.data.split('_')
        if len(parts) < 2:
            return

        item_id = int(parts[1])
        item = navigation.get_item_details(item_id)

        if not item:
            bot.answer_callback_query(call.id, "❌ Пункт не найден")
            return

        text = navigation.format_item_details(item)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("📄 Загрузить документ", callback_data=f"upload_doc_{item_id}"))
        keyboard.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_sections"))

        bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            reply_markup=keyboard, parse_mode='Markdown',
        )
        bot.answer_callback_query(call.id)
