# Передача проекта: Telegram-бот управления ремонтом судов

> Документ для передачи работы ассистенту (Claude). Содержит полный контекст,
> текущее состояние, известные проблемы и план дальнейших действий.

## 1. Что это за проект

Telegram-бот для управления ремонтом судов. Позволяет:
- просматривать ремонтные ведомости по судам (разделы → пункты);
- загружать/заменять/удалять документы (акты дефектации, АВР, прочее) к пунктам;
- импортировать готовые акты из папки `acts/`;
- проверять параметры по ГОСТам (модуль `gost_checker.py`).

**Стек:** Python, pyTelegramBotAPI, SQLAlchemy (sync), SQLite (локально) / PostgreSQL (на Railway).
**Деплой:** Railway. **Репозиторий:** `c:\Users\user\Desktop\BOT\mytgbot`.

## 2. Как запускать / тестировать

- Локально: `python bot.py` (использует SQLite `data/documents.db`).
- Тесты: `python -m pytest tests -q` → ожидается **58 passed**.
- На Railway: `DATABASE_URL` указывает на PostgreSQL.

**Важно про окружение (Windows/PowerShell):**
- Git только через полный путь: `& 'C:\Program Files\Git\bin\git.exe' -C 'c:\Users\user\Desktop\BOT\mytgbot' <cmd>`.
- `<<` и `&&` в PowerShell НЕ работают — разделять команды через `;`.
- Многострочные `python -c "..."` ломаются (PSReadLine) — писать скрипты в файлы.
- Кириллица в аргументах командной строки ломается — имена файлов с кириллицей хардкодить в скриптах, ставить `$env:PYTHONIOENCODING='utf-8'` перед запуском.

## 3. Архитектура (ключевые файлы)

| Файл | Назначение |
|------|-----------|
| `bot.py` | Точка входа. Регистрация обработчиков, автозагрузка ведомости (`[AUTO]`), автоимпорт актов (`[ACTS]`), `start_bot_with_retry()`. |
| `models.py` | ORM: `User`, `Ship`, `RepairStatement`, `StatementItem`, `Document`. |
| `document_manager.py` | Навигация по разделам/пунктам, `section_hash`, `ensure_repair_list_loaded`, `paginate_list`. |
| `bot_handlers_new.py` | Обработчики навигации (суда → разделы → пункты), команда `/scan_acts`. |
| `document_handlers.py` | Загрузка/замена/удаление документов через StatesGroup. |
| `file_storage.py` | Абстракция доступа к файлам (`FileStorage`, `LocalStorageBackend`). |
| `act_importer.py` | Импорт готовых актов из папки `acts/`. |
| `config.py` | `DATABASE_URL`, `DATA_DIR`, `TEMPLATES_DIR`, `validate()`. |
| `scanner.py` | Парсинг ремонтных ведомостей из Excel. |
| `handlers/callback_handlers.py` | Сейчас содержит только `bot_context.bot = bot` (дубликаты удалены). |

### Модель `Document` (models.py)
```python
class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("statement_items.id"), index=True)
    category = Column(String, nullable=False)  # defect_act, avr, other
    file_ref = Column(String, nullable=False)
    file_type = Column(String)
    version = Column(Integer, default=1)
    status = Column(String, default="draft", index=True)  # draft / approved / archived
    uploaded_by = Column(BigInteger, ForeignKey("users.telegram_id"))
    uploaded_at = Column(DateTime, server_default=func.now())
```

## 4. Текущее состояние (что уже сделано)

- ✅ Восстановлена ремонтная ведомость «Славянская» (251 пункт: 152 active + 59 reduced + 40 extra; 4 раздела + «Дополнительные работы»).
- ✅ Автозагрузка ведомости при старте бота (`dm.ensure_repair_list_loaded` в `bot.py`).
- ✅ Навигация по разделам через стабильный md5-хеш (`dm.section_hash`).
- ✅ Устранена корневая причина «Раздел не найден» (удалены дублирующие обработчики из `handlers/callback_handlers.py`).
- ✅ Пагинация пунктов (`items_`, `back_to_items_`).
- ✅ Кнопка «Загрузить документ» отправляет `upload_{item_id}`.
- ✅ Импорт актов из `acts/` (`act_importer.py`, команда `/scan_acts`, автоимпорт при старте).
- ✅ `ACTS_DIR` и `DATA_DIR` настраиваются через env.
- ✅ Все изменения закоммичены и запушены. Последний коммит `e3734e4` на `origin/master`.

## 5. ⚠️ Известные проблемы (важно!)

