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

# --- Настройки ---
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

if not BOT_TOKEN:
    raise ValueError("Переменная TELEGRAM_BOT_TOKEN не найдена!")

bot = telebot.TeleBot(BOT_TOKEN)
bot.add_custom_filter(custom_filters.StateFilter(bot))

# ============================================================
#  БАЗА ДАННЫХ НАСОСОВ (ВСТРОЕННАЯ)
# ============================================================
class PumpDatabase:
    def __init__(self):
        # ----- Центробежные насосы -----
        self.centrifugal = {
            "clearances": {
                "radial": {
                    "description": "Радиальный зазор между валом и корпусом",
                    "standard": {"min": 0.1, "max": 0.3, "unit": "мм"},
                    "max_allowed": 0.5,
                    "repair_after": "Замена втулок или расточка корпуса"
                },
                "axial": {
                    "description": "Осевой зазор крыльчатки",
                    "standard": {"min": 0.2, "max": 0.5, "unit": "мм"},
                    "max_allowed": 1.0,
                    "repair_after": "Регулировка или замена крыльчатки"
                },
                "bearing": {
                    "description": "Зазор в подшипниках",
                    "standard": {"min": 0.02, "max": 0.08, "unit": "мм"},
                    "max_allowed": 0.15,
                    "repair_after": "Замена подшипников"
                },
                "seal": {
                    "description": "Зазор в сальниковом уплотнении",
                    "standard": {"min": 0.1, "max": 0.2, "unit": "мм"},
                    "max_allowed": 0.4,
                    "repair_after": "Замена набивки или колец"
                }
            },
            "common_defects": [
                "износ подшипников",
                "износ крыльчатки",
                "кавитационный износ",
                "повышенный радиальный зазор",
                "повышенный осевой зазор",
                "течь сальникового уплотнения",
                "коррозия корпуса",
                "трещины в корпусе",
                "деформация вала",
                "износ уплотнительных колец"
            ],
            "repair_methods": {
                "подшипник": "Замена подшипников на новые",
                "крыльчатк": "Восстановление наплавкой или замена",
                "вал": "Шлифовка или замена вала",
                "корпус": "Заварка трещин, механическая обработка",
                "сальник": "Замена набивки или установка новых колец",
                "уплотнительн": "Замена уплотнительных колец",
                "радиальн": "Замена втулок или расточка корпуса",
                "осев": "Регулировка или замена крыльчатки"
            }
        }
        
        # ----- Шестерёнчатые насосы ROTAN -----
        self.gear = {
            "clearances": {
                "radial": {
                    "description": "Радиальный зазор между шестернями и корпусом",
                    "standard": {"min": 0.05, "max": 0.15, "unit": "мм"},
                    "max_allowed": 0.3,
                    "repair_after": "Замена шестерен или корпуса"
                },
                "axial": {
                    "description": "Осевой зазор в шестернях",
                    "standard": {"min": 0.1, "max": 0.3, "unit": "мм"},
                    "max_allowed": 0.5,
                    "repair_after": "Регулировка или замена шестерен"
                },
                "bearing": {
                    "description": "Зазор в подшипниках",
                    "standard": {"min": 0.02, "max": 0.06, "unit": "мм"},
                    "max_allowed": 0.12,
                    "repair_after": "Замена подшипников"
                },
                "seal": {
                    "description": "Зазор в уплотнении вала",
                    "standard": {"min": 0.1, "max": 0.2, "unit": "мм"},
                    "max_allowed": 0.35,
                    "repair_after": "Замена уплотнительных колец"
                }
            },
            "common_defects": [
                "износ зубьев шестерен",
                "износ подшипников",
                "повышенный осевой зазор",
                "повышенный радиальный зазор",
                "течь уплотнения вала",
                "износ пальцев",
                "износ втулок",
                "заедание перепускного клапана"
            ],
            "repair_methods": {
                "шестерн": "Замена шестерен в сборе",
                "подшипник": "Замена подшипников",
                "вал": "Шлифовка или замена вала",
                "уплотнен": "Замена уплотнительных колец",
                "пальц": "Замена пальцев",
                "втулк": "Замена втулок",
                "перепускн": "Разборка, чистка, регулировка",
                "радиальн": "Замена шестерен или корпуса",
                "осев": "Регулировка или замена шестерен"
            }
        }

    def get_pump_types(self):
        return ["centrifugal", "gear"]

    def get_clearances(self, pump_type, clearance_type):
        if pump_type == "centrifugal":
            return self.centrifugal["clearances"].get(clearance_type)
        elif pump_type == "gear":
            return self.gear["clearances"].get(clearance_type)
        return None

    def check_clearance(self, pump_type, clearance_type, measured_value):
        clearance_data = self.get_clearances(pump_type, clearance_type)
        if not clearance_data:
            return {
                "status": "unknown",
                "message": f"Данные по зазору '{clearance_type}' для '{pump_type}' отсутствуют",
                "action": "Проверьте правильность ввода"
            }
        
        standard = clearance_data["standard"]
        max_allowed = clearance_data["max_allowed"]
        repair_after = clearance_data.get("repair_after", "Требуется ремонт")
        
        if measured_value < standard["min"]:
            return {
                "status": "warning",
                "message": f"Зазор МЕНЬШЕ нормы: {measured_value} мм (норма: {standard['min']}-{standard['max']} мм)",
                "action": "Проверьте точность измерения"
            }
        elif measured_value <= standard["max"]:
            return {
                "status": "ok",
                "message": f"Зазор В НОРМЕ: {measured_value} мм (норма: {standard['min']}-{standard['max']} мм)",
                "action": "Деталь работоспособна"
            }
        elif measured_value <= max_allowed:
            return {
                "status": "critical",
                "message": f"Зазор ПРЕВЫШЕН (допустимый предел): {measured_value} мм (макс: {max_allowed} мм)",
                "action": f"Рекомендуется ремонт: {repair_after}"
            }
        else:
            return {
                "status": "fatal",
                "message": f"Зазор КРИТИЧЕСКИ превышен: {measured_value} мм (макс: {max_allowed} мм)",
                "action": f"Требуется срочная замена: {repair_after}"
            }

    def get_common_defects(self, pump_type):
        if pump_type == "centrifugal":
            return self.centrifugal["common_defects"]
        elif pump_type == "gear":
            return self.gear["common_defects"]
        return []

    def get_repair_method(self, pump_type, defect_text):
        defect_lower = defect_text.lower()
        if pump_type == "centrifugal":
            for key, method in self.centrifugal["repair_methods"].items():
                if key in defect_lower:
                    return method
        elif pump_type == "gear":
            for key, method in self.gear["repair_methods"].items():
                if key in defect_lower:
                    return method
        return None

