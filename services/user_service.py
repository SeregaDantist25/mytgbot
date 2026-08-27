# -*- coding: utf-8 -*-
"""
Сервис работы с пользователями.

Содержит функции CRUD для пользователей, работающие через ORM-модель
User (models.py). Обратная совместимость с bot.py сохранена: сигнатуры
функций совпадают с теми, что были в монолитном bot.py.
"""

from typing import List, Optional

from models import SessionLocal, User, PendingUser, AuditLog


def get_user(user_id: int) -> Optional[User]:
    """Возвращает пользователя по telegram_id.

    Args:
        user_id: Telegram ID пользователя.

    Returns:
        Объект User или None, если пользователь не найден.
    """
    session = SessionLocal()
    try:
        return session.query(User).filter_by(telegram_id=user_id).first()
    finally:
        session.close()


def create_user(user_id: int, name: str, role: str, phone: str = None, approved: int = 0) -> User:
    """Создаёт пользователя.

    Args:
        user_id: Telegram ID пользователя.
        name: Имя пользователя.
        role: Роль пользователя.
        phone: Телефон (опционально).
        approved: Флаг одобрения (0/1).

    Returns:
        Созданный объект User.
    """
    session = SessionLocal()
    try:
        user = User(telegram_id=user_id, role=role, name=name, phone=phone, approved=approved)
        session.add(user)
        session.commit()
        return user
    finally:
        session.close()


def get_or_create_user(user_id: int, name: str, role: str = "customer") -> User:
    """Возвращает пользователя, создавая его при отсутствии.

    Args:
        user_id: Telegram ID пользователя.
        name: Имя пользователя (используется при создании).
        role: Роль пользователя (по умолчанию customer).

    Returns:
        Существующий или созданный объект User.
    """
    user = get_user(user_id)
    if user:
        return user
    return create_user(user_id, name, role)


def get_users() -> List[User]:
    """Возвращает список всех пользователей.

    Returns:
        Список объектов User.
    """
    session = SessionLocal()
    try:
        return session.query(User).order_by(User.telegram_id).all()
    finally:
        session.close()


def get_stats() -> dict:
    """Возвращает статистику по пользователям.

    Returns:
        Словарь со статистикой (общее число пользователей и по ролям).
    """
    session = SessionLocal()
    try:
        users = session.query(User).all()
        stats = {
            "total": len(users),
            "by_role": {},
        }
        for u in users:
            stats["by_role"][u.role] = stats["by_role"].get(u.role, 0) + 1
        return stats
    finally:
        session.close()


def update_user_role(user_id: int, new_role: str) -> bool:
    """Обновляет роль пользователя.

    Args:
        user_id: Telegram ID пользователя.
        new_role: Новая роль.

    Returns:
        True, если роль обновлена; False, если пользователь не найден.
    """
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            return False
        user.role = new_role
        session.commit()
        return True
    finally:
        session.close()


# ============================================================
#  РОЛИ И ПРАВА
# ============================================================

ROLE_ENGINEER = "engineer"
ROLE_ENGINEER_TECHNOLOGIST = "engineer_technologist"
ROLE_DIRECTOR = "director"
ROLE_BUILDER = "builder"
ROLE_CUSTOMER = "customer"

ROLE_LABELS = {
    ROLE_ENGINEER: "Инженер-технолог",
    ROLE_ENGINEER_TECHNOLOGIST: "Инженер-технолог",
    ROLE_DIRECTOR: "Директор",
    ROLE_BUILDER: "Строитель",
    ROLE_CUSTOMER: "Заказчик",
}


def is_engineer(user) -> bool:
    return bool(user) and user.role in (ROLE_ENGINEER, ROLE_ENGINEER_TECHNOLOGIST)


def is_director(user) -> bool:
    return bool(user) and user.role == ROLE_DIRECTOR


def is_builder(user) -> bool:
    return bool(user) and user.role == ROLE_BUILDER


def is_customer(user) -> bool:
    return bool(user) and user.role == ROLE_CUSTOMER


def can_approve_users(user) -> bool:
    """Кто может одобрять новых пользователей."""
    return bool(user) and (is_engineer(user) or is_director(user))


def get_user_role(telegram_id: int) -> str:
    """Возвращает роль пользователя (или customer, если не найден)."""
    user = get_user(telegram_id)
    return user.role if user else ROLE_CUSTOMER


def can_upload_repair_list(telegram_id: int) -> bool:
    """Ремонтные ведомости могут загружать все производственные роли."""
    return get_user_role(telegram_id) in {
        ROLE_ENGINEER,
        ROLE_ENGINEER_TECHNOLOGIST,
        ROLE_DIRECTOR,
        ROLE_BUILDER,
    }


# ============================================================
#  ЗАЯВКИ НА РЕГИСТРАЦИЮ
# ============================================================

def add_pending_user(user_id: int, name: str, role: str, phone: str = None) -> None:
    session = SessionLocal()
    try:
        pending = session.query(PendingUser).filter_by(user_id=user_id).first()
        if pending:
            pending.name = name
            pending.role_requested = role
            pending.phone = phone
        else:
            session.add(PendingUser(user_id=user_id, name=name, role_requested=role, phone=phone))
        session.commit()
    finally:
        session.close()


def get_pending_users() -> list:
    session = SessionLocal()
    try:
        rows = session.query(PendingUser).order_by(PendingUser.created_at).all()
        return [
            {
                "user_id": p.user_id,
                "name": p.name,
                "role_requested": p.role_requested,
                "phone": p.phone,
            }
            for p in rows
        ]
    finally:
        session.close()


def get_pending_user(user_id: int) -> Optional[dict]:
    """Вернуть одну ожидающую заявку по Telegram ID."""
    session = SessionLocal()
    try:
        pending = session.query(PendingUser).filter_by(user_id=user_id).first()
        if not pending:
            return None
        return {
            "user_id": pending.user_id,
            "name": pending.name,
            "role_requested": pending.role_requested,
            "phone": pending.phone,
        }
    finally:
        session.close()


def remove_pending_user(user_id: int) -> None:
    session = SessionLocal()
    try:
        pending = session.query(PendingUser).filter_by(user_id=user_id).first()
        if pending:
            session.delete(pending)
            session.commit()
    finally:
        session.close()


# ============================================================
#  ЖУРНАЛ ДЕЙСТВИЙ
# ============================================================

def log_action(user_id: int, action: str, ship_id: int = None, doc_id: int = None, details: str = None) -> None:
    session = SessionLocal()
    try:
        session.add(AuditLog(user_id=user_id, action=action, ship_id=ship_id, doc_id=doc_id, details=details))
        session.commit()
    finally:
        session.close()
