import os
import telebot
from telebot.handler_backends import State, StatesGroup
from telebot import custom_filters
import httpx
from datetime import datetime
from docx import Document
from docx.shared import Pt, Cm
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
#  ИМПОРТ ГОСТ ЧЕКЕРА И АЛИСЫ
# ============================================================

try:
    from gost_checker import GOSTChecker
    gost_checker = GOSTChecker()
    print(f"✅ ГОСТ чекер загружен. Доступно ГОСТов: {len(gost_checker.get_all_gosts())}")
except Exception as e:
    print(f"⚠️ Ошибка при загрузке ГОСТ чекера: {e}")
    gost_checker = None

# Пытаемся загрузить Алису (ai_router)
alisa_router = None
try:
    from models.ai_router import router as alisa_router
    print(f"✅ Алиса (YandexGPT) загружена успешно!")
except ImportError as e:
    print(f"⚠️ Модуль ai_router не найден: {e}")
except Exception as e:
    print(f"⚠️ Ошибка при загрузке Алисы: {e}")

# ============================================================
#  ЗАГРУЗКА ДАННЫХ ИЗ JSON
# ============================================================

def load_checklists():
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
    template_path = os.path.join(TEMPLATES_DIR, filename)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Шаблон {filename} не найден в {TEMPLATES_DIR}")
    return Document(template_path)

def replace_placeholders(doc, placeholders):
    for paragraph in doc.paragraphs:
        for key, value in placeholders.items():
            if f"{{{{{key}}}}}" in paragraph.text:
                inline = paragraph.runs
                for run in inline:
                    if f"{{{{{key}}}}}" in run.text:
                        run.text = run.text.replace(f"{{{{{key}}}}}", str(value))
    
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for key, value in placeholders.items():
                        if f"{{{{{key}}}}}" in paragraph.text:
                            paragraph.text = paragraph.text.replace(f"{{{{{key}}}}}", str(value))
    return doc

def get_counter(doc_type):
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    
    if os.path.exists(COUNTERS_FILE):
        with open(COUNTERS_FILE, 'r', encoding='utf-8') as f:
            counters = json.load(f)
    else:
        counters = {"da": 0, "avr": 0}
    
    return counters.get(doc_type, 0) + 1

def update_counter(doc_type, new_number):
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
#  ОПРЕДЕЛЕНИЕ ТИПА ОБОРУДОВАНИЯ (ЛОКАЛЬНОЕ)
# ============================================================

def detect_equipment_type(text):
    """Определяет тип оборудования локально (без AI)"""
    text_lower = text.lower()
    if any(word in text_lower for word in ["двигател", "дизель", "мотор", "гд"]):
        return "engine"
    elif any(word in text_lower for word in ["компрессор", "компрес"]):
        return "compressor"
    elif any(word in text_lower for word in ["насос", "помп"]):
        return "pump"
    else:
        return None

def ask_for_clarification(equipment):
    """Формирует вопрос для уточнения типа оборудования"""
    return f"🔍 Я нашёл упоминание '{equipment}'. Уточните, это:\n1️⃣ Насос\n2️⃣ Двигатель\n3️⃣ Другое оборудование\n\nПросто напишите номер или название."

# ============================================================
#  РАСШИРЕННЫЙ АНАЛИЗ ЗАПРОСОВ
# ============================================================

def detect_ship(text):
    text_lower = text.lower()
    ships = ["аргака", "пластун", "славянская", "первоуральск", "керчь", "краснодар"]
    for ship in ships:
        if ship in text_lower:
            return ship.capitalize()
    return None

def detect_pump_type(text):
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
    text_lower = text.lower()
    equipment_keywords = ["насос", "двигатель", "компрессор", "вентилятор", 
                         "генератор", "кран", "лебедка", "редуктор", "гидромотор",
                         "брашпиль", "котёл", "водонагреватель", "дизель", "мотор"]
    for kw in equipment_keywords:
        if kw in text_lower:
            pattern = r'(\w+\s+){0,2}' + kw + r'(\s+\w+){0,2}'
            match = re.search(pattern, text)
            if match:
                return match.group(0).strip()
    return None

