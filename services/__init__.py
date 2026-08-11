# -*- coding: utf-8 -*-
"""
Сервисный слой бота.

Содержит бизнес-логику, отделённую от обработчиков:
- user_service — работа с пользователями
- document_service — работа с документами (создание, утверждение, удаление)
- file_service — обёртка над FileStorage
- excel_service — парсинг Excel (обёртка над scanner.py)
- document_builder — создание документов Word (акты дефектации, АВР)
- extra — прочая вспомогательная бизнес-логика (счётчики, chat_state,
  git, детекция, парсинг текста, база насосов)
"""

from . import user_service
from . import document_service
from . import file_service
from . import excel_service
from . import document_builder
from . import extra

__all__ = [
    'user_service',
    'document_service',
    'file_service',
    'excel_service',
    'document_builder',
    'extra',
]
