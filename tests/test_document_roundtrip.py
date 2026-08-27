# -*- coding: utf-8 -*-

from io import BytesIO

from openpyxl import load_workbook

from ai.act_dialog import build_act_file
from file_storage import storage
from models import SessionLocal, Ship, RepairStatement, StatementItem, User
from services.document_service import create_document, delete_document, get_document, replace_document


def _create_item():
    session = SessionLocal()
    try:
        user = User(telegram_id=1001, role="engineer", name="Технолог")
        ship = Ship(name="Тестовое судно")
        session.add_all([user, ship])
        session.flush()
        statement = RepairStatement(ship_id=ship.id)
        session.add(statement)
        session.flush()
        item = StatementItem(
            statement_id=statement.id,
            item_number="4.10",
            description="Воздушный клапан Ду-25",
            quantity="2 шт.",
        )
        session.add(item)
        session.commit()
        return item.id
    finally:
        session.close()


def _xlsx(defect):
    return build_act_file({
        "item_number": "4.10",
        "ship": "Тестовое судно",
        "equipment": "Воздушный клапан Ду-25",
        "equipment_type": "general",
        "pump_type": None,
        "gosts": [],
        "defects": [defect],
        "repair_type": "Текущий ремонт",
        "extra_info": "",
        "order_number": "24-01",
        "manager_name": "Технолог",
        "contractor_name": "Технолог",
        "item_quantity": "2 шт.",
    })[0]


def test_generated_xlsx_roundtrip_replace_and_delete():
    item_id = _create_item()
    original = _xlsx("Износ уплотнения")
    doc = create_document(item_id, "defect_act", original, 1001, ".xlsx")

    assert doc is not None
    assert storage.get_file(document_id=doc.id) == original
    assert load_workbook(BytesIO(original))["Акт дефектации"]

    replacement = _xlsx("Трещина корпуса")
    ok, _ = replace_document(doc.id, replacement, 1001, ".xlsx")
    assert ok is True
    assert get_document(doc.id) is not None
    assert storage.get_file(document_id=doc.id) == replacement

    ok, _ = delete_document(doc.id, 1001, admin_ids=[])
    assert ok is True
    assert get_document(doc.id) is None
