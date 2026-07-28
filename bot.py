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

# --- Настройки ---
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

if not BOT_TOKEN:
    raise ValueError("Переменная TELEGRAM_BOT_TOKEN не найдена!")

bot = telebot.TeleBot(BOT_TOKEN)
bot.add_custom_filter(custom_filters.StateFilter(bot))

# --- Состояния диалога ---
class DefectStates(StatesGroup):
    ship = State()
    equipment = State()
    defect_description = State()
    measurements = State()

# --- Команда /defect ---
@bot.message_handler(commands=['defect'])
def start_defect(message):
    bot.set_state(message.from_user.id, DefectStates.ship, message.chat.id)
    bot.send_message(message.chat.id, "🏗️ Начинаем создание Акта дефектации.\nВведите **название судна** (например, Аргака):")

# --- Сбор данных ---
@bot.message_handler(state=DefectStates.ship)
def get_ship(message):
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['ship'] = message.text.strip()
    bot.send_message(message.chat.id, "Введите **оборудование** (например, Пожарный насос №1):")
    bot.set_state(message.from_user.id, DefectStates.equipment, message.chat.id)

@bot.message_handler(state=DefectStates.equipment)
def get_equipment(message):
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['equipment'] = message.text.strip()
    bot.send_message(message.chat.id, "Опишите **дефекты** (кратко, но с замерами, если есть):")
    bot.set_state(message.from_user.id, DefectStates.defect_description, message.chat.id)

@bot.message_handler(state=DefectStates.defect_description)
def get_defect(message):
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['defect_description'] = message.text.strip()
    bot.send_message(message.chat.id, "Введите **фактические замеры** (например, 'зазор 0.2 мм' или '---'):")
    bot.set_state(message.from_user.id, DefectStates.measurements, message.chat.id)

# --- Генерация акта в Word и отправка ---
@bot.message_handler(state=DefectStates.measurements)
def generate_act(message):
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['measurements'] = message.text.strip()
        ship = data.get('ship', 'Не указано')
        equipment = data.get('equipment', 'Не указано')
        defect_description = data.get('defect_description', 'Не указано')
        measurements = data.get('measurements', 'Не указано')

    # 1. Генерация объёма работ через AI (если есть ключ)
    work_volume = "Демонтаж, разборка, дефектация, замена/восстановление, сборка, монтаж, предъявление л/с."
    if GROQ_API_KEY:
        try:
            client = httpx.Client(timeout=30.0)
            response = client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": "mixtral-8x7b-32768",
                    "messages": [
                        {"role": "system", "content": "Ты — инженер-технолог судоремонта. По описанию дефекта составляй объём работ, обязательно включая демонтаж, разборку, замену/восстановление, сборку, монтаж и предъявление л/с. Отвечай коротко, только перечень работ."},
                        {"role": "user", "content": f"Дефект: {defect_description}. Замеры: {measurements}"}
                    ]
                }
            )
            if response.status_code == 200:
                work_volume = response.json()['choices'][0]['message']['content']
        except Exception as e:
            print(f"Ошибка AI: {e}")

    # 2. Создание Word-документа
    doc = Document()
    # Стиль для нормального текста
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(11)

    # --- Шапка (выделена жирным) ---
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run = p.add_run('ООО «Новое время»')
    run.bold = True
    run.font.size = Pt(14)

    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p.add_run('692906, Приморский край, г. Находка, ул. Первая, зд. 1Б').font.size = Pt(11)

    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p.add_run('тел.: +7 (423) 662-97-79').font.size = Pt(11)

    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p.add_run('СПП № 24.44.01.01544.171 до 01.08.2028 г.').font.size = Pt(10)

    doc.add_paragraph()  # Пустая строка

    # --- Заголовок акта ---
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run = p.add_run('АКТ ДЕФЕКТАЦИИ')
    run.bold = True
    run.font.size = Pt(15)

    date_str = datetime.now().strftime('%d.%m.%Y')
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p.add_run(f'№ {ship[:3].upper()}-ДА-{datetime.now().strftime("%y")}-01').font.size = Pt(12)

    doc.add_paragraph(f'г. Находка / борт т/х «{ship}»        {date_str}')
    doc.add_paragraph(f'Судно: Т/х «{ship}»')
    doc.add_paragraph(f'Оборудование: {equipment}')
    doc.add_paragraph(f'Объект работ: Текущий ремонт')
    doc.add_paragraph()

    # --- Таблица дефектов ---
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
    row[1].text = equipment
    row[2].text = f'{defect_description} ({measurements})'
    row[3].text = work_volume

    # --- Заключение и подписи ---
    doc.add_paragraph()
    doc.add_paragraph('Заключение дефектационной комиссии:')
    doc.add_paragraph('Детали подлежат замене/восстановлению согласно указанному объёму работ.')

    doc.add_paragraph()
    p = doc.add_paragraph('Представитель подрядчика (Исполнитель):')
    p.add_run(' Инженер-технолог / Мастер участка		/ *[ФИО]* /')

    p = doc.add_paragraph('Представитель заказчика (Судовладелец / Экипаж):')
    p.add_run(f'Старший механик т/х «{ship}»		/ *[ФИО]* /')

    # --- Сохранение документа в память ---
    file_stream = BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)

    # --- Отправка файла ---
    bot.send_document(message.chat.id, file_stream, visible_file_name=f'Акт_дефектации_{ship}.docx')
    bot.send_message(message.chat.id, "📄 Акт в формате Word отправлен! Проверьте файл.")

    # Завершаем диалог
    bot.delete_state(message.from_user.id, message.chat.id)

# --- Команда /start ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 Привет! Я помогу создать Акт дефектации в формате Word.\nОтправь команду /defect, чтобы начать.")

# --- Запуск бота ---
if __name__ == '__main__':
    print("Бот запускается...")
    bot.infinity_polling()