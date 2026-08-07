# -*- coding: utf-8 -*-
"""
Слой данных для системы документооборота по судам.

Хранит пользователей, суда, пункты ремонтной ведомости, документы,
комментарии, заявки на регистрацию и журнал действий — в SQLite.

Использует ту же базу, что и счётчики (data/counters.db), чтобы не плодить
отдельные файлы.
"""

import os
import json
import sqlite3
import threading
from datetime import datetime

DATA_DIR = "data"
DB_PATH = os.path.join(DATA_DIR, "counters.db")

# Роли
ROLE_ENGINEER = "engineer"      # инженер-технолог (абсолютные права)
ROLE_DIRECTOR = "director"      # директор
ROLE_BUILDER = "builder"        # строитель
ROLE_CUSTOMER = "customer"      # заказчик

ROLE_LABELS = {
    ROLE_ENGINEER: "Инженер-технолог",
    ROLE_DIRECTOR: "Директор",
    ROLE_BUILDER: "Строитель",
    ROLE_CUSTOMER: "Заказчик",
}

# Статусы судов
SHIP_IN_WORK = "in_work"
SHIP_COMPLETED = "completed"
SHIP_ARCHIVED = "archived"

# Типы документов
DOC_REPAIR_LIST = "repair_list"   # ремонтная ведомость
DOC_DEFECT_ACT = "defect_act"     # акт дефектации
DOC_WORK_ACT = "work_act"         # акт выполненных работ
DOC_CONTRACT = "contract"         # скан-копия договора

DOC_LABELS = {
    DOC_REPAIR_LIST: "Ремонтная ведомость",
    DOC_DEFECT_ACT: "Акт дефектации",
    DOC_WORK_ACT: "Акт выполненных работ",
    DOC_CONTRACT: "Договор",
}

# Максимум версий на один акт (кроме договора)
MAX_DOC_VERSIONS = 5

_lock = threading.Lock()


