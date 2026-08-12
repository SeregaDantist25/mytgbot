# -*- coding: utf-8 -*-
"""
ORM-модели для новой схемы документооборота.

Почему SQLAlchemy (sync):
1. Текущий код бота полностью синхронный (pyTelegramBotAPI, sqlite3) —
   async ORM потребовал бы async-драйвер и async-сессии в каждом месте,
   что ломает существующую архитектуру.
2. SQLAlchemy sync даёт возможность в будущем переехать с SQLite
   на PostgreSQL (как в schema.sql) сменой строки подключения без
   переписывания запросов.
3. Однопоточная модель бота (infinity_polling) не нуждается в async I/O.
"""

import os
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    Text,
    String,
    ForeignKey,
    DateTime,
    func,
    create_engine,
    LargeBinary,
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# Строка подключения. По умолчанию — та же SQLite-база, что использует db.py.
# Для PostgreSQL: postgresql+psycopg2://user:pass@host:5432/dbname
# На Railway: DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/documents.db")

# Параметры для разных БД
engine_kwargs = {"echo": False}
if "postgresql" in DATABASE_URL:
    # Для PostgreSQL добавляем параметры подключения
    engine_kwargs["pool_pre_ping"] = True  # Проверка соединения перед использованием
    engine_kwargs["pool_recycle"] = 3600  # Переиспользование соединений

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

Base = declarative_base()


class User(Base):
    """Пользователь бота. telegram_id — первичный ключ (см. ТЗ).

    Роли:
    - engineer: инженер-технолог (абсолютные права)
    - engineer_technologist: синоним инженера-технолога (обратная совместимость)
    - director: директор
    - builder: строитель
    - customer: заказчик
    """

    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True)
    role = Column(String, nullable=False, default="customer")
    name = Column(String)
    phone = Column(String)
    approved = Column(Integer, default=0)

    documents = relationship("Document", back_populates="uploader")


class PendingUser(Base):
    """Заявка на регистрацию пользователя."""

    __tablename__ = "pending_users"

    user_id = Column(BigInteger, primary_key=True)
    name = Column(String, nullable=False)
    role_requested = Column(String, nullable=False)
    phone = Column(String)
    created_at = Column(DateTime, server_default=func.now())


class AuditLog(Base):
    """Журнал действий пользователей."""

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    action = Column(String, nullable=False)
    ship_id = Column(Integer)
    doc_id = Column(Integer)
    details = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class Ship(Base):
    """Судно, находящееся в ремонте."""

    __tablename__ = "ships"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    status = Column(String, default="в работе")
    year = Column(Integer)

    statements = relationship("RepairStatement", back_populates="ship")


class RepairStatement(Base):
    """Ремонтная ведомость судна (одна загрузка excel-файла)."""

    __tablename__ = "repair_statements"

    id = Column(Integer, primary_key=True)
    ship_id = Column(Integer, ForeignKey("ships.id"))
    source_excel_file_ref = Column(String)
    created_at = Column(DateTime, server_default=func.now())

    ship = relationship("Ship", back_populates="statements")
    items = relationship("StatementItem", back_populates="statement")


class StatementItem(Base):
    """Пункт ремонтной ведомости."""

    __tablename__ = "statement_items"

    id = Column(Integer, primary_key=True)
    statement_id = Column(Integer, ForeignKey("repair_statements.id"))
    item_number = Column(String)
    description = Column(Text)
    quantity = Column(String)
    section = Column(String)
    status = Column(String, default="active")

    statement = relationship("RepairStatement", back_populates="items")
    documents = relationship("Document", back_populates="item")


class Document(Base):
    """Файл документа, привязанный к пункту ведомости."""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("statement_items.id"), index=True)
    category = Column(String, nullable=False)  # defect_act_draft, defect_act_approved, avr, other
    file_ref = Column(String, nullable=False)
    file_type = Column(String)
    version = Column(Integer, default=1)
    status = Column(String, default="draft", index=True)
    uploaded_by = Column(BigInteger, ForeignKey("users.telegram_id"))
    uploaded_at = Column(DateTime, server_default=func.now())
    file_data = Column(LargeBinary)  # Содержимое файла (для PostgreSQL/Railway)
    source = Column(String, default="bot")  # bot — загрузка через бота, folder — импорт из папки

    item = relationship("StatementItem", back_populates="documents")
    uploader = relationship("User", back_populates="documents")


def init_models():
    """Создаёт таблицы через ORM (для SQLite) и добавляет недостающие колонки."""
    Base.metadata.create_all(engine)
    _ensure_column("documents", "source", "VARCHAR DEFAULT 'bot'")
    _ensure_column("documents", "file_data", "BLOB")
    _ensure_column("users", "name", "VARCHAR")
    _ensure_column("users", "phone", "VARCHAR")
    _ensure_column("users", "approved", "INTEGER DEFAULT 0")


def _ensure_column(table, column, ddl_type):
    """Добавляет колонку в существующую таблицу, если её нет (SQLite/PostgreSQL)."""
    try:
        inspector = __import__("sqlalchemy").inspect(engine)
        if column in [c["name"] for c in inspector.get_columns(table)]:
            return
        with engine.begin() as conn:
            conn.execute(__import__("sqlalchemy").text(
                f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"
            ))
    except Exception:
        # Если колонка уже есть или БД не поддерживает — игнорируем
        pass


def sync_ships_from_json(ships_data):
    """
    Синхронизирует суда из ships.json в таблицу ships.
    ships_data: dict {"название": "Название"}
    """
    session = SessionLocal()
    try:
        for name in ships_data.values():
            existing = session.query(Ship).filter_by(name=name).first()
            if not existing:
                session.add(Ship(name=name, status="в работе"))
        session.commit()
    finally:
        session.close()
