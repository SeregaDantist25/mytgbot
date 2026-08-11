# -*- coding: utf-8 -*-
"""
Патч для handle_message - добавляет проверку роли пользователя.

Этот код должен быть добавлен в bot.py после строки 1583 (после проверки авторизации).
"""

# Добавить после проверки авторизации (после строки 1583):
"""
    # --- ПРОВЕРКА РОЛИ (НОВОЕ) ---
    # Если пользователь customer и не в процессе регистрации → показать меню
    if DOCUMENT_MANAGER_AVAILABLE:
        user_role = document_manager.get_user_role(message.chat.id)
        if user_role == document_manager.ROLE_CUSTOMER:
            # Заказчик может только просматривать документы через меню
            from telebot import types
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
"""
