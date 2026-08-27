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


def test_root_handler_modules_are_compatibility_shims():
    expected_targets = {
        "document_handlers.py": "handlers.document_handlers",
        "category_handlers.py": "handlers.category_handlers",
        "bot_handlers_new.py": "handlers.repair_handlers",
    }
    for file_name, target in expected_targets.items():
        source = (ROOT / file_name).read_text(encoding="utf-8")
        assert target in source
        assert len(source.splitlines()) < 30


def test_registry_uses_package_handlers_not_root_shims():
    source = (ROOT / "handlers" / "registry.py").read_text(encoding="utf-8")
    assert "from handlers.category_handlers import" in source
    assert "from handlers import repair_handlers" in source
    assert "from category_handlers import" not in source
    assert "import bot_handlers_new" not in source


def test_obsolete_patch_and_empty_callback_modules_are_removed():
    obsolete = [
        "handle_message_patch.py",
        "patch_bot.py",
        "handlers/callback_handlers.py",
        "Новый текстовый документ.txt",
    ]
    assert all(not (ROOT / relative_path).exists() for relative_path in obsolete)


def test_message_handlers_use_dedicated_chat_state_service():
    source = (ROOT / "handlers" / "message_handlers.py").read_text(encoding="utf-8")
    assert "from services.chat_state_service import" in source
    extra_import = source.split("from services.extra import (", 1)[1].split(")", 1)[0]
    assert "get_chat_state" not in extra_import
    assert "set_chat_state" not in extra_import


def test_document_builder_uses_dedicated_counter_service():
    source = (ROOT / "services" / "document_builder.py").read_text(encoding="utf-8")
    assert "from services.document_counter_service import get_next_number" in source
