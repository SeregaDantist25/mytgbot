# -*- coding: utf-8 -*-
"""
Обновляет роль пользователя в БД на engineer_technologist.

Использование:
    python scripts/set_engineer_role.py <telegram_id>

Обновляет роль в обеих БД (documents.db — основная, counters.db — legacy),
если пользователь с таким telegram_id существует. Если пользователя нет —
выводит предупреждение и ничего не меняет.
"""

import os
import sqlite3
import sys

DOCUMENTS_DB = os.path.join("data", "documents.db")
COUNTERS_DB = os.path.join("data", "counters.db")

ROLE = "engineer_technologist"


def update_documents_db(telegram_id):
    if not os.path.exists(DOCUMENTS_DB):
        print(f"  documents.db не найден: {DOCUMENTS_DB}")
        return 0
    conn = sqlite3.connect(DOCUMENTS_DB)
    cur = conn.execute("SELECT 1 FROM users WHERE telegram_id = ?", (telegram_id,))
    if not cur.fetchone():
        print(f"  documents.db: пользователь {telegram_id} не найден, пропуск")
        conn.close()
        return 0
    conn.execute("UPDATE users SET role = ? WHERE telegram_id = ?", (ROLE, telegram_id))
    conn.commit()
    conn.close()
    print(f"  documents.db: роль пользователя {telegram_id} обновлена на {ROLE}")
    return 1


def update_counters_db(telegram_id):
    if not os.path.exists(COUNTERS_DB):
        print(f"  counters.db не найден: {COUNTERS_DB}")
        return 0
    conn = sqlite3.connect(COUNTERS_DB)
    cur = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (telegram_id,))
    if not cur.fetchone():
        print(f"  counters.db: пользователь {telegram_id} не найден, пропуск")
        conn.close()
        return 0
    conn.execute("UPDATE users SET role = ? WHERE user_id = ?", (ROLE, telegram_id))
    conn.commit()
    conn.close()
    print(f"  counters.db: роль пользователя {telegram_id} обновлена на {ROLE}")
    return 1


def main():
    if len(sys.argv) < 2:
        print("Использование: python scripts/set_engineer_role.py <telegram_id>")
        sys.exit(1)
    try:
        telegram_id = int(sys.argv[1])
    except ValueError:
        print("telegram_id должен быть числом")
        sys.exit(1)

    print(f"Обновление роли пользователя {telegram_id} на {ROLE}:")
    total = 0
    total += update_documents_db(telegram_id)
    total += update_counters_db(telegram_id)
    if total == 0:
        print("Пользователь не найден ни в одной БД. Роль не изменена.")
    else:
        print("Готово.")


if __name__ == "__main__":
    main()
