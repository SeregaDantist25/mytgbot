# -*- coding: utf-8 -*-
"""
Общий контекст бота: разделяемые глобальные объекты.

Модуль создан, чтобы избежать циклических импортов между bot.py
(тонкий entry point) и пакетами handlers/ и services/. bot.py
заполняет эти атрибуты при инициализации, а обработчики читают их
через `import bot_context` (атрибуты модуля читаются "на лету").
"""

# Экземпляр TeleBot. Заполняется в bot.py.
bot = None

# ГОСТ-чекер (gost_checker.GOSTChecker) или None.
gost_checker = None

# Роутер Алисы (ai.ai_router.router) или None.
alisa_router = None

# Создатель актов через Алису (ai.alisa_act_creator.act_creator) или None.
alisa_act_creator = None

# База данных насосов (services.extra.PumpDatabase) или None.
pump_db = None

# Список ID администраторов.
ADMIN_IDS = []

# Секретный код инженера-технолога.
ENGINEER_CODE = None

# Доступны ли модули документооборота (document_manager, bot_handlers_new).
DOCUMENT_MANAGER_AVAILABLE = False

# История диалогов для контекста Алисы: {user_id: [messages]}.
user_histories = {}
