import os
import telebot
from telebot.handler_backends import State, StatesGroup
from telebot import custom_filters
import httpx
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from io import BytesIO
import json
import re

# --- Настройки ---
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

if not BOT_TOKEN:
    raise ValueError("Переменная TELEGRAM_BOT_TOKEN не найдена!")

bot = telebot.TeleBot(BOT_TOKEN)
bot.add_custom_filter(custom_filters.StateFilter(bot))

# --- Системные промпты для AI (язык запроса к Groq) ---
SYSTEM_PROMPT_ANALYZE = """
Ты — интеллектуальный помощник инженера-технолога судоремонтного предприятия.
Проанализируй запрос пользователя и верни результат строго в формате JSON.

Поля JSON:
- "document_type": тип документа (defect, avr, tech, unknown)
- "ship": название судна (если указано, иначе null)
- "equipment": название оборудования (если указано, иначе null)
- "defects": список дефектов (если есть, иначе [])
- "measurements": список замеров (если есть, иначе [])
- "summary": краткое описание работ (для АВР)

Пример 1:
Запрос: "Судно Аргака, фекальный насос, разрушена крылатка, ржавый крепеж, вал. Сделай акт дефектации и АВР."
Ответ: {"document_type": "defect", "ship": "Аргака", "equipment": "фекальный насос", "defects": ["разрушена крылатка", "ржавый крепеж", "коцаный вал"], "measurements": [], "summary": "Ремонт фекального насоса"}

Пример 2:
Запрос: "Сделай акт выполненных работ по пластуну, заменили сальники и подшипники"
Ответ: {"document_type": "avr", "ship": "Пластун", "equipment": "насос", "defects": [], "measurements": [], "summary": "Замена сальников и подшипников"}

Пример 3:
Запрос: "Привет, как дела?"
Ответ: {"document_type": "unknown", "ship": null, "equipment": null, "defects": [], "measurements": [], "summary": ""}

Верни только JSON, без пояснений.
"""

SYSTEM_PROMPT_GENERATE = """
Ты — инженер-технолог. По описанию дефектов составь объём работ.
Обязательно включи: демонтаж, разборку, дефектацию, замену/восстановление, сборку, монтаж, предъявление л/с.
Отвечай кратко, только перечень работ.
"""

# --- Функция для анализа запроса через Groq ---
def analyze_query(user_text):
    if not GROQ_API_KEY:
        return {"document_type": "unknown", "ship": None, "equipment": None, "defects": [], "measurements": [], "summary": ""}
    
    try:
        client = httpx.Client(timeout=30.0)
        response = client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": "mixtral-8x7b-32768",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT_ANALYZE},
                    {"role": "user", "content": user_text}
                ]
            }
        )
        if response.status_code == 200:
            result = response.json()['choices'][0]['message']['content']
            # Попытка извлечь JSON из ответа
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {"document_type": "unknown", "ship": None, "equipment": None, "defects": [], "measurements": [], "summary": ""}
        else:
            return {"document_type": "unknown", "ship": None, "equipment": None, "defects": [], "measurements": [], "summary": ""}
    except Exception as e:
        print(f"Ошибка анализа: {e}")
        return {"document_type": "unknown", "ship": None, "equipment": None, "defects": [], "measurements": [], "summary": ""}

# --- Функция генерации объёма работ через AI ---
def generate_work_volume(defects, measurements):
    if not GROQ_API_KEY or not defects:
        return "Демонтаж, разборка, дефектация, замена/восстановление, сборка, монтаж, предъявление л/с."
    
    try:
        client = httpx.Client(timeout=30.0)
        defect_text = "; ".join(defects)
        measurements_text = "; ".join(measurements) if measurements else "без замеров"
        prompt = f"Дефекты: {defect_text}. Замеры: {measurements_text}"
        
        response = client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": "mixtral-8x7b-32768",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT_GENERATE},
                    {"role": "user", "content": prompt}
                ]
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
def create_defect_document(ship, equipment, defects, measurements, work_volume):
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
    row[2].text = "; ".join(defects) if defects else "Не указано"
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

    # Сохранение в память
    file_stream = BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream

# --- Обработчик всех текстовых сообщений (интеллектуальный ввод) ---
@bot.message_handler(func=lambda message: True)
def handle_intelligent_input(message):
    user_text = message.text
    if user_text.startswith('/'):
        return  # Пропускаем команды, они обрабатываются отдельно

    # 1. Анализ запроса
    analysis = analyze_query(user_text)
    doc_type = analysis.get('document_type', 'unknown')
    ship = analysis.get('ship')
    equipment = analysis.get('equipment')
    defects = analysis.get('defects', [])
    measurements = analysis.get('measurements', [])

    if doc_type == 'unknown':
        bot.reply_to(message, "🤔 Не понял запрос. Я умею делать Акты дефектации и АВР. Просто опишите ситуацию, и я создам документы.")
        return

    # 2. Если нужно сделать Акт дефектации
    if doc_type in ['defect', 'both']:
        work_volume = generate_work_volume(defects, measurements)
        file_stream = create_defect_document(ship, equipment, defects, measurements, work_volume)
        bot.send_document(message.chat.id, file_stream, visible_file_name=f'Акт_дефектации_{ship or "судна"}.docx')
        bot.send_message(message.chat.id, "📄 Акт дефектации в Word отправлен!")

    # 3. Если нужно сделать АВР
    if doc_type == 'avr':
        # Пока заглушка — позже добавим полноценную генерацию АВР
        bot.send_message(message.chat.id, "📄 АВР пока в разработке. Скоро я научусь делать и его!")

# --- Команда /start ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 Привет! Я — твой инженерный ассистент.\n"
                          "Просто опиши задачу: например, 'Судно Аргака, насос, сломан подшипник, сделай акт'.\n"
                          "Я проанализирую и создам нужные документы в формате Word.\n\n"
                          "📌 Пока я умею делать только Акты дефектации. АВР — в разработке.")

# --- Запуск бота ---
if __name__ == '__main__':
    print("Бот-ассистент запущен!")
    bot.infinity_polling()