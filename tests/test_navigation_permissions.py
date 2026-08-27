# -*- coding: utf-8 -*-

import bot_context
from bot_handlers_new import (
    _approved_role,
    _can_edit_repair_list,
    _can_upload_repair_list,
    _can_view_repair_list,
)
from models import SessionLocal, User


def _user(user_id, role, approved):
    session = SessionLocal()
    try:
        session.add(User(
            telegram_id=user_id,
            name="Пользователь",
            role=role,
            approved=approved,
        ))
        session.commit()
    finally:
        session.close()


def test_unregistered_and_unapproved_users_cannot_view_repair_list():
    _user(9301, "builder", approved=0)
    assert _approved_role(9301) is None
    assert not _can_view_repair_list(9301)
    assert not _can_view_repair_list(9399)
    assert not _can_upload_repair_list(9301)


def test_approved_roles_have_expected_repair_list_permissions():
    _user(9302, "customer", approved=1)
    _user(9303, "builder", approved=1)
    _user(9304, "engineer_technologist", approved=1)

    assert _can_view_repair_list(9302)
    assert not _can_upload_repair_list(9302)
    assert not _can_edit_repair_list(9302)

    assert _can_upload_repair_list(9303)
    assert _can_edit_repair_list(9303)
    assert _can_upload_repair_list(9304)
    assert _can_edit_repair_list(9304)


def test_configured_admin_has_access_without_user_record(monkeypatch):
    monkeypatch.setattr(bot_context, "ADMIN_IDS", [9305])
    assert _can_view_repair_list(9305)
    assert _can_upload_repair_list(9305)
    assert _can_edit_repair_list(9305)
