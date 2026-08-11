# Руководство по интеграции новых модулей

## Обзор изменений

Реализованы все 5 пунктов ТЗ:

1. ✅ **PostgreSQL** — поддержка переменной окружения `DATABASE_URL`
2. ✅ **Категории документов** — интеграция в меню навигации
3. ✅ **StatesGroup** — управление состояниями для загрузки/замены/удаления
4. ✅ **Замена документа** — функционал для draft-документов
5. ✅ **Конвертация в PDF** — при утверждении документа

---

## Новые файлы

### 1. `document_states.py`
Определяет состояния для работы с документами:
- `waiting_for_file` — ожидание загрузки файла
- `waiting_for_replacement` — ожидание замены файла
- `confirming_delete` — подтверждение удаления
- `waiting_for_category` — выбор категории

### 2. `document_handlers.py`
Обработчики для StatesGroup:
- Загрузка документа с выбором категории
- Замена draft-документа
- Удаление с подтверждением

**Регистрация в bot.py:**
```python
from document_handlers import register_document_handlers
register_document_handlers(bot)
```

### 3. `document_utils.py`
Утилиты для работы с документами:
- `handle_document_replace()` — замена draft-документа
- `convert_to_pdf()` — конвертация в PDF
- `handle_document_approve_with_pdf()` — утверждение с конвертацией

### 4. `category_handlers.py`
Обработчики для навигации по категориям:
- Показ категорий для пункта
- Показ документов по категории
- Показ деталей документа

**Регистрация в bot.py:**
```python
from category_handlers import register_category_handlers
register_category_handlers(bot)
```

### 5. `navigation.py` (обновлён)
Расширенные функции навигации:
- `get_categories_for_item()` — получить категории
- `get_documents_for_category()` — получить документы
- `build_categories_keyboard()` — клавиатура категорий
- `build_documents_keyboard()` — клавиатура документов
- `format_document_details()` — форматирование деталей

---

## Изменения в существующих файлах

### `models.py`
```python
import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/documents.db")

# Параметры для PostgreSQL
engine_kwargs = {"echo": False}
if "postgresql" in DATABASE_URL:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 3600

engine = create_engine(DATABASE_URL, **engine_kwargs)
```

### `requirements.txt`
Добавлены:
- `psycopg2-binary==2.9.9` — драйвер PostgreSQL
- `reportlab==4.0.9` — конвертация в PDF

---

## Интеграция в bot.py

### 1. Импорты
```python
from document_states import DocumentStates
from document_handlers import register_document_handlers
from category_handlers import register_category_handlers
from document_utils import handle_document_approve_with_pdf
```

### 2. Регистрация обработчиков (в `__main__`)
```python
if __name__ == '__main__':
    # ... существующий код ...
    
    # Регистрируем обработчики документов
    register_document_handlers(bot)
    register_category_handlers(bot)
    
    # ... остальной код ...
```

### 3. Обновление обработчика выбора пункта
Когда пользователь выбирает пункт, показываем категории:

```python
@bot.callback_query_handler(func=lambda call: call.data.startswith("item_"))
def handle_item_selection(call):
    try:
        item_id = int(call.data.split("_")[1])
        
        # Получаем детали пункта
        item = navigation.get_item_details(item_id)
        if not item:
            bot.answer_callback_query(call.id, "❌ Пункт не найден", show_alert=True)
            return
        
        # Форматируем текст
        text = navigation.format_item_details(item)
        text += "\n\n📂 **Выберите категорию документов:**"
        
        # Строим клавиатуру с категориями
        keyboard = navigation.build_categories_keyboard(item_id)
        
        if not keyboard:
            text = "❌ Нет документов для этого пункта"
            keyboard = None
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
```

### 4. Обновление обработчика утверждения документа
```python
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def handle_approve_button(call):
    try:
        doc_id = int(call.data.split("_")[1])
        
        # Утверждаем с конвертацией в PDF
        if handle_document_approve_with_pdf(doc_id, call.from_user.id):
            bot.answer_callback_query(call.id, "✅ Документ утверждён и конвертирован в PDF")
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка при утверждении", show_alert=True)
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
```

---

## Переменные окружения

### Локальная разработка (SQLite)
```bash
# Не требуется, используется по умолчанию
```

### Railway (PostgreSQL)
```bash
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/dbname
BOT_TOKEN=your_token
GROQ_API_KEY=your_key
ENGINEER_CODE=your_code
ADMIN_IDS=123456789,987654321
DATA_DIR=/app/data
```

---

## Структура callback-данных

### Категории
- `categories_<item_id>` — показать категории для пункта
- `cat_<category>` — выбрать категорию при загрузке

### Документы
- `docs_<item_id>_<category>_<page>` — показать документы категории
- `doc_<doc_id>` — показать детали документа
- `upload_<item_id>` — загрузить документ
- `replace_<doc_id>` — заменить документ
- `delete_<doc_id>` — удалить документ
- `approve_<doc_id>` — утвердить документ
- `archive_<doc_id>` — архивировать документ

---

## Проверка совместимости

✅ Все новые функции используют существующие импорты
✅ Обратная совместимость с SQLite
✅ Не ломаются существующие обработчики
✅ Callback-структура остаётся в пределах 64 байт
✅ Синтаксис Python 3.8+

---

## Тестирование

### 1. Проверка синтаксиса
```bash
python -m py_compile models.py navigation.py document_states.py document_handlers.py document_utils.py category_handlers.py
```

### 2. Проверка импортов
```bash
python -c "from models import *; from navigation import *; from document_states import *; from document_handlers import *; from document_utils import *; from category_handlers import *; print('✅ Все импорты успешны')"
```

### 3. Проверка БД
```bash
python -c "from models import init_models; init_models(); print('✅ БД инициализирована')"
```

---

## Порядок развёртывания

1. Обновить `models.py` (PostgreSQL)
2. Обновить `requirements.txt` (новые зависимости)
3. Добавить новые файлы в проект
4. Обновить `bot.py` (импорты и регистрация)
5. Протестировать локально
6. Развернуть на Railway

---

## Известные ограничения

1. **PDF-конвертация** — использует reportlab, может потребовать оптимизации для больших файлов
2. **Callback-данные** — ограничены 64 байтами (используется хеширование для длинных строк)
3. **Состояния** — требуют включения `State` в боте (уже включено в импортах)

---

## Дальнейшие улучшения

1. Добавить аудит-логирование (кто, когда, что сделал)
2. Реализовать полнотекстовый поиск по документам
3. Добавить экспорт документов в ZIP
4. Реализовать уведомления при изменении статуса
5. Добавить версионирование с историей изменений
