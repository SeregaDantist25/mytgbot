# -*- coding: utf-8 -*-
"""
Обработчики сообщений и callback'ов бота.

Содержит обработчики сообщений, документов, категорий, ремонтных ведомостей и
единую точку их регистрации. Навигационные callback находятся рядом со своим
сценарием, а не в общем модуле-перехватчике.
"""

__all__ = [
    'message_handlers',
    'document_handlers',
    'category_handlers',
    'repair_handlers',
    'error_handlers',
    'registry',
]