# Создаём экземпляр базы
pump_db = PumpDatabase()

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
    gear_keywords = ["шестерен", "шестерн", "ротан", "rotan", "зубчат", "маслян"]
    for kw in gear_keywords:
        if kw in text_lower:
            return "gear"
    centrifugal_keywords = ["центробеж", "центр", "крыльчатк"]
    for kw in centrifugal_keywords:
        if kw in text_lower:
            return "centrifugal"
    if "насос" in text_lower:
        if "маслян" in text_lower:
            return "gear"
        if "крыльчатк" in text_lower:
            return "centrifugal"
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
                    elif part in ["radial", "axial", "bearing", "seal", 
                                 "радиальн", "осев", "подшипник", "сальник"]:
                        clearance_map = {
                            "радиальн": "radial",
                            "осев": "axial", 
                            "подшипник": "bearing",
                            "сальник": "seal"
                        }
                        clearance_type = clearance_map.get(part, part)
                if value is not None:
                    clearances.append({
                        "type": clearance_type or "unknown",
                        "value": value,
                        "raw": match
                    })
            else:
                if re.match(r'^\d+\.?\d*$', match):
                    for ct in ["radial", "axial", "bearing", "seal", 
                              "радиальн", "осев", "подшипник", "сальник"]:
                        if ct in text_lower:
                            clearance_map = {
                                "радиальн": "radial",
                                "осев": "axial",
                                "подшипник": "bearing", 
                                "сальник": "seal"
                            }
                            clearances.append({
                                "type": clearance_map.get(ct, ct),
                                "value": float(match),
                                "raw": match
                            })
                            break
    return clearances

