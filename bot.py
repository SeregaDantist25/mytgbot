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
                "message": f"❌ Данные по зазору '{clearance_type}' для '{pump_type}' отсутствуют",
                "action": "Проверьте правильность ввода"
            }
        
        standard = clearance_data["standard"]
        max_allowed = clearance_data["max_allowed"]
        repair_after = clearance_data.get("repair_after", "Требуется ремонт")
        
        if measured_value < standard["min"]:
            return {
                "status": "warning",
                "message": f"⚠️ Зазор МЕНЬШЕ нормы: {measured_value} мм (норма: {standard['min']}-{standard['max']} мм)",
                "action": "Проверьте точность измерения"
            }
        elif measured_value <= standard["max"]:
            return {
                "status": "ok",
                "message": f"✅ Зазор В НОРМЕ: {measured_value} мм (норма: {standard['min']}-{standard['max']} мм)",
                "action": "Деталь работоспособна"
            }
        elif measured_value <= max_allowed:
            return {
                "status": "critical",
                "message": f"🔴 Зазор ПРЕВЫШЕН (допустимый предел): {measured_value} мм (макс: {max_allowed} мм)",
                "action": f"⚠️ Рекомендуется ремонт: {repair_after}"
            }
        else:
            return {
                "status": "fatal",
                "message": f"❌ Зазор КРИТИЧЕСКИ превышен: {measured_value} мм (макс: {max_allowed} мм)",
                "action": f"🚨 Требуется срочная замена: {repair_after}"
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
#  ФУНКЦИИ АНАЛИЗА И РАСПОЗНАВАНИЯ
# ============================================================

def detect_pump_type(text):
    """Определяет тип насоса по тексту"""
    text_lower = text.lower()
    if any(word in text_lower for word in ["центробеж", "центр"]):
        return "centrifugal"
    elif any(word in text_lower for word in ["шестерен", "ротан", "rotan", "зубчат"]):
        return "gear"
    return None

def extract_clearance_request(text):
    """Извлекает данные для проверки зазора из текста"""
    text_lower = text.lower()
    
    # Определяем тип насоса
    pump_type = detect_pump_type(text_lower)
    if not pump_type:
        return None
    
    # Определяем вид зазора
    clearance_types = ["radial", "axial", "bearing", "seal"]
    clearance_type = None
    for ct in clearance_types:
        if ct in text_lower:
            clearance_type = ct
            break
    
    if not clearance_type:
        return None
    
    # Ищем число (значение зазора)
    numbers = re.findall(r'(\d+\.?\d*)', text_lower)
    if not numbers:
        return None
    
    value = float(numbers[0])
    
    return {
        "pump_type": pump_type,
        "clearance_type": clearance_type,
        "value": value
    }

def detect_ship(text):
    """Определяет судно по тексту"""
    text_lower = text.lower()
    ships = ["аргака", "пластун", "славянская", "первоуральск", "керчь", "краснодар"]
    for ship in ships:
        if ship in text_lower:
            return ship.capitalize()
    return None

def extract_equipment(text):
    """Извлекает название оборудования"""
    text_lower = text.lower()
    equipment_keywords = ["насос", "двигатель", "компрессор", "вентилятор", 
                         "генератор", "кран", "лебедка", "редуктор"]
    for kw in equipment_keywords:
        if kw in text_lower:
            pattern = r'(\w+\s+){0,2}' + kw + r'(\s+\w+){0,2}'
            match = re.search(pattern, text)
            if match:
                return match.group(0).strip()
    return None

def extract_defects(text):
    """Извлекает дефекты из текста"""
    text_lower = text.lower()
    defects = []
    
    # Если есть явное "дефекты:"
    if "дефекты" in text_lower:
        defect_part = re.split(r'дефекты[:;]', text_lower, flags=re.IGNORECASE)
        if len(defect_part) > 1:
            # Разбиваем на отдельные дефекты
            parts = defect_part[1].strip().split(',')
            defects = [p.strip() for p in parts if p.strip()]
            return defects
    
    # Ищем по ключевым словам
    defect_keywords = ["износ", "течь", "коррози", "трещин", "разруш", 
                      "зазор", "выкрашиван", "задир", "деформац", "ржав",
                      "люфт", "биение", "стук", "вибрац"]
    found_defects = []
    for sentence in re.split(r'[,.!?;]', text):
        for kw in defect_keywords:
            if kw in sentence.lower():
                found_defects.append(sentence.strip())
                break
    
    if found_defects:
        return found_defects
    
    return defects

# ============================================================
#  ГЕНЕРАЦИЯ ОБЪЁМА РАБОТ
# ============================================================

def generate_work_volume(defects, full_text, pump_type=None):
    """Генерирует объём работ с учётом базы данных"""
    
    # Если есть AI - используем его
    if GROQ_API_KEY:
        try:
            return generate_with_ai(defects, full_text, pump_type)
        except Exception as e:
            print(f"Ошибка AI: {e}")
    
    # Иначе используем базу данных
    return generate_from_database(defects, pump_type)

def generate_with_ai(defects, full_text, pump_type):
    """Генерация через Groq AI"""
    client = httpx.Client(timeout=30.0)
    defect_text = "\n".join(defects) if defects else full_text
    
    # Добавляем информацию из базы
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

Обязательно включи в объём работ:
1. Демонтаж узла
2. Разборку и дефектацию
3. Замену или восстановление деталей (с учётом типовых дефектов)
4. Сборку с проверкой зазоров
5. Монтаж
6. Предъявление лицу сдающему

Отвечай в виде нумерованного списка, коротко и по делу.
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
    
    # Добавляем методы ремонта из базы
    if pump_type and defects:
        methods = []
        for defect in defects:
            method = pump_db.get_repair_method(pump_type, defect)
            if method:
                methods.append(method)
        if methods:
            # Убираем дубликаты
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

    doc.add_paragraph(f'г. Находка / борт т/х «{ship or "Не указано"}»        {date_str}')
    doc.add_paragraph(f'Судно: Т/х «{ship or "Не указано"}»')
    doc.add_paragraph(f'Оборудование: {equipment or "Не указано"}')
    doc.add_paragraph(f'Объект работ: Текущий ремонт')
    doc.add_paragraph()

    # Таблица
    doc.add_paragraph('Произведён осмотр. Выявлены следующие дефекты и определён объём работ:')
    table = doc.add_table(rows=2, cols=4)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = '№'
    hdr_cells[1].text = 'Позиция'
    hdr_cells[2].text = 'Дефект / Состояние'
    hdr_cells[3].text = 'Объём работ'

    row = table.rows[1].cells
    row[0].text = '1'
    row[1].text = equipment or "Не указано"
    row[2].text = "\n".join(defects) if defects else "Не указано"
    row[3].text = work_volume

    # Заключение и подписи
    doc.add_paragraph()
    doc.add_paragraph('Заключение дефектационной комиссии:')
    doc.add_paragraph('Детали подлежат замене/восстановлению согласно указанному объёму работ.')

    doc.add_paragraph()
    p = doc.add_paragraph('Представитель подрядчика (Исполнитель):')
    p.add_run(' Инженер-технолог / Мастер участка		/ *[ФИО]* /')

    p = doc.add_paragraph('Представитель заказчика (Судовладелец / Экипаж):')
    p.add_run(f'Старший механик т/х «{ship or "Не указано"}»		/ *[ФИО]* /')

    file_stream = BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream

# ============================================================
#  ОБРАБОТЧИКИ СООБЩЕНИЙ
# ============================================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, 
        "👋 Привет! Я — твой инженерный ассистент.\n\n"
        "📌 Что я умею:\n"
        "• Создавать Акты дефектации (просто опиши проблему)\n"
        "• Проверять зазоры по ТУ (напиши 'проверь зазор')\n"
        "• Показывать частые дефекты (спроси про насос)\n"
        "• Давать рекомендации по ремонту\n\n"
        "💬 Просто пиши на естественном языке — я пойму!\n\n"
        "📝 Примеры:\n"
        "• 'Судно Аргака, насос центробежный, износ подшипников'\n"
        "• 'Проверь зазор центробежный радиальный 0.25'\n"
        "• 'Какие дефекты бывают у шестерёнчатого насоса?'"
    )

