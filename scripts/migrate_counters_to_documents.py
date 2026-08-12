# -*- coding: utf-8 -*-
"""
Миграция данных из старой БД (data/counters.db, слой db.py) в новую
(data/documents.db, ORM models.py).

Сопоставление таблиц:
  counters.users        -> documents.users        (telegram_id, role)
  counters.ships        -> documents.ships        (name, status) с дедупликацией
  counters.repair_items -> documents.statement_items (через repair_statements)
  counters.documents   -> documents.documents     (item_id, category, file_ref, ...)
  counters.counters     -> documents.counters     (doc_type, value)

Скрипт идемпотентен: повторный запуск не создаёт дубликатов (проверка по
уникальным ключам). Ничего не удаляет из исходной БД.

Запуск:
    python scripts/migrate_counters_to_documents.py
"""

import os
import sqlite3
import sys

SRC = os.path.join("data", "counters.db")
DST = os.path.join("data", "documents.db")

# Маппинг статусов судов: старая схема (in_work/completed/archived) -> новая
SHIP_STATUS_MAP = {
    "in_work": "в работе",
    "completed": "завершено",
    "archived": "архивировано",
}

# Маппинг типов документов: старая схема (doc_type) -> новая категория
DOC_TYPE_MAP = {
    "repair_list": "repair_list",
    "defect_act": "defect_act",
    "work_act": "avr",
    "contract": "contract",
}


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_counters_table(dst):
    """Создаёт таблицу counters в новой БД, если её нет."""
    with dst:
        dst.execute(
            "CREATE TABLE IF NOT EXISTS counters ("
            "doc_type TEXT PRIMARY KEY, value INTEGER)"
        )


def migrate_users(src, dst):
    rows = src.execute("SELECT * FROM users").fetchall()
    inserted = 0
    for r in rows:
        cur = dst.execute(
            "SELECT 1 FROM users WHERE telegram_id = ?", (r["user_id"],)
        )
        if cur.fetchone():
            continue
        dst.execute(
            "INSERT INTO users (telegram_id, role) VALUES (?, ?)",
            (r["user_id"], r["role"]),
        )
        inserted += 1
    return inserted


def migrate_ships(src, dst):
    """Переносит суда с дедупликацией по названию. Возвращает маппинг
    {старый ship_id: новый ship_id}."""
    rows = src.execute("SELECT * FROM ships").fetchall()
    mapping = {}
    inserted = 0
    for r in rows:
        cur = dst.execute("SELECT id FROM ships WHERE name = ?", (r["name"],))
        existing = cur.fetchone()
        if existing:
            mapping[r["ship_id"]] = existing["id"]
            continue
        status = SHIP_STATUS_MAP.get(r["status"], r["status"] or "в работе")
        cur = dst.execute(
            "INSERT INTO ships (name, status) VALUES (?, ?)",
            (r["name"], status),
        )
        mapping[r["ship_id"]] = cur.lastrowid
        inserted += 1
    return mapping, inserted


def migrate_repair_items(src, dst, ship_mapping):
    """Переносит пункты ремонтной ведомости. Для каждого судна создаёт
    RepairStatement и привязывает пункты. Возвращает маппинг
    {старый item_id: новый item_id}."""
    rows = src.execute("SELECT * FROM repair_items").fetchall()
    item_mapping = {}
    statement_cache = {}
    inserted = 0
    for r in rows:
        new_ship_id = ship_mapping.get(r["ship_id"])
        if new_ship_id is None:
            continue
        if new_ship_id not in statement_cache:
            cur = dst.execute(
                "SELECT id FROM repair_statements WHERE ship_id = ?",
                (new_ship_id,),
            )
            stmt = cur.fetchone()
            if stmt:
                statement_cache[new_ship_id] = stmt["id"]
            else:
                cur = dst.execute(
                    "INSERT INTO repair_statements (ship_id, source_excel_file_ref) "
                    "VALUES (?, ?)",
                    (new_ship_id, "migrated_from_counters"),
                )
                statement_cache[new_ship_id] = cur.lastrowid
        statement_id = statement_cache[new_ship_id]

        # Дедупликация по (statement_id, item_number)
        cur = dst.execute(
            "SELECT id FROM statement_items WHERE statement_id = ? AND item_number = ?",
            (statement_id, r["item_number"]),
        )
        existing = cur.fetchone()
        if existing:
            item_mapping[r["item_id"]] = existing["id"]
            continue

        cur = dst.execute(
            "INSERT INTO statement_items "
            "(statement_id, item_number, description, quantity, section, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                statement_id,
                r["item_number"],
                r["description"],
                r["quantity"],
                None,  # section в старой схеме нет
                r["status"] or "active",
            ),
        )
        item_mapping[r["item_id"]] = cur.lastrowid
        inserted += 1
    return item_mapping, inserted


def migrate_documents(src, dst, ship_mapping, item_mapping):
    """Переносит документы. В старой схеме документы привязаны к ship_id и
    item_id; в новой — к item_id (statement_items)."""
    rows = src.execute("SELECT * FROM documents").fetchall()
    inserted = 0
    for r in rows:
        new_item_id = item_mapping.get(r["item_id"])
        if new_item_id is None:
            # Документ без пункта — пропускаем (в новой схеме item_id обязателен)
            continue
        category = DOC_TYPE_MAP.get(r["doc_type"], r["doc_type"] or "other")
        status = "approved" if r["approved"] else "draft"
        cur = dst.execute(
            "SELECT 1 FROM documents WHERE item_id = ? AND file_ref = ?",
            (new_item_id, r["file_path"]),
        )
        if cur.fetchone():
            continue
        dst.execute(
            "INSERT INTO documents "
            "(item_id, category, file_ref, file_type, version, status, uploaded_by, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_item_id,
                category,
                r["file_path"],
                os.path.splitext(r["file_path"])[1] if r["file_path"] else None,
                r["version"] or 1,
                status,
                r["uploaded_by"],
                "folder",
            ),
        )
        inserted += 1
    return inserted


def migrate_counters(src, dst):
    rows = src.execute("SELECT * FROM counters").fetchall()
    inserted = 0
    for r in rows:
        cur = dst.execute(
            "SELECT 1 FROM counters WHERE doc_type = ?", (r["doc_type"],)
        )
        if cur.fetchone():
            continue
        dst.execute(
            "INSERT INTO counters (doc_type, value) VALUES (?, ?)",
            (r["doc_type"], r["value"]),
        )
        inserted += 1
    return inserted


def main():
    if not os.path.exists(SRC):
        print(f"Исходная БД не найдена: {SRC}")
        sys.exit(1)
    if not os.path.exists(DST):
        print(f"Целевая БД не найдена: {DST}")
        sys.exit(1)

    src = connect(SRC)
    dst = connect(DST)
    try:
        ensure_counters_table(dst)
        with dst:
            n_users = migrate_users(src, dst)
            ship_mapping, n_ships = migrate_ships(src, dst)
            item_mapping, n_items = migrate_repair_items(src, dst, ship_mapping)
            n_docs = migrate_documents(src, dst, ship_mapping, item_mapping)
            n_counters = migrate_counters(src, dst)

        print("Миграция завершена:")
        print(f"  users:            +{n_users}")
        print(f"  ships:            +{n_ships}")
        print(f"  statement_items:  +{n_items}")
        print(f"  documents:        +{n_docs}")
        print(f"  counters:         +{n_counters}")
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    main()
