# -*- coding: utf-8 -*-

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_document_navigation_has_no_repair_list_duplicates():
    source = (ROOT / "navigation.py").read_text(encoding="utf-8")
    assert "def get_sections_for_ship" not in source
    assert "def get_items_for_section" not in source
    assert "def build_sections_keyboard" not in source
    assert "def build_items_keyboard" not in source


def test_bot_registers_handlers_only_through_registry():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert "from handlers.registry import register_all_handlers" in source
    assert "register_message_handlers(bot)" not in source
    assert "register_callback_handlers(bot)" not in source
    assert "register_document_handlers(bot)" not in source
