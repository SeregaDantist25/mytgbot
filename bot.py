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
#  АНАЛИЗ ЗАПРОСА С ПОМОЩЬЮ AI (GROQ)
# ============================================================

def analyze_with_ai(text):
    """Отправляет запрос в Groq для интеллектуального анализа"""
    if not GROQ_API_KEY:
        return None
    
    try:
        client = httpx.Client(timeout=30.0)
        
        prompt = f"""
Ты — инженерный ассистент для судоремонта. Разбери запрос пользователя и верни ответ строго в формате JSON.

Запрос пользователя: {text}

Ответ должен содержать следующие поля:
- "ship": название судна (если есть, иначе null)
- "equipment": название оборудования (насос, двигатель, компрессор и т.д.)
- "equipment_type": тип оборудования (pump, engine, compressor, other)
- "pump_type": если это насос — тип (centrifugal, gear, piston, null)
- "defects": список дефектов (массив строк)
- "clearances": список зазоров (массив объектов с полями "type" и "value")

Пример ответа:
{{
  "ship": "Славянская",
  "equipment": "двигатель MAN 6S42MC",
  "equipment_type": "engine",
  "pump_type": null,
  "defects": ["течь по втулке", "протечка форсунки", "подтеки масла"],
  "clearances": []
}}

Важно:
- "pump_type" может быть только: centrifugal, gear, piston, null
- "equipment_type" может быть только: pump, engine, compressor, other
- Если какое-то поле не определено — укажи null или пустой массив.

Ответь ТОЛЬКО JSON, без лишнего текста, без маркеров кода.
"""

        response = client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": "mixtral-8x7b-32768",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1
            },
            timeout=30.0
        )
        
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            # Парсим JSON из ответа
            try:
                # Ищем JSON в ответе
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_str = content[json_start:json_end]
                    return json.loads(json_str)
            except:
                pass
            return None
        else:
            print(f"Groq API error: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Ошибка AI анализа: {e}")
        return None

# ============================================================
#  РАСШИРЕННЫЙ АНАЛИЗ ЗАПРОСОВ (С AI)
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
    """Полный анализ запроса с использованием AI"""
    
    # 1. Сначала пробуем AI
    ai_result = analyze_with_ai(text)
    
    if ai_result:
        # Преобразуем AI результат в нужный формат
        return {
            "ship": ai_result.get("ship"),
            "equipment": ai_result.get("equipment"),
            "defects": ai_result.get("defects", []),
            "pump_type": ai_result.get("pump_type"),
            "equipment_type": ai_result.get("equipment_type"),
            "clearances": ai_result.get("clearances", []),
            "full_text": text,
            "source": "ai"
        }
    
    # 2. Если AI не справился — используем старую логику
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
#  ГЕНЕРАЦИЯ ОБЪЁМА РАБОТ С ИСПОЛЬЗОВАНИЕМ AI
# ============================================================

def generate_work_volume(defects, full_text, pump_type=None, equipment_type=None):
    """Генерирует объём работ с использованием AI"""
    
    # Пытаемся использовать Groq
    if GROQ_API_KEY:
        try:
            return generate_with_ai(defects, full_text, pump_type, equipment_type)
        except Exception as e:
            print(f"Ошибка AI генерации: {e}")
            return generate_base_work_volume(defects)
    
    # Если нет ключа — базовый шаблон
    return generate_base_work_volume(defects)

def generate_with_ai(defects, full_text, pump_type, equipment_type):
    """Генерация объёма работ через Groq AI"""
    client = httpx.Client(timeout=30.0)
    defect_text = "\n".join(defects) if defects else full_text
    
    # Определяем тип оборудования для контекста
    equip_name = "оборудования"
    if equipment_type == "pump":
        equip_name = "насоса"
        if pump_type:
            pump_name = pump_db.get_pump_name(pump_type)
            equip_name = f"{pump_name} насоса"
    elif equipment_type == "engine":
        equip_name = "двигателя"
    
    prompt = f"""
Ты — опытный инженер-судоремонтник. На основе описания дефектов составь подробный, конкретный объём работ для ремонта {equip_name}.

Описание дефектов:
{defect_text}

Требования к ответу:
1. Ответ должен быть в виде нумерованного списка (1., 2., 3. и т.д.)
2. Каждый пункт должен начинаться с глагола (Демонтаж, Разборка, Замена, Восстановление, Сборка, Монтаж, Проверка, Регулировка, Испытание)
3. Указывай конкретные детали и узлы (не просто "замена деталей", а "замена поршневых колец" или "проточка седла клапана")
4. Учитывай специфику дефектов: если есть "течь" — добавь "замена уплотнений", если "износ" — "восстановление или замена"
5. Обязательно включи:
   - Демонтаж узла
   - Разборку и дефектацию всех повреждённых деталей
   - Конкретные работы по замене/восстановлению
   - Сборку с проверкой зазоров
   - Монтаж
   - Предъявление лицу сдающему
6. Не используй общие фразы, пиши конкретно для этого случая.

Ответь коротко и по делу, без лишних объяснений.
"""

    response = client.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": "mixtral-8x7b-32768",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        },
        timeout=30.0
    )
    
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    else:
        print(f"Groq API error (work volume): {response.status_code}")
        return generate_base_work_volume(defects)

