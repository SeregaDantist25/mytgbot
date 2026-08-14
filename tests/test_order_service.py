# -*- coding: utf-8 -*-
"""
Тесты для services/order_service.py (заявки на ремонт).
"""

import pytest

from models import SessionLocal, Ship
from services.order_service import (
    create_order,
    get_order,
    list_orders,
    update_cost,
    change_status,
    delete_order,
    get_status_history,
    format_cost,
)


@pytest.fixture()
def ship_id():
    """Создаёт судно для заявок."""
    session = SessionLocal()
    try:
        ship = Ship(name="Тестовое судно", status="в работе")
        session.add(ship)
        session.commit()
        return ship.id
    finally:
        session.close()


# --- Создание ---

def test_create_order_ok(ship_id):
    ok, msg, order_id = create_order(ship_id, "Ремонт насоса", user_id=1, cost_kopecks=150000)
    assert ok is True
    assert order_id is not None
    order = get_order(order_id)
    assert order.status == "new"
    assert order.cost_kopecks == 150000
    # История содержит стартовую запись None → new
    hist = get_status_history(order_id)
    assert len(hist) == 1
    assert hist[0].from_status is None
    assert hist[0].to_status == "new"


def test_create_order_missing_ship():
    ok, msg, order_id = create_order(999999, "Работы", user_id=1)
    assert ok is False
    assert order_id is None


def test_create_order_negative_cost(ship_id):
    ok, msg, order_id = create_order(ship_id, "Работы", user_id=1, cost_kopecks=-1)
    assert ok is False


def test_create_order_empty_work_type(ship_id):
    ok, msg, order_id = create_order(ship_id, "   ", user_id=1)
    assert ok is False


# --- Смена статуса ---

def test_status_valid_transition(ship_id):
    _, _, order_id = create_order(ship_id, "Работы", user_id=1)
    ok, msg = change_status(order_id, "in_progress", user_id=1)
    assert ok is True
    assert get_order(order_id).status == "in_progress"
    # История дополнилась переходом
    hist = get_status_history(order_id)
    assert hist[-1].from_status == "new"
    assert hist[-1].to_status == "in_progress"


def test_status_invalid_transition(ship_id):
    _, _, order_id = create_order(ship_id, "Работы", user_id=1)
    # new → closed напрямую запрещён
    ok, msg = change_status(order_id, "closed", user_id=1)
    assert ok is False
    assert get_order(order_id).status == "new"


def test_status_same_status(ship_id):
    _, _, order_id = create_order(ship_id, "Работы", user_id=1)
    ok, msg = change_status(order_id, "new", user_id=1)
    assert ok is False


def test_status_unknown_value(ship_id):
    _, _, order_id = create_order(ship_id, "Работы", user_id=1)
    ok, msg = change_status(order_id, "teleported", user_id=1)
    assert ok is False


def test_status_terminal_is_final(ship_id):
    _, _, order_id = create_order(ship_id, "Работы", user_id=1)
    assert change_status(order_id, "cancelled", user_id=1)[0] is True
    # из cancelled никуда нельзя
    ok, msg = change_status(order_id, "in_progress", user_id=1)
    assert ok is False


def test_full_lifecycle(ship_id):
    _, _, order_id = create_order(ship_id, "Работы", user_id=1)
    assert change_status(order_id, "in_progress", user_id=1)[0] is True
    assert change_status(order_id, "done", user_id=1)[0] is True
    assert change_status(order_id, "closed", user_id=1)[0] is True
    assert get_order(order_id).status == "closed"


# --- Стоимость ---

def test_update_cost_ok(ship_id):
    _, _, order_id = create_order(ship_id, "Работы", user_id=1)
    ok, msg = update_cost(order_id, 250050)
    assert ok is True
    assert get_order(order_id).cost_kopecks == 250050


def test_update_cost_negative(ship_id):
    _, _, order_id = create_order(ship_id, "Работы", user_id=1)
    ok, msg = update_cost(order_id, -5)
    assert ok is False


def test_update_cost_blocked_when_closed(ship_id):
    _, _, order_id = create_order(ship_id, "Работы", user_id=1)
    change_status(order_id, "cancelled", user_id=1)
    ok, msg = update_cost(order_id, 100)
    assert ok is False


# --- Список и удаление ---

def test_list_orders_filter(ship_id):
    create_order(ship_id, "A", user_id=1)
    create_order(ship_id, "B", user_id=1)
    assert len(list_orders(ship_id=ship_id)) == 2
    assert len(list_orders(ship_id=ship_id, status="new")) == 2
    assert len(list_orders(ship_id=ship_id, status="closed")) == 0


def test_delete_requires_admin(ship_id):
    _, _, order_id = create_order(ship_id, "Работы", user_id=1)
    ok, msg = delete_order(order_id, user_id=1, admin_ids=[])
    assert ok is False
    ok, msg = delete_order(order_id, user_id=1, admin_ids=[1])
    assert ok is True
    assert get_order(order_id) is None


def test_delete_cascades_history(ship_id):
    _, _, order_id = create_order(ship_id, "Работы", user_id=1)
    change_status(order_id, "in_progress", user_id=1)
    delete_order(order_id, user_id=1, admin_ids=[1])
    assert get_status_history(order_id) == []


# --- Форматирование ---

def test_format_cost():
    assert format_cost(0) == "0.00 \u20bd"
    assert format_cost(150000) == "1 500.00 \u20bd"
    assert format_cost(250050) == "2 500.50 \u20bd"