def extract_clearances_from_text(text):
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
        "закоксовыван", "загрязнен", "неплотн", "подтекани", "протечк"
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
            "note": ""
        })
    
    return works

def analyze_query_local(text):
    """Локальный анализ запроса (без AI)"""
    result = {
        "ship": detect_ship(text),
        "equipment": extract_equipment(text),
        "defects": extract_defects(text),
        "pump_type": detect_pump_type(text),
        "equipment_type": detect_equipment_type(text),
        "clearances": extract_clearances_from_text(text),
        "works": parse_works_for_avr(text),
        "full_text": text,
        "source": "local"
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

def generate_work_volume(defects, full_text, pump_type=None, equipment_type=None):
    """Генерирует объём работ с использованием базы знаний или AI"""
    
    # 1. Пробуем Алису через ai_router
    if alisa_router:
        try:
            ai_result = alisa_router.generate_work_volume(defects, equipment_type, pump_type)
            if ai_result:
                print(f"✅ Сгенерировано через Алису")
                return ai_result
        except Exception as e:
            print(f"⚠️ Ошибка при вызове Алисы: {e}")
    
    # 2. Если есть оборудование и дефекты — пытаемся найти в старой базе знаний
    if equipment_type and defects:
        try:
            from models.router import router
            work = router._find_work_by_defect(defects[0])
            if work:
                print(f"✅ Найдено в старой базе знаний: {work}")
                return work
        except Exception as e:
            print(f"⚠️ Ошибка при поиске в старой базе: {e}")
    
    # 3. Если ничего не помогло — базовый шаблон
    print("⚠️ Использую базовый шаблон")
    return generate_base_work_volume(defects)

def generate_base_work_volume(defects):
    """Базовый объём работ (запасной вариант)"""
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

def build_defect_table_pump(pump_type, defects, work_volume):
    """Строит таблицу для насосов (7 колонок)"""
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
        row["work"] = work_volume
    
    return rows

# ============================================================
#  ПОСТРОЕНИЕ ТАБЛИЦЫ (ДЛЯ ДВИГАТЕЛЕЙ)
# ============================================================

def build_defect_table_engine(defects, work_volume):
    """Строит таблицу для двигателей (6 колонок)"""
    rows = []
    
    sections = {
        "Цилиндропоршневая группа": [],
        "Головка цилиндров и газораспределение": [],
        "Системы и вспомогательное оборудование": [],
        "Сборочные и испытательные работы": []
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
        
        rows.append({
            "num": f"{i}.{i}",
            "defect": defect,
            "work": work_volume,
            "unit": "компл.",
            "qty": "1",
            "section": section
        })
    
    return rows

# ============================================================
#  ФУНКЦИИ СОЗДАНИЯ ДОКУМЕНТОВ
# ============================================================

def create_defect_document(ship, equipment, defects, work_volume, pump_type=None):
    """Созда center акта дефектации с таблицей, подходящей под тип оборудования"""
    doc = load_template("defect_act_template.docx")
    
    number = get_counter("da")
    update_counter("da", number)
    
    date_str = datetime.now().strftime('%d.%m.%Y')
    ship_code = ship[:3].upper() if ship else "XXX"
    
    equipment_type = detect_equipment_type(equipment or "")
    if equipment_type is None:
        equipment_type = "pump"
    
    if equipment_type == "pump":
        rows_data = build_defect_table_pump(pump_type, defects, work_volume)
        cols = 7
        headers = ['№', 'Позиция', 'Дефект / Состояние', 'Объём работ', 'Ед. изм.', 'Кол-во', 'Примечание']
        sections = {
            "1": "Корпус и проточная часть",
            "2": "Ротор / рабочая часть",
            "3": "Уплотнения вала",
            "4": "Подшипниковый узел",
            "5": "Электропривод",
            "6": "Арматура и обвязка"
        }
        get_section_key = lambda row: row["num"].split(".")[0]
        show_purpose = True
        show_basis = True
        show_conclusion = True
        show_notes = False
    else:
        rows_data = build_defect_table_engine(defects, work_volume)
        cols = 6
        headers = ['№ п/п', 'Наименование дефекта', 'Объём работ', 'Ед. изм.', 'Кол-во', 'Примечание']
        sections = {}
        get_section_key = lambda row: row.get("section", "Прочее")
        show_purpose = False
        show_basis = False
        show_conclusion = False
        show_notes = True
        notes_text = "Все СЗЧ (поршневые кольца, поршни, втулка, комплекты для форсунок, РТИ) — поставка Заказчика, если не указано иное.\nРаботы по проточке и транспортировке деталей выполняются Подрядчиком за отдельную плату (акт дополнительных работ)."
    
    table_paragraph_index = None
    for i, paragraph in enumerate(doc.paragraphs):
        if "{{table}}" in paragraph.text:
            table_paragraph_index = i
            paragraph.text = ""
            break
    
    table = doc.add_table(rows=1, cols=cols)
    table.autofit = False
    table.allow_autofit = False
    
    if cols == 7:
        widths = [Cm(1.3), Cm(3.8), Cm(5.0), Cm(5.0), Cm(2.0), Cm(1.8), Cm(3.8)]
    else:
        widths = [Cm(1.8), Cm(5.0), Cm(6.0), Cm(2.2), Cm(2.0), Cm(3.0)]
    
    for i, width in enumerate(widths):
        table.columns[i].width = width
    
    header_cells = table.rows[0].cells
    for i, header in enumerate(headers):
        header_cells[i].text = header
        header_cells[i].paragraphs[0].runs[0].bold = True
        header_cells[i].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    
    current_section = None
    for row_data in rows_data:
        section_key = get_section_key(row_data)
        if section_key != current_section:
            current_section = section_key
            row = table.add_row().cells
            for cell in row:
                cell.text = ""
            if cols == 7:
                row[0].text = sections.get(section_key, "")
            else:
                row[0].text = section_key
            for cell in row:
                cell.paragraphs[0].runs[0].bold = True
                cell.paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        
        row = table.add_row().cells
        if cols == 7:
            row[0].text = row_data["num"]
            row[1].text = row_data["part"]
            row[2].text = row_data.get("defect", "—")
            row[3].text = row_data.get("work", "—")
            row[4].text = row_data["unit"]
            row[5].text = row_data["qty"]
            row[6].text = "—"
        else:
            row[0].text = row_data["num"]
            row[1].text = row_data.get("defect", "—")
            row[2].text = row_data.get("work", "—")
            row[3].text = row_data.get("unit", "компл.")
            row[4].text = row_data.get("qty", "1")
            row[5].text = "—"
    
    if table_paragraph_index is not None:
        target_paragraph = doc.paragraphs[table_paragraph_index]
        tbl = table._tbl
        target_paragraph._element.addprevious(tbl)
    
    placeholders = {
        "ship_code": ship_code,
        "number": str(number).zfill(2),
        "date": date_str,
        "ship": ship or "Не указано",
        "equipment": equipment or "Не указано",
        "work_object": "Текущий ремонт"
    }
    
    if show_purpose:
        placeholders["purpose"] = "По назначению"
    if show_basis:
        placeholders["basis"] = "По заявке"
    if show_conclusion:
        placeholders["conclusion"] = "Детали подлежат замене/восстановлению согласно указанному объёму работ."
    if show_notes:
        placeholders["notes"] = notes_text
    
    doc = replace_placeholders(doc, placeholders)
    
    if equipment_type != "pump":
        for i, paragraph in enumerate(doc.paragraphs):
            if "Представитель Подрядчика" in paragraph.text or "Представитель заказчика" in paragraph.text:
                p = doc.paragraphs[i].insert_paragraph_before()
                run = p.add_run('Особые отметки:')
                run.bold = True
                p = doc.paragraphs[i].insert_paragraph_before()
                p.text = notes_text
                p = doc.paragraphs[i].insert_paragraph_before()
                p.text = ""
                break
    
    if equipment_type != "pump":
        for paragraph in doc.paragraphs:
            if "Представитель подрядчика (Исполнитель)" in paragraph.text:
                paragraph.text = "Представитель Подрядчика:"
            if "Представитель заказчика (Судовладелец / Экипаж)" in paragraph.text:
                paragraph.text = "Представитель Заказчика:"
            if "Старший механик" in paragraph.text:
                paragraph.text = "Должность      / *[ФИО]* /"
            if "Согласовано (при необходимости)" in paragraph.text:
                paragraph.text = ""
            if "Инспектор РМРС" in paragraph.text:
                paragraph.text = ""
    
    file_stream = BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream

def create_avr_document(ship, works, executor="ООО «Новое время»", customer="АО «Бункерная компания»", location="Рейд 4ый район, г. Находка"):
    doc = load_template("avr_template.docx")
    
    number = get_counter("avr")
    update_counter("avr", number)
    
    date_str = datetime.now().strftime('%d.%m.%Y')
    ship_code = ship[:3].upper() if ship else "XXX"
    
    table_paragraph_index = None
    for i, paragraph in enumerate(doc.paragraphs):
        if "{{table}}" in paragraph.text:
            table_paragraph_index = i
            paragraph.text = ""
            break
    
    table = doc.add_table(rows=1, cols=6)
    table.autofit = False
    table.allow_autofit = False
    
    widths = [Cm(1.8), Cm(5.0), Cm(6.0), Cm(2.2), Cm(2.0), Cm(3.0)]
    for i, width in enumerate(widths):
        table.columns[i].width = width
    
    headers = ['№ п/п', 'Наименование работ', 'Описание выполненных работ', 'Кол-во', 'Ед. изм.', 'Примечание']
    header_cells = table.rows[0].cells
    for i, header in enumerate(headers):
        header_cells[i].text = header
        header_cells[i].paragraphs[0].runs[0].bold = True
        header_cells[i].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    
    if works:
        for i, work in enumerate(works, 1):
            row = table.add_row().cells
            row[0].text = str(i)
            row[1].text = work.get('name', '')
            row[2].text = work.get('description', '')
            row[3].text = str(work.get('quantity', ''))
            row[4].text = work.get('unit', '')
            row[5].text = work.get('note', '')
    else:
        row = table.add_row().cells
        row[0].text = "1"
        row[1].text = "Основные работы"
        row[2].text = "Выполнены работы согласно дефектации"
        row[3].text = "1"
        row[4].text = "компл."
        row[5].text = ""
    
    if table_paragraph_index is not None:
        target_paragraph = doc.paragraphs[table_paragraph_index]
        tbl = table._tbl
        target_paragraph._element.addprevious(tbl)
    
    placeholders = {
        "ship_code": ship_code,
        "number": str(number).zfill(2),
        "date": date_str,
        "ship": ship or "Не указано",
        "executor": executor,
        "customer": customer,
        "location": location,
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
        "• Проверять параметры по ГОСТам (скажи 'проверь по ГОСТ')\n"
        "• Показывать частые дефекты (спроси 'какие дефекты')\n"
        "• Показывать чек-лист деталей (спроси 'чек-лист насоса')\n\n"
        "📌 Типы оборудования в базе:\n"
        "• Насосы: центробежные, шестерёнчатые, поршневые\n"
        "• Двигатели (MAN, Caterpillar и др.)\n\n"
        "📌 Доступные команды:\n"
        "• /gosts — список всех ГОСТов\n"
        "• /search — поиск по ГОСТам\n"
        "• /stats — статистика AI\n\n"
        "🧠 Я использую Яндекс.Алису и базу знаний для анализа запросов!\n\n"
        "📝 Примеры:\n"
        "• 'Судно Славянская, пожарный насос, повреждена крылатка. Сделай акт'\n"
        "• 'Судно Аргака, главный двигатель MAN, износ поршневых колец. Сделай акт'\n"
        "• 'проверь по ГОСТ 520-2011 диаметр=50'\n"
        "• 'проверь по ГОСТ 3325-85 зазор=0.15'"
    )

@bot.message_handler(commands=['stats'])
def show_stats(message):
    """Показывает статистику использования AI"""
    if alisa_router:
        try:
            stats = alisa_router.get_stats()
            response = "📊 **Статистика Алисы (YandexGPT):**\n\n"
            response += f"✅ Вызовов: {stats['calls']}\n"
            response += f"❌ Ошибок: {stats['errors']}\n"
            bot.reply_to(message, response, parse_mode='Markdown')
            return
        except Exception as e:
            print(f"⚠️ Ошибка при получении статистики: {e}")
    
    bot.reply_to(message, "❌ Статистика недоступна")

# ============================================================
#  КОМАНДА /GOSTS — СПИСОК ВСЕХ ГОСТОВ
# ============================================================

@bot.message_handler(commands=['gosts'])
def show_gosts(message):
    """Показывает список всех доступных ГОСТов"""
    if not gost_checker:
        bot.reply_to(message, "❌ ГОСТ чекер не загружен. Проверьте файл gost_checker.py")
        return
    
    gosts = gost_checker.get_all_gosts()
    if not gosts:
        bot.reply_to(message, "❌ База ГОСТов не загружена. Запустите merge_gosts.py")
        return
    
    response = "📁 **Доступные ГОСТы:**\n\n"
    
    # Группируем по разделам
    sections = {}
    for gost_id, data in gosts.items():
        section = data.get("section", "Общие")
        if section not in sections:
            sections[section] = []
        sections[section].append((gost_id, data.get("title", "")[:50]))
    
    for section, items in sections.items():
        response += f"**{section}** ({len(items)})\n"
        for gost_id, title in items[:5]:
            response += f"• {gost_id} — {title}...\n"
        if len(items) > 5:
            response += f"  _... и ещё {len(items)-5}_\n"
        response += "\n"
    
    response += "💡 Используйте `проверь по ГОСТ {номер} {параметр}={значение}`\n"
    response += "Пример: `проверь по ГОСТ 520-2011 диаметр=50`"
    
    bot.reply_to(message, response, parse_mode='Markdown')

# ============================================================
#  КОМАНДА /SEARCH — ПОИСК ПО ГОСТАМ
# ============================================================

@bot.message_handler(commands=['search'])
def search_gosts(message):
    """Поиск по ГОСТам"""
    if not gost_checker:
        bot.reply_to(message, "❌ ГОСТ чекер не загружен")
        return
    
    query = message.text.replace('/search', '').strip()
    if not query:
        bot.reply_to(message, "📝 Введите поисковый запрос: `/search подшипник`")
        return
    
    results = gost_checker.search(query)
    if not results:
        bot.reply_to(message, f"❌ Ничего не найдено по запросу '{query}'")
        return
    
    response = f"📋 **Результаты поиска по '{query}':**\n\n"
    for gost_id, data in list(results.items())[:10]:
        response += f"• **{gost_id}** — {data.get('title', 'Без названия')[:60]}...\n"
    
    if len(results) > 10:
        response += f"\n_... и ещё {len(results)-10} результатов_"
    
    bot.reply_to(message, response, parse_mode='Markdown')

# ============================================================
#  ГЛАВНЫЙ ОБРАБОТЧИК (ЧЕРЕЗ АЛИСУ)
# ============================================================

clarification_states = {}

# История диалогов для контекста (для Алисы)
user_histories = {}

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_text = message.text
    text_lower = user_text.lower()
    
    if user_text.startswith('/'):
        return
    
    # --- ОБРАБОТКА УТОЧНЕНИЙ ---
    if message.chat.id in clarification_states and clarification_states[message.chat.id]:
        equipment_type = text_lower
        if "1" in equipment_type or "насос" in equipment_type:
            clarification_states[message.chat.id] = "pump"
            bot.reply_to(message, "✅ Принято: насос")
            return
        elif "2" in equipment_type or "двигател" in equipment_type:
            clarification_states[message.chat.id] = "engine"
            bot.reply_to(message, "✅ Принято: двигатель")
            return
        else:
            clarification_states[message.chat.id] = "other"
            bot.reply_to(message, "✅ Принято: другое оборудование")
            return
    
    # ---- 1. БЫСТРЫЕ КОМАНДЫ (БЕЗ АЛИСЫ) ----
    
    # Создание акта
    if any(word in text_lower for word in ['сделай акт', 'акт дефектации', 'оформи акт', 'составь акт']):
        handle_act_creation(message, user_text)
        return
    
    # Создание АВР
    if any(word in text_lower for word in ['авр', 'акт выполненных', 'сделай авр', 'оформи авр']):
        handle_avr_creation(message, user_text)
        return
    
    # Проверка по ГОСТам (явная)
    if any(word in text_lower for word in ['проверь по госту', 'по ГОСТ', 'по госту', 'гост']):
        # Пытаемся распарсить ГОСТ
        gost_match = re.search(r'гост\s*([\d-]+)', text, re.IGNORECASE)
        if gost_match and gost_checker:
            gost_id = gost_match.group(1)
            param_match = re.search(r'(\w+)\s*[=:]\s*([\d.]+)', text)
            if param_match:
                param_name = param_match.group(1).strip()
                value = float(param_match.group(2))
                result = gost_checker.check_parameter(gost_id, param_name, value)
                
                response = f"📊 **Проверка по ГОСТ {gost_id}**\n\n"
                response += f"🔹 Параметр: {param_name}\n"
                response += f"🔹 Значение: {value}\n\n"
                response += f"{result.get('message', '')}"
                if result.get('action'):
                    response += f"\n\n🔧 **Рекомендация:** {result['action']}"
                
                bot.reply_to(message, response, parse_mode='Markdown')
                return
    
    # ---- 2. ВСЁ ОСТАЛЬНОЕ — ЧЕРЕЗ АЛИСУ ----
    
    if alisa_router:
        # Получаем историю пользователя
        user_id = message.chat.id
        if user_id not in user_histories:
            user_histories[user_id] = []
        
        history = user_histories[user_id]
        
        # Отправляем в Алису
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            result = alisa_router.process_query(user_text, history)
            
            # Сохраняем в историю
            history.append(f"Пользователь: {user_text}")
            history.append(f"Бот: {result.get('response', '')[:200]}")
            if len(history) > 10:
                history = history[-10:]
            user_histories[user_id] = history
            
            # Отправляем ответ
            if result.get('status') == 'ok':
                bot.reply_to(message, result.get('response', 'Извините, не удалось получить ответ.'))
            else:
                # Если Алиса вернула ошибку — пробуем локальный режим
                bot.reply_to(message, "🤔 Попробую ответить без Алисы...")
                handle_local_fallback(message, user_text)
                
        except Exception as e:
            print(f"⚠️ Ошибка при вызове Алисы: {e}")
            bot.reply_to(message, "⚠️ Произошла ошибка при обращении к Алисе. Отвечаю в локальном режиме.")
            handle_local_fallback(message, user_text)
    else:
        # Алиса недоступна — локальный режим
        handle_local_fallback(message, user_text)


# ============================================================
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ОБРАБОТЧИКА
# ============================================================

def handle_act_creation(message, user_text):
    """Создание Акта дефектации"""
    try:
        bot.send_message(message.chat.id, "🧠 Анализирую запрос для создания акта...")
        
        analysis = analyze_query_local(user_text)
        
        ship = analysis.get('ship')
        equipment = analysis.get('equipment')
        defects = analysis.get('defects', [])
        pump_type = analysis.get('pump_type')
        equipment_type = analysis.get('equipment_type')
        clearances = analysis.get('clearances', [])
        
        if not equipment:
            bot.reply_to(message, "🤔 Не удалось определить оборудование. Уточните: это насос, двигатель или другое оборудование?")
            return
        
        if not equipment_type or equipment_type == "other":
            equip_type = detect_equipment_type(equipment)
            if equip_type is None:
                clarification_states[message.chat.id] = True
                bot.reply_to(message, ask_for_clarification(equipment))
                return
            else:
                equipment_type = equip_type
        
        for c in clearances:
            defect_text = f"зазор {c['type']}: {c['value']} мм"
            if defect_text not in defects:
                defects.append(defect_text)
        
        if not defects:
            for kw in ["износ", "течь", "коррози", "трещин", "выкрашиван", "задир", "деформац", "люфт", "зазор", "загрязнен", "неплотн", "протечк"]:
                if kw in user_text.lower():
                    defects.append(kw)
            if not defects:
                bot.reply_to(message, "🤔 Я не нашёл дефектов. Опишите дефекты подробнее.")
                return
        
        if not equipment:
            if "двигател" in user_text.lower() or "мотор" in user_text.lower() or "дизель" in user_text.lower():
                equipment = "двигатель"
            else:
                pump_name = pump_db.get_pump_name(pump_type) if pump_type else ""
                equipment = f"насос {pump_name}".strip() if pump_name else "насос"
        
        work_volume = generate_work_volume(defects, user_text, pump_type, equipment_type)
        file_stream = create_defect_document(ship, equipment, defects, work_volume, pump_type)
        
        bot.send_document(
            message.chat.id, 
            file_stream, 
            visible_file_name=f'Акт_дефектации_{ship or "судна"}.docx'
        )
        bot.send_message(message.chat.id, "📄 Акт дефектации в Word отправлен!")
        
    except Exception as e:
        import traceback
        error_text = f"❌ Ошибка при создании акта:\n\n{str(e)}"
        bot.send_message(message.chat.id, error_text)
        print(traceback.format_exc())


def handle_avr_creation(message, user_text):
    """Создание Акта выполненных работ"""
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


def handle_local_fallback(message, user_text):
    """Локальный режим работы (без Алисы)"""
    text_lower = user_text.lower()
    
    # Проверка зазоров
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
                    
                    # Проверка по ГОСТам
                    if gost_checker:
                        if c['type'] == 'bearing':
                            gost_result = gost_checker.check_parameter("3325-85", "clearance", c['value'])
                            if gost_result.get('status') != 'error':
                                responses.append(f"   📌 ГОСТ 3325-85: {gost_result.get('message', '')}")
                        elif c['type'] == 'axial' or c['type'] == 'radial':
                            gost_result = gost_checker.check_parameter("24643-81", "runout", c['value'])
                            if gost_result.get('status') != 'error':
                                responses.append(f"   📌 ГОСТ 24643-81: {gost_result.get('message', '')}")
            
            if responses:
                response = "📊 **Результаты проверки зазоров:**\n\n" + "\n".join(responses)
                bot.reply_to(message, response, parse_mode='Markdown')
                return
    
    # Чек-лист
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
    
    # Дефекты
    if any(word in text_lower for word in ['какие дефекты', 'частые дефекты', 'список дефектов', 'дефекты бывают']):
        if any(word in text_lower for word in ["двигател", "дизель", "мотор"]):
            defects = pump_db.get_common_defects("engine")
            response = f"📋 **Частые дефекты двигателей:**\n\n"
            for i, defect in enumerate(defects, 1):
                response += f"{i}. {defect}\n"
            bot.reply_to(message, response, parse_mode='Markdown')
            return
        
        pump_type = detect_pump_type(user_text)
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
            bot.reply_to(message, "📌 Уточните тип оборудования: насос или двигатель")
            return
    
    # Нормативы
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
    
    # Если ничего не подошло
    bot.reply_to(message,
        "🤔 Я не совсем понял запрос.\n\n"
        "Что нужно?\n"
        "📄 Акт дефектации — 'сделай акт'\n"
        "📋 АВР — 'сделай АВР'\n"
        "🔧 Проверить зазор — 'проверь зазор'\n"
        "📋 Дефекты — 'какие дефекты у поршневого насоса'\n"
        "📐 Нормативы — 'нормативы зазоров'\n"
        "📋 Чек-лист — 'чек-лист центробежного насоса'\n"
        "📁 Проверка по ГОСТам — 'проверь по ГОСТ 520-2011 диаметр=50'\n"
        "📋 Список ГОСТов — '/gosts'\n"
        "🔎 Поиск по ГОСТам — '/search подшипник'"
    )

# ============================================================
#  ЗАПУСК
# ============================================================

if __name__ == '__main__':
    print("🤖 Бот-ассистент запущен!")
    print("📌 Типы оборудования в базе: насосы (центробежные, шестерёнчатые, поршневые), двигатели")
    print("📌 Доступные функции: ДА, АВР, проверка зазоров, дефекты, нормативы, чек-лист")
    
    if alisa_router:
        print("🧠 Алиса (YandexGPT) активна — все запросы проходят через неё!")
    else:
        print("⚠️ Алиса НЕ загружена — работаю в локальном режиме")
    
    # Статистика по ГОСТам
    if gost_checker:
        gosts = gost_checker.get_all_gosts()
        print(f"📚 Загружено ГОСТов: {len(gosts)}")
        if gosts:
            sections = {}
            for gost_id, data in gosts.items():
                section = data.get("section", "Общие")
                sections[section] = sections.get(section, 0) + 1
            print("📋 Разделы ГОСТов:")
            for section, count in sections.items():
                print(f"   • {section}: {count}")
    else:
        print("⚠️ ГОСТ чекер не загружен")
    
    import time

def start_bot_with_retry():
    max_retries = 5
    retry_delay = 10
    
    for attempt in range(max_retries):
        try:
            print(f"🔄 Попытка подключения {attempt + 1}/{max_retries}...")
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
            break
        except Exception as e:
            print(f"⚠️ Ошибка: {e}")
            if attempt < max_retries - 1:
                print(f"⏳ Повтор через {retry_delay} секунд...")
                time.sleep(retry_delay)
                retry_delay += 5
            else:
                print("❌ Не удалось подключиться после всех попыток")
                raise

if __name__ == '__main__':
    print("🤖 Бот-ассистент запущен!")
    print("📌 Типы оборудования в базе: насосы (центробежные, шестерёнчатые, поршневые), двигатели")
    print("📌 Доступные функции: ДА, АВР, проверка зазоров, дефекты, нормативы, чек-лист")
    
    if alisa_router:
        print("🧠 Алиса (YandexGPT) активна — все запросы проходят через неё!")
    else:
        print("⚠️ Алиса НЕ загружена — работаю в локальном режиме")
    
    # Статистика по ГОСТам
    if gost_checker:
        gosts = gost_checker.get_all_gosts()
        print(f"📚 Загружено ГОСТов: {len(gosts)}")
        if gosts:
            sections = {}
            for gost_id, data in gosts.items():
                section = data.get("section", "Общие")
                sections[section] = sections.get(section, 0) + 1
            print("📋 Разделы ГОСТов:")
            for section, count in sections.items():
                print(f"   • {section}: {count}")
    else:
        print("⚠️ ГОСТ чекер не загружен")
    
    # Запуск с повторными попытками
    start_bot_with_retry()