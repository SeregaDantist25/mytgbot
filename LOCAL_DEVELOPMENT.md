# Локальная рабочая модель

Для разработки и проверки платный хостинг не нужен. Бот работает с локальной
SQLite-базой; после стабилизации ту же версию можно перенести на сервер и
переключить на PostgreSQL через `DATABASE_URL`.

## Первый запуск

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

### Linux / macOS

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Заполните `TELEGRAM_BOT_TOKEN` токеном отдельного тестового бота и укажите свой
Telegram ID в `ADMIN_IDS`. Не используйте токен действующего производственного
бота в разработке и не добавляйте `.env` в Git.

Если Telegram ID неизвестен, сначала оставьте `ADMIN_IDS=` пустым, запустите
бота и отправьте ему `/myid`. Скопируйте полученное число в `.env`, остановите
бота сочетанием `Ctrl+C` и запустите снова. При первом `/login` ID из
`ADMIN_IDS` автоматически регистрируется как одобренный инженер-технолог.

## Проверка без Telegram

```bash
python manage.py test
```

Тесты используют SQLite и проверяют сервисы без внешнего хостинга.

## Запуск тестового бота

Проверка конфигурации без вывода токена:

```bash
python manage.py check
```

Запуск:

```bash
python manage.py run
```

В Windows вместо `python` можно использовать `.venv\Scripts\python.exe`, в
Linux/macOS — `.venv/bin/python`.

Для круглосуточной работы компьютер должен оставаться включённым. Этот режим
предназначен для разработки и демонстрации; производственный хостинг выбирается
после приёмки модели.