### 5.1. Файлы не сохраняются на Railway (главная проблема)
Бот хранит файлы актов в **локальной файловой системе контейнера** (`DATA_DIR`/`ACTS_DIR`),
которая **стирается при каждом передеплое**. На Railway нет volume (бесплатный тариф),
поэтому папка `acts/` не сохраняется.

**Решение (выбрано):** хранить содержимое файлов прямо в **PostgreSQL** (поле `bytea`),
т.к. Postgres уже есть на Railway и не теряет данные.

### 5.2. Загрузка через кнопку сломана (TypeError)
В `document_handlers.py` (строки 112–118 и 207–214) вызывается:
```python
storage.save_file(
    file_name=file_name,
    file_content=downloaded_file,
    item_id=item_id,
    category=category,
    user_id=message.from_user.id
)
```
Но реальная сигнатура `save_file(self, file_data, path)` — это вызовет `TypeError`.
Тесты не покрывают этот путь, поэтому баг не был пойман. Нужно перевести на `save_document(...)`.

### 5.3. Незакоммиченное изменение
В рабочем дереве есть незакоммиченное изменение `models.py` — добавлен `LargeBinary` в импорт
(строка 26). Это начало работы над хранением файлов в БД. **Не откатывать.**

## 6. План дальнейших действий

### Шаг 1. Хранение файлов в PostgreSQL
1. Добавить поле `file_data = Column(LargeBinary)` в модель `Document` (импорт `LargeBinary` уже добавлен).
2. Переделать `file_storage.py`:
   - `save_document(...)` — сохранять байты в `Document.file_data` вместо файла на диск;
   - `get_file(...)` — читать из БД по `document_id`/`file_ref`;
   - `delete_file(...)` — удалять запись/байты из БД.
3. Исправить `document_handlers.py`:
   - `handle_file_upload` → использовать `storage.save_document(file_name, downloaded_file, item_id, category, user_id)`.
   - `handle_file_replacement` → обновлять `file_data` у существующего документа.
4. Обновить `act_importer.py` — сохранять импортированные акты в БД, а не на диск.
5. Добавить миграцию для существующей БД (новое поле `file_data`).

### Шаг 2. Проверка
- `python -m pytest tests -q` → 58 passed.
- Проверить загрузку документа через кнопку (путь, который раньше падал с TypeError).
- Проверить импорт актов.

### Шаг 3. Деплой на Railway
- Закоммитить и запушить.
- Убедиться, что `DATABASE_URL` указывает на PostgreSQL.
- Проверить, что файлы переживают передеплой.

## 7. Полезные детали

- В `counters.db` судно «Славянская» имеет `ship_id=1`; в `documents.db` — `id=3`.
- Разделы Славянской: «Основные работы» (93), «Раздел IХ. Швартово-ходовые испытания» (41),
  «Раздел V. Электромеханическая часть» (15), «Раздел VI. Палубные устройства и механизмы» (3),
  «Дополнительные работы» (40).
- Исходный Excel ведомости: `repair_docs/_processed/Ремведомость_Славянская осн..xlsx` (закоммичен).
- Валидные расширения для загрузки: `.docx`, `.xlsx`, `.pdf`.
- `act_importer.py`: `ACTS_DIR = os.getenv("ACTS_DIR", "acts")`, `PROCESSED_DIR = os.path.join(ACTS_DIR, "_processed")`.
- `file_storage.py`: `storage = FileStorage()` — единый экземпляр.
- `config.py:80`: `DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///data/documents.db')`.
- `config.py:83`: `DATA_DIR = os.getenv('DATA_DIR', 'data')`.
- `models.py:32`: `DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/documents.db")`.

## 8. Коммиты (последние)
```
e3734e4 feat: папка acts/ настраивается через env ACTS_DIR (для volume на Railway)
4c570f6 feat: импорт готовых актов дефектации из папки acts/ (команда /scan_acts + автоимпорт при старте)
53be689 fix: кнопка 'Загрузить документ' отправляет upload_<item_id> (исправление invalid literal 'doc')
36c876f fix: добавить обработчики пагинации пунктов (items_) и возврата к разделам (back_to_items_)
269dc95 fix: убрать дублирующий обработчик section_/item_ из callback_handlers (конфликт с bot_handlers_new)
148b33b fix: стабильный выбор раздела по хешу + раздел «Дополнительные работы» (extra-пункты)
3d26bd8 feat: автозагрузка ремонтной ведомости Славянской при старте бота (для Railway/PostgreSQL)
```
