import os
import telebot

# Токен бота забирается из переменной окружения, которую создадим на Railway
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я работаю на Railway!")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, "Вы сказали: " + message.text)

if __name__ == '__main__':
    print("Бот запускается...")
    bot.infinity_polling()