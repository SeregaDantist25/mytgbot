# -*- coding: utf-8 -*-

import json
from datetime import datetime, timedelta

import bot_context
from ai.act_dialog import (
    SESSION_TIMEOUT,
    _check_access,
    _get_item_and_ship,
    _load_session,
    _save_session,
)
from models import (
    ActDialogSession,
    RepairStatement,
    SessionLocal,
    Ship,
    StatementItem,
    User,
)


def _session_data():
    return {
        "item_id": 10,
        "item_number": "4.10",
        "ship": "Славянская",
        "equipment": "Воздушный клапан Ду-25",
        "equipment_type": "general",
        "pump_type": None,
        "gosts": [],
        "defects": ["Износ уплотнения"],
        "repair_type": "Текущий ремонт",
        "extra_info": "Ду-25, 2 шт.",
        "corrections": ["Указать испытание"],
        "edit_count": 1,
        "work_volume": "Разобрать и испытать",
        "last_file": b"xlsx-bytes",
        "order_number": "24-01",
        "manager_name": "С. В. Бачурин",
        "contractor_name": "С. В. Бачурин",
        "item_quantity": "2 шт.",
    }


def test_session_roundtrip_preserves_act_metadata():
    _save_session(1001, _session_data())
    restored = _load_session(1001)
    assert restored["order_number"] == "24-01"
    assert restored["manager_name"] == "С. В. Бачурин"
    assert restored["item_quantity"] == "2 шт."
    assert restored["corrections"] == ["Указать испытание"]
    assert restored["last_file"] == b"xlsx-bytes"


def test_old_session_list_format_remains_readable():
    db = SessionLocal()
    try:
        data = _session_data()
        row = ActDialogSession(
            chat_id=1002,
            item_id=data["item_id"],
            item_number=data["item_number"],
            ship=data["ship"],
            equipment=data["equipment"],
            defects_json=json.dumps(data["defects"], ensure_ascii=False),
            corrections_json=json.dumps(["Старая правка"], ensure_ascii=False),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
    finally:
        db.close()
    restored = _load_session(1002)
    assert restored["corrections"] == ["Старая правка"]
    assert restored["order_number"] == ""


def test_expired_session_is_removed():
    db = SessionLocal()
    try:
        row = ActDialogSession(
            chat_id=1003,
            item_id=10,
            item_number="1",
            ship="Судно",
            equipment="Механизм",
            updated_at=datetime.utcnow() - SESSION_TIMEOUT - timedelta(minutes=1),
        )
        db.add(row)
        db.commit()
    finally:
        db.close()
    assert _load_session(1003) is None


def test_item_lookup_returns_quantity():
    db = SessionLocal()
    try:
        ship = Ship(name="Славянская")
        db.add(ship)
        db.flush()
        statement = RepairStatement(ship_id=ship.id)
        db.add(statement)
        db.flush()
        item = StatementItem(
            statement_id=statement.id,
            item_number="4.10",
            description="Воздушный клапан",
            quantity="2 шт.",
            section="Механизмы",
        )
        db.add(item)
        db.commit()
        item_id = item.id
    finally:
        db.close()
    details, ship_name = _get_item_and_ship(item_id)
    assert ship_name == "Славянская"
    assert details["quantity"] == "2 шт."


def test_engineer_alias_and_admin_have_access():
    db = SessionLocal()
    try:
        db.add(User(telegram_id=2001, role="engineer_technologist", name="Технолог"))
        db.add(User(telegram_id=2002, role="customer", name="Заказчик"))
        db.commit()
    finally:
        db.close()
    previous_admins = bot_context.ADMIN_IDS
    try:
        bot_context.ADMIN_IDS = [3001]
        assert _check_access(2001) is True
        assert _check_access(2002) is False
        assert _check_access(3001) is True
    finally:
        bot_context.ADMIN_IDS = previous_admins