def extract_defects(text):
    """Извлекает дефекты из текста в структурированном виде"""
    text_lower = text.lower()
    defects = []
    
    # 1. Явное указание "дефекты:"
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
    
    # 2. Ищем по ключевым словам
    defect_keywords = {
        "износ": ["подшипник", "крыльчатк", "вал", "шестерн", "зуб", "сальник", "втулк"],
        "течь": ["сальник", "уплотнен"],
        "коррози": ["корпус"],
        "трещин": ["корпус", "вал"],
        "разруш": ["шестерн", "зуб"],
        "выкрашиван": ["шестерн", "зуб"],
        "задир": ["вал", "шестерн"],
        "деформац": ["вал", "корпус"],
        "ржав": ["корпус"],
        "люфт": ["вал", "подшипник"],
        "биение": ["вал"],
        "стук": ["подшипник"],
        "вибрац": ["подшипник"],
        "зазор": ["радиальн", "осев", "подшипник", "сальник"]
    }
    
    found_defects = []
    sentences = re.split(r'[,.!?;]', text)
    for sentence in sentences:
        sentence_lower = sentence.lower().strip()
        if not sentence_lower:
            continue
        for keyword, contexts in defect_keywords.items():
            if keyword in sentence_lower:
                for context in contexts:
                    if context in sentence_lower:
                        defect_desc = sentence.strip()
                        if keyword == "зазор":
                            for ct in ["радиальн", "осев", "подшипник", "сальник"]:
                                if ct in sentence_lower:
                                    defect_desc = f"{keyword} {ct}: {sentence.strip()}"
                                    break
                        found_defects.append(defect_desc)
                        break
                break
    
    if found_defects:
        return found_defects
    
    # 3. Если есть описание зазоров
    if "зазор" in text_lower:
        clearances = extract_clearances_from_text(text)
        for c in clearances:
            found_defects.append(f"зазор {c['type']}: {c['value']} мм")
        return found_defects
    
    # 4. Если ничего не нашли
    return []

def parse_works_for_avr(text):
    """Парсит выполненные работы для АВР — структурированно"""
    works = []
    text_lower = text.lower()
    
    # Убираем маркеры "АВР", "сделай авр" и т.д.
    clean_text = re.sub(r'(авр|акт выполненных|сделай авр|создай авр|оформи авр)\s*', '', text_lower, flags=re.IGNORECASE)
    clean_text = re.sub(r'по судну\s+\w+\s*', '', clean_text)
    clean_text = re.sub(r'судно\s+\w+\s*', '', clean_text)
    clean_text = clean_text.strip()
    
    # Разбиваем на работы по номерам или маркерам
    lines = re.split(r'\n|\.\s+|;\s+', clean_text)
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if len(line) < 5:
            continue
        
        # Пытаемся извлечь работу
        work = {"name": "", "description": "", "quantity": "", "unit": "", "note": ""}
        
        # Ищем количество
        quantity_match = re.search(r'(\d+)\s*(шт|компл|м|кг|л|шт\.|компл\.|м\.|кг\.|л\.)', line)
        if quantity_match:
            work["quantity"] = quantity_match.group(1)
            work["unit"] = quantity_match.group(2).replace('.', '')
            line = line.replace(quantity_match.group(0), '').strip()
        
        # Ищем примечание (в скобках)
        note_match = re.search(r'\([^)]+\)', line)
        if note_match:
            work["note"] = note_match.group(0).strip('()')
            line = line.replace(note_match.group(0), '').strip()
        
        # Разделяем на название и описание
        if ':' in line or '—' in line or '-' in line:
            parts = re.split(r':\s*|—\s*|-\s*', line, 1)
            if len(parts) == 2:
                work["name"] = parts[0].strip().capitalize()
                work["description"] = parts[1].strip().capitalize()
            else:
                work["description"] = line.capitalize()
        else:
            # Если нет разделителя, пробуем определить по контексту
            if any(word in line for word in ["замена", "ремонт", "восстановлен", "изготовлен", "монтаж", "демонтаж"]):
                work["name"] = "Ремонтные работы"
                work["description"] = line.capitalize()
            else:
                work["description"] = line.capitalize()
        
        if work["name"] or work["description"]:
            if not work["unit"]:
                work["unit"] = "компл." if not work["quantity"] else ""
            works.append(work)
    
    # Если ничего не нашли, но текст есть — создаём одну работу
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
    
    # Если есть зазоры - добавляем их в дефекты
    if result["clearances"] and not result["defects"]:
        for c in result["clearances"]:
            result["defects"].append(f"зазор {c['type']}: {c['value']} мм")
    
    # Если оборудование не определено, но есть насос
    if not result["equipment"] and "насос" in text.lower():
        pump_type = "шестерёнчатый" if result["pump_type"] == "gear" else "центробежный" if result["pump_type"] else ""
        result["equipment"] = f"насос {pump_type}".strip() if pump_type else "насос"
    
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
        pump_name = "центробежный" if pump_type == "centrifugal" else "шестерёнчатый"
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
#  СОЗДАНИЕ ДОКУМЕНТОВ
# ============================================================

