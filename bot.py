import os
import telebot
from telebot.handler_backends import State, StatesGroup
from telebot import custom_filters
import httpx
from datetime import datetime
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from io import BytesIO
import re
import json

# --- Настройки ---
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

if not BOT_TOKEN:
    raise ValueError("Переменная TELEGRAM_BOT_TOKEN не найдена!")

bot = telebot.TeleBot(BOT_TOKEN)
bot.add_custom_filter(custom_filters.StateFilter(bot))

# --- Пути к файлам ---
TEMPLATES_DIR = "templates"
DATA_DIR = "data"
CHECKLISTS_FILE = os.path.join(DATA_DIR, "checklists.json")
COUNTERS_FILE = os.path.join(DATA_DIR, "counters.json")


# ============================================================
#  ЗАГРУЗКА ДАННЫХ ИЗ JSON
# ============================================================

def load_checklists():
    """Загружает чек-листы из JSON-файла"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    
    if not os.path.exists(CHECKLISTS_FILE):
        raise FileNotFoundError(f"Файл {CHECKLISTS_FILE} не найден!")
    
    with open(CHECKLISTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


class PumpDatabase:
    def __init__(self):
        self.data = load_checklists()
    
    def get_pump_types(self):
        return list(self.data.keys())
    
    def get_pump_name(self, pump_type):
        return self.data.get(pump_type, {}).get("name", pump_type)
    
    def get_checklist(self, pump_type):
        return self.data.get(pump_type, {}).get("items", [])
    
    def get_clearances(self, pump_type, clearance_type):
        clearances = self.data.get(pump_type, {}).get("clearances", {})
        return clearances.get(clearance_type)
    
    def check_clearance(self, pump_type, clearance_type, measured_value):
        clearance_data = self.get_clearances(pump_type, clearance_type)
        if not clearance_data:
            return {
                "status": "unknown",
                "message": f"Данные по зазору '{clearance_type}' для '{pump_type}' отсутствуют",
                "action": "Проверьте правильность ввода"
            }
        
        standard_min = clearance_data.get("min", 0)
        standard_max = clearance_data.get("max", 0)
        unit = clearance_data.get("unit", "мм")
        
        if "мм/мм" in unit:
            return {
                "status": "info",
                "message": f"📌 Зазор зависит от диаметра: {standard_min}-{standard_max} {unit}",
                "action": "Уточните диаметр для точного расчёта"
            }
        
        if measured_value < standard_min:
            return {
                "status": "warning",
                "message": f"⚠️ Зазор МЕНЬШЕ нормы: {measured_value} мм (норма: {standard_min}-{standard_max} мм)",
                "action": "Проверьте точность измерения"
            }
        elif measured_value <= standard_max:
            return {
                "status": "ok",
                "message": f"✅ Зазор В НОРМЕ: {measured_value} мм (норма: {standard_min}-{standard_max} мм)",
                "action": "Деталь работоспособна"
            }
        else:
            return {
                "status": "critical",
                "message": f"🔴 Зазор ПРЕВЫШЕН: {measured_value} мм (норма: {standard_min}-{standard_max} мм)",
                "action": "Требуется ремонт"
            }
    
    def get_common_defects(self, pump_type):
        return self.data.get(pump_type, {}).get("defects", [])
    
    def get_repair_method(self, pump_type, defect_text):
        defect_lower = defect_text.lower()
        methods = self.data.get(pump_type, {}).get("repair_methods", {})
        for key, method in methods.items():
            if key in defect_lower:
                return method
        return None


pump_db = PumpDatabase()


# ============================================================
#  РАБОТА С ШАБЛОНАМИ
# ============================================================

def load_template(filename):
    """Загружает шаблон Word из папки templates"""
    template_path = os.path.join(TEMPLATES_DIR, filename)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Шаблон {filename} не найден в {TEMPLATES_DIR}")
    return Document(template_path)


def replace_placeholders(doc, placeholders):
    """Заменяет плейсхолдеры {{variable}} в документе"""
    # Замена в параграфах
    for paragraph in doc.paragraphs:
        for key, value in placeholders.items():
            if f"{{{{{key}}}}}" in paragraph.text:
                inline = paragraph.runs
                for run in inline:
                    if f"{{{{{key}}}}}" in run.text:
                        run.text = run.text.replace(f"{{{{{key}}}}}", str(value))
    
    # Замена в таблицах
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for key, value in placeholders.items():
                        if f"{{{{{key}}}}}" in paragraph.text:
                            paragraph.text = paragraph.text.replace(f"{{{{{key}}}}}", str(value))
    return doc


def get_counter(doc_type):
    """Получает текущий номер для типа документа"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    
    if os.path.exists(COUNTERS_FILE):
        with open(COUNTERS_FILE, 'r', encoding='utf-8') as f:
            counters = json.load(f)
    else:
        counters = {"da": 0, "avr": 0}
    
    return counters.get(doc_type, 0) + 1


