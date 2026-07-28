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

# --- Анализ запроса ---
def analyze_query(text):
    text_lower = text.lower()
    result = {
        "ship": None,
        "equipment": None,
        "defects": [],
        "full_text": text
    }

    # 1. Ищем судно (по ключевым словам)
    ships = ["аргака", "пластун", "славянская", "первоуральск"]
    for ship in ships:
        if ship in text_lower:
            result["ship"] = ship.capitalize()
            break

    # 2. Ищем оборудование (берём фразу между "судно" и "дефекты")
    # Простой вариант: ищем "насос", "двигатель" и т.д.
    equipment_keywords = ["насос", "двигатель", "компрессор", "вентилятор", "генератор", "кран", "лебедка", "редуктор"]
    for kw in equipment_keywords:
        if kw in text_lower:
            # Берём 3 слова до и после ключевого
            pattern = r'(\w+\s+){0,2}' + kw + r'(\s+\w+){0,2}'
            match = re.search(pattern, text)
            if match:
                result["equipment"] = match.group(0).strip()
                break

    # 3. Определяем дефекты — всё, что находится после слов "дефекты", "зазоры", "проблемы" или в конце текста
    # Если есть явное упоминание "дефекты:", берём текст после
    if "дефекты" in text_lower:
        defect_part = re.split(r'дефекты[:;]', text_lower, flags=re.IGNORECASE)
        if len(defect_part) > 1:
            result["defects"].append(defect_part[1].strip())
    else:
        # Иначе ищем фразы с типичными словами дефектов
        defect_keywords = ["износ", "течь", "коррози", "трещин", "разруш", "зазор", "выкрашиван", "задир", "деформац", "ржав"]
        found_defects = []
        for sentence in re.split(r'[,.!?;]', text):
            for kw in defect_keywords:
                if kw in sentence.lower():
                    found_defects.append(sentence.strip())
                    break
        if found_defects:
            result["defects"] = found_defects

    # Если дефекты не найдены, но запрос похож на дефектовку — используем весь текст как описание
    if not result["defects"] and any(word in text_lower for word in ["акт", "дефектовк"]):
        result["defects"] = [text]

    return result

# --- Генерация объёма работ через AI ---
def generate_work_volume(defects, full_text):
    if not GROQ_API_KEY:
        return "Демонтаж, разборка, дефектация, замена/восстановление, сборка, монтаж, предъявление л/с."

    try:
        client = httpx.Client(timeout=30.0)
        defect_text = "\n".join(defects) if defects else full_text

        prompt = f"""
На основе описания дефектов составь подробный объём работ для ремонта судового оборудования.

Описание дефектов:
{defect_text}

Обязательно включи в объём работ:
1. Демонтаж узла.
2. Разборку и дефектацию.
3. Замену или восстановление деталей.
4. Сборку.
5. Монтаж.
6. Предъявление лицу сдающему.

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
            return "Демонтаж, разборка, дефектация, замена/восстановление, сборка, монтаж, предъявление л/с."
    except Exception as e:
        print(f"Ошибка генерации: {e}")
        return "Демонтаж, разборка, дефектация, замена/восстановление, сборка, монтаж, предъявление л/с."

# --- Создание Акта дефектации (Word) ---
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

# --- Обработчик сообщений ---
@bot.message_handler(func=lambda message: True)
def handle_intelligent_input(message):
    user_text = message.text
    if user_text.startswith('/'):
        return

    # 1. Анализ запроса
    analysis = analyze_query(user_text)
    ship = analysis.get('ship')
    equipment = analysis.get('equipment')
    defects = analysis.get('defects', [])
    full_text = analysis.get('full_text', user_text)

    # 2. Если запрос не похож на дефектовку
    if not defects and not any(word in user_text.lower() for word in ["акт", "дефектовк", "ремонт", "судно"]):
        bot.reply_to(message, "🤔 Я создаю Акты дефектации. Напишите что-то вроде:\n"
                              "«Судно Аргака, насос, износ подшипников, течь сальника. Сделай акт.»")
        return

    # 3. Генерация объёма работ
    work_volume = generate_work_volume(defects, full_text)

    # 4. Создание документа
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