def create_defect_document(ship, equipment, defects, work_volume):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(11)

    # Шапка
    for text in [
        "ООО «Новое время»",
        "692906, Приморский край, г. Находка, ул. Первая, зд. 1Б",
        "тел.: +7 (423) 662-97-79",
        "СПП № 24.44.01.01544.171 до 01.08.2028 г."
    ]:
        p = doc.add_paragraph()
        p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        run = p.add_run(text)
        if "ООО" in text:
            run.bold = True
            run.font.size = Pt(14)
        else:
            run.font.size = Pt(11)

    doc.add_paragraph()

    # Заголовок
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run = p.add_run('АКТ ДЕФЕКТАЦИИ')
    run.bold = True
    run.font.size = Pt(15)

    date_str = datetime.now().strftime('%d.%m.%Y')
    ship_code = ship[:3].upper() if ship else "XXX"
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p.add_run(f'№ {ship_code}-ДА-{datetime.now().strftime("%y")}-01').font.size = Pt(12)

    doc.add_paragraph(f'г. Находка        {date_str} г.')
    doc.add_paragraph(f'Судно: Т/х «{ship or "Не указано"}»')
    doc.add_paragraph(f'Оборудование: {equipment or "Не указано"}')
    doc.add_paragraph(f'Объект работ: Текущий ремонт')
    doc.add_paragraph()

    # Таблица
    doc.add_paragraph('Произведён осмотр. Выявлены следующие дефекты и определён объём работ, подлежащих выполнению.')
    table = doc.add_table(rows=2, cols=7)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    headers = ['№', 'Позиция', 'Дефект / Состояние', 'Объём работ', 'Ед. изм', 'Кол-во', 'Примечание']
    for i, header in enumerate(headers):
        hdr_cells[i].text = header

    row = table.rows[1].cells
    row[0].text = '1'
    row[1].text = equipment or "Не указано"
    # Формируем красивое описание дефектов
    if defects:
        defect_text = "\n".join([f"• {d}" for d in defects])
    else:
        defect_text = "Не указано"
    row[2].text = defect_text
    row[3].text = work_volume
    row[4].text = 'компл.'
    row[5].text = '1'
    row[6].text = '---'

    # Заключение
    doc.add_paragraph()
    doc.add_paragraph('Заключение дефектационной комиссии:')
    doc.add_paragraph('Детали подлежат замене/восстановлению согласно указанному объёму работ.')

    doc.add_paragraph()
    p = doc.add_paragraph('Представитель подрядчика:')
    p.add_run(' Инженер-технолог / Мастер участка    / *[ФИО]* /')

    p = doc.add_paragraph('Представитель заказчика:')
    p.add_run(f'Старший механик т/х «{ship or "Не указано"}»    / *[ФИО]* /')

    file_stream = BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream

