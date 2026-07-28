import os
import telebot
from telebot.handler_backends import State, StatesGroup
from telebot import custom_filters
import json
import httpx
from datetime import datetime

# --- Настройки ---
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')  # Если нет, можно пока закомментировать AI

if not BOT_TOKEN:
    raise ValueError("Переменная TELEGRAM_BOT_TOKEN не найдена!")

bot = telebot.TeleBot(BOT_TOKEN)

# --- Состояния для диалога ---
class DefectStates(StatesGroup):
    ship = State()
    equipment = State()
    defect_description = State()
    measurements = State()

# --- Команда для запуска дефектовки ---
@bot.message_handler(commands=['defect'])
def start_defect(message):
    bot.set_state(message.from_user.id, DefectStates.ship, message.chat.id)
    bot.send_message(message.chat.id, "🏗️ Начинаем создание Акта дефектации.\nВведите **название судна** (например, Аргака):")

# --- Диалог сбора данных ---
@bot.message_handler(state=DefectStates.ship)
def get_ship(message):
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['ship'] = message.text
    bot.send_message(message.chat.id, "Введите **оборудование** (например, Пожарный насос №1):")
    bot.set_state(message.from_user.id, DefectStates.equipment, message.chat.id)

@bot.message_handler(state=DefectStates.equipment)
def get_equipment(message):
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['equipment'] = message.text
    bot.send_message(message.chat.id, "Опишите **дефекты** (кратко, но с замерами, если есть):")
    bot.set_state(message.from_user.id, DefectStates.defect_description, message.chat.id)

@bot.message_handler(state=DefectStates.defect_description)
def get_defect(message):
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['defect_description'] = message.text
    bot.send_message(message.chat.id, "Введите **фактические замеры** (например, 'зазор 0.2 мм' или '---' если нет):")
    bot.set_state(message.from_user.id, DefectStates.measurements, message.chat.id)

# --- Финал: генерация акта ---
@bot.message_handler(state=DefectStates.measurements)
def generate_act(message):
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['measurements'] = message.text
        ship = data.get('ship', 'Не указано')
        equipment = data.get('equipment', 'Не указано')
        defect_description = data.get('defect_description', 'Не указано')
        measurements = data.get('measurements', 'Не указано')

    # --- 1. Генерация объёма работ через AI (если есть ключ) ---
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

    # --- 2. Сборка финального акта ---
    current_date = datetime.now().strftime("%d.%m.%Y")
    act_template = f"""
**ООО «Новое время»**

692906, Приморский край, г. Находка, ул. Первая, зд. 1Б
тел.: +7 (423) 662-97-79
СПП № 24.44.01.01544.171 до 01.08.2028 г.

**АКТ ДЕФЕКТАЦИИ**
№ {ship[:3].upper()}-ДА-{datetime.now().strftime("%y")}-01

г. Находка / борт т/х «{ship}»        {current_date}

**Судно:** Т/х «{ship}»
**Оборудование:** {equipment}
**Объект работ:** Текущий ремонт

Произведён осмотр (визуальный, с применением средств НК, с замерами). Выявлены следующие дефекты и определён объём работ:

| **№** | **Позиция (наименование детали / узла)** | **Дефект / Состояние (с указанием фактических размеров износа)** | **Объём работ (технология восстановления)** |
|-------|-----------------------------------------|-------------------------------------------------------------------|---------------------------------------------|
| 1     | {equipment}                             | {defect_description} ({measurements})                              | {work_volume}                               |

**Заключение дефектационной комиссии:** Детали подлежат замене/восстановлению согласно указанному объёму работ.

**Представитель подрядчика (Исполнитель):**
Инженер-технолог / Мастер участка		/ *[ФИО]* /

**Представитель заказчика (Судовладелец / Экипаж):**
Старший механик т/х «{ship}»		/ *[ФИО]* /
"""
    # --- 3. Отправка результата ---
    bot.send_message(message.chat.id, f"✅ Акт дефектации сформирован:\n\n{act_template}")
    bot.send_message(message.chat.id, "📌 Вы можете скопировать текст и сохранить в Obsidian или Word.")

    # Завершаем диалог
    bot.delete_state(message.from_user.id, message.chat.id)

# --- Команда /start ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 Привет! Я помогу создать Акт дефектации.\nОтправь команду /defect, чтобы начать.")

# --- Запуск бота ---
if __name__ == '__main__':
    print("Бот запускается...")
    bot.infinity_polling()