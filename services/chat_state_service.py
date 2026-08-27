# -*- coding: utf-8 -*-
"""Потокобезопасное персистентное состояние Telegram-диалогов."""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading


class ChatStateStore:
    """Хранилище небольших состояний чатов в атомарно обновляемом JSON."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._state = self._load()

    def _load(self) -> dict:
        with self._lock:
            if not self.path.exists():
                return {}
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except (OSError, json.JSONDecodeError):
                return {}

    def _write_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(f"{self.path.name}.tmp")
        temp_path.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_path, self.path)

    def get(self, chat_id, key: str):
        with self._lock:
            return self._state.get(str(chat_id), {}).get(key)

    def set(self, chat_id, key: str, value) -> None:
        with self._lock:
            chat_key = str(chat_id)
            if value is None:
                chat_state = self._state.get(chat_key)
                if chat_state:
                    chat_state.pop(key, None)
                    if not chat_state:
                        self._state.pop(chat_key, None)
            else:
                self._state.setdefault(chat_key, {})[key] = value
            self._write_unlocked()


DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
CHAT_STATE_FILE = DATA_DIR / "chat_state.json"
store = ChatStateStore(CHAT_STATE_FILE)


def get_chat_state(chat_id, key: str):
    """Вернуть значение состояния чата или None."""
    return store.get(chat_id, key)


def set_chat_state(chat_id, key: str, value) -> None:
    """Установить или удалить значение состояния чата."""
    store.set(chat_id, key, value)
