# -*- coding: utf-8 -*-
"""
Тесты для services/document_service.py (версионирование документов).
"""

import os
import tempfile

import pytest

from models import SessionLocal, User, Ship, RepairStatement, StatementItem
from services.document_service import (
    create_document,
    get_document,
    get_documents,
    approve_document,
    archive_document,
    delete_document,
    replace_document,
    count_drafts_for_item,
    get_oldest_draft,
)


@pytest.fixture()
def item():
    """Создаёт судно, ведомость и пункт для тестов."""
    session = SessionLocal()
    try:
        ship = Ship(name="Тестовое судно", status="в работе")
        session.add(ship)
        session.flush()
        stmt = RepairStatement(ship_id=ship.id, source_excel_file_ref="test")
        session.add(stmt)
        session.flush()
        item = StatementItem(
            statement_id=stmt.id,
            item_number="1.1",
            description="Корпус насоса",
            quantity="1",
            section="Корпус",
            status="active",
        )
        session.add(item)
        session.commit()
        return item.id
    finally:
        session.close()


class TestDocumentService:
    """Тесты сервиса документов."""

    def test_create_document(self, item):
        doc = create_document(item, "defect_act_draft", b"file-content", 1001, ".pdf")
        assert doc.id is not None
        assert doc.status == "draft"
        assert doc.version == 1
        assert doc.category == "defect_act_draft"

    def test_get_document(self, item):
        doc = create_document(item, "defect_act_draft", b"data", 1001)
        fetched = get_document(doc.id)
        assert fetched is not None
        assert fetched.id == doc.id

    def test_get_documents_by_status(self, item):
        create_document(item, "defect_act_draft", b"d1", 1001)
        create_document(item, "defect_act_draft", b"d2", 1001)
        docs = get_documents(item, "defect_act_draft", status="draft")
        assert len(docs) == 2

    def test_approve_document(self, item):
        doc = create_document(item, "defect_act_draft", b"data", 1001)
        ok, msg = approve_document(doc.id, 1001)
        assert ok is True
        assert get_document(doc.id).status == "approved"

    def test_approve_non_draft(self, item):
        doc = create_document(item, "defect_act_draft", b"data", 1001)
        approve_document(doc.id, 1001)
        ok, msg = approve_document(doc.id, 1001)
        assert ok is False

    def test_archive_document_admin(self, item):
        doc = create_document(item, "defect_act_draft", b"data", 1001)
        approve_document(doc.id, 1001)
        ok, msg = archive_document(doc.id, 1001, admin_ids=[1001])
        assert ok is True
        assert get_document(doc.id).status == "archived"

    def test_archive_document_non_admin(self, item):
        doc = create_document(item, "defect_act_draft", b"data", 1001)
        approve_document(doc.id, 1001)
        ok, msg = archive_document(doc.id, 1001, admin_ids=[999])
        assert ok is False

    def test_delete_draft_anyone(self, item):
        doc = create_document(item, "defect_act_draft", b"data", 1001)
        ok, msg = delete_document(doc.id, 1001, admin_ids=[])
        assert ok is True
        assert get_document(doc.id) is None

    def test_delete_approved_only_admin(self, item):
        doc = create_document(item, "defect_act_draft", b"data", 1001)
        approve_document(doc.id, 1001)
        ok, msg = delete_document(doc.id, 1001, admin_ids=[])
        assert ok is False
        ok, msg = delete_document(doc.id, 1001, admin_ids=[1001])
        assert ok is True

    def test_replace_document(self, item):
        doc = create_document(item, "defect_act_draft", b"old", 1001, ".pdf")
        ok, msg = replace_document(doc.id, b"new", 1001, ".pdf")
        assert ok is True
        # file_ref детерминирован (путь одинаковый), проверяем содержимое файла
        from file_storage import storage
        updated = get_document(doc.id)
        assert storage.get_file(updated.file_ref) == b"new"

    def test_replace_approved_fails(self, item):
        doc = create_document(item, "defect_act_draft", b"old", 1001)
        approve_document(doc.id, 1001)
        ok, msg = replace_document(doc.id, b"new", 1001)
        assert ok is False

    def test_count_drafts(self, item):
        create_document(item, "defect_act_draft", b"d1", 1001)
        create_document(item, "defect_act_draft", b"d2", 1001)
        assert count_drafts_for_item(item, "defect_act_draft") == 2

    def test_get_oldest_draft(self, item):
        create_document(item, "defect_act_draft", b"d1", 1001)
        create_document(item, "defect_act_draft", b"d2", 1001)
        oldest = get_oldest_draft(item, "defect_act_draft")
        assert oldest is not None
        assert oldest.status == "draft"