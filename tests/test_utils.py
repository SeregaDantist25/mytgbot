# -*- coding: utf-8 -*-
"""
Тесты для utils/constants.py и utils/formatters.py.
"""

from utils.constants import (
    UserRole,
    DocumentStatus,
    DocumentCategory,
    MAX_DRAFTS_PER_ITEM,
    MAX_FILE_SIZE,
    ALLOWED_EXTENSIONS,
    NAVIGATION_BUTTONS,
)


class TestUserRole:
    """Тесты Enum UserRole."""

    def test_values(self):
        assert UserRole.ENGINEER.value == "engineer_technologist"
        assert UserRole.DIRECTOR.value == "director"
        assert UserRole.BUILDER.value == "builder"
        assert UserRole.CUSTOMER.value == "customer"

    def test_str_enum(self):
        # str-Enum: значение сравнивается со строкой
        assert UserRole.CUSTOMER == "customer"


class TestDocumentStatus:
    """Тесты Enum DocumentStatus."""

    def test_values(self):
        assert DocumentStatus.DRAFT.value == "draft"
        assert DocumentStatus.APPROVED.value == "approved"
        assert DocumentStatus.ARCHIVED.value == "archived"


class TestDocumentCategory:
    """Тесты Enum DocumentCategory."""

    def test_values(self):
        assert DocumentCategory.DEFECT_ACT_DRAFT.value == "defect_act_draft"
        assert DocumentCategory.DEFECT_ACT_APPROVED.value == "defect_act_approved"
        assert DocumentCategory.AVR.value == "avr"
        assert DocumentCategory.OTHER.value == "other"


class TestConstants:
    """Тесты констант."""

    def test_max_drafts(self):
        assert MAX_DRAFTS_PER_ITEM == 4

    def test_max_file_size(self):
        assert MAX_FILE_SIZE == 50 * 1024 * 1024

    def test_allowed_extensions(self):
        assert ".pdf" in ALLOWED_EXTENSIONS
        assert ".docx" in ALLOWED_EXTENSIONS
        assert ".xlsx" in ALLOWED_EXTENSIONS

    def test_navigation_buttons(self):
        assert "🚢 Суда" in NAVIGATION_BUTTONS
        assert len(NAVIGATION_BUTTONS) == 3


class TestFormatters:
    """Тесты форматтеров."""

    def test_format_document_info(self):
        from utils.formatters import format_document_info

        class FakeUploader:
            name = "Иванов"

        class FakeDoc:
            status = "draft"
            category = "defect_act_draft"
            uploaded_at = __import__("datetime").datetime(2026, 8, 11, 10, 30)
            uploader = FakeUploader()

        text = format_document_info(FakeDoc())
        assert "Черновик" in text
        assert "defect_act_draft" in text
        assert "11.08.2026 10:30" in text
        assert "Иванов" in text

    def test_format_item_details(self):
        from utils.formatters import format_item_details

        class FakeItem:
            item_number = "1.1"
            description = "Корпус насоса"
            quantity = "2"
            section = "Корпус"

        text = format_item_details(FakeItem())
        assert "1.1" in text
        assert "Корпус насоса" in text
        assert "2" in text
        assert "Корпус" in text