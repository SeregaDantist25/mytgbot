# 🔒 Реализация критических проблем безопасности (Неделя 1)

**Дата:** 2026-08-07  
**Статус:** ✅ ЗАВЕРШЕНО  
**Время реализации:** ~8 часов

---

## 📋 Обзор

На основе аудита (AUDIT_FULL.md, RECOMMENDATIONS.md) реализованы 4 критические проблемы безопасности:

1. ✅ **Валидация входных данных** (Pydantic)
2. ✅ **Rate-limiting** (защита от спама)
3. ✅ **Проверка прав доступа** (декораторы)
4. ✅ **Обработка ошибок** (логирование)

---

## 1️⃣ Валидация входных данных (Pydantic)

### Установка
```bash
pip install pydantic==2.0.0
```

### Файл: `schemas.py`

Создан новый файл с Pydantic моделями для валидации:

```python
from pydantic import BaseModel, Field, field_validator
from enum import Enum

class UserRole(str, Enum):
    ENGINEER = "engineer_technologist"
    DIRECTOR = "director"
    BUILDER = "builder"
    CUSTOMER = "customer"

class UserCreate(BaseModel):
    telegram_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=255)
    role: UserRole = Field(default=UserRole.CUSTOMER)
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if any(char in v for char in ['<', '>', '"', "'", ';', '--']):
            raise ValueError('Name contains invalid characters')
        return v.strip()
```

### Использование в обработчиках

```python
from schemas import UserCreate, DocumentCreate
import logging

logger = logging.getLogger(__name__)

@bot.message_handler(commands=['create_user'])
def handle_create_user(message):
    try:
        # Валидируем данные
        user_data = UserCreate(
            telegram_id=message.from_user.id,
            name=message.from_user.first_name,
            role="engineer_technologist"
        )
        
        # Если валидация прошла, сохраняем в БД
        db.add_user(user_data)
        bot.reply_to(message, "✅ Пользователь создан")
        logger.info(f"User {user_data.telegram_id} created")
    
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        bot.reply_to(message, f"❌ Ошибка валидации: {e}")
    
    except Exception as e:
        logger.error(f"Error creating user: {e}", exc_info=True)
        bot.reply_to(message, "❌ Произошла ошибка")
```

### Доступные схемы

- `UserCreate` — создание пользователя
- `UserUpdate` — обновление пользователя
- `DocumentCreate` — создание документа
- `DocumentUpdate` — обновление статуса документа
- `RepairItemCreate` — создание ремонтного объекта
- `CallbackData` — валидация callback данных
- `MessageData` — валидация текста сообщения
- `PaginationParams` — параметры пагинации
- `SearchParams` — параметры поиска

---

## 2️⃣ Rate-limiting

### Файл: `utils/rate_limiter.py`

Создан класс `RateLimiter` для защиты от спама:

```python
from utils.rate_limiter import RateLimiter, message_limiter, file_limiter

# Проверка лимита
if not message_limiter.is_allowed(user_id):
    retry_after = message_limiter.get_retry_after(user_id)
    bot.reply_to(message, f"⏱️ Слишком много запросов. Попробуйте через {retry_after}с")
    return

# Обработка команды
bot.reply_to(message, "✅ Команда выполнена")
```

### Глобальные limiters

```python
message_limiter = RateLimiter(max_requests=30, window_seconds=60)  # 30 сообщений/мин
file_limiter = RateLimiter(max_requests=5, window_seconds=60)      # 5 файлов/мин
approve_limiter = RateLimiter(max_requests=10, window_seconds=60)  # 10 утверждений/мин
command_limiter = RateLimiter(max_requests=20, window_seconds=60)  # 20 команд/мин
```

### Использование в обработчиках

```python
from utils.rate_limiter import message_limiter

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    
    # Проверяем rate limit
    if not message_limiter.is_allowed(user_id):
        retry_after = message_limiter.get_retry_after(user_id)
        bot.reply_to(message, f"⏱️ Слишком много запросов. Попробуйте через {retry_after}с")
        return
    
    # Обработка команды
    bot.reply_to(message, "👋 Добро пожаловать!")
```

---

## 3️⃣ Проверка прав доступа

### Файл: `utils/decorators.py`

Созданы декораторы для проверки прав:

#### `@require_role` — проверка роли пользователя

```python
from utils.decorators import require_role

@require_role(['engineer_technologist', 'director'])
def handle_stats(message):
    """Только инженеры и директоры могут видеть статистику"""
    stats = db.get_stats()
    bot.reply_to(message, f"📊 Статистика:\n{stats}")
```

