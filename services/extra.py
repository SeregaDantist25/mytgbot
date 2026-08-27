# -*- coding: utf-8 -*-
"""
Совместимый фасад и оставшаяся инженерная обработка текста.

Новые модули импортируют специализированные сервисы напрямую. Переэкспорты
здесь временно сохраняют работу старых интеграций до завершения миграции.
"""

import re
import logging

from services.document_service import (
    approve_document as handle_document_approve,
    archive_document as handle_document_archive,
    delete_document as handle_document_delete,
)
from services.repair_statement_service import save_repair_items_to_db
from services.user_service import can_upload_repair_list, get_user_role
from services.chat_state_service import get_chat_state, set_chat_state
from services.document_counter_service import (
    get_counter,
    get_next_number,
    update_counter,
)
from services.catalog_service import (
    CHECKLISTS_FILE,
    COMPANIES_FILE,
    EMPLOYEES_FILE,
    SHIPS_FILE,
    add_company,
    add_ship,
    find_employee_role,
    load_checklists,
    load_companies,
    load_employees,
    load_ships,
)
from services.template_service import load_template, replace_placeholders
from services.pump_knowledge_service import PumpDatabase, pump_db

logger = logging.getLogger(__name__)

# ============================================================
#  ОПРЕДЕЛЕНИЕ ТИПА ОБОРУДОВАНИЯ (ЛОКАЛЬНОЕ)
# ============================================================

def detect_equipment_type(text: str) -> str | None:
    """Определяет тип оборудования локально (без AI)."""
    text_lower = text.lower()
    if any(word in text_lower for word in ["двигател", "дизель", "мотор", "гд"]):
        return "engine"
    elif any(word in text_lower for word in ["компрессор", "компрес"]):
        return "compressor"
    elif any(word in text_lower for word in ["насос", "помп"]):
        return "pump"
    else:
        return None


def ask_for_clarification(equipment: str) -> str:
    """Формирует вопрос для уточнения типа оборудования."""
    return (
        f"🔍 Я нашёл упоминание '{equipment}'. Уточните, это:\n"
        "1️⃣ Насос\n2️⃣ Двигатель\n3️⃣ Другое оборудование\n\n"
        "Просто напишите номер или название."
    )


# ============================================================
#  РАСШИРЕННЫЙ АНАЛИЗ ЗАПРОСОВ
# ============================================================

def detect_ship(text: str) -> str | None:
    """Определяет судно по тексту."""
    text_lower = text.lower()
    ships = load_ships()
    for key, name in ships.items():
        if key in text_lower:
            return name
    return None


def detect_pump_type(text: str) -> str | None:
    """Определяет тип насоса по тексту."""
    text_lower = text.lower()

    piston_keywords = ["поршн", "плунж", "прямодейств", "паровой"]
    for kw in piston_keywords:
        if kw in text_lower:
            return "piston"

    gear_keywords = ["шестерен", "шестерён", "шестерн", "ротан", "rotan", "зубчат", "маслян"]
    for kw in gear_keywords:
        if kw in text_lower:
            return "gear"

    centrifugal_keywords = ["центробеж", "центр", "крыльчатк"]
    for kw in centrifugal_keywords:
        if kw in text_lower:
            return "centrifugal"

    if "насос" in text_lower:
        if any(kw in text_lower for kw in ["маслян", "ротан"]):
            return "gear"
        if any(kw in text_lower for kw in ["крыльчатк", "центр"]):
            return "centrifugal"
        if any(kw in text_lower for kw in ["поршн", "плунж"]):
            return "piston"

    return None


def extract_equipment(text: str) -> str | None:
    """Извлекает упоминание оборудования из текста."""
    text_lower = text.lower()
    equipment_keywords = [
        "насос", "двигатель", "компрессор", "вентилятор",
        "генератор", "кран", "лебедка", "редуктор", "гидромотор",
        "брашпиль", "котёл", "водонагреватель", "дизель", "мотор",
    ]
    for kw in equipment_keywords:
        if kw in text_lower:
            pattern = r'(\w+\s+){0,2}' + kw + r'(\s+\w+){0,2}'
            match = re.search(pattern, text)
            if match:
                return match.group(0).strip()
    return None


