# -*- coding: utf-8 -*-
"""
Менеджер документов и ремонтных ведомостей.

Функции для:
1. Загрузки и парсинга Excel ремонтных ведомостей
2. Навигации по пунктам (с пагинацией)
3. Версионирования документов (draft → approved → archived)
4. Проверки прав доступа по ролям
"""

import os
from datetime import datetime
from models import SessionLocal, User, Ship, RepairStatement, StatementItem, Document
from file_storage import storage
import db

# Роли (из db.py)
ROLE_ENGINEER = "engineer"
ROLE_DIRECTOR = "director"
ROLE_BUILDER = "builder"
ROLE_CUSTOMER = "customer"

# Роли, которые могут загружать ремонтные ведомости
ROLES_CAN_UPLOAD_REPAIR_LIST = {ROLE_ENGINEER, ROLE_DIRECTOR, ROLE_BUILDER}

# Роли, которые могут редактировать/удалять ремонтные ведомости
ROLES_CAN_EDIT_REPAIR_LIST = {ROLE_ENGINEER, ROLE_BUILDER}

# Роли, которые могут удалять approved документы
ROLES_CAN_DELETE_APPROVED = {ROLE_ENGINEER}


def get_user_role(telegram_id):
    """Получить роль пользователя из ORM. Возвращает роль или None."""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        return user.role if user else None
    finally:
        session.close()


def ensure_user_exists(telegram_id, role=ROLE_CUSTOMER):
    """Создать пользователя, если его нет. Возвращает User."""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            user = User(telegram_id=telegram_id, role=role)
            session.add(user)
            session.commit()
        return user
    finally:
        session.close()


def ensure_ship_exists(ship_name):
    """Создать судно, если его нет. Возвращает Ship."""
    session = SessionLocal()
    try:
        ship = session.query(Ship).filter_by(name=ship_name).first()
        if not ship:
            ship = Ship(name=ship_name, status="в работе")
            session.add(ship)
            session.commit()
        return ship
    finally:
        session.close()