def generate_base_work_volume(defects):
    """Базовый объём работ (запасной вариант)"""
    lines = ["1. Демонтаж узла", "2. Разборка и дефектация"]
    
    # Пытаемся добавить конкретные работы по дефектам
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
        # Убираем дубли
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
    
    # Распределяем дефекты по позициям
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
    """Строит таблицу для двигателей (6 колонок, как в образце)"""
    rows = []
    
    # Секции
    sections = {
        "Цилиндропоршневая группа": [],
        "Головка цилиндров и газораспределение": [],
        "Системы и вспомогательное оборудование": [],
        "Сборочные и испытательные работы": []
    }
    
    # Определяем, к какой секции относится дефект
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
    """Создаёт акт дефектации с таблицей, подходящей под тип оборудования"""
    doc = load_template("defect_act_template.docx")
    
    number = get_counter("da")
    update_counter("da", number)
    
    date_str = datetime.now().strftime('%d.%m.%Y')
    ship_code = ship[:3].upper() if ship else "XXX"
    
    # Определяем тип оборудования
    equipment_type = detect_equipment_type(equipment or "")
    
    # Если тип не определён — используем насос по умолчанию
    if equipment_type is None:
        equipment_type = "pump"
    
    # Строим таблицу в зависимости от типа
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
        # Поля для насоса
        show_purpose = True
        show_basis = True
        show_conclusion = True
        show_notes = False
    else:
        # Двигатели, компрессоры и другое — 6 колонок
        rows_data = build_defect_table_engine(defects, work_volume)
        cols = 6
        headers = ['№ п/п', 'Наименование дефекта', 'Объём работ', 'Ед. изм.', 'Кол-во', 'Примечание']
        sections = {}
        get_section_key = lambda row: row.get("section", "Прочее")
        # Поля для двигателя
        show_purpose = False
        show_basis = False
        show_conclusion = False
        show_notes = True
        notes_text = "Все СЗЧ (поршневые кольца, поршни, втулка, комплекты для форсунок, РТИ) — поставка Заказчика, если не указано иное.\nРаботы по проточке и транспортировке деталей выполняются Подрядчиком за отдельную плату (акт дополнительных работ)."
    
    # Находим параграф с {{table}}
    table_paragraph_index = None
    for i, paragraph in enumerate(doc.paragraphs):
        if "{{table}}" in paragraph.text:
            table_paragraph_index = i
            paragraph.text = ""
            break
    
    # Создаём таблицу
    table = doc.add_table(rows=1, cols=cols)
    table.autofit = False
    table.allow_autofit = False
    
    if cols == 7:
        widths = [Cm(1.3), Cm(3.8), Cm(5.0), Cm(5.0), Cm(2.0), Cm(1.8), Cm(3.8)]
    else:
        widths = [Cm(1.8), Cm(5.0), Cm(6.0), Cm(2.2), Cm(2.0), Cm(3.0)]
    
    for i, width in enumerate(widths):
        table.columns[i].width = width
    
    # Заголовки
    header_cells = table.rows[0].cells
    for i, header in enumerate(headers):
        header_cells[i].text = header
        header_cells[i].paragraphs[0].runs[0].bold = True
        header_cells[i].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    
    # Заполняем строки
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
    
    # Перемещаем таблицу на место плейсхолдера
    if table_paragraph_index is not None:
        target_paragraph = doc.paragraphs[table_paragraph_index]
        tbl = table._tbl
        target_paragraph._element.addprevious(tbl)
    
    # Подготавливаем плейсхолдеры
    placeholders = {
        "ship_code": ship_code,
        "number": str(number).zfill(2),
        "date": date_str,
        "ship": ship or "Не указано",
        "equipment": equipment or "Не указано",
        "work_object": "Текущий ремонт"
    }
    
    # Добавляем поля для насоса
    if show_purpose:
        placeholders["purpose"] = "По назначению"
    if show_basis:
        placeholders["basis"] = "По заявке"
    if show_conclusion:
        placeholders["conclusion"] = "Детали подлежат замене/восстановлению согласно указанному объёму работ."
    if show_notes:
        placeholders["notes"] = notes_text
    
    doc = replace_placeholders(doc, placeholders)
    
    # Если это двигатель — добавляем блок "Особые отметки" перед подписями
    if equipment_type != "pump":
        # Ищем место для вставки "Особые отметки" перед подписями
        for i, paragraph in enumerate(doc.paragraphs):
            if "Представитель Подрядчика" in paragraph.text or "Представитель заказчика" in paragraph.text:
                # Вставляем блок "Особые отметки" перед этим параграфом
                p = doc.paragraphs[i].insert_paragraph_before()
                run = p.add_run('Особые отметки:')
                run.bold = True
                p = doc.paragraphs[i].insert_paragraph_before()
                p.text = notes_text
                p = doc.paragraphs[i].insert_paragraph_before()
                p.text = ""
                break
    
    # Корректируем подписи в зависимости от типа
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
    
    # Находим параграф с {{table}}
    table_paragraph_index = None
    for i, paragraph in enumerate(doc.paragraphs):
        if "{{table}}" in paragraph.text:
            table_paragraph_index = i
            paragraph.text = ""
            break
    
    # Создаём таблицу АВР
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
    
    # Перемещаем таблицу на место плейсхолдера
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
        "• Показывать частые дефекты (спроси 'какие дефекты')\n"
        "• Показывать чек-лист деталей (спроси 'чек-лист насоса')\n\n"
        "📌 Типы оборудования в базе:\n"
        "• Насосы: центробежные, шестерёнчатые, поршневые\n"
        "• Двигатели (MAN, Caterpillar и др.)\n\n"
        "🧠 Я использую нейросеть для анализа запросов!\n\n"
        "📝 Примеры:\n"
        "• 'Судно Славянская, пожарный насос, повреждена крылатка. Сделай акт'\n"
        "• 'Судно Аргака, главный двигатель MAN, износ поршневых колец. Сделай акт'"
    )

