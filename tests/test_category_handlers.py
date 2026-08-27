# -*- coding: utf-8 -*-

import bot_context
from category_handlers import _build_document_actions_keyboard
from models import Document, RepairStatement, SessionLocal, Ship, StatementItem, User


def _callbacks(keyboard):
    return {
        button.callback_data
        for row in keyboard.keyboard
        for button in row
        if button.callback_data
    }


def _document(status="draft"):
    session = SessionLocal()
    try:
        ship = Ship(name="Тестовое судно")
        session.add(ship)
        session.flush()
        statement = RepairStatement(ship_id=ship.id)
        session.add(statement)
        session.flush()
        item = StatementItem(statement_id=statement.id, item_number="1.1", description="Насос")
        session.add(item)
        session.flush()
        doc = Document(
            item_id=item.id,
            category="defect_act",
            file_ref="documents/act.xlsx",
            file_type=".xlsx",
            status=status,
            file_data=b"xlsx",
        )
        session.add(doc)
        session.commit()
        return doc.id
    finally:
        session.close()


def _user(user_id, role, approved=1):
    session = SessionLocal()
    try:
        session.add(User(telegram_id=user_id, name="Пользователь", role=role, approved=approved))
        session.commit()
    finally:
        session.close()


def test_manager_sees_draft_actions_and_download():
    _user(9101, "engineer_technologist")
    doc_id = _document("draft")
    callbacks = _callbacks(_build_document_actions_keyboard(doc_id, 9101))
    assert {f"download_doc_{doc_id}", f"replace_{doc_id}", f"approve_{doc_id}", f"delete_{doc_id}"} <= callbacks


def test_customer_only_sees_download_and_back():
    _user(9102, "customer")
    doc_id = _document("draft")
    callbacks = _callbacks(_build_document_actions_keyboard(doc_id, 9102))
    assert f"download_doc_{doc_id}" in callbacks
    assert f"approve_{doc_id}" not in callbacks
    assert f"delete_{doc_id}" not in callbacks


def test_only_admin_sees_archive_action(monkeypatch):
    doc_id = _document("approved")
    monkeypatch.setattr(bot_context, "ADMIN_IDS", [9103])
    admin_callbacks = _callbacks(_build_document_actions_keyboard(doc_id, 9103))
    viewer_callbacks = _callbacks(_build_document_actions_keyboard(doc_id, 9104))
    assert f"archive_{doc_id}" in admin_callbacks
    assert f"archive_{doc_id}" not in viewer_callbacks
