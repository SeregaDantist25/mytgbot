# -*- coding: utf-8 -*-
"""
Сервис парсинга Excel-файлов ремонтных ведомостей.

Обёртка над scanner.py. scanner импортируется лениво (внутри функций),
т.к. требует openpyxl, который может отсутствовать на сервере при старте.
"""

from typing import List, Optional


def parse_repair_list(filepath: str) -> List[dict]:
    """Парсит Excel-файл ремонтной ведомости.

    Args:
        filepath: Путь к Excel-файлу.

    Returns:
        Список пунктов ремонтной ведомости (список словарей).
    """
    import scanner
    return scanner.parse_repair_list(filepath)


def save_repair_items_to_db(ship_id: int, items: List[dict]):
    """Сохраняет пункты ремонтной ведомости в БД.

    Args:
        ship_id: ID судна.
        items: Список пунктов ремонтной ведомости.

    Returns:
        Результат сохранения (зависит от реализации document_manager).
    """
    import document_manager as dm
    return dm.save_repair_items_to_db(ship_id, items)


def can_upload_repair_list(user_id: int) -> bool:
    """Проверяет, может ли пользователь загружать ремонтную ведомость.

    Args:
        user_id: Telegram ID пользователя.

    Returns:
        True, если пользователь может загружать ведомость.
    """
    import document_manager as dm
    role = dm.get_user_role(user_id)
    return dm.can_upload_repair_list(role)