def update_counter(doc_type, new_number):
    """Обновляет номер документа"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    
    if os.path.exists(COUNTERS_FILE):
        with open(COUNTERS_FILE, 'r', encoding='utf-8') as f:
            counters = json.load(f)
    else:
        counters = {"da": 0, "avr": 0}
    
    counters[doc_type] = new_number
    with open(COUNTERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(counters, f, ensure_ascii=False, indent=2)


# ============================================================
#  ДИНАМИЧЕСКАЯ СБОРКА ТАБЛИЦЫ
# ============================================================

def build_defect_table(pump_type, defects, work_volume):
    """
    Собирает таблицу для Акта дефектации в зависимости от типа насоса.
    Возвращает список строк для таблицы.
    """
    rows = []
    
    # ---- Секция 1: Корпус и проточная часть (для всех) ----
    rows.append({"num": "1.1", "part": "Корпус насоса", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
    rows.append({"num": "1.2", "part": "Уплотнительное кольцо", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
    rows.append({"num": "1.3", "part": "Всасывающий/напорный патрубок", "defect": "", "work": "", "unit": "компл.", "qty": "1", "note": ""})
    
    # ---- Секция 2: Ротор / рабочая часть (в зависимости от типа) ----
    if pump_type == "centrifugal":
        rows.append({"num": "2.1", "part": "Рабочее колесо (крыльчатка)", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
        rows.append({"num": "2.2", "part": "Вал насоса", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
        rows.append({"num": "2.3", "part": "Шпонка рабочего колеса", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
    elif pump_type == "gear":
        rows.append({"num": "2.1", "part": "Ведущая шестерня", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
        rows.append({"num": "2.2", "part": "Ведомая шестерня", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
        rows.append({"num": "2.3", "part": "Пальцы и втулки", "defect": "", "work": "", "unit": "компл.", "qty": "1", "note": ""})
        rows.append({"num": "2.4", "part": "Перепускной клапан", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
    elif pump_type == "piston":
        rows.append({"num": "2.1", "part": "Цилиндр (зеркало)", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
        rows.append({"num": "2.2", "part": "Поршень / плунжер", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
        rows.append({"num": "2.3", "part": "Поршневые кольца", "defect": "", "work": "", "unit": "компл.", "qty": "1", "note": ""})
        rows.append({"num": "2.4", "part": "Шток / плунжер", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
        rows.append({"num": "2.5", "part": "Крейцкопф (башмаки, направляющие)", "defect": "", "work": "", "unit": "компл.", "qty": "1", "note": ""})
    
    # ---- Секция 3: Уплотнения (для всех) ----
    rows.append({"num": "3.1", "part": "Уплотнение вала (сальник/торцевое)", "defect": "", "work": "", "unit": "компл.", "qty": "1", "note": ""})
    
    # ---- Секция 4: Подшипники (для всех) ----
    rows.append({"num": "4.1", "part": "Подшипниковый узел", "defect": "", "work": "", "unit": "компл.", "qty": "1", "note": ""})
    rows.append({"num": "4.2", "part": "Корпус подшипников / крышки", "defect": "", "work": "", "unit": "компл.", "qty": "1", "note": ""})
    rows.append({"num": "4.3", "part": "Масляная камера", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
    
    # ---- Секция 5: Привод (для всех) ----
    rows.append({"num": "5.1", "part": "Обмотка статора", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
    rows.append({"num": "5.2", "part": "Клеммная коробка и кабельный ввод", "defect": "", "work": "", "unit": "компл.", "qty": "1", "note": ""})
    rows.append({"num": "5.3", "part": "Муфта соединения", "defect": "", "work": "", "unit": "компл.", "qty": "1", "note": ""})
    
    # ---- Секция 6: Арматура (для всех) ----
    rows.append({"num": "6.1", "part": "Обратный клапан", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
    rows.append({"num": "6.2", "part": "Задвижка на всасывании", "defect": "", "work": "", "unit": "шт.", "qty": "1", "note": ""})
    rows.append({"num": "6.3", "part": "Крепёж и расходные материалы", "defect": "", "work": "", "unit": "компл.", "qty": "1", "note": ""})
    
    # ---- Заполняем дефектами ----
    if defects:
        defect_index = 0
        for row in rows:
            if defect_index < len(defects):
                row["defect"] = defects[defect_index]
                defect_index += 1
    
    # ---- Заполняем объём работ ----
    for row in rows:
        row["work"] = work_volume
    
    return rows


def build_avr_table(works):
    """Собирает таблицу для АВР"""
    rows = []
    if works:
        for i, work in enumerate(works, 1):
            rows.append({
                "num": str(i),
                "name": work.get("name", ""),
                "desc": work.get("description", ""),
                "qty": str(work.get("quantity", "")),
                "unit": work.get("unit", ""),
                "note": work.get("note", "")
            })
    else:
        rows.append({
            "num": "1",
            "name": "Основные работы",
            "desc": "Выполнены работы согласно дефектации",
            "qty": "1",
            "unit": "компл.",
            "note": ""
        })
    return rows


def table_to_html_defect(rows):
    """Превращает список строк в HTML-таблицу для ДА"""
    html = """
    <table border="1" cellpadding="4" cellspacing="0" style="width:100%; border-collapse:collapse; font-size:10pt;">
        <tr>
            <th style="width:5%;">№</th>
            <th style="width:15%;">Позиция</th>
            <th style="width:25%;">Дефект / Состояние</th>
            <th style="width:25%;">Объём работ</th>
            <th style="width:8%;">Ед. изм.</th>
            <th style="width:7%;">Кол-во</th>
            <th style="width:15%;">Примечание</th>
        </tr>
    """
    
    sections = {
        "1": "Корпус и проточная часть",
        "2": "Ротор / рабочая часть",
        "3": "Уплотнения вала",
        "4": "Подшипниковый узел",
        "5": "Электропривод",
        "6": "Арматура и обвязка"
    }
    
    current_section = None
    for row in rows:
        section_key = row["num"].split(".")[0]
        if section_key != current_section:
            current_section = section_key
            html += f"""
        <tr>
            <td colspan="7" style="text-align:center; font-weight:bold; background-color:#e8e8e8;">
                {sections.get(section_key, '')}
            </td>
        </tr>"""
        
        html += f"""
        <tr>
            <td>{row["num"]}</td>
            <td>{row["part"]}</td>
            <td>{row["defect"] or "—"}</td>
            <td>{row["work"] or "—"}</td>
            <td>{row["unit"]}</td>
            <td>{row["qty"]}</td>
            <td>{row["note"] or "—"}</td>
        </tr>"""
    
    html += "</table>"
    return html


def table_to_html_avr(rows):
    """Превращает список строк в HTML-таблицу для АВР"""
    html = """
    <table border="1" cellpadding="4" cellspacing="0" style="width:100%; border-collapse:collapse; font-size:10pt;">
        <tr>
            <th style="width:8%;">№ п/п</th>
            <th style="width:20%;">Наименование работ</th>
            <th style="width:30%;">Описание выполненных работ</th>
            <th style="width:10%;">Кол-во</th>
            <th style="width:10%;">Ед. изм.</th>
            <th style="width:22%;">Примечание</th>
        </tr>
    """
    
    for row in rows:
        html += f"""
        <tr>
            <td>{row["num"]}</td>
            <td>{row["name"]}</td>
            <td>{row["desc"]}</td>
            <td>{row["qty"]}</td>
            <td>{row["unit"]}</td>
            <td>{row["note"]}</td>
        </tr>"""
    
    html += "</table>"
    return html


# ============================================================
#  РАСШИРЕННЫЙ АНАЛИЗ ЗАПРОСОВ
# ============================================================

def detect_ship(text):
    """Определяет судно по тексту"""
    text_lower = text.lower()
    ships = ["аргака", "пластун", "славянская", "первоуральск", "керчь", "краснодар"]
    for ship in ships:
        if ship in text_lower:
            return ship.capitalize()
    return None


def detect_pump_type(text):
    """Определяет тип насоса по тексту"""
    text_lower = text.lower()
    
    piston_keywords = ["поршн", "плунж", "прямодейств", "паровой"]
    for kw in piston_keywords:
        if kw in text_lower:
            return "piston"
    
    gear_keywords = ["шестерен", "шестерн", "ротан", "rotan", "зубчат", "маслян"]
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


def extract_equipment(text):
    """Извлекает название оборудования"""
    text_lower = text.lower()
    equipment_keywords = ["насос", "двигатель", "компрессор", "вентилятор", 
                         "генератор", "кран", "лебедка", "редуктор", "гидромотор",
                         "брашпиль", "котёл", "водонагреватель"]
    for kw in equipment_keywords:
        if kw in text_lower:
            pattern = r'(\w+\s+){0,2}' + kw + r'(\s+\w+){0,2}'
            match = re.search(pattern, text)
            if match:
                return match.group(0).strip()
    return None


def extract_clearances_from_text(text):
    """Извлекает все зазоры из текста"""
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
        "грундбукс": "seal_wear"
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
                    elif part in clearance_map:
                        clearance_type = clearance_map[part]
                    elif part in ["radial", "axial", "bearing", "seal"]:
                        clearance_type = part
                if value is not None:
                    clearances.append({
                        "type": clearance_type or "unknown",
                        "value": value,
                        "raw": match
                    })
            else:
                if re.match(r'^\d+\.?\d*$', match):
                    for ct, mapped in clearance_map.items():
                        if ct in text_lower:
                            clearances.append({
                                "type": mapped,
                                "value": float(match),
                                "raw": match
                            })
                            break
    return clearances


def extract_defects(text):
    """Извлекает дефекты из текста"""
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
        "износ", "течь", "коррози", "трещин", "разруш", "выкрашиван", 
        "задир", "деформац", "ржав", "люфт", "биение", "стук", "вибрац",
        "зазор", "перегрев", "заедание"
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


def parse_works_for_avr(text):
    """Парсит выполненные работы для АВР"""
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
            parts = re.split(r':\s*|—\s*|-\s*', line, 1)
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
            "note": ""
        })
    
    return works


def analyze_query(text):
    """Полный анализ запроса"""
    result = {
        "ship": detect_ship(text),
        "equipment": extract_equipment(text),
        "defects": extract_defects(text),
        "pump_type": detect_pump_type(text),
        "clearances": extract_clearances_from_text(text),
        "works": parse_works_for_avr(text),
        "full_text": text
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

def generate_work_volume(defects, full_text, pump_type=None):
    """Генерирует объём работ с учётом базы данных"""
    if GROQ_API_KEY:
        try:
            return generate_with_ai(defects, full_text, pump_type)
        except Exception as e:
            print(f"Ошибка AI: {e}")
    return generate_from_database(defects, pump_type)


def generate_with_ai(defects, full_text, pump_type):
    """Генерация через Groq AI"""
    client = httpx.Client(timeout=30.0)
    defect_text = "\n".join(defects) if defects else full_text
    
    base_info = ""
    if pump_type:
        pump_name = pump_db.get_pump_name(pump_type)
        base_info += f"Тип насоса: {pump_name}\n"
        defects_list = pump_db.get_common_defects(pump_type)
        if defects_list:
            base_info += f"Частые дефекты для этого типа: {', '.join(defects_list[:5])}\n"
    
    prompt = f"""