# ============================================================
#  ГЛАВНЫЙ ОБРАБОТЧИК
# ============================================================

# Словарь для хранения состояния уточнения (в памяти)
clarification_states = {}

@bot.message_handler(func=lambda message: True)
def handle_intelligent_input(message):
    user_text = message.text
    text_lower = user_text.lower()
    
    if user_text.startswith('/'):
        return
    
    # Проверяем, не находится ли пользователь в режиме уточнения
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
    
    # ---- 1. АКТ ДЕФЕКТАЦИИ (ГЛАВНЫЙ ПРИОРИТЕТ) ----
    wants_act = any(word in text_lower for word in [
        'акт', 'дефектовк', 'сделай акт', 'оформи', 'составь', 'создай',
        'двигател', 'мотор', 'дизель', 'гд', 'насос', 'помп'
    ])
    
    if wants_act:
        try:
            bot.send_message(message.chat.id, "🧠 Анализирую запрос...")
            
            analysis = analyze_query(user_text)
            
            # Если анализ сделан AI, покажем это
            if analysis.get("source") == "ai":
                bot.send_message(message.chat.id, "✅ Запрос проанализирован нейросетью")
            else:
                bot.send_message(message.chat.id, "✅ Запрос проанализирован (стандартный парсер)")
            
            ship = analysis.get('ship')
            equipment = analysis.get('equipment')
            defects = analysis.get('defects', [])
            pump_type = analysis.get('pump_type')
            equipment_type = analysis.get('equipment_type')
            clearances = analysis.get('clearances', [])
            
            # Если оборудование не определено — пробуем уточнить
            if not equipment:
                bot.reply_to(message, "🤔 Не удалось определить оборудование. Уточните: это насос, двигатель или другое оборудование?")
                return
            
            # Если оборудование определено, но тип неясен — уточняем
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
                    if kw in text_lower:
                        defects.append(kw)
                if not defects:
                    bot.reply_to(message, "🤔 Я не нашёл дефектов в вашем сообщении. Опишите дефекты подробнее.")
                    return
            
            if not equipment:
                if "двигател" in text_lower or "мотор" in text_lower or "дизель" in text_lower:
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
            error_text = f"❌ Ошибка при создании акта:\n\n{str(e)}\n\n{traceback.format_exc()}"
            if len(error_text) > 4000:
                error_text = error_text[:4000] + "\n\n... (обрезано)"
            bot.send_message(message.chat.id, error_text)
            print(error_text)
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
    
    # ---- 3. ЧЕК-ЛИСТ ----
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
    
    # ---- 4. ПРОВЕРКА ЗАЗОРОВ ----
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
    
    # ---- 5. ДЕФЕКТЫ ----
    if any(word in text_lower for word in ['какие дефекты', 'частые дефекты', 'список дефектов', 'дефекты бывают']):
        # Проверяем, о чём спрашивают: о насосе или о двигателе
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
            bot.reply_to(message, "📌 Уточните тип оборудования: насос (центробежный, шестерёнчатый, поршневой) или двигатель")
            return
    
    # ---- 6. НОРМАТИВЫ ----
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
    print("📌 Типы оборудования в базе: насосы (центробежные, шестерёнчатые, поршневые), двигатели")
    print("📌 Доступные функции: ДА, АВР, проверка зазоров, дефекты, нормативы, чек-лист")
    print("📌 Используется Groq AI для интеллектуального анализа запросов и генерации объёма работ")
    bot.infinity_polling()