# -*- coding: utf-8 -*-

import hashlib

import document_manager as dm
from category_handlers import _parse_documents_callback
from models import RepairStatement, SessionLocal, Ship, StatementItem, User
from services import user_service


def _ship(name="Славянская"):
    session = SessionLocal()
    try:
        ship = Ship(name=name, status="в работе")
        session.add(ship)
        session.commit()
        return ship.id
    finally:
        session.close()


def test_section_hash_is_deterministic_md5_prefix():
    section = "Судовые системы и трубопроводы"
    expected = str(int(hashlib.md5(section.encode("utf-8")).hexdigest()[:8], 16))
    assert dm.section_hash(section) == expected


def test_save_repair_items_skips_duplicates_in_same_upload():
    ship_id = _ship()
    item = {
        "item_number": "4.47",
        "description": "Замена трубопровода",
        "quantity": "1",
        "section": "Трубопроводы",
    }

    result = dm.save_repair_items_to_db(ship_id, [item, item.copy()])

    assert result == {"success": True, "created": 1, "skipped": 1, "errors": []}
    session = SessionLocal()
    try:
        assert session.query(StatementItem).count() == 1
    finally:
        session.close()


def test_navigation_reads_all_statements_and_groups_extra_items():
    ship_id = _ship()
    session = SessionLocal()
    try:
        first = RepairStatement(ship_id=ship_id, source_excel_file_ref="one.xlsx")
        second = RepairStatement(ship_id=ship_id, source_excel_file_ref="two.xlsx")
        session.add_all([first, second])
        session.flush()
        session.add_all([
            StatementItem(
                statement_id=first.id, item_number="1.1", description="Насос",
                section="Механизмы", status="active",
            ),
            StatementItem(
                statement_id=second.id, item_number="2.1", description="Клапан",
                section="Арматура", status="active",
            ),
            StatementItem(
                statement_id=second.id, item_number="Д-1", description="Допработа",
                section="Вне ведомости", status="extra",
            ),
        ])
        session.commit()
    finally:
        session.close()

    assert dm.get_sections_for_ship(ship_id) == [
        "Арматура", "Механизмы", "Дополнительные работы"
    ]
    extra = dm.get_items_for_section(ship_id, "Дополнительные работы")
    assert [item["item_number"] for item in extra] == ["Д-1"]
    details = dm.get_item_details(extra[0]["id"])
    assert details["navigation_section"] == "Дополнительные работы"


def test_engineer_alias_has_engineer_permissions():
    session = SessionLocal()
    try:
        user = User(telegram_id=7001, role="engineer_technologist", name="Технолог")
        session.add(user)
        session.commit()
    finally:
        session.close()

    user = user_service.get_user(7001)
    assert user_service.is_engineer(user)
    assert user_service.can_approve_users(user)
    assert dm.can_upload_repair_list(user.role)
    assert dm.can_edit_repair_list(user.role)
    assert dm.can_delete_document(user.role, "approved")


def test_parse_documents_callback_preserves_underscored_category():
    assert _parse_documents_callback("docs_42_defect_act_3") == (42, "defect_act", 3)
