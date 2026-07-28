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

# --- Упрощённый анализ запроса (без AI) ---
def simple_analyze(text):
    text_lower = text.lower()
    result = {
        "document_type": "unknown",
        "ship": None,
        "equipment": None,
        "defects": [],
        "measurements": []
    }
    
    # 1. Определяем тип документа
    if "акт" in text_lower or "дефектовк" in text_lower:
        result["document_type"] = "defect"
    elif "авр" in text_lower or "выполненных" in text_lower:
        result["document_type"] = "avr"
    else:
        # Если нет явных слов, но есть описание дефектов — считаем дефектовкой
        if any(word in text_lower for word in ["слом", "износ", "течь", "коррози", "трещин", "разруш"]):
            result["document_type"] = "defect"
    
    # 2. Ищем судно (по ключевым словам)
    ships = ["аргака", "пластун", "славянская", "первоуральск"]
    for ship in ships:
        if ship in text_lower:
            result["ship"] = ship.capitalize()
            break
    
    # 3. Ищем оборудование (пытаемся найти что-то после "насос", "двигатель" и т.д.)
    equipment_keywords = ["насос", "двигатель", "компрессор", "вентилятор", "генератор", "кран", "лебедка"]
    for kw in equipment_keywords:
        if kw in text_lower:
            # Берём слово перед ключевым или после
            parts = re.split(r'[,.!?;]', text)
            for part in parts:
                if kw in part.lower():
                    result["equipment"] = part.strip()
                    break
            if result["equipment"]:
                break
    
    # 4. Ищем дефекты (ключевые слова)
    defect_keywords = ["износ", "течь", "коррози", "трещин", "разруш", "слом", "задир", "деформац", "ржав"]
    for defect in defect_keywords:
        if defect in text_lower:
            # Извлекаем фразу с дефектом
            for sentence in re.split(r'[,.!?;]', text):
                if defect in sentence.lower():
                    result["defects"].append(sentence.strip())
                    break
    
    if not result["defects"] and result["document_type"] != "unknown":
        result["defects"] = ["Дефекты не указаны, требуется уточнение"]
    
    return result

# --- Функция генерации объёма работ через AI ---
def generate_work_volume(defects):
    if not GROQ_API_KEY or not defects:
        return "Демонтаж, разборка, дефектация, замена/восстановление, сборка, монтаж, предъявление л/с."
    
    try:
        client = httpx.Client(timeout=30.0)
        defect_text = "; ".join(defects)
        prompt = f"Составь объём работ для дефектов: {defect_text}. Включи демонтаж, разборку, замену/восстановление, сборку, монтаж, предъявление л/с. Отвечай коротко."
        
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
            return "Демонтаж, разборка, дефектация, замена/восстановление, сборка, монтаж, предъявление л/с."
    except Exception as e:
        print(f"Ошибка генерации: {e}")
        return "Демонтаж, разборка, дефектация, замена/восстановление, сборка, монтаж, предъявление л/с."

# --- Функция создания Акта дефектации (Word) ---
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

# --- Обработчик всех текстовых сообщений ---
@bot.message_handler(func=lambda message: True)
def handle_intelligent_input(message):
    user_text = message.text
    if user_text.startswith('/'):
        return

    # 1. Упрощённый анализ
    analysis = simple_analyze(user_text)
    doc_type = analysis.get('document_type', 'unknown')
    ship = analysis.get('ship')
    equipment = analysis.get('equipment')
    defects = analysis.get('defects', [])

    if doc_type == 'unknown':
        bot.reply_to(message, "🤔 Не понял запрос. Я умею делать Акты дефектации.\n\n"
                              "Пример: *Судно Аргака, пожарный насос, износ подшипников, течь сальника. Сделай акт.*\n"
                              "Или просто опишите ситуацию.")
        return

    # 2. Генерация акта
    work_volume = generate_work_volume(defects)
    file_stream = create_defect_document(ship, equipment, defects, work_volume)
    bot.send_document(message.chat.id, file_stream, visible_file_name=f'Акт_дефектации_{ship or "судна"}.docx')
    bot.send_message(message.chat.id, "📄 Акт дефектации в Word отправлен!")

# --- Команда /start ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 Привет! Я — твой инженерный ассистент.\n"
                          "Просто опиши задачу, и я создам Акт дефектации.\n\n"
                          "📌 Пример: 'Судно Аргака, пожарный насос, износ подшипников, течь сальника. Сделай акт.'")

# --- Запуск ---
if __name__ == '__main__':
    print("Бот-ассистент запущен!")
    bot.infinity_polling()