def sync_ships_from_json():
    """Синхронизирует суда из data/ships.json в таблицу ships.

    Если файла нет или он пуст — ничего не делает.
    Возвращает список названий судов, добавленных в БД.
    """
    import json
    data_dir = os.getenv("DATA_DIR", "data")
    ships_file = os.path.join(data_dir, "ships.json")
    if not os.path.exists(ships_file):
        return []
    try:
        with open(ships_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    added = []
    for name in data.values():
        ship = ensure_ship_exists(name)
        if ship:
            added.append(ship.name)
    return added


# ============================================================
#  ПЛАН 1: ИНТЕГРАЦИЯ ПАРСЕРА EXCEL
# ============================================================

def save_repair_items_to_db(ship_id, items):
    """
    Сохранить пункты ремонтной ведомости в БД.
    
    Args:
        ship_id: ID судна
        items: список dict {item_number, description, quantity, section}
    
    Returns:
        dict {
            "success": bool,
            "created": int,  # новых пунктов
            "skipped": int,  # дубликатов
            "errors": [str]  # ошибки
        }
    """
    session = SessionLocal()
    try:
        result = {"success": True, "created": 0, "skipped": 0, "errors": []}
        
        # Получить или создать RepairStatement
        statement = session.query(RepairStatement).filter_by(ship_id=ship_id).first()
        if not statement:
            statement = RepairStatement(ship_id=ship_id)
            session.add(statement)
            session.flush()  # чтобы получить ID
        
        # Получить существующие пункты (для дедупликации)
        existing_items = session.query(StatementItem).filter_by(
            statement_id=statement.id
        ).all()
        existing_keys = {(item.item_number, item.section) for item in existing_items}
        
        # Вставить новые пункты
        for item_data in items:
            key = (item_data.get("item_number"), item_data.get("section"))
            
            if key in existing_keys:
                result["skipped"] += 1
                continue
            
            try:
                item = StatementItem(
                    statement_id=statement.id,
                    item_number=item_data.get("item_number"),
                    description=item_data.get("description"),
                    quantity=item_data.get("quantity"),
                    section=item_data.get("section"),
                    status="active"
                )
                session.add(item)
                result["created"] += 1
            except Exception as e:
                result["errors"].append(f"Ошибка при добавлении пункта {item_data.get('item_number')}: {str(e)}")
        
        session.commit()
        return result
    except Exception as e:
        session.rollback()
        return {
            "success": False,
            "created": 0,
            "skipped": 0,
            "errors": [f"Ошибка БД: {str(e)}"]
        }
    finally:
        session.close()


# ============================================================
#  ПЛАН 2: НАВИГАЦИЯ ПО ПУНКТАМ
# ============================================================

def get_sections_for_ship(ship_id):
    """Получить список уникальных разделов для судна."""
    session = SessionLocal()
    try:
        statement = session.query(RepairStatement).filter_by(ship_id=ship_id).first()
        if not statement:
            return []
        
        sections = session.query(StatementItem.section).filter_by(
            statement_id=statement.id,
            status="active"
        ).distinct().all()
        
        return [s[0] for s in sections if s[0]]  # отфильтровать None
    finally:
        session.close()


def get_items_for_section(ship_id, section):
    """Получить пункты ремонтной ведомости для раздела."""
    session = SessionLocal()
    try:
        statement = session.query(RepairStatement).filter_by(ship_id=ship_id).first()
        if not statement:
            return []
        
        items = session.query(StatementItem).filter_by(
            statement_id=statement.id,
            section=section,
            status="active"
        ).all()
        
        return [
            {
                "id": item.id,
                "item_number": item.item_number,
                "description": item.description,
                "quantity": item.quantity,
                "section": item.section,
            }
            for item in items
        ]
    finally:
        session.close()


def get_item_details(item_id):
    """Получить детали пункта ремонтной ведомости."""
    session = SessionLocal()
    try:
        item = session.query(StatementItem).filter_by(id=item_id).first()
        if not item:
            return None
        
        # Получить документы для этого пункта
        documents = session.query(Document).filter_by(item_id=item_id).all()
        
        return {
            "id": item.id,
            "item_number": item.item_number,
            "description": item.description,
            "quantity": item.quantity,
            "section": item.section,
            "documents": [
                {
                    "id": doc.id,
                    "category": doc.category,
                    "file_ref": doc.file_ref,
                    "status": doc.status,
                    "version": doc.version,
                }
                for doc in documents
            ]
        }
    finally:
        session.close()


def paginate_list(items, page, page_size=10):
    """
    Разбить список на страницы.
    
    Returns:
        dict {
            "items": items на текущей странице,
            "page": текущая страница,
            "total_pages": всего страниц,
            "has_next": есть ли следующая,
            "has_prev": есть ли предыдущая
        }
    """
    total = len(items)
    total_pages = (total + page_size - 1) // page_size
    page = max(0, min(page, total_pages - 1))
    
    start = page * page_size
    end = start + page_size
    
    return {
        "items": items[start:end],
        "page": page,
        "total_pages": total_pages,
        "has_next": page < total_pages - 1,
        "has_prev": page > 0,
    }


# ============================================================
#  ПЛАН 3: ВЕРСИОНИРОВАНИЕ ДОКУМЕНТОВ
# ============================================================

MAX_DRAFTS_PER_CATEGORY = 4


def count_drafts_for_item(item_id, category):
    """Кол-во draft'ов для пункта и категории."""
    session = SessionLocal()
    try:
        count = session.query(Document).filter_by(
            item_id=item_id,
            category=category,
            status="draft"
        ).count()
        return count
    finally:
        session.close()


def get_oldest_draft(item_id, category):
    """Получить самый старый draft для пункта и категории."""
    session = SessionLocal()
    try:
        doc = session.query(Document).filter_by(
            item_id=item_id,
            category=category,
            status="draft"
        ).order_by(Document.uploaded_at).first()
        
        if doc:
            return {
                "id": doc.id,
                "file_ref": doc.file_ref,
                "uploaded_at": doc.uploaded_at,
            }
        return None
    finally:
        session.close()


def create_document(item_id, category, file_ref, file_type, uploaded_by):
    """
    Создать новый документ.
    
    Если draft'ов уже MAX_DRAFTS_PER_CATEGORY, возвращает информацию о старом draft.
    
    Returns:
        dict {
            "success": bool,
            "document_id": int (если успешно),
            "message": str,
            "oldest_draft": dict (если нужно удалить старый)
        }
    """
    session = SessionLocal()
    try:
        draft_count = session.query(Document).filter_by(
            item_id=item_id,
            category=category,
            status="draft"
        ).count()
        
        if draft_count >= MAX_DRAFTS_PER_CATEGORY:
            oldest = session.query(Document).filter_by(
                item_id=item_id,
                category=category,
                status="draft"
            ).order_by(Document.uploaded_at).first()
            
            return {
                "success": False,
                "message": f"Достигнут лимит черновиков ({MAX_DRAFTS_PER_CATEGORY}). Удалите старый?",
                "oldest_draft": {
                    "id": oldest.id,
                    "file_ref": oldest.file_ref,
                    "uploaded_at": oldest.uploaded_at.isoformat() if oldest.uploaded_at else None,
                }
            }
        
        # Создать новый документ
        doc = Document(
            item_id=item_id,
            category=category,
            file_ref=file_ref,
            file_type=file_type,
            status="draft",
            uploaded_by=uploaded_by,
            version=1
        )
        session.add(doc)
        session.commit()
        
        return {
            "success": True,
            "document_id": doc.id,
            "message": "Документ загружен как черновик",
            "oldest_draft": None
        }
    except Exception as e:
        session.rollback()
        return {
            "success": False,
            "message": f"Ошибка при создании документа: {str(e)}",
            "oldest_draft": None
        }
    finally:
        session.close()


def approve_document(document_id, user_id):
    """
    Утвердить документ (draft → approved).
    Конвертировать в PDF, если нужно.
    
    Returns:
        dict {"success": bool, "message": str}
    """
    session = SessionLocal()
    try:
        doc = session.query(Document).filter_by(id=document_id).first()
        if not doc:
            return {"success": False, "message": "Документ не найден"}
        
        if doc.status != "draft":
            return {"success": False, "message": f"Документ уже имеет статус '{doc.status}'"}
        
        # TODO: конвертировать в PDF, если нужно (DOCX → PDF)
        # Пока просто меняем статус
        
        doc.status = "approved"
        session.commit()
        
        return {"success": True, "message": "Документ утвержден"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": f"Ошибка: {str(e)}"}
    finally:
        session.close()


def delete_document(document_id, user_id, user_role):
    """
    Удалить документ.
    
    Правила:
    - draft можно удалять всем (кроме customer)
    - approved может удалять только engineer
    
    Returns:
        dict {"success": bool, "message": str}
    """
    session = SessionLocal()
    try:
        doc = session.query(Document).filter_by(id=document_id).first()
        if not doc:
            return {"success": False, "message": "Документ не найден"}
        
        # Проверка прав
        if doc.status == "approved" and user_role not in ROLES_CAN_DELETE_APPROVED:
            return {"success": False, "message": "Только инженер-технолог может удалять утвержденные документы"}
        
        if doc.status == "draft" and user_role == ROLE_CUSTOMER:
            return {"success": False, "message": "Заказчик не может удалять документы"}
        
        # Удалить файл
        storage.delete_file(doc.file_ref)
        
        # Удалить запись из БД
        session.delete(doc)
        session.commit()
        
        return {"success": True, "message": "Документ удален"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": f"Ошибка: {str(e)}"}
    finally:
        session.close()


def archive_document(document_id):
    """Архивировать документ (approved → archived)."""
    session = SessionLocal()
    try:
        doc = session.query(Document).filter_by(id=document_id).first()
        if not doc:
            return {"success": False, "message": "Документ не найден"}
        
        if doc.status != "approved":
            return {"success": False, "message": "Можно архивировать только утвержденные документы"}
        
        doc.status = "archived"
        session.commit()
        
        return {"success": True, "message": "Документ архивирован"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": f"Ошибка: {str(e)}"}
    finally:
        session.close()


# ============================================================
#  ПЛАН 4: ПРОВЕРКА ПРАВ ДОСТУПА
# ============================================================

def can_upload_repair_list(user_role):
    """Может ли пользователь загружать ремонтные ведомости."""
    return user_role in ROLES_CAN_UPLOAD_REPAIR_LIST


def can_edit_repair_list(user_role):
    """Может ли пользователь редактировать ремонтные ведомости."""
    return user_role in ROLES_CAN_EDIT_REPAIR_LIST


def can_delete_document(user_role, document_status):
    """Может ли пользователь удалить документ."""
    if document_status == "approved":
        return user_role in ROLES_CAN_DELETE_APPROVED
    return user_role != ROLE_CUSTOMER