def extract_clearances_from_text(text: str) -> list:
    """Извлекает зазоры из текста."""
    text_lower = text.lower()
    clearances = []

    clearance_map = {
        "радиальн": "radial",
        "осев": "axial",
        "подшипник": "bearing",
        "сальник": "seal",
        "цилиндр": "cylinder_piston",
        "канавк": "ring_groove",
        "замк": "ring_gap",
        "крейцкопф": "crosshead",
        "коренн": "main_bearing",
        "шатун": "connecting_rod",
        "грундбукс": "seal_wear",
    }

    patterns = [
        r'зазор\s+(\w+)\s+(\d+\.?\d*)',
        r'(\w+)\s+зазор\s+(\d+\.?\d*)',
        r'зазор\s+(\d+\.?\d*)\s+(\w+)',
        r'зазор\s+(\d+\.?\d*)',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            if isinstance(match, tuple):
                parts = list(match)
                value = None
                clearance_type = None
                for part in parts:
                    if re.match(r'^\d+\.?\d*$', part):
                        value = float(part)
                    else:
                        # Стем-маппинг: part может быть полным словом
                        # (например, "радиальный"), а в clearance_map — корень
                        # ("радиальн"). Сравниваем по префиксу.
                        for stem, mapped in clearance_map.items():
                            if part.startswith(stem):
                                clearance_type = mapped
                                break
                        else:
                            if part in ["radial", "axial", "bearing", "seal"]:
                                clearance_type = part
                if value is not None:
                    clearances.append({
                        "type": clearance_type or "unknown",
                        "value": value,
                        "raw": match,
                    })
            else:
                if re.match(r'^\d+\.?\d*$', match):
                    for ct, mapped in clearance_map.items():
                        if ct in text_lower:
                            clearances.append({
                                "type": mapped,
                                "value": float(match),
                                "raw": match,
                            })
                            break

    return clearances


def extract_defects(text: str) -> list:
    """Извлекает дефекты из текста."""
    text_lower = text.lower()
    defects = []

    if "дефекты" in text_lower:
        defect_part = re.split(r'дефекты[:;]', text_lower, flags=re.IGNORECASE)
        if len(defect_part) > 1:
            parts = defect_part[1].strip().split(',')
            parts = [p.strip() for p in parts if p.strip()]
            for p in parts:
                if p:
                    defects.append(p)
            if defects:
                return defects

    defect_keywords = [
        "поврежден", "повреждена", "повреждено", "повреждены",
        "сгнил", "сгнила", "сгнило", "сгнили",
        "высох", "высохла", "высохло", "высохли",
        "треснул", "треснула", "треснуло", "треснули",
        "сломан", "сломана", "сломано", "сломаны",
        "разбит", "разбита", "разбито", "разбиты",
        "износ", "течь", "коррози", "трещин", "разруш", "выкрашиван",
        "задир", "деформац", "ржав", "люфт", "биение", "стук", "вибрац",
        "зазор", "перегрев", "заедание", "отказ", "неисправн", "поломк",
        "изгиб", "скручиван", "ослаблен", "изношен", "выработк",
        "закоксовыван", "загрязнен", "неплотн", "подтекани", "протечк",
    ]

    found_defects = []
    sentences = re.split(r'[,.!?;]', text)
    for sentence in sentences:
        sentence_lower = sentence.lower().strip()
        if not sentence_lower:
            continue
        for kw in defect_keywords:
            if kw in sentence_lower:
                found_defects.append(sentence.strip())
                break

    if found_defects:
        return found_defects

    if "зазор" in text_lower:
        clearances = extract_clearances_from_text(text)
        for c in clearances:
            found_defects.append(f"зазор {c['type']}: {c['value']} мм")
        return found_defects

    return []


def parse_works_for_avr(text: str) -> list:
    """Парсит выполненные работы для АВР из текста."""
    works = []
    text_lower = text.lower()

    clean_text = re.sub(r'(авр|акт выполненных|сделай авр|создай авр|оформи авр)\s*', '', text_lower, flags=re.IGNORECASE)
    clean_text = re.sub(r'по судну\s+\w+\s*', '', clean_text)
    clean_text = re.sub(r'судно\s+\w+\s*', '', clean_text)
    clean_text = clean_text.strip()

    lines = re.split(r'\n|\.\s+|;\s+', clean_text)

    for line in lines:
        line = line.strip()
        if not line or len(line) < 5:
            continue

        work = {"name": "", "description": "", "quantity": "", "unit": "", "note": ""}

        quantity_match = re.search(r'(\d+)\s*(шт|компл|м|кг|л|шт\.|компл\.|м\.|кг\.|л\.)', line)
        if quantity_match:
            work["quantity"] = quantity_match.group(1)
            work["unit"] = quantity_match.group(2).replace('.', '')
            line = line.replace(quantity_match.group(0), '').strip()

        note_match = re.search(r'\([^)]+\)', line)
        if note_match:
            work["note"] = note_match.group(0).strip('()')
            line = line.replace(note_match.group(0), '').strip()

        if ':' in line or '—' in line or '-' in line:
            parts = re.split(r':\s*|—\s*|-\s*', line, maxsplit=1)
            if len(parts) == 2:
                work["name"] = parts[0].strip().capitalize()
                work["description"] = parts[1].strip().capitalize()
            else:
                work["description"] = line.capitalize()
        else:
            if any(word in line for word in ["замена", "ремонт", "восстановлен", "изготовлен", "монтаж", "демонтаж"]):
                work["name"] = "Ремонтные работы"
                work["description"] = line.capitalize()
            else:
                work["description"] = line.capitalize()

        if work["name"] or work["description"]:
            if not work["unit"]:
                work["unit"] = "компл." if not work["quantity"] else ""
            works.append(work)

    if not works and text.strip():
        works.append({
            "name": "Основные работы",
            "description": text.strip().capitalize(),
            "quantity": "1",
            "unit": "компл.",
            "note": "",
        })

    return works


def analyze_query_local(text: str) -> dict:
    """Локальный анализ запроса (без AI)."""
    result = {
        "ship": detect_ship(text),
        "equipment": extract_equipment(text),
        "defects": extract_defects(text),
        "pump_type": detect_pump_type(text),
        "equipment_type": detect_equipment_type(text),
        "clearances": extract_clearances_from_text(text),
        "works": parse_works_for_avr(text),
        "full_text": text,
        "source": "local",
    }

    if result["clearances"] and not result["defects"]:
        for c in result["clearances"]:
            result["defects"].append(f"зазор {c['type']}: {c['value']} мм")

    if not result["equipment"] and "насос" in text.lower():
        pump_name = pump_db.get_pump_name(result["pump_type"]) if result["pump_type"] else ""
        result["equipment"] = f"насос {pump_name}".strip() if pump_name else "насос"

    return result


# ============================================================
#  ГЕНЕРАЦИЯ ОБЪЁМА РАБОТ
# ============================================================

def generate_work_volume(defects: list, full_text: str, pump_type: str | None = None, equipment_type: str | None = None) -> str:
    """Генерирует объём работ с использованием базы знаний или AI."""
    import bot_context

    if bot_context.alisa_router:
        try:
            ai_result = bot_context.alisa_router.generate_work_volume(defects, equipment_type, pump_type)
            if ai_result:
                logger.info("Сгенерировано через Алису")
                return ai_result
        except Exception as e:
            logger.warning(f"Ошибка при вызове Алисы: {e}")

    logger.warning("Использую базовый шаблон")
    return generate_base_work_volume(defects)


def generate_base_work_volume(defects: list) -> str:
    """Базовый объём работ (запасной вариант)."""
    lines = ["1. Демонтаж узла", "2. Разборка и дефектация"]

    work_items = []
    for defect in defects:
        defect_lower = defect.lower()
        if "течь" in defect_lower or "уплотнен" in defect_lower:
            work_items.append("замена уплотнительных элементов")
        elif "износ" in defect_lower or "изношен" in defect_lower:
            work_items.append("восстановление или замена изношенных деталей")
        elif "трещин" in defect_lower:
            work_items.append("заварка трещин или замена детали")
        elif "коррози" in defect_lower:
            work_items.append("зачистка и восстановление коррозионных повреждений")
        elif "зазор" in defect_lower:
            work_items.append("регулировка зазоров")
        elif "протечк" in defect_lower:
            work_items.append("замена уплотнений и проверка герметичности")

    if work_items:
        unique_items = list(dict.fromkeys(work_items))
        lines.append("3. " + "; ".join(unique_items))
    else:
        lines.append("3. Замена/восстановление деталей")

    lines.append("4. Сборка с проверкой зазоров")
    lines.append("5. Монтаж")
    lines.append("6. Предъявление лицу сдающему")

    return "\n".join(lines)


# ============================================================
#  ПОСТРОЕНИЕ ТАБЛИЦЫ (ДЛЯ НАСОСОВ)
# ============================================================

DEFECT_MAP = {
    "крыльчатк": "2.1",
    "крылатк": "2.1",
    "колес": "2.1",
    "вал": "2.2",
    "трещин вала": "2.2",
    "шпонк": "2.3",
    "уплотнен": "3.1",
    "сальник": "3.1",
    "подшипник": "4.1",
    "крепеж": "6.3",
    "болт": "6.3",
    "гайк": "6.3",
}

DEFAULT_NO_DEFECT_TEXT = "Визуальный осмотр. Дефектов не обнаружено."
DEFAULT_NO_DEFECT_WORK = "Мыть, чистить. Годен к дальнейшей эксплуатации."

ACTION_MAP = {
    "эксплуатационный износ": "Замена.",
    "износ": "Замена.",
    "коррози": "Чистка УШМ, грунтовка. Пригодна к дальнейшей эксплуатации.",
    "грязев": "Мыть, чистить. Годен к дальнейшей эксплуатации.",
    "окисление": "Мыть, чистить. Годен к дальнейшей эксплуатации.",
    "трещин": "Замена.",
    "течь": "Замена уплотнений, проверка герметичности.",
}


def build_defect_table_pump(pump_type: str | None, defects: list, work_volume: str) -> list:
    """Строит таблицу для насосов (7 колонок)."""
    rows = [
        {"num": "1.1", "part": "Корпус насоса", "defect": "", "unit": "шт.", "qty": "1"},
        {"num": "1.2", "part": "Уплотнительное кольцо", "defect": "", "unit": "шт.", "qty": "1"},
        {"num": "1.3", "part": "Всасывающий/напорный патрубок", "defect": "", "unit": "компл.", "qty": "1"},
    ]

    if pump_type == "centrifugal":
        rows.extend([
            {"num": "2.1", "part": "Рабочее колесо (крыльчатка)", "defect": "", "unit": "шт.", "qty": "1"},
            {"num": "2.2", "part": "Вал насоса", "defect": "", "unit": "шт.", "qty": "1"},
            {"num": "2.3", "part": "Шпонка рабочего колеса", "defect": "", "unit": "шт.", "qty": "1"},
        ])
    elif pump_type == "gear":
        rows.extend([
            {"num": "2.1", "part": "Ведущая шестерня", "defect": "", "unit": "шт.", "qty": "1"},
            {"num": "2.2", "part": "Ведомая шестерня", "defect": "", "unit": "шт.", "qty": "1"},
            {"num": "2.3", "part": "Пальцы и втулки", "defect": "", "unit": "компл.", "qty": "1"},
            {"num": "2.4", "part": "Перепускной клапан", "defect": "", "unit": "шт.", "qty": "1"},
        ])
    elif pump_type == "piston":
        rows.extend([
            {"num": "2.1", "part": "Цилиндр (зеркало)", "defect": "", "unit": "шт.", "qty": "1"},
            {"num": "2.2", "part": "Поршень / плунжер", "defect": "", "unit": "шт.", "qty": "1"},
            {"num": "2.3", "part": "Поршневые кольца", "defect": "", "unit": "компл.", "qty": "1"},
            {"num": "2.4", "part": "Шток / плунжер", "defect": "", "unit": "шт.", "qty": "1"},
            {"num": "2.5", "part": "Крейцкопф (башмаки, направляющие)", "defect": "", "unit": "компл.", "qty": "1"},
        ])

    rows.extend([
        {"num": "3.1", "part": "Уплотнение вала (сальник/торцевое)", "defect": "", "unit": "компл.", "qty": "1"},
        {"num": "4.1", "part": "Подшипниковый узел", "defect": "", "unit": "компл.", "qty": "1"},
        {"num": "4.2", "part": "Корпус подшипников / крышки", "defect": "", "unit": "компл.", "qty": "1"},
        {"num": "4.3", "part": "Масляная камера", "defect": "", "unit": "шт.", "qty": "1"},
        {"num": "5.1", "part": "Обмотка статора", "defect": "", "unit": "шт.", "qty": "1"},
        {"num": "5.2", "part": "Клеммная коробка и кабельный ввод", "defect": "", "unit": "компл.", "qty": "1"},
        {"num": "5.3", "part": "Муфта соединения", "defect": "", "unit": "компл.", "qty": "1"},
        {"num": "6.1", "part": "Обратный клапан", "defect": "", "unit": "шт.", "qty": "1"},
        {"num": "6.2", "part": "Задвижка на всасывании", "defect": "", "unit": "шт.", "qty": "1"},
        {"num": "6.3", "part": "Крепёж и расходные материалы", "defect": "", "unit": "компл.", "qty": "1"},
    ])

    for defect in defects:
        defect_lower = defect.lower()
        placed = False
        for keyword, pos in DEFECT_MAP.items():
            if keyword in defect_lower:
                for row in rows:
                    if row["num"] == pos and not row["defect"]:
                        row["defect"] = defect
                        placed = True
                        break
                if placed:
                    break
        if not placed:
            for row in rows:
                if row["num"] == "1.1" and not row["defect"]:
                    row["defect"] = defect
                    break

    for row in rows:
        if not row["defect"]:
            row["defect"] = DEFAULT_NO_DEFECT_TEXT
            row["work"] = DEFAULT_NO_DEFECT_WORK
        else:
            defect_lower = row["defect"].lower()
            matched = None
            for keyword, action in ACTION_MAP.items():
                if keyword in defect_lower:
                    matched = action
                    break
            row["work"] = matched or work_volume

    return rows


# ============================================================
#  ПОСТРОЕНИЕ ТАБЛИЦЫ (ДЛЯ ДВИГАТЕЛЕЙ)
# ============================================================

def build_defect_table_engine(defects: list, work_volume: str) -> list:
    """Строит таблицу для двигателей (6 колонок)."""
    rows = []

    sections = {
        "Цилиндропоршневая группа": [],
        "Головка цилиндров и газораспределение": [],
        "Системы и вспомогательное оборудование": [],
        "Сборочные и испытательные работы": [],
    }

    for i, defect in enumerate(defects, 1):
        defect_lower = defect.lower()
        section = None

        if any(word in defect_lower for word in ["поршн", "цилиндр", "кольц", "втулк"]):
            section = "Цилиндропоршневая группа"
        elif any(word in defect_lower for word in ["крышк", "клапан", "форсунк", "толкател", "газораспредел"]):
            section = "Головка цилиндров и газораспределение"
        elif any(word in defect_lower for word in ["рубашк", "сальник", "турбо", "масл", "охлажд"]):
            section = "Системы и вспомогательное оборудование"
        elif any(word in defect_lower for word in ["испытани", "сборк"]):
            section = "Сборочные и испытательные работы"
        else:
            section = "Прочее"

        if not defect or defect == "Не указано":
            defect_text = DEFAULT_NO_DEFECT_TEXT
            work_text = DEFAULT_NO_DEFECT_WORK
        else:
            defect_lower = defect.lower()
            matched = None
            for keyword, action in ACTION_MAP.items():
                if keyword in defect_lower:
                    matched = action
                    break
            defect_text = defect
            work_text = matched or work_volume

        rows.append({
            "num": str(i),
            "defect": defect_text,
            "work": work_text,
            "unit": "компл.",
            "qty": "1",
            "section": section,
        })

    return rows
