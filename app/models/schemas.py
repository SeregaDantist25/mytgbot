# -*- coding: utf-8 -*-
"""
ORM-модели для новой архитектуры.

Используем SQLAlchemy 2.0 с async support для PostgreSQL и SQLite.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    LargeBinary,
    Index,
    func,
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import functions

Base = declarative_base()


class User(Base):
    """Пользователь системы."""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="customer")
    phone = Column(String(50))
    inn = Column(String(20))  # ИНН для заказчиков
    approved = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    documents = relationship("Document", back_populates="uploader")
    ships = relationship("Ship", back_populates="builder")
    audit_logs = relationship("AuditLog", back_populates="user")
    
    __table_args__ = (
        Index('idx_users_telegram_id', 'telegram_id'),
        Index('idx_users_role', 'role'),
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, role={self.role})>"


class Ship(Base):
    """Судно в ремонте."""
    
    __tablename__ = "ships"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    type = Column(String(100))  # Тип судна
    registry_number = Column(String(50))  # Регистровый номер
    year_built = Column(Integer)  # Год постройки
    status = Column(String(50), default="in_work")  # in_work, completed, archived
    customer_name = Column(String(255))  # Название компании-заказчика
    customer_inn = Column(String(20))  # ИНН заказчика
    customer_contact = Column(Text)  # Контакты заказчика
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    builder_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    builder = relationship("User", back_populates="ships")
    statements = relationship("RepairStatement", back_populates="ship", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="ship")
    
    __table_args__ = (
        Index('idx_ships_status', 'status'),
        Index('idx_ships_name', 'name'),
    )
    
    def __repr__(self):
        return f"<Ship(id={self.id}, name='{self.name}', status={self.status})>"


class RepairStatement(Base):
    """Ремонтная ведомость (загруженный Excel файл)."""
    
    __tablename__ = "repair_statements"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ship_id = Column(Integer, ForeignKey("ships.id"), nullable=False)
    source_excel_file_ref = Column(String(500))  # Путь к исходному Excel
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    ship = relationship("Ship", back_populates="statements")
    items = relationship("StatementItem", back_populates="statement", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<RepairStatement(id={self.id}, ship_id={self.ship_id})>"


class StatementItem(Base):
    """Пункт ремонтной ведомости."""
    
    __tablename__ = "statement_items"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    statement_id = Column(Integer, ForeignKey("repair_statements.id"), nullable=False)
    item_number = Column(String(50))  # Номер пункта (например, "4.56.2")
    description = Column(Text, nullable=False)  # Описание работ
    quantity = Column(String(100))  # Количество/объём
    section = Column(String(255))  # Раздел/категория
    status = Column(String(50), default="active")  # active, completed, cancelled
    unit_price = Column(Integer)  # Цена за единицу (опционально)
    total_price = Column(Integer)  # Общая стоимость (опционально)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    statement = relationship("RepairStatement", back_populates="items")
    documents = relationship("Document", back_populates="item", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_items_statement_id', 'statement_id'),
        Index('idx_items_status', 'status'),
    )
    
    def __repr__(self):
        return f"<StatementItem(id={self.id}, item_number='{self.item_number}')>"


class Document(Base):
    """Документ (акт, АВР, договор и т.д.)."""
    
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("statement_items.id"), nullable=False, index=True)
    category = Column(String(50), nullable=False)  # defect_act, work_act, contract, technical_act
    file_ref = Column(String(500))  # Путь к файлу
    file_type = Column(String(20))  # pdf, docx, xlsx
    file_data = Column(LargeBinary)  # Содержимое файла (для PostgreSQL)
    version = Column(Integer, default=1)
    status = Column(String(50), default="draft", index=True)  # draft, approved, archived, rejected
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    uploaded_at = Column(DateTime, server_default=func.now())
    approved_by = Column(Integer, ForeignKey("users.id"))  # Кто утвердил
    approved_at = Column(DateTime)  # Когда утвердили
    rejection_reason = Column(Text)  # Причина отклонения
    ai_generated = Column(Boolean, default=False)  # Сгенерирован ли ИИ
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    item = relationship("StatementItem", back_populates="documents")
    uploader = relationship("User", foreign_keys=[uploaded_by], back_populates="documents")
    approver = relationship("User", foreign_keys=[approved_by])
    
    __table_args__ = (
        Index('idx_documents_item_category', 'item_id', 'category'),
        Index('idx_documents_status', 'status'),
    )
    
    def __repr__(self):
        return f"<Document(id={self.id}, category={self.category}, status={self.status})>"


class Company(Base):
    """Компания-заказчик."""
    
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    inn = Column(String(20), unique=True)  # ИНН
    kpp = Column(String(9))  # КПП
    address = Column(Text)  # Юридический адрес
    contact_person = Column(String(255))  # Контактное лицо
    phone = Column(String(50))
    email = Column(String(255))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Company(id={self.id}, name='{self.name}')>"


class Employee(Base):
    """Сотрудник (для внутренней учётки)."""
    
    __tablename__ = "employees"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(255), nullable=False)
    position = Column(String(100))  # Должность
    qualification = Column(String(255))  # Квалификация/разряд
    department = Column(String(100))  # Отдел
    phone = Column(String(50))
    email = Column(String(255))
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User")
    
    def __repr__(self):
        return f"<Employee(id={self.id}, name='{self.full_name}')>"


class AuditLog(Base):
    """Журнал аудита действий пользователей."""
    
    __tablename__ = "audit_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(100), nullable=False)  # create, update, delete, approve, reject
    entity_type = Column(String(50))  # ship, document, statement_item
    entity_id = Column(Integer)  # ID сущности
    ship_id = Column(Integer, ForeignKey("ships.id"))
    doc_id = Column(Integer, ForeignKey("documents.id"))
    details = Column(Text)  # JSON с деталями изменения
    ip_address = Column(String(45))  # IP (если доступно)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")
    ship = relationship("Ship", back_populates="audit_logs")
    
    __table_args__ = (
        Index('idx_audit_user_id', 'user_id'),
        Index('idx_audit_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f"<AuditLog(id={self.id}, action={self.action}, user_id={self.user_id})>"


class ActTemplate(Base):
    """Шаблон акта для генерации через ИИ."""
    
    __tablename__ = "act_templates"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)  # Название шаблона
    act_type = Column(String(50), nullable=False)  # defect_act, work_act, technical_act
    template_path = Column(String(500))  # Путь к файлу шаблона
    fields_json = Column(Text)  # JSON с описанием полей
    prompt_template = Column(Text)  # Шаблон промпта для ИИ
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<ActTemplate(id={self.id}, name='{self.name}', type={self.act_type})>"
