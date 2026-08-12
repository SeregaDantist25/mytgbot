# -*- coding: utf-8 -*-
"""Загрузка ремонтной ведомости «Славянская» в PostgreSQL на Railway.

Использование:
    $env:DATABASE_URL="postgresql+psycopg2://user:pass@host:5432/dbname"
    python scripts/load_slavyanskaya_to_railway.py

Скрипт:
1. Парсит исходный Excel-файл ведомости (с разделами).
2. Применяет исключения.
3. Пунктам без раздела назначает «Основные работы».
4. Сохраняет в БД, указанную в DATABASE_URL (PostgreSQL на Railway).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scanner
from models import SessionLocal, Ship, RepairStatement, StatementItem

SHIP_NAME = "Славянская"
SRC = os.path.join("repair_docs", "_processed", "Ремведомость_Славянская осн..xlsx")


def main():
    if not os.getenv("DATABASE_URL"):
        print("❌ DATABASE_URL не установлен. Задайте его перед запуском.")
        sys.exit(1)

    # 1. Парсим исходный файл (с разделами)
    items = scanner.parse_repair_list(SRC)
    print(f"Исходный файл: {len(items)} пунктов")

    # 2. Применяем исключения
    ex = scanner.parse_exclusions(SRC)
    print(f"Исключения: partial={len(ex['partial'])}, full={len(ex['full'])}, extra={len(ex['extra'])}")
    result = scanner.apply_exclusions(items, ex)
    print(f"После исключений: {len(result)} пунктов")

    # 2.1. Пунктам без раздела назначаем «Основные работы»
    for it in result:
        if not it.get("section"):
            it["section"] = "Основные работы"

    # 3. Сохраняем в БД (PostgreSQL на Railway)
    s = SessionLocal()
    try:
        ship = s.query(Ship).filter_by(name=SHIP_NAME).first()
        if not ship:
            print(f"❌ Судно «{SHIP_NAME}» не найдено в БД. Сначала синхронизируйте суда.")
            sys.exit(1)

        # Удаляем старые данные этого судна
        old_stmts = s.query(RepairStatement).filter_by(ship_id=ship.id).all()
        for st in old_stmts:
            s.query(StatementItem).filter_by(statement_id=st.id).delete()
            s.delete(st)
        s.flush()

        # Создаём новый statement
        statement = RepairStatement(ship_id=ship.id, source_excel_file_ref=os.path.basename(SRC))
        s.add(statement)
        s.flush()

        created = 0
        for it in result:
            item = StatementItem(
                statement_id=statement.id,
                item_number=it["item_number"],
                description=it["description"],
                quantity=it.get("quantity"),
                section=it.get("section"),
                status=it.get("status", "active"),
            )
            s.add(item)
            created += 1

        s.commit()
        print(f"✅ Сохранено {created} пунктов (statement_id={statement.id})")
    finally:
        s.close()


if __name__ == "__main__":
    main()
