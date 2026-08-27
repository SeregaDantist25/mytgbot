# -*- coding: utf-8 -*-
"""Атомарная нумерация создаваемых документов."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3


class DocumentCounterStore:
    """SQLite-хранилище счётчиков с однократной миграцией старого JSON."""

    def __init__(self, db_path: str | Path, legacy_path: str | Path | None = None):
        self.db_path = Path(db_path)
        self.legacy_path = Path(legacy_path) if legacy_path else None
        self._initialize()

    def _connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path, timeout=30)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS counters "
                "(doc_type TEXT PRIMARY KEY, value INTEGER NOT NULL)"
            )
            if not self.legacy_path or not self.legacy_path.exists():
                return
            try:
                old = json.loads(self.legacy_path.read_text(encoding="utf-8"))
                if not isinstance(old, dict):
                    return
                for doc_type, value in old.items():
                    connection.execute(
                        "INSERT OR IGNORE INTO counters (doc_type, value) VALUES (?, ?)",
                        (str(doc_type), int(value)),
                    )
                migrated = self.legacy_path.with_suffix(
                    f"{self.legacy_path.suffix}.migrated"
                )
                self.legacy_path.replace(migrated)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                # Повреждённый legacy-файл не должен блокировать запуск бота.
                return

    def next(self, doc_type: str) -> int:
        """Атомарно увеличить счётчик и вернуть новое значение."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT value FROM counters WHERE doc_type = ?", (doc_type,)
            ).fetchone()
            value = (int(row[0]) + 1) if row else 1
            connection.execute(
                "INSERT INTO counters (doc_type, value) VALUES (?, ?) "
                "ON CONFLICT(doc_type) DO UPDATE SET value = excluded.value",
                (doc_type, value),
            )
            return value

    def set(self, doc_type: str, value: int) -> None:
        """Установить значение счётчика."""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO counters (doc_type, value) VALUES (?, ?) "
                "ON CONFLICT(doc_type) DO UPDATE SET value = excluded.value",
                (doc_type, int(value)),
            )


DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
store = DocumentCounterStore(DATA_DIR / "counters.db", DATA_DIR / "counters.json")


def get_next_number(doc_type: str) -> int:
    return store.next(doc_type)


def get_counter(doc_type: str) -> int:
    """Совместимость: исторически функция также увеличивает счётчик."""
    return get_next_number(doc_type)


def update_counter(doc_type: str, new_number: int) -> None:
    store.set(doc_type, new_number)
