# -*- coding: utf-8 -*-
"""
Обработчики сообщений и callback'ов бота.

Содержит:
- message_handlers — команды (/start, /login, /approve, /users, /set_role,
  /scan, /stats, /gosts, /search, /approve_contract, /reject_contract)
  и главный обработчик сообщений
- callback_handlers — callback'и навигации (section_, item_)
- document_handlers — загрузка, утверждение, удаление документов
- error_handlers — глобальная обработка ошибок
"""

from . import message_handlers
from . import callback_handlers
from . import document_handlers
from . import error_handlers

__all__ = [
    'message_handlers',
    'callback_handlers',
    'document_handlers',
    'error_handlers',
]
