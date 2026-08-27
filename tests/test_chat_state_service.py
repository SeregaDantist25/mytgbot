# -*- coding: utf-8 -*-

import json

from services.chat_state_service import ChatStateStore


def test_state_roundtrip_and_reload(tmp_path):
    path = tmp_path / "chat_state.json"
    state = ChatStateStore(path)
    state.set(1001, "step", "role")
    state.set(1001, "name", "Иванов")

    reloaded = ChatStateStore(path)
    assert reloaded.get(1001, "step") == "role"
    assert reloaded.get(1001, "name") == "Иванов"


def test_removing_last_key_removes_empty_chat_entry(tmp_path):
    path = tmp_path / "chat_state.json"
    state = ChatStateStore(path)
    state.set(1002, "step", "name")
    state.set(1002, "step", None)

    assert state.get(1002, "step") is None
    assert json.loads(path.read_text(encoding="utf-8")) == {}


def test_corrupt_or_non_object_json_starts_with_empty_state(tmp_path):
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{broken", encoding="utf-8")
    assert ChatStateStore(corrupt).get(1, "key") is None

    array_file = tmp_path / "array.json"
    array_file.write_text("[]", encoding="utf-8")
    assert ChatStateStore(array_file).get(1, "key") is None


def test_legacy_extra_imports_point_to_new_service():
    from services import extra
    from services import chat_state_service

    assert extra.get_chat_state is chat_state_service.get_chat_state
    assert extra.set_chat_state is chat_state_service.set_chat_state
