# -*- coding: utf-8 -*-
"""
Состояния (StatesGroup) для работы с документами.
Используются для управления сценариями загрузки, замены и удаления документов.
"""

from telebot.handler_backends import State, StatesGroup


class DocumentStates(StatesGroup):
    """Состояния для работы с документами."""
    
    waiting_for_file = State()  # Ожидание загрузки файла
    waiting_for_replacement = State()  # Ожидание замены файла
    confirming_delete = State()  # Подтверждение удаления
    waiting_for_category = State()  # Выбор категории при загрузке
