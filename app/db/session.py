# -*- coding: utf-8 -*-
"""
База данных: сессии и утилиты.

Поддержка async для PostgreSQL (asyncpg) и SQLite (aiosqlite).
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings


class DatabaseManager:
    """Менеджер подключений к БД."""
    
    def __init__(self):
        self.engine: AsyncEngine = None
        self.async_session_maker: async_sessionmaker = None
        self._initialized = False
    
    def initialize(self) -> None:
        """Инициализирует движок и фабрику сессий."""
        if self._initialized:
            return
        
        # Параметры для разных БД
        engine_kwargs = {
            "echo": settings.LOG_LEVEL == "DEBUG",
            "pool_pre_ping": True,  # Проверка соединения перед использованием
        }
        
        if settings.is_postgresql:
            # PostgreSQL с asyncpg
            engine_kwargs.update({
                "pool_size": 10,
                "max_overflow": 20,
                "pool_recycle": 3600,
            })
        elif settings.is_sqlite:
            # SQLite с aiosqlite
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            engine_kwargs["poolclass"] = NullPool  # Отключаем пул для SQLite
        
        self.engine = create_async_engine(
            settings.DATABASE_URL,
            **engine_kwargs
        )
        
        self.async_session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        
        self._initialized = True
    
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Генератор сессий для dependency injection."""
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def create_tables(self) -> None:
        """Создаёт все таблицы в БД."""
        from app.models.schemas import Base
        
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def drop_tables(self) -> None:
        """Удаляет все таблицы (для тестов)."""
        from app.models.schemas import Base
        
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    
    async def close(self) -> None:
        """Закрывает соединения с БД."""
        if self.engine:
            await self.engine.dispose()


# Глобальный экземпляр
db_manager = DatabaseManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency для получения сессии БД."""
    async for session in db_manager.get_session():
        yield session
