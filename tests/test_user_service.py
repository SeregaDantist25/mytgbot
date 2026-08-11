# -*- coding: utf-8 -*-
"""
Тесты для services/user_service.py (CRUD пользователей).
"""

from services.user_service import (
    get_user,
    create_user,
    get_or_create_user,
    get_users,
    get_stats,
    update_user_role,
)


class TestUserService:
    """Тесты сервиса пользователей."""

    def test_create_and_get(self):
        user = create_user(1001, "Иванов", "engineer_technologist")
        assert user.telegram_id == 1001
        assert user.role == "engineer_technologist"

        fetched = get_user(1001)
        assert fetched is not None
        assert fetched.role == "engineer_technologist"

    def test_get_missing(self):
        assert get_user(999999) is None

    def test_get_or_create_existing(self):
        create_user(1002, "Петров", "builder")
        user = get_or_create_user(1002, "Петров", "customer")
        # Существующий пользователь не пересоздаётся
        assert user.role == "builder"

    def test_get_or_create_new(self):
        user = get_or_create_user(1003, "Сидоров", "customer")
        assert user.telegram_id == 1003
        assert user.role == "customer"

    def test_get_users(self):
        create_user(1004, "А", "customer")
        create_user(1005, "Б", "director")
        users = get_users()
        ids = [u.telegram_id for u in users]
        assert 1004 in ids
        assert 1005 in ids

    def test_get_stats(self):
        create_user(1006, "В", "customer")
        create_user(1007, "Г", "customer")
        stats = get_stats()
        assert stats["total"] == 2
        assert stats["by_role"].get("customer") == 2

    def test_update_user_role(self):
        create_user(1008, "Д", "customer")
        assert update_user_role(1008, "director") is True
        assert get_user(1008).role == "director"

    def test_update_missing_user(self):
        assert update_user_role(999999, "director") is False