def _connect():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Создаёт все таблицы, если их нет."""
    with _lock:
        conn = _connect()
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                phone TEXT,
                approved INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ships (
                ship_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                builder_id INTEGER,
                start_date TEXT,
                end_date TEXT,
                customer TEXT,
                customer_phone TEXT,
                status TEXT NOT NULL DEFAULT 'in_work',
                created_at TEXT NOT NULL,
                FOREIGN KEY (builder_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS repair_items (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ship_id INTEGER NOT NULL,
                item_number TEXT NOT NULL,
                description TEXT,
                FOREIGN KEY (ship_id) REFERENCES ships(ship_id)
            );

            CREATE TABLE IF NOT EXISTS documents (
                doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ship_id INTEGER NOT NULL,
                item_id INTEGER,
                doc_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                uploaded_by INTEGER,
                created_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                approved INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (ship_id) REFERENCES ships(ship_id),
                FOREIGN KEY (item_id) REFERENCES repair_items(item_id),
                FOREIGN KEY (uploaded_by) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS comments (
                comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ship_id INTEGER NOT NULL,
                item_id INTEGER,
                user_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (ship_id) REFERENCES ships(ship_id),
                FOREIGN KEY (item_id) REFERENCES repair_items(item_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS pending_users (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                role_requested TEXT NOT NULL,
                phone TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                ship_id INTEGER,
                doc_id INTEGER,
                details TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
        conn.close()


# ============================================================
#  ПОЛЬЗОВАТЕЛИ
# ============================================================

def get_user(user_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(user_id, name, role, phone=None, approved=0):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO users (user_id, name, role, phone, approved, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, name, role, phone, approved, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def update_user(user_id, **fields):
    if not fields:
        return
    allowed = {"name", "role", "phone", "approved"}
    sets = []
    vals = []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            vals.append(v)
    if not sets:
        return
    vals.append(user_id)
    conn = _connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE user_id = ?", vals)
    conn.commit()
    conn.close()


def get_users():
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_engineer(user):
    return bool(user) and user.get("role") == ROLE_ENGINEER


def is_director(user):
    return bool(user) and user.get("role") == ROLE_DIRECTOR


def is_builder(user):
    return bool(user) and user.get("role") == ROLE_BUILDER


def is_customer(user):
    return bool(user) and user.get("role") == ROLE_CUSTOMER


def can_edit(user, ship):
    """Может ли пользователь редактировать документы по судну."""
    if not user or not user.get("approved"):
        return False
    if is_engineer(user) or is_director(user):
        return True
    if is_builder(user):
        return ship.get("builder_id") == user.get("user_id")
    return False


def can_approve_users(user):
    """Кто может одобрять новых пользователей."""
    return bool(user) and (is_engineer(user) or is_director(user))


# ============================================================
#  ЗАЯВКИ НА РЕГИСТРАЦИЮ
# ============================================================

def add_pending_user(user_id, name, role, phone=None):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO pending_users (user_id, name, role_requested, phone, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, name, role, phone, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def get_pending_users():
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM pending_users ORDER BY created_at")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def remove_pending_user(user_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM pending_users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ============================================================
#  СУДА
# ============================================================

def add_ship(name, builder_id=None, start_date=None, end_date=None,
             customer=None, customer_phone=None, status=SHIP_IN_WORK):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ships (name, builder_id, start_date, end_date, customer, customer_phone, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, builder_id, start_date, end_date, customer, customer_phone, status,
         datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    ship_id = cur.lastrowid
    conn.close()
    return ship_id


def get_ship_by_name(name):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ships WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_ship(ship_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ships WHERE ship_id = ?", (ship_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_ships(status=None):
    conn = _connect()
    cur = conn.cursor()
    if status:
        cur.execute("SELECT * FROM ships WHERE status = ? ORDER BY name", (status,))
    else:
        cur.execute("SELECT * FROM ships ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_ship(ship_id, **fields):
    if not fields:
        return
    allowed = {"builder_id", "start_date", "end_date", "customer", "customer_phone", "status"}
    sets = []
    vals = []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            vals.append(v)
    if not sets:
        return
    vals.append(ship_id)
    conn = _connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE ships SET {', '.join(sets)} WHERE ship_id = ?", vals)
    conn.commit()
    conn.close()


# ============================================================
#  ПУНКТЫ РЕМОНТНОЙ ВЕДОМОСТИ
# ============================================================

def add_repair_item(ship_id, item_number, description=None):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO repair_items (ship_id, item_number, description) VALUES (?, ?, ?)",
        (ship_id, item_number, description),
    )
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return item_id


def get_repair_items(ship_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM repair_items WHERE ship_id = ? ORDER BY item_number", (ship_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_repair_item(item_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM repair_items WHERE item_id = ?", (item_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# ============================================================
#  ДОКУМЕНТЫ
# ============================================================

def add_document(ship_id, doc_type, file_path, uploaded_by, item_id=None, approved=0):
    """Добавляет документ. Для актов (не договор) ограничивает число версий."""
    conn = _connect()
    cur = conn.cursor()
    if doc_type != DOC_CONTRACT:
        cur.execute(
            "SELECT COUNT(*) AS c FROM documents WHERE ship_id = ? AND doc_type = ? AND item_id IS ?",
            (ship_id, doc_type, item_id),
        )
        count = cur.fetchone()["c"]
        if count >= MAX_DOC_VERSIONS:
            conn.close()
            return None, f"Достигнут лимит версий ({MAX_DOC_VERSIONS}) для этого документа."
    cur.execute(
        "INSERT INTO documents (ship_id, item_id, doc_type, file_path, uploaded_by, created_at, version, approved) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ship_id, item_id, doc_type, file_path, uploaded_by,
         datetime.now().isoformat(timespec="seconds"), 1, approved),
    )
    conn.commit()
    doc_id = cur.lastrowid
    conn.close()
    return doc_id, None


def get_documents(ship_id, doc_type=None, item_id=None):
    conn = _connect()
    cur = conn.cursor()
    sql = "SELECT * FROM documents WHERE ship_id = ?"
    params = [ship_id]
    if doc_type:
        sql += " AND doc_type = ?"
        params.append(doc_type)
    if item_id is not None:
        sql += " AND item_id = ?"
        params.append(item_id)
    sql += " ORDER BY created_at DESC"
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_document(doc_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_document(doc_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
    conn.commit()
    conn.close()


def approve_document(doc_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE documents SET approved = 1 WHERE doc_id = ?", (doc_id,))
    conn.commit()
    conn.close()


# ============================================================
#  КОММЕНТАРИИ
# ============================================================

def add_comment(ship_id, user_id, text, item_id=None):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO comments (ship_id, item_id, user_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
        (ship_id, item_id, user_id, text, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def get_comments(ship_id, item_id=None):
    conn = _connect()
    cur = conn.cursor()
    if item_id is not None:
        cur.execute(
            "SELECT * FROM comments WHERE ship_id = ? AND item_id = ? ORDER BY created_at",
            (ship_id, item_id),
        )
    else:
        cur.execute(
            "SELECT * FROM comments WHERE ship_id = ? ORDER BY created_at",
            (ship_id,),
        )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
#  ЖУРНАЛ ДЕЙСТВИЙ
# ============================================================

def log_action(user_id, action, ship_id=None, doc_id=None, details=None):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO audit_log (user_id, action, ship_id, doc_id, details, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, action, ship_id, doc_id, details,
         datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def get_audit_log(ship_id=None, limit=100):
    conn = _connect()
    cur = conn.cursor()
    if ship_id is not None:
        cur.execute(
            "SELECT * FROM audit_log WHERE ship_id = ? ORDER BY created_at DESC LIMIT ?",
            (ship_id, limit),
        )
    else:
        cur.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
#  МИГРАЦИЯ СУЩЕСТВУЮЩИХ ДАННЫХ
# ============================================================

def migrate_ships_from_json():
    """Переносит суда из data/ships.json в таблицу ships (только 'Славянская')."""
    ships_file = os.path.join(DATA_DIR, "ships.json")
    if not os.path.exists(ships_file):
        return
    try:
        with open(ships_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    # По решению владельца — мигрируем только «Славянская»
    target = data.get("славянская") or data.get("Славянская")
    if target and not get_ship_by_name(target):
        add_ship(target)
        print(f"Судно «{target}» перенесено в базу данных.")


# Инициализация при импорте
init_db()
migrate_ships_from_json()