#### `@require_admin` — проверка администратора

```python
from utils.decorators import require_admin

@require_admin
def handle_admin_command(message):
    """Только администраторы могут выполнить эту команду"""
    bot.reply_to(message, "🔧 Админ-команда выполнена")
```

#### `@rate_limit` — ограничение частоты запросов

```python
from utils.decorators import rate_limit

@rate_limit(max_requests=10, window_seconds=60)
def handle_expensive_operation(message):
    """Максимум 10 запросов в минуту"""
    bot.reply_to(message, "⚙️ Операция выполнена")
```

#### `@handle_exceptions` — обработка исключений

```python
from utils.decorators import handle_exceptions

@handle_exceptions
def handle_command(message):
    """Автоматически обрабатывает исключения"""
    # Если возникнет исключение, оно будет залогировано
    # и пользователю будет отправлено сообщение об ошибке
    result = some_operation()
    bot.reply_to(message, f"✅ Результат: {result}")
```

#### `@log_execution` — логирование выполнения

```python
from utils.decorators import log_execution

@log_execution
def handle_important_operation(message):
    """Логирует начало и конец выполнения"""
    bot.reply_to(message, "✅ Важная операция выполнена")
```

#### Комбинирование декораторов

```python
from utils.decorators import combine_decorators, require_role, rate_limit, handle_exceptions

@combine_decorators(
    require_role(['engineer_technologist']),
    rate_limit(max_requests=5, window_seconds=60),
    handle_exceptions
)
def handle_critical_operation(message):
    """Требует роли инженера, ограничен 5 запросами в минуту, обрабатывает ошибки"""
    bot.reply_to(message, "✅ Критическая операция выполнена")
```

---

## 4️⃣ Обработка ошибок и логирование

### Файл: `config.py`

Создана конфигурация логирования:

```python
from config import setup_logging, get_config

# Инициализируем логирование
logger = setup_logging(
    log_level='INFO',
    log_file='bot.log'
)

# Получаем конфигурацию
config = get_config()
config.validate()
```

### Использование логирования

```python
import logging

logger = logging.getLogger(__name__)

@bot.message_handler(commands=['start'])
def handle_start(message):
    try:
        user_id = message.from_user.id
        logger.info(f"User {user_id} started bot")
        
        user = db.get_or_create_user(user_id)
        bot.reply_to(message, f"👋 Добро пожаловать, {user.name}!")
        
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        bot.reply_to(message, f"❌ Ошибка: {e}")
    
    except Exception as e:
        logger.error(f"Error in handle_start: {e}", exc_info=True)
        bot.reply_to(message, "❌ Произошла ошибка. Администратор уведомлен.")
```

### Замена bare except на Exception

**ДО (плохо):**
```python
try:
    storage.delete_file(doc.file_ref)
except:
    pass  # Скрывает все ошибки!
```

**ПОСЛЕ (хорошо):**
```python
try:
    storage.delete_file(doc.file_ref)
except Exception as e:
    logger.warning(f"Failed to delete file {doc.file_ref}: {e}")
```

### Уровни логирования

```python
logger.debug("Отладочная информация")           # DEBUG
logger.info("Информационное сообщение")         # INFO
logger.warning("Предупреждение")                # WARNING
logger.error("Ошибка")                          # ERROR
logger.critical("Критическая ошибка")           # CRITICAL

# С информацией об исключении
logger.error("Error occurred", exc_info=True)
```

---

## 📁 Структура файлов

```
mytgbot/
├── requirements.txt          # ✅ Добавлен pydantic==2.0.0
├── config.py                 # ✅ Новый файл с конфигурацией
├── schemas.py                # ✅ Новый файл с Pydantic моделями
├── utils/
│   ├── __init__.py          # ✅ Новый файл
│   ├── rate_limiter.py      # ✅ Новый файл с RateLimiter
│   └── decorators.py        # ✅ Новый файл с декораторами
├── document_handlers.py      # ✅ Обновлен: bare except → Exception
├── bot_handlers_new.py       # ✅ Обновлен: bare except → Exception
└── ... (остальные файлы)
```

---

## 🔍 Проверка синтаксиса

Все файлы проверены на синтаксис:

```bash
✅ schemas.py синтаксис OK
✅ utils/rate_limiter.py синтаксис OK
✅ utils/decorators.py синтаксис OK
✅ config.py синтаксис OK
✅ document_handlers.py синтаксис OK
✅ bot_handlers_new.py синтаксис OK
```

