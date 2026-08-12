# -*- coding: utf-8 -*-
"""
Импорт готовых актов дефектации из папки acts/.

Структура папки:
    acts/<Судно>/<номер пункта>_<что угодно>.docx|xlsx|pdf

Бот сканирует папку, извлекает номер пункта из имени файла (до первого
разделителя _ - пробел), находит пункт ремонтной ведомости судна по
item_number и сохраняет файл как документ категории defect_act.

Обработанные файлы перемещаются в acts/_processed/.
"""

import os
import re
import shutil
import time

from models import SessionLocal, Ship, RepairStatement, StatementItem
from file_storage import storage

ACTS_DIR = os.getenv("ACTS_DIR", "acts")
PROCESSED_DIR = os.path.join(ACTS_DIR, "_processed")
ALLOWED_EXT = (".docx", ".xlsx", ".pdf")


def _norm_item_number(num):
    """Нормализует номер пункта: убирает завершающую точку и пробелы."""
    return str(num).strip().rstrip(".")


def _extract_item_number(filename):
    """
    Извлекает номер пункта из имени файла.

    Номер — это часть имени до первого разделителя (_ - пробел).
    Примеры:
        "3.12_Акт.docx"      -> "3.12"
        "3.28.1 акт.pdf"     -> "3.28.1"
        "Доп-1_акт.xlsx"     -> "Доп-1"
    Возвращает нормализованный номер или None.
    """
    base = os.path.splitext(os.path.basename(filename))[0].strip()
    # Отделяем номер до первого разделителя
    num = re.split(r"[_\-\s]+", base, maxsplit=1)[0].strip()
    num = _norm_item_number(num)
    if not num:
        return None
    return num


def _find_item(session, ship_id, item_number):
    """Находит пункт ведомости судна по номеру. Возвращает StatementItem или None."""
    statement = session.query(RepairStatement).filter_by(ship_id=ship_id).first()
    if not statement:
        return None
    return (
        session.query(StatementItem)
        .filter_by(statement_id=statement.id, item_number=item_number)
        .first()
    )


def _move_to_processed(src):
    """Перемещает обработанный файл в acts/_processed."""
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)
    dst = os.path.join(PROCESSED_DIR, os.path.basename(src))
    if os.path.exists(dst):
        base, ext = os.path.splitext(dst)
        dst = f"{base}_{int(time.time())}{ext}"
    shutil.move(src, dst)
    return dst


def import_acts():
    """
    Сканирует папку acts/ и импортирует готовые акты дефектации.

    Возвращает список сообщений о результатах.
    """
    if not os.path.exists(ACTS_DIR):
        return ["Папка acts/ не найдена."]

    messages = []
    session = SessionLocal()
    try:
        # Перебираем подпапки (по одному судну)
        for ship_dir_name in sorted(os.listdir(ACTS_DIR)):
            ship_dir = os.path.join(ACTS_DIR, ship_dir_name)
            if not os.path.isdir(ship_dir):
                continue
            if ship_dir_name.startswith("_"):
                continue

            ship = session.query(Ship).filter_by(name=ship_dir_name).first()
            if not ship:
                messages.append(f"⚠️ Судно «{ship_dir_name}» не найдено в БД.")
                continue

            for filename in sorted(os.listdir(ship_dir)):
                path = os.path.join(ship_dir, filename)
                if not os.path.isfile(path):
                    continue
                if not filename.lower().endswith(ALLOWED_EXT):
                    messages.append(f"⚠️ Неподдерживаемый формат: {filename}")
                    continue

                item_number = _extract_item_number(filename)
                if not item_number:
                    messages.append(f"⚠️ Не удалось определить номер пункта из имени: {filename}")
                    continue

                item = _find_item(session, ship.id, item_number)
                if not item:
                    messages.append(
                        f"❌ Пункт {item_number} не найден в ведомости «{ship_dir_name}»: {filename}"
                    )
                    continue

                # Читаем файл и сохраняем как документ
                try:
                    with open(path, "rb") as f:
                        content = f.read()
                except Exception as e:
                    messages.append(f"❌ Ошибка чтения {filename}: {e}")
                    continue

                result = storage.save_document(
                    file_name=filename,
                    file_content=content,
                    item_id=item.id,
                    category="defect_act",
                    user_id=None,
                    source="folder",
                )

                if result["success"]:
                    _move_to_processed(path)
                    messages.append(
                        f"✅ «{ship_dir_name}» пункт {item_number}: {filename} → документ #{result['document_id']}"
                    )
                else:
                    messages.append(f"❌ {filename}: {result['message']}")
    finally:
        session.close()

    if not messages:
        messages.append("Новых актов для импорта не найдено.")
    return messages
