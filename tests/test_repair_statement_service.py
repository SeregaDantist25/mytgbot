# -*- coding: utf-8 -*-

from models import SessionLocal, Ship
from services.repair_statement_service import save_repair_items_to_db


def _ship_id():
    session = SessionLocal()
    try:
        ship = Ship(name="Тестовое судно")
        session.add(ship)
        session.commit()
        return ship.id
    finally:
        session.close()


def test_repeated_upload_reuses_statement_and_skips_duplicates():
    ship_id = _ship_id()
    item = {
        "item_number": "4.10",
        "description": "Клапан Ду-25",
        "quantity": "2 шт.",
        "section": "Механическая часть",
    }

    first = save_repair_items_to_db(ship_id, [item, item.copy()])
    second = save_repair_items_to_db(ship_id, [item])

    assert first[0:2] == (1, 1)
    assert second[0:2] == (0, 1)
    assert first[2] == second[2]


def test_two_distinct_items_are_inserted():
    ship_id = _ship_id()
    items = [
        {"item_number": "1.1", "description": "Насос", "section": "МО"},
        {"item_number": "1.2", "description": "Клапан", "section": "МО"},
    ]

    inserted, skipped, _ = save_repair_items_to_db(ship_id, items)
    assert (inserted, skipped) == (2, 0)
