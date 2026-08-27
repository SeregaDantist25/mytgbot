# -*- coding: utf-8 -*-

import json

from services.document_counter_service import DocumentCounterStore


def test_counter_increments_independently(tmp_path):
    store = DocumentCounterStore(tmp_path / "counters.db")

    assert store.next("da") == 1
    assert store.next("da") == 2
    assert store.next("avr") == 1


def test_counter_value_survives_reload_and_can_be_set(tmp_path):
    path = tmp_path / "counters.db"
    store = DocumentCounterStore(path)
    store.set("da", 40)

    assert DocumentCounterStore(path).next("da") == 41


def test_legacy_json_is_migrated_once(tmp_path):
    legacy = tmp_path / "counters.json"
    legacy.write_text(json.dumps({"da": 7}), encoding="utf-8")

    store = DocumentCounterStore(tmp_path / "counters.db", legacy)

    assert store.next("da") == 8
    assert not legacy.exists()
    assert (tmp_path / "counters.json.migrated").exists()


def test_legacy_extra_imports_point_to_counter_service():
    from services import document_counter_service, extra

    assert extra.get_next_number is document_counter_service.get_next_number
    assert extra.get_counter is document_counter_service.get_counter
    assert extra.update_counter is document_counter_service.update_counter
