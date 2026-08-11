# -*- coding: utf-8 -*-
"""
Константы и перечисления для бота.

Содержит Enum'ы ролей, статусов и категорий документов, а также
общие константы (лимиты, допустимые расширения файлов).
"""

from enum import Enum


class UserRole(str, Enum):
    """Роли пользователей бота."""
    ENGINEER = "engineer_technologist"
    DIRECTOR = "director"
    BUILDER = "builder"
    CUSTOMER = "customer"


class DocumentStatus(str, Enum):
    """Статусы документов."""
    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"


class DocumentCategory(str, Enum):
    """Категории документов."""
    DEFECT_ACT_DRAFT = "defect_act_draft"
    DEFECT_ACT_APPROVED = "defect_act_approved"
    AVR = "avr"
    OTHER = "other"


# --- Константы ---

# Максимальное количество черновиков на один пункт ремонтной ведомости
MAX_DRAFTS_PER_ITEM = 4

# Максимальный размер загружаемого файла (50 MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# Допустимые расширения загружаемых файлов
ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.xlsx', '.jpg', '.png']

# Кнопки навигации (ReplyKeyboardMarkup)
NAVIGATION_BUTTONS = ["📋 Ремонтная ведомость", "📄 Документы", "🚢 Суда"]