На основе описания дефектов составь подробный объём работ для ремонта судового оборудования.

{base_info}

Описание дефектов:
{defect_text}

Обязательно включи в объём работ в виде нумерованного списка:
1. Демонтаж узла
2. Разборка и дефектация
3. Замену или восстановление деталей
4. Сборку с проверкой зазоров
5. Монтаж
6. Предъявление лицу сдающему
"""

    response = client.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": "mixtral-8x7b-32768",
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    else:
        return generate_from_database(defects, pump_type)


def generate_from_database(defects, pump_type):
    """Генерация объёма работ из базы данных"""
    lines = ["1. Демонтаж узла", "2. Разборка и дефектация"]
    if pump_type and defects:
        methods = []
        for defect in defects:
            method = pump_db.get_repair_method(pump_type, defect)
            if method:
                methods.append(method)
        if methods:
            unique_methods = list(dict.fromkeys(methods))
            lines.append("3. " + "; ".join(unique_methods))
        else:
            lines.append("3. Замена/восстановление деталей")
    else:
        lines.append("3. Замена/восстановление деталей")
    lines.append("4. Сборка с проверкой зазоров")
    lines.append("5. Монтаж")
    lines.append("6. Предъявление лицу сдающему")
    return "\n".join(lines)


# ============================================================
#  СОЗДАНИЕ ДОКУМЕНТОВ ИЗ ШАБЛОНОВ
# ============================================================

def create_defect_document(ship, equipment, defects, work_volume, pump_type=None):
    """Создаёт Акт дефектации из шаблона с динамической таблицей"""
    doc = load_template("defect_act_template.docx")
    
    number = get_counter("da")
    update_counter("da", number)
    
    date_str = datetime.now().strftime('%d.%m.%Y')
    ship_code = ship[:3].upper() if ship else "XXX"
    
    # Собираем таблицу
    table_rows = build_defect_table(pump_type, defects, work_volume)
    table_html = table_to_html_defect(table_rows)
    
    placeholders = {
        "ship_code": ship_code,
        "number": str(number).zfill(2),
        "date": date_str,
        "ship": ship or "Не указано",
        "equipment": equipment or "Не указано",
        "purpose": "По назначению",
        "work_object": "Текущий ремонт",
        "basis": "По заявке",
        "table": table_html,
        "conclusion": "Детали подлежат замене/восстановлению согласно указанному объёму работ."
    }
    
    doc = replace_placeholders(doc, placeholders)
    
    file_stream = BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream


def create_avr_document(ship, works, executor="ООО «Новое время»", customer="АО «Бункерная компания»", location="Рейд 4ый район, г. Находка"):
    """Создаёт АВР из шаблона с динамической таблицей"""
    doc = load_template("avr_template.docx")
    
    number = get_counter("avr")
    update_counter("avr", number)
    
    date_str = datetime.now().strftime('%d.%m.%Y')
    ship_code = ship[:3].upper() if ship else "XXX"
    
    table_rows = build_avr_table(works)
    table_html = table_to_html_avr(table_rows)
    
    placeholders = {
        "ship_code": ship_code,
        "number": str(number).zfill(2),
        "date": date_str,
        "ship": ship or "Не указано",
        "executor": executor,
        "customer": customer,
        "location": location,
        "table": table_html
    }
    
    doc = replace_placeholders(doc, placeholders)
    
    file_stream = BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream


# ============================================================
#  КОМАНДА /START
# ============================================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, 
        "👋 Привет! Я — твой инженерный ассистент.\n\n"
        "📌 Что я умею:\n"
        "• Создавать Акты дефектации (скажи 'сделай акт')\n"
        "• Создавать Акты выполненных работ (скажи 'сделай АВР')\n"
        "• Проверять зазоры по ТУ (скажи 'проверь зазор')\n"
        "• Показывать частые дефекты (спроси 'какие дефекты')\n"
        "• Показывать чек-лист деталей (спроси 'чек-лист насоса')\n\n"
        "📌 Типы насосов в базе:\n"
        "• Центробежные\n"
        "• Шестерёнчатые (ROTAN)\n"
        "• Поршневые и плунжерные (ОТУ-80)"
    )


# ============================================================
#  ГЛАВНЫЙ ОБРАБОТЧИК
# ============================================================

@bot.message_handler(func=lambda message: True)
def handle_intelligent_input(message):
    user_text = message.text
    text_lower = user_text.lower()
    
    if user_text.startswith('/'):
        return
    
    # ---- 1. ЧЕК-ЛИСТ ----
    if any(word in text_lower for word in ['чек-лист', 'перечень деталей', 'какие детали']):
        pump_type = detect_pump_type(user_text)
        if pump_type:
            items = pump_db.get_checklist(pump_type)
            pump_name = pump_db.get_pump_name(pump_type)
            response = f"📋 **Чек-лист для {pump_name} насоса:**\n\n"
            for i, item in enumerate(items, 1):
                response += f"{i}. {item}\n"
            bot.reply_to(message, response, parse_mode='Markdown')
        else:
            bot.reply_to(message, "📌 Уточните тип насоса: центробежный, шестерёнчатый или поршневой")
        return
    
    # ---- 2. АВР ----
    if any(word in text_lower for word in ['авр', 'акт выполненных', 'выполненные работы']):
        ship = detect_ship(user_text)
        works = parse_works_for_avr(user_text)
        
        if not works:
            bot.reply_to(message,
                "🤔 Для создания АВР опишите выполненные работы:\n"
                "Пример: 'АВР: Кабель-трасса: замена уголков 44 шт, болтов 194 шт.'"
            )
            return
        
        file_stream = create_avr_document(ship, works)
        bot.send_document(
            message.chat.id,
            file_stream,
            visible_file_name=f'АВР_{ship or "судна"}.docx'
        )
        bot.send_message(message.chat.id, "📄 Акт выполненных работ отправлен!")
        return
    
    # ---- 3. ПРОВЕРКА ЗАЗОРОВ ----
    if any(word in text_lower for word in ['проверь зазор', 'проверка зазора', 'какой зазор', 'норма зазора']):
        clearances = extract_clearances_from_text(user_text)
        if clearances:
            responses = []
            for c in clearances:
                if c['type'] != 'unknown':
                    pump_type = detect_pump_type(user_text)
                    if not pump_type:
                        if "шестерен" in text_lower or "ротан" in text_lower:
                            pump_type = "gear"
                        elif "поршн" in text_lower or "плунж" in text_lower or "паровой" in text_lower:
                            pump_type = "piston"
                        else:
                            pump_type = "centrifugal"
                    result = pump_db.check_clearance(pump_type, c['type'], c['value'])
                    responses.append(f"🔹 {c['type']}: {c['value']} мм -> {result['message']}")
            if responses:
                response = "📊 **Результаты проверки зазоров:**\n\n" + "\n".join(responses)
                bot.reply_to(message, response, parse_mode='Markdown')
                return
        
        bot.reply_to(message,
            "🔧 Чтобы проверить зазор, напишите:\n"
            "`проверь зазор центробежный радиальный 0.25`\n"
            "`проверь зазор поршневой cylinder_piston 0.15`\n\n"
            "Доступные зазоры для поршневых: cylinder_piston, ring_groove, ring_gap, crosshead, main_bearing, connecting_rod, seal_wear"
        )
        return
    
    # ---- 4. ДЕФЕКТЫ ----
    if any(word in text_lower for word in ['какие дефекты', 'частые дефекты', 'список дефектов', 'дефекты бывают']):
        pump_type = detect_pump_type(text_lower)
        if pump_type:
            pump_name = pump_db.get_pump_name(pump_type)
            defects = pump_db.get_common_defects(pump_type)
            response = f"📋 **Частые дефекты {pump_name} насоса:**\n\n"
            for i, defect in enumerate(defects, 1):
                method = pump_db.get_repair_method(pump_type, defect)
                method_text = f" -> {method}" if method else ""
                response += f"{i}. {defect}{method_text}\n"
            bot.reply_to(message, response, parse_mode='Markdown')
            return
        else:
            bot.reply_to(message, "📌 Уточните тип насоса: центробежный, шестерёнчатый или поршневой")
            return
    
    # ---- 5. НОРМАТИВЫ ----
    if any(word in text_lower for word in ['норматив', 'норма', 'ту', 'техническ']):
        response = "📐 **Нормативы зазоров по ТУ**\n\n"
        for pump_type in pump_db.get_pump_types():
            pump_name = pump_db.get_pump_name(pump_type)
            response += f"**{pump_name.capitalize()} насос:**\n"
            clearances = pump_db.data.get(pump_type, {}).get("clearances", {})
            for ct, data in clearances.items():
                min_val = data.get("min", 0)
                max_val = data.get("max", 0)
                unit = data.get("unit", "мм")
                response += f"  • {ct}: {min_val}-{max_val} {unit}\n"
            response += "\n"
        bot.reply_to(message, response, parse_mode='Markdown')
        return
    
    # ---- 6. АКТ ДЕФЕКТАЦИИ ----
    wants_act = any(word in text_lower for word in ['акт', 'дефектовк', 'сделай акт', 'оформи', 'составь', 'создай'])
    
    if wants_act:
        analysis = analyze_query(user_text)
        
        ship = analysis.get('ship')
        equipment = analysis.get('equipment')
        defects = analysis.get('defects', [])
        pump_type = analysis.get('pump_type')
        clearances = analysis.get('clearances', [])
        
        for c in clearances:
            defect_text = f"зазор {c['type']}: {c['value']} мм"
            if defect_text not in defects:
                defects.append(defect_text)
        
        if not defects:
            for kw in ["износ", "течь", "коррози", "трещин", "выкрашиван", "задир", "деформац", "люфт", "зазор"]:
                if kw in text_lower:
                    defects.append(kw)
            if not defects:
                bot.reply_to(message,
                    "🤔 Я не нашёл дефектов в вашем сообщении.\n"
                    "Опишите дефекты: 'износ цилиндра, износ поршневых колец'"
                )
                return
        
        if not equipment:
            pump_name = pump_db.get_pump_name(pump_type) if pump_type else ""
            equipment = f"насос {pump_name}".strip() if pump_name else "насос"
        
        work_volume = generate_work_volume(defects, user_text, pump_type)
        file_stream = create_defect_document(ship, equipment, defects, work_volume, pump_type)
        bot.send_document(
            message.chat.id, 
            file_stream, 
            visible_file_name=f'Акт_дефектации_{ship or "судна"}.docx'
        )
        bot.send_message(message.chat.id, "📄 Акт дефектации в Word отправлен!")
        return
    
    # ---- 7. НЕПОНЯТНО ----
    bot.reply_to(message,
        "🤔 Я не понял запрос.\n\n"
        "Что нужно?\n"
        "📄 Акт дефектации — 'сделай акт'\n"
        "📋 АВР — 'сделай АВР'\n"
        "🔧 Проверить зазор — 'проверь зазор'\n"
        "📋 Дефекты — 'какие дефекты у поршневого насоса'\n"
        "📐 Нормативы — 'нормативы зазоров'\n"
        "📋 Чек-лист — 'чек-лист центробежного насоса'"
    )


# ============================================================
#  ЗАПУСК
# ============================================================

if __name__ == '__main__':
    print("🤖 Бот-ассистент запущен!")
    print("📌 Типы насосов в базе: центробежные, шестерёнчатые, поршневые/плунжерные")
    print("📌 Доступные функции: ДА, АВР, проверка зазоров, дефекты, нормативы, чек-лист")
    bot.infinity_polling()