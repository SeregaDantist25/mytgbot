# -*- coding: utf-8 -*-
"""Сохранение загруженных пунктов ремонтной ведомости."""

from models import SessionLocal, RepairStatement, StatementItem


def save_repair_items_to_db(ship_id: int, items: list) -> tuple[int, int, int]:
    """Добавить только новые пункты и вернуть ``(добавлено, пропущено, id)``."""
    session = SessionLocal()
    try:
        statement = (
            session.query(RepairStatement)
            .filter_by(ship_id=ship_id)
            .order_by(RepairStatement.id.desc())
            .first()
        )
        if statement is None:
            statement = RepairStatement(
                ship_id=ship_id,
                source_excel_file_ref="uploaded",
            )
            session.add(statement)
            session.flush()

        existing_keys = {
            (row.item_number, row.section)
            for row in session.query(StatementItem)
            .filter_by(statement_id=statement.id)
            .all()
        }
        inserted = 0
        skipped = 0
        for item in items:
            key = (item.get("item_number"), item.get("section"))
            if key in existing_keys:
                skipped += 1
                continue
            session.add(
                StatementItem(
                    statement_id=statement.id,
                    item_number=item.get("item_number"),
                    description=item.get("description"),
                    quantity=item.get("quantity"),
                    section=item.get("section"),
                    status="active",
                )
            )
            existing_keys.add(key)
            inserted += 1

        session.commit()
        return inserted, skipped, statement.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
