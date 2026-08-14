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
from datetime import date
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    Text,
    String,
    ForeignKey,
    DateTime,
    Date,
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
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)

    statements = relationship("RepairStatement", back_populates="ship")
    company = relationship("Company", back_populates="ships")
    repair_requests = relationship("RepairRequest", back_populates="ship")


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


class RepairOrder(Base):
    """Заявка на ремонт судна.

    Отличается от RepairStatement: RepairStatement — это загруженная из Excel
    ремонтная ведомость (перечень пунктов), а RepairOrder — управленческая
    заявка (когда, что за работы, в каком статусе, за сколько).

    Почему стоимость в копейках (BigInteger), а не Numeric/float:
    хранение денег как float даёт ошибки округления; целое число копеек
    точно, компактно и одинаково работает в SQLite и PostgreSQL.
    """

    __tablename__ = "repair_orders"

    # Разрешённые статусы и допустимые переходы между ними.
    # Ключ — текущий статус, значение — множество статусов, куда можно перейти.
    STATUSES = ("new", "in_progress", "done", "closed", "cancelled")
    TRANSITIONS = {
        "new": {"in_progress", "cancelled"},
        "in_progress": {"done", "cancelled"},
        "done": {"closed", "in_progress"},
        "closed": set(),
        "cancelled": set(),
    }

    id = Column(Integer, primary_key=True)
    ship_id = Column(Integer, ForeignKey("ships.id"), nullable=False, index=True)
    work_type = Column(String)
    status = Column(String, nullable=False, default="new", index=True)
    cost_kopecks = Column(BigInteger, nullable=False, default=0)
    created_by = Column(BigInteger, ForeignKey("users.telegram_id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    ship = relationship("Ship")
    status_history = relationship(
        "OrderStatusHistory",
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderStatusHistory(Base):
    """История изменений статуса заявки на ремонт (аудит переходов)."""

    __tablename__ = "order_status_history"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("repair_orders.id"), nullable=False, index=True)
    from_status = Column(String)
    to_status = Column(String, nullable=False)
    changed_by = Column(BigInteger)
    changed_at = Column(DateTime, server_default=func.now())

    order = relationship("RepairOrder", back_populates="status_history")


class ActDialogSession(Base):
    """Персистентная сессия диалога создания акта дефектации через AI.

    Хранится в БД (SQLite/PostgreSQL), а не только в памяти процесса,
    чтобы данные диалога (дефекты, правки, сгенерированный файл) не
    терялись при перезапуске/передеплое бота (например, на Railway).
    Списковые/словарные поля хранятся как JSON-строки.
    """

    __tablename__ = "act_dialog_sessions"

    chat_id = Column(BigInteger, primary_key=True)
    item_id = Column(Integer, nullable=False)
    item_number = Column(String)
    ship = Column(String)
    equipment = Column(Text)
    equipment_type = Column(String)
    pump_type = Column(String)
    gosts_json = Column(Text)  # JSON-список строк
    defects_json = Column(Text)  # JSON-список строк
    repair_type = Column(String)
    extra_info = Column(Text)
    corrections_json = Column(Text)  # JSON-список строк
    edit_count = Column(Integer, default=0)
    work_volume = Column(Text)
    last_file = Column(LargeBinary)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Company(Base):
    """Компания-заказчик.

    Ранее хранилась в data/companies.json — перенесено в БД для:
    - CRUD операций через сервис
    - Связей с судами и заявками
    - Аудита изменений
    - Поиска и фильтрации
    """

    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True, index=True)
    inn = Column(String, unique=True, index=True)  # ИНН 10/12 цифр
    contact_person = Column(String)  # Контактное лицо
    phone = Column(String)
    email = Column(String)
    address = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    ships = relationship("Ship", back_populates="company")
    repair_requests = relationship("RepairRequest", back_populates="company")


class Employee(Base):
    """Сотрудник предприятия.

    Ранее хранился в data/employees.json — перенесено в БД для:
    - CRUD операций через сервис
    - Связей с заявками и документами
    - Квалификации и допусков
    - Поиска по должности/ФИО
    """

    __tablename__ = "employees"

    id = Column(Integer, primary_key=True)
    full_name = Column(String, nullable=False, index=True)
    position = Column(String)  # Должность
    qualification = Column(String)  # Квалификация (разряд, категория)
    phone = Column(String)
    email = Column(String)
    department = Column(String)  # Отдел/цех
    hire_date = Column(Date)
    is_active = Column(Integer, default=1)  # 1 — работает, 0 — уволен
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class RepairRequest(Base):
    """Заявка на ремонт судна.

    Связывает заказчика, судно и перечень работ.
    Имеет жизненный цикл: draft → submitted → in_progress → completed → closed.
    """

    __tablename__ = "repair_requests"

    id = Column(Integer, primary_key=True)
    request_number = Column(String, unique=True, nullable=False)  # Номер заявки (RR-2025-001)
    company_id = Column(Integer, ForeignKey("companies.id"))
    ship_id = Column(Integer, ForeignKey("ships.id"))
    description = Column(Text)  # Описание проблемы
    priority = Column(String, default="normal")  # low, normal, high, critical
    status = Column(String, default="draft", index=True)  # draft, submitted, in_progress, completed, closed
    estimated_cost = Column(Integer)  # Ожидаемая стоимость (копейки)
    actual_cost = Column(Integer)  # Фактическая стоимость
    start_date = Column(Date)  # Плановая дата начала
    end_date = Column(Date)  # Плановая дата завершения
    actual_start_date = Column(Date)  # Фактическая дата начала
    actual_end_date = Column(Date)  # Фактическая дата завершения
    assigned_employee_id = Column(Integer, ForeignKey("employees.id"))  # Ответственный сотрудник
    created_by = Column(BigInteger, ForeignKey("users.telegram_id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    company = relationship("Company", back_populates="repair_requests")
    ship = relationship("Ship", back_populates="repair_requests")
    assigned_employee = relationship("Employee")
    creator = relationship("User")


class ActTemplate(Base):
    """Шаблон документа для автоматического заполнения.

    Хранит шаблоны актов (дефектации, выполненных работ и т.д.)
    с метаданными для подстановки данных из БД.
    """

    __tablename__ = "act_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)  # Название шаблона
    template_type = Column(String, nullable=False)  # defect_act, work_act, technical_act, repair_sheet
    file_ref = Column(String, nullable=False)  # Путь к файлу шаблона (DOCX/XLSX)
    description = Column(Text)  # Описание шаблона
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


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