# ============================================================
#  ГЛАВНЫЙ ОБРАБОТЧИК (СВОБОДНОЕ ОБЩЕНИЕ)
# ============================================================

@bot.message_handler(func=lambda message: True)
def handle_intelligent_input(message):
    user_text = message.text
    text_lower = user_text.lower()
    
    # Если команда — пропускаем
    if user_text.startswith('/'):
        return
    
    # ---- 1. ПРОВЕРКА ЗАЗОРОВ ----
    if any(word in text_lower for word in ['зазор', 'допуск', 'проверь', 'норма']):
        clearance_data = extract_clearance_request(user_text)
        if clearance_data:
            result = pump_db.check_clearance(
                clearance_data["pump_type"],
                clearance_data["clearance_type"],
                clearance_data["value"]
            )
            
            response = f"📊 **Результат проверки зазора**\n\n"
            response += f"🔹 Тип насоса: {clearance_data['pump_type']}\n"
            response += f"🔹 Вид зазора: {clearance_data['clearance_type']}\n"
            response += f"🔹 Измеренное значение: {clearance_data['value']} мм\n\n"
            response += f"{result['message']}\n\n"
            response += f"🔧 **Рекомендация:** {result['action']}"
            
            bot.reply_to(message, response, parse_mode='Markdown')
            return
        else:
            bot.reply_to(message,
                "🔧 Чтобы проверить зазор, напишите в формате:\n"
                "`центробежный радиальный 0.25`\n"
                "`шестерёнчатый осевой 0.4`\n\n"
                "Доступные зазоры: radial, axial, bearing, seal",
                parse_mode='Markdown'
            )
            return
    
    # ---- 2. ИНФОРМАЦИЯ О ДЕФЕКТАХ ----
    if any(word in text_lower for word in ['дефект', 'неисправн', 'поломк', 'часто бывает', 'какие']):
        pump_type = detect_pump_type(text_lower)
        if pump_type:
            pump_name = "центробежном" if pump_type == "centrifugal" else "шестерёнчатом"
            defects = pump_db.get_common_defects(pump_type)
            response = f"📋 **Частые дефекты {pump_name} насоса:**\n\n"
            for i, defect in enumerate(defects, 1):
                # Добавляем метод ремонта
                method = pump_db.get_repair_method(pump_type, defect)
                method_text = f" → {method}" if method else ""
                response += f"{i}. {defect}{method_text}\n"
            bot.reply_to(message, response, parse_mode='Markdown')
            return
        else:
            bot.reply_to(message,
                "📌 Уточните тип насоса:\n"
                "• центробежный\n"
                "• шестерёнчатый (ротан)\n\n"
                "Например: 'дефекты центробежного насоса'"
            )
            return
    
    # ---- 3. НОРМАТИВЫ ЗАЗОРОВ ----
    if any(word in text_lower for word in ['норматив', 'норма', 'ту', 'техническ']):
        response = "📐 **Нормативы зазоров по ТУ**\n\n"
        for pump_type in pump_db.get_pump_types():
            pump_name = "Центробежный" if pump_type == "centrifugal" else "Шестерёнчатый"
            response += f"**{pump_name} насос:**\n"
            clearances = pump_db.centrifugal["clearances"] if pump_type == "centrifugal" else pump_db.gear["clearances"]
            for ct, data in clearances.items():
                std = data["standard"]
                response += f"  • {ct}: {std['min']}-{std['max']} {std['unit']}\n"
            response += "\n"
        bot.reply_to(message, response, parse_mode='Markdown')
        return
    
    # ---- 4. СОЗДАНИЕ АКТА ДЕФЕКТАЦИИ ----
    if any(word in text_lower for word in ['акт', 'дефектовк', 'сделай акт', 'оформи', 'составь']):
        # Анализируем запрос
        ship = detect_ship(user_text)
        equipment = extract_equipment(user_text)
        defects = extract_defects(user_text)
        pump_type = detect_pump_type(user_text)
        
        # Если нет дефектов, но есть описание — используем весь текст
        if not defects and any(word in text_lower for word in ["ремонт", "судно", "насос"]):
            defects = [user_text]
        
        if not defects:
            bot.reply_to(message, 
                "🤔 Я не нашёл дефектов в вашем сообщении.\n"
                "Пожалуйста, опишите дефекты подробнее.\n\n"
                "Пример: 'Судно Аргака, насос центробежный, износ подшипников и течь сальника'"
            )
            return
        
        # Генерируем объём работ
        work_volume = generate_work_volume(defects, user_text, pump_type)
        
        # Создаём документ
        file_stream = create_defect_document(ship, equipment, defects, work_volume)
        bot.send_document(
            message.chat.id, 
            file_stream, 
            visible_file_name=f'Акт_дефектации_{ship or "судна"}.docx'
        )
        bot.send_message(message.chat.id, "📄 Акт дефектации в Word отправлен!")
        return
    
    # ---- 5. СПРАВКА ПО НАСОСАМ ----
    if any(word in text_lower for word in ['насос', 'помп']):
        pump_type = detect_pump_type(text_lower)
        if pump_type:
            pump_name = "центробежный" if pump_type == "centrifugal" else "шестерёнчатый"
            response = f"📌 **Информация о {pump_name} насосе**\n\n"
            
            # Основные характеристики
            if pump_type == "centrifugal":
                response += "• Рабочее колесо (крыльчатка)\n"
                response += "• Корпус улиточного типа\n"
                response += "• Подшипники качения\n"
                response += "• Сальниковое уплотнение\n\n"
            else:
                response += "• Две шестерни (ведущая и ведомая)\n"
                response += "• Корпус с перепускным клапаном\n"
                response += "• Подшипники скольжения\n"
                response += "• Торцевое уплотнение\n\n"
            
            response += "💡 Для проверки зазоров используйте:\n"
            response += f"  `{pump_type} radial 0.15`\n"
            response += f"  `{pump_type} axial 0.3`\n"
            
            bot.reply_to(message, response, parse_mode='Markdown')
            return
    
    # ---- 6. НЕПОНЯТНЫЙ ЗАПРОС ----
    bot.reply_to(message,
        "🤔 Я не совсем понял ваш запрос.\n\n"
        "Вот что я умею:\n"
        "📄 **Создать акт дефектации**\n"
        "  → Опишите судно и дефекты\n\n"
        "🔧 **Проверить зазор**\n"
        "  → Напишите 'центробежный радиальный 0.25'\n\n"
        "📋 **Показать дефекты**\n"
        "  → Спросите 'дефекты шестерёнчатого насоса'\n\n"
        "📐 **Показать нормативы**\n"
        "  → Спросите 'нормативы зазоров'\n\n"
        "💬 Просто пишите на русском — я пойму!"
    )

# ============================================================
#  ЗАПУСК
# ============================================================

if __name__ == '__main__':
    print("🤖 Бот-ассистент запущен!")
    print("📌 Доступные функции:")
    print("  • Создание актов дефектации")
    print("  • Проверка зазоров по ТУ")
    print("  • Информация о дефектах")
    print("  • Нормативы зазоров")
    print("  • Свободное общение")
    bot.infinity_polling()