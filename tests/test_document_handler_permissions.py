# -*- coding: utf-8 -*-

import bot_context
from document_handlers import _can_manage_documents
from models import SessionLocal, User


def _add_user(user_id, role, approved=1):
    session = SessionLocal()
    try:
        session.add(User(
            telegram_id=user_id,
            name=f"Пользователь {user_id}",
            role=role,
            approved=approved,
        ))
        session.commit()
    finally:
        session.close()


def test_engineer_alias_can_manage_documents():
    _add_user(8101, "engineer_technologist")
    assert _can_manage_documents(8101)


def test_builder_and_director_can_manage_documents():
    _add_user(8102, "builder")
    _add_user(8103, "director")
    assert _can_manage_documents(8102)
    assert _can_manage_documents(8103)


def test_customer_and_unapproved_user_cannot_manage_documents():
    _add_user(8104, "customer")
    _add_user(8105, "builder", approved=0)
    assert not _can_manage_documents(8104)
    assert not _can_manage_documents(8105)
    assert not _can_manage_documents(8999)


def test_configured_admin_can_manage_without_database_record(monkeypatch):
    monkeypatch.setattr(bot_context, "ADMIN_IDS", [8199])
    assert _can_manage_documents(8199)
