"""
Pydantic schemas для валидации входных данных.
"""

from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Optional
from datetime import datetime


class UserRole(str, Enum):
    """Роли пользователей"""
    ENGINEER = "engineer_technologist"
    DIRECTOR = "director"
    BUILDER = "builder"
    CUSTOMER = "customer"


class UserCreate(BaseModel):
    """Схема для создания пользователя"""
    telegram_id: int = Field(..., gt=0, description="Telegram ID должен быть положительным")
    name: str = Field(..., min_length=1, max_length=255, description="Имя 1-255 символов")
    role: UserRole = Field(default=UserRole.CUSTOMER, description="Роль пользователя")
    
    @field_validator('telegram_id')
    @classmethod
    def validate_telegram_id(cls, v: int) -> int:
        """Проверяет корректность Telegram ID"""
        if v > 9999999999:  # Telegram ID не может быть больше
            raise ValueError('Invalid Telegram ID: too large')
        return v
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Проверяет, что имя не содержит опасных символов"""
        if any(char in v for char in ['<', '>', '"', "'", ';', '--']):
            raise ValueError('Name contains invalid characters')
        return v.strip()


class UserUpdate(BaseModel):
    """Схема для обновления пользователя"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    role: Optional[UserRole] = None
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Проверяет, что имя не содержит опасных символов"""
        if v is None:
            return v
        if any(char in v for char in ['<', '>', '"', "'", ';', '--']):
            raise ValueError('Name contains invalid characters')
        return v.strip()


class DocumentCreate(BaseModel):
    """Схема для создания документа"""
    item_id: int = Field(..., gt=0, description="ID ремонтного объекта")
    category: str = Field(..., min_length=1, max_length=100, description="Категория документа")
    file_name: str = Field(..., min_length=1, max_length=255, description="Имя файла")
    file_size: int = Field(..., gt=0, le=52428800, description="Размер файла (макс 50 MB)")
    
    @field_validator('category')
    @classmethod
    def validate_category(cls, v: str) -> str:
        """Проверяет категорию"""
        allowed_categories = [
            "defect_act", "work_act", "repair_sheet", "photo", "other"
        ]
        if v not in allowed_categories:
            raise ValueError(f'Invalid category. Allowed: {", ".join(allowed_categories)}')
        return v
    
    @field_validator('file_name')
    @classmethod
    def validate_file_name(cls, v: str) -> str:
        """Проверяет имя файла"""
        if any(char in v for char in ['<', '>', ':', '"', '|', '?', '*', '\\']):
            raise ValueError('File name contains invalid characters')
        return v.strip()


class DocumentUpdate(BaseModel):
    """Схема для обновления документа"""
    status: Optional[str] = Field(None, description="Статус документа")
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        """Проверяет статус"""
        if v is None:
            return v
        allowed_statuses = ["draft", "approved", "archived"]
        if v not in allowed_statuses:
            raise ValueError(f'Invalid status. Allowed: {", ".join(allowed_statuses)}')
        return v


class RepairItemCreate(BaseModel):
    """Схема для создания ремонтного объекта"""
    ship_name: str = Field(..., min_length=1, max_length=255, description="Название судна")
    item_number: str = Field(..., min_length=1, max_length=50, description="Номер объекта")
    description: Optional[str] = Field(None, max_length=1000, description="Описание")
    
    @field_validator('ship_name', 'item_number')
    @classmethod
    def validate_text_fields(cls, v: str) -> str:
        """Проверяет текстовые поля"""
        if any(char in v for char in ['<', '>', '"', "'", ';', '--']):
            raise ValueError('Field contains invalid characters')
        return v.strip()


class CallbackData(BaseModel):
    """Схема для валидации callback данных"""
    action: str = Field(..., min_length=1, max_length=50, description="Действие")
    item_id: Optional[int] = Field(None, gt=0, description="ID объекта")
    doc_id: Optional[int] = Field(None, gt=0, description="ID документа")
    
    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        """Проверяет действие"""
        allowed_actions = [
            "view_item", "create_doc", "approve_doc", "delete_doc",
            "archive_doc", "view_docs", "back", "main_menu"
        ]
        if v not in allowed_actions:
            raise ValueError(f'Invalid action. Allowed: {", ".join(allowed_actions)}')
        return v


class MessageData(BaseModel):
    """Схема для валидации данных сообщения"""
    user_id: int = Field(..., gt=0, description="ID пользователя")
    text: str = Field(..., min_length=1, max_length=4096, description="Текст сообщения")
    
    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v: int) -> int:
        """Проверяет ID пользователя"""
        if v > 9999999999:
            raise ValueError('Invalid user ID')
        return v


class PaginationParams(BaseModel):
    """Схема для параметров пагинации"""
    page: int = Field(default=1, ge=1, description="Номер страницы")
    page_size: int = Field(default=10, ge=1, le=100, description="Размер страницы")


class SearchParams(BaseModel):
    """Схема для параметров поиска"""
    query: str = Field(..., min_length=1, max_length=255, description="Поисковый запрос")
    category: Optional[str] = None
    status: Optional[str] = None
    
    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Проверяет поисковый запрос"""
        if any(char in v for char in ['<', '>', '"', "'", ';', '--']):
            raise ValueError('Query contains invalid characters')
        return v.strip()