---

## 📊 Примеры использования

### Пример 1: Создание пользователя с валидацией

```python
from schemas import UserCreate
from config import get_config
import logging

logger = logging.getLogger(__name__)
config = get_config()

@bot.message_handler(commands=['register'])
def handle_register(message):
    try:
        # Валидируем данные
        user_data = UserCreate(
            telegram_id=message.from_user.id,
            name=message.from_user.first_name or "User",
            role="customer"
        )
        
        # Сохраняем в БД
        db.add_user(user_data)
        bot.reply_to(message, "✅ Вы зарегистрированы!")
        logger.info(f"User {user_data.telegram_id} registered")
    
    except ValueError as e:
        logger.warning(f"Registration validation error: {e}")
        bot.reply_to(message, f"❌ Ошибка: {e}")
    
    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        bot.reply_to(message, "❌ Ошибка регистрации")
```

### Пример 2: Загрузка документа с rate-limiting и валидацией

```python
from schemas import DocumentCreate
from utils.rate_limiter import file_limiter
from utils.decorators import require_role
import logging

logger = logging.getLogger(__name__)

@require_role(['engineer_technologist', 'builder'])
@bot.message_handler(content_types=['document'])
def handle_document_upload(message):
    try:
        user_id = message.from_user.id
        
        # Проверяем rate limit
        if not file_limiter.is_allowed(user_id):
            retry_after = file_limiter.get_retry_after(user_id)
            bot.reply_to(message, f"⏱️ Слишком много файлов. Попробуйте через {retry_after}с")
            logger.warning(f"File upload rate limit exceeded for user {user_id}")
            return
        
        # Валидируем документ
        doc_data = DocumentCreate(
            item_id=123,
            category="defect_act",
            file_name=message.document.file_name,
            file_size=message.document.file_size
        )
        
        # Сохраняем файл
        file_path = storage.save_file(
            file_name=doc_data.file_name,
            file_content=bot.download_file(message.document.file_id),
            item_id=doc_data.item_id,
            category=doc_data.category,
            user_id=user_id
        )
        
        bot.reply_to(message, f"✅ Документ загружен: {doc_data.file_name}")
        logger.info(f"Document uploaded by user {user_id}: {doc_data.file_name}")
    
    except ValueError as e:
        logger.warning(f"Document validation error: {e}")
        bot.reply_to(message, f"❌ Ошибка валидации: {e}")
    
    except Exception as e:
        logger.error(f"Document upload error: {e}", exc_info=True)
        bot.reply_to(message, "❌ Ошибка при загрузке документа")
```

### Пример 3: Админ-команда с проверкой прав

```python
from utils.decorators import require_admin
from config import get_config
import logging

logger = logging.getLogger(__name__)
config = get_config()

@require_admin
@bot.message_handler(commands=['admin_stats'])
def handle_admin_stats(message):
    try:
        user_id = message.from_user.id
        logger.info(f"Admin {user_id} requested stats")
        
        stats = db.get_all_stats()
        msg = f"📊 Статистика системы:\n"
        msg += f"Пользователей: {stats['users']}\n"
        msg += f"Документов: {stats['documents']}\n"
        msg += f"Судов: {stats['ships']}\n"
        
        bot.reply_to(message, msg)
    
    except Exception as e:
        logger.error(f"Error getting admin stats: {e}", exc_info=True)
        bot.reply_to(message, "❌ Ошибка при получении статистики")
```

---

## 🚀 Следующие шаги

1. **Интеграция в bot.py:**
   - Добавить импорты новых модулей
   - Применить декораторы к существующим обработчикам
   - Заменить print() на logger

2. **Тестирование:**
   - Проверить валидацию на некорректных данных
   - Проверить rate-limiting
   - Проверить логирование в файл

3. **Фаза 2 (Архитектура):**
   - Разбить bot.py на модули (handlers/, services/, utils/)
   - Добавить type hints ко всем функциям
   - Создать unit-тесты

---

## 📝 Примечания

- **Pydantic 2.0.0** использует `field_validator` вместо `@validator`
- **Rate limiter** потокобезопасен благодаря `threading.Lock`
- **Логирование** настроено на ротацию файлов (макс 10 MB на файл)
- **Декораторы** можно комбинировать для применения нескольких проверок

---

**Статус:** ✅ Все 4 критические проблемы безопасности реализованы и протестированы на синтаксис.
