# -*- coding: utf-8 -*-
"""Профили оборудования для универсального акта дефектации."""

from __future__ import annotations

import re
from typing import Iterable


PROFILE_KEYWORDS = {
    "pipeline": ("трубопровод", "труба", "дюрит", "штуцер", "отвод"),
    "heat_exchanger": ("теплообмен", "холодильник", "конденсатор", "радиатор"),
    "hydraulic": ("гидро", "рулевая машина", "цилиндр", "шток", "золотник"),
    "electrical": ("генератор", "электро", "изоляц", "возбуждени", "кабель"),
    "deck_machinery": ("брашпиль", "шпиль", "лебед", "редуктор", "кран-бал"),
    "ventilation": ("вентиляц", "воздуховод", "компенсатор", "брезентов"),
}

PROFILE_LABELS = {
    "pipeline": "Трубопровод",
    "heat_exchanger": "Теплообменный аппарат",
    "hydraulic": "Гидравлическое оборудование",
    "electrical": "Электрооборудование",
    "deck_machinery": "Палубный механизм / редуктор",
    "ventilation": "Вентиляция",
    "general": "Механизм / устройство",
}

PROFILE_QUESTIONS = {
    "pipeline": "Укажите диаметр, толщину стенки, материал, длину участка, количество отводов и соединений.",
    "heat_exchanger": "Укажите тип и площадь аппарата, состояние трубок/решёток и результаты опрессовки, если она проводилась.",
    "hydraulic": "Укажите диаметры штока и гильзы, фактические зазоры, давление, места течи и состояние уплотнений.",
    "electrical": "Укажите результаты измерения сопротивления изоляции, состояние обмоток, контактов, блоков управления и защиты.",
    "deck_machinery": "Укажите состояние корпуса, валов, зубьев, подшипников, муфт, тормоза и измеренные зазоры.",
    "ventilation": "Укажите размеры, материал, толщину листа, состояние заслонок, уплотнений, крепежа и приводов.",
    "general": "Укажите тип, марку, размеры, измеренные зазоры и другие фактические параметры.",
}


def detect_defect_profile(equipment: str) -> str:
    text = (equipment or "").lower()
    for profile, keywords in PROFILE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return profile
    return "general"


def get_profile_question(profile: str) -> str:
    return PROFILE_QUESTIONS.get(profile, PROFILE_QUESTIONS["general"])


def _repair_for_defect(defect: str, profile: str) -> str:
    text = defect.lower()
    rules = (
        (("трещин", "прогар", "сквозн"), "Дефектный участок удалить; восстановить или заменить; выполнить контроль качества."),
        (("корроз", "раковин"), "Очистить, определить остаточную толщину; восстановить или заменить по результатам контроля."),
        (("течь", "подтек"), "Устранить негерметичность; заменить уплотнения и крепёж; выполнить испытание."),
        (("износ", "выработ", "овальн"), "Выполнить обмер; восстановить до допустимого размера либо заменить."),
        (("люфт", "зазор", "биени"), "Выполнить контрольные обмеры; отрегулировать, восстановить или заменить сопряжённые детали."),
        (("изоляц", "обмот"), "Очистить и просушить; устранить повреждение; выполнить контрольные электрические измерения."),
    )
    for keywords, work in rules:
        if any(keyword in text for keyword in keywords):
            return work
    if profile == "pipeline":
        return "Дефектный участок демонтировать и заменить; соединения собрать; систему испытать на герметичность."
    if profile == "heat_exchanger":
        return "Разобрать, очистить и дефектовать; устранить дефекты; собрать и испытать давлением."
    if profile == "electrical":
        return "Провести диагностику, устранить неисправность и выполнить контрольные электрические измерения."
    return "Разобрать и дефектовать; деталь восстановить либо заменить; собрать и испытать."


def build_defect_rows(
    equipment: str,
    defects: Iterable[str],
    work_volume: str,
    profile: str | None = None,
    quantity: str | None = None,
) -> list[dict[str, str]]:
    """Преобразует данные старого диалога в строки универсального акта."""
    profile = profile or detect_defect_profile(equipment)
    quantity_match = re.search(r"([\d.,]+)\s*([^\d\s]+)?", quantity or "")
    item_quantity = quantity_match.group(1) if quantity_match else "1"
    item_unit = quantity_match.group(2) if quantity_match and quantity_match.group(2) else "шт."
    clean_defects = [str(value).strip() for value in defects if str(value).strip()]
    if not clean_defects:
        clean_defects = ["Техническое состояние требует уточнения при разборке"]

    if profile in {"pipeline", "ventilation"}:
        return [
            {
                "num": str(index),
                "defect": defect,
                "work": _repair_for_defect(defect, profile),
                "unit": item_unit,
                "qty": item_quantity,
                "note": "",
            }
            for index, defect in enumerate(clean_defects, 1)
        ]

    rows = [{
        "num": "1",
        "defect": equipment,
        "work": work_volume,
        "unit": "компл.",
        "qty": item_quantity,
        "note": "",
    }]
    rows.extend(
        {
            "num": f"1.{index}",
            "defect": defect,
            "work": _repair_for_defect(defect, profile),
            "unit": "шт.",
            "qty": "1",
            "note": "",
        }
        for index, defect in enumerate(clean_defects, 1)
    )
    return rows