def create_avr_document(ship, works, executor="ООО «Новое время»", customer="АО «Бункерная компания»", location="Рейд 4ый район, г. Находка"):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(11)

    # Шапка
    for text in [
        "ООО «Новое время»",
        "692906, Приморский край, г. Находка, ул. Первая, зд. 1Б",
        "тел.: +7 (423) 662-97-79",
        "СПП № 24.44.01.01544.171 до 01.08.2028 г."
    ]:
        p = doc.add_paragraph()
        p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        run = p.add_run(text)
        if "ООО" in text:
            run.bold = True
            run.font.size = Pt(14)
        else:
            run.font.size = Pt(11)

    doc.add_paragraph()

    # Заголовок
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run = p.add_run('АКТ ВЫПОЛНЕННЫХ РАБОТ')
    run.bold = True
    run.font.size = Pt(15)

    date_str = datetime.now().strftime('%d.%m.%Y')
    ship_code = ship[:3].upper() if ship else "XXX"
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p.add_run(f'№ {ship_code}-АВР-{datetime.now().strftime("%y")}-01').font.size = Pt(12)
    
    doc.add_paragraph(f'г. Находка        {date_str} г.')
    doc.add_paragraph()
    
    # Реквизиты
    doc.add_paragraph(f'Исполнитель: {executor}')
    doc.add_paragraph(f'Заказчик: {customer}')
    doc.add_paragraph(f'Судно: Т/х «{ship or "Не указано"}»')
    doc.add_paragraph(f'Место стоянки: {location}')
    doc.add_paragraph()

    # Таблица
    doc.add_paragraph('Выполнены следующие работы:')
    table = doc.add_table(rows=1, cols=6)
    table.style = 'Table Grid'
    
    # Заголовки
    hdr_cells = table.rows[0].cells
    headers = ['№ п/п', 'Наименование работ', 'Описание выполненных работ', 'Кол-во', 'Ед. изм.', 'Примечание']
    for i, header in enumerate(headers):
        hdr_cells[i].text = header
    
    # Данные
    if works:
        for i, work in enumerate(works, 1):
            row = table.add_row().cells
            row[0].text = str(i)
            row[1].text = work.get('name', '')
            row[2].text = work.get('description', '')
            row[3].text = str(work.get('quantity', ''))
            row[4].text = work.get('unit', '')
            row[5].text = work.get('note', '')
    
    doc.add_paragraph()

    # Подписи
    doc.add_paragraph('Представитель подрядчика:')
    doc.add_paragraph('Инженер-технолог / Мастер участка    / *[ФИО]* /')
    doc.add_paragraph(f'Дата: {date_str}')
    doc.add_paragraph()
    
    doc.add_paragraph('Представитель заказчика:')
    doc.add_paragraph('Должность    / *[ФИО]* /')
    doc.add_paragraph(f'Дата: {date_str}')
    doc.add_paragraph()
    doc.add_paragraph('М.П.    М.П.')

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
        "• Показывать частые дефекты (спроси 'какие дефекты')\n\n"
        "📝 Примеры:\n"
        "• 'Судно Аргака, масляный насос шестеренчатый, дефекты: износ зубьев, зазор радиальный 0.4. Сделай акт'\n"
        "• 'АВР: Кабель-трасса: замена уголков 44 шт, болтов 194 шт. Предъявили л/с.'"
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
    
    # ---- 1. АВР ----
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
    
    # ---- 2. ПРОВЕРКА ЗАЗОРОВ ----
    if any(word in text_lower for word in ['проверь зазор', 'проверка зазора', 'какой зазор', 'норма зазора']):
        clearances = extract_clearances_from_text(user_text)
        if clearances:
            responses = []
            for c in clearances:
                if c['type'] != 'unknown':
                    pump_type = detect_pump_type(user_text)
                    if not pump_type:
                        pump_type = "gear" if "шестерен" in text_lower else "centrifugal"
                    result = pump_db.check_clearance(pump_type, c['type'], c['value'])
                    responses.append(f"🔹 {c['type']}: {c['value']} мм -> {result['message']}")
            if responses:
                response = "📊 **Результаты проверки зазоров:**\n\n" + "\n".join(responses)
                bot.reply_to(message, response, parse_mode='Markdown')
                return
        
        bot.reply_to(message,
            "🔧 Чтобы проверить зазор, напишите:\n"
            "`проверь зазор радиальный 0.25`\n"
            "`шестерёнчатый осевой 0.4`"
        )
        return
    
    # ---- 3. ДЕФЕКТЫ ----
    if any(word in text_lower for word in ['какие дефекты', 'частые дефекты', 'список дефектов', 'дефекты бывают']):
        pump_type = detect_pump_type(text_lower)
        if pump_type:
            pump_name = "центробежном" if pump_type == "centrifugal" else "шестерёнчатом"
            defects = pump_db.get_common_defects(pump_type)
            response = f"📋 **Частые дефекты {pump_name} насоса:**\n\n"
            for i, defect in enumerate(defects, 1):
                method = pump_db.get_repair_method(pump_type, defect)
                method_text = f" -> {method}" if method else ""
                response += f"{i}. {defect}{method_text}\n"
            bot.reply_to(message, response, parse_mode='Markdown')
            return
        else:
            bot.reply_to(message, "📌 Уточните тип насоса: центробежный или шестерёнчатый")
            return
    
    # ---- 4. АКТ ДЕФЕКТАЦИИ ----
    wants_act = any(word in text_lower for word in ['акт', 'дефектовк', 'сделай акт', 'оформи', 'составь', 'создай'])
    
    if wants_act:
        analysis = analyze_query(user_text)
        
        ship = analysis.get('ship')
        equipment = analysis.get('equipment')
        defects = analysis.get('defects', [])
        pump_type = analysis.get('pump_type')
        clearances = analysis.get('clearances', [])
        
        # Добавляем зазоры в дефекты
        for c in clearances:
            defect_text = f"зазор {c['type']}: {c['value']} мм"
            if defect_text not in defects:
                defects.append(defect_text)
        
        # Если дефектов нет - ищем ключевые слова
        if not defects:
            for kw in ["износ", "течь", "коррози", "трещин", "выкрашиван", "задир", "деформац", "люфт"]:
                if kw in text_lower:
                    defects.append(kw)
            if not defects:
                bot.reply_to(message,
                    "🤔 Я не нашёл дефектов в вашем сообщении.\n"
                    "Опишите дефекты: 'износ подшипников, течь сальника'"
                )
                return
        
        if not equipment:
            pump_name = "шестерёнчатый" if pump_type == "gear" else "центробежный" if pump_type else ""
            equipment = f"насос {pump_name}".strip() if pump_name else "насос"
        
        work_volume = generate_work_volume(defects, user_text, pump_type)
        file_stream = create_defect_document(ship, equipment, defects, work_volume)
        bot.send_document(
            message.chat.id, 
            file_stream, 
            visible_file_name=f'Акт_дефектации_{ship or "судна"}.docx'
        )
        bot.send_message(message.chat.id, "📄 Акт дефектации в Word отправлен!")
        return
    
    # ---- 5. НЕПОНЯТНО ----
    bot.reply_to(message,
        "🤔 Я не понял запрос.\n\n"
        "Что нужно?\n"
        "📄 Акт дефектации — 'сделай акт'\n"
        "📋 АВР — 'сделай АВР'\n"
        "🔧 Проверить зазор — 'проверь зазор'\n"
        "📋 Дефекты — 'какие дефекты у насоса'"
    )

# ============================================================
#  ЗАПУСК
# ============================================================

if __name__ == '__main__':
    print("🤖 Бот-ассистент запущен!")
    bot.infinity_polling()