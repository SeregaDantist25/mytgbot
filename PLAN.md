# План реализации оставшихся 5 пунктов ТЗ

## 1. Переход на PostgreSQL (высокий приоритет)

### Изменения в `models.py`:
- Заменить `DATABASE_URL = "sqlite:///data/documents.db"` на:
  ```python
  import os
  DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/documents.db")
  ```
- Добавить обработку для PostgreSQL (psycopg2 драйвер)
- Убедиться, что `init_models()` работает с обоими БД
- Проверить, что `sync_ships_from_json()` работает с Postgres

### Требования:
- Обратная совместимость с SQLite (по умолчанию)
- На Railway: `DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname`
- Добавить `psycopg2-binary` в requirements.txt

---

## 2. Интеграция категорий документов в меню (высокий приоритет)

### Новые функции в `navigation.py`:
- `get_categories_for_item(item_id)` — получить категории документов для пункта
- `get_documents_for_category(item_id, category)` — получить документы по категории
- `build_categories_keyboard(item_id)` — клавиатура с категориями
- `build_documents_keyboard(item_id, category, page=0)` — клавиатура с документами

### Новые callback-обработчики в `bot.py`:
- `@bot.callback_query_handler(func=lambda call: call.data.startswith("categories_"))` — показать категории
- `@bot.callback_query_handler(func=lambda call: call.data.startswith("docs_"))` — показать документы категории

### Логика:
1. Пользователь выбирает пункт → показываются категории (Акты дефектации, АВР, Прочее)
2. Пользователь выбирает категорию → показываются документы с версией и статусом
3. Каждый документ: "v1 (draft)" или "v2 (approved)" или "v3 (archived)"

### Callback-структура:
- `categories_<item_id>` — показать категории для пункта
- `docs_<item_id>_<category>_<page>` — показать документы категории

---

## 3. Использование StatesGroup (средний приоритет)

### Новые состояния в `bot.py`:
```python
class DocumentStates(StatesGroup):
    waiting_for_file = State()  # Ожидание загрузки файла
    waiting_for_replacement = State()  # Ожидание замены файла
    confirming_delete = State()  # Подтверждение удаления
```

### Сценарий загрузки файла:
1. Пользователь нажимает "Загрузить документ" → переход в `waiting_for_file`
2. Бот ожидает файл (DOCX, XLSX, PDF)
3. При получении файла → сохранение в БД, выход из состояния

### Сценарий подтверждения удаления:
1. Пользователь нажимает "Удалить" → переход в `confirming_delete`
2. Бот показывает "Вы уверены? Да/Нет"
3. При "Да" → удаление, выход из состояния

### Обработчики:
- `@bot.message_handler(state=DocumentStates.waiting_for_file, content_types=['document'])`
- `@bot.message_handler(state=DocumentStates.confirming_delete)`

---

## 4. Редактирование/замена документа (средний приоритет)

### Новая функция в `bot.py`:
- `handle_document_replace(document_id, new_file_path, user_id)` — заменить draft-документ

### Логика:
1. Пользователь нажимает "Заменить" на draft-документе → переход в `waiting_for_replacement`
2. Бот ожидает новый файл
3. При получении файла:
   - Старый файл удаляется из хранилища
   - Новый файл сохраняется с тем же `item_id` и `category`
   - Версия остаётся той же (не инкрементируется)
   - Статус остаётся `draft`

### Callback-структура:
- `replace_<document_id>` — начать замену документа

---

## 5. Конвертация в PDF (низкий приоритет)

### Новая функция в `bot.py`:
- `convert_to_pdf(file_path, file_type)` — конвертировать DOCX/XLSX в PDF

### Логика:
1. При утверждении документа (draft → approved):
   - Если файл DOCX → конвертировать в PDF
   - Если файл XLSX → конвертировать в PDF
   - Если файл уже PDF → оставить как есть
2. Сохранить PDF в хранилище
3. Обновить `file_ref` в БД на путь PDF

### Инструменты:
- `python-docx` (уже в requirements.txt) — для DOCX
- `openpyxl` (уже в requirements.txt) — для XLSX
- `reportlab` или `pypdf` — для создания PDF из XLSX

### Альтернатива:
- Использовать `libreoffice --headless --convert-to pdf` (требует LibreOffice на сервере)

---

## Порядок реализации:
1. **Пункт 1** (PostgreSQL) — базовая инфраструктура
2. **Пункт 2** (категории) — основной функционал
3. **Пункт 3** (StatesGroup) — улучшение UX
4. **Пункт 4** (замена) — дополнительный функционал
5. **Пункт 5** (PDF) — опциональный функционал

---

## Проверка совместимости:
- ✅ Все новые функции используют существующие импорты
- ✅ Обратная совместимость с SQLite
- ✅ Не ломаются существующие обработчики
- ✅ Callback-структура остаётся в пределах 64 байт
