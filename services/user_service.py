# -*- coding: utf-8 -*-
"""
Сервис работы с пользователями.

Содержит функции CRUD для пользователей, работающие через ORM-модель
User (models.py). Обратная совместимость с bot.py сохранена: сигнатуры
функций совпадают с теми, что были в монолитном bot.py.
"""

from typing import List, Optional

from models import SessionLocal, User


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


def create_user(user_id: int, name: str, role: str) -> User:
    """Создаёт пользователя.

    Args:
        user_id: Telegram ID пользователя.
        name: Имя пользователя.
        role: Роль пользователя.

    Returns:
        Созданный объект User.
    """
    session = SessionLocal()
    try:
        user = User(telegram_id=user_id, role=role)
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
