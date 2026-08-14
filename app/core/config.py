# -*- coding: utf-8 -*-
"""
Конфигурация приложения.

Использует pydantic-settings для валидации и загрузки из .env
"""

import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Настройки приложения."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # ============================================
    #  TELEGRAM
    # ============================================
    BOT_TOKEN: str = Field(
        default="",
        description="Токен Telegram бота"
    )
    ADMIN_IDS: List[int] = Field(
        default_factory=list,
        description="ID администраторов (через запятую)"
    )
    
    @field_validator('ADMIN_IDS', mode='before')
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        return v
    
    # ============================================
    #  DATABASE
    # ============================================
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///data/documents.db",
        description="URL подключения к БД"
    )
    
    @field_validator('DATABASE_URL', mode='before')
    @classmethod
    def ensure_database_url(cls, v):
        if not v:
            return "sqlite+aiosqlite:///data/documents.db"
        # Конвертируем postgresql:// в postgresql+asyncpg://
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://")
        return v
    
    # ============================================
    #  AI / YANDEX GPT
    # ============================================
    YANDEX_API_KEY: Optional[str] = Field(
        default=None,
        description="API ключ Яндекс.Алисы"
    )
    YANDEX_FOLDER_ID: Optional[str] = Field(
        default=None,
        description="Folder ID для YandexGPT"
    )
    
    # ============================================
    #  FILE STORAGE
    # ============================================
    DATA_DIR: str = Field(
        default="data",
        description="Папка для данных"
    )
    TEMPLATES_DIR: str = Field(
        default="templates",
        description="Папка для шаблонов документов"
    )
    ACTS_DIR: str = Field(
        default="acts",
        description="Папка для сгенерированных актов"
    )
    MAX_FILE_SIZE: int = Field(
        default=52428800,  # 50 MB
        description="Максимальный размер файла"
    )
    ALLOWED_EXTENSIONS: List[str] = Field(
        default_factory=lambda: ['.pdf', '.docx', '.xlsx', '.jpg', '.png'],
        description="Разрешённые расширения файлов"
    )
    
    # ============================================
    #  LOGGING
    # ============================================
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Уровень логирования"
    )
    LOG_FILE: str = Field(
        default="bot.log",
        description="Путь к файлу логов"
    )
    
    # ============================================
    #  RATE LIMITING
    # ============================================
    RATE_LIMIT_MESSAGES: int = Field(
        default=30,
        description="Лимит сообщений в минуту"
    )
    RATE_LIMIT_FILES: int = Field(
        default=5,
        description="Лимит файлов в минуту"
    )
    RATE_LIMIT_WINDOW: int = Field(
        default=60,
        description="Окно rate limiting (секунды)"
    )
    
    # ============================================
    #  CACHE
    # ============================================
    CACHE_TTL: int = Field(
        default=300,
        description="TTL кэша (секунды)"
    )
    
    # ============================================
    #  PAGINATION
    # ============================================
    PAGE_SIZE: int = Field(
        default=20,
        description="Элементов на страницу"
    )
    MAX_PAGE_SIZE: int = Field(
        default=100,
        description="Максимум элементов на страницу"
    )
    
    # ============================================
    #  SECURITY
    # ============================================
    SECRET_KEY: str = Field(
        default_factory=lambda: os.urandom(32).hex(),
        description="Секретный ключ для JWT/сессий"
    )
    TOKEN_EXPIRE_HOURS: int = Field(
        default=24,
        description="Время жизни токена (часы)"
    )
    
    def validate_paths(self) -> None:
        """Создаёт необходимые директории."""
        for dir_path in [self.DATA_DIR, self.TEMPLATES_DIR, self.ACTS_DIR]:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
    
    @property
    def is_postgresql(self) -> bool:
        """True если используется PostgreSQL."""
        return "postgresql" in self.DATABASE_URL
    
    @property
    def is_sqlite(self) -> bool:
        """True если используется SQLite."""
        return "sqlite" in self.DATABASE_URL


# Глобальный экземпляр
settings = Settings()
settings.validate_paths()
