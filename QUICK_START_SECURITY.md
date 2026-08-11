# ⚡ Быстрый старт: Компоненты безопасности

**Для нетерпеливых:** 5 минут на интеграцию

---

## 1️⃣ Установка

```bash
pip install pydantic==2.0.0
```

---

## 2️⃣ Импорты в bot.py

```python
import logging
from config import setup_logging, get_config
from schemas import UserCreate, DocumentCreate
from utils.rate_limiter import message_limiter, file_limiter
from utils.decorators import require_role, require_admin, rate_limit
```

---

## 3️⃣ Инициализация

```python
if __name__ == '__main__':
    # Логирование
    logger = setup_logging(log_level='INFO', log_file='bot.log')
    
    # Конфигурация
    config = get_config()
    config.validate()
    
    logger.info("Bot started")
    bot.infinity_polling()
```

---

## 4️⃣ Примеры использования

### Валидация пользователя

```python
from schemas import UserCreate

try:
    user = UserCreate(
        telegram_id=message.from_user.id,
        name=message.from_user.first_name,
        role="customer"
    )
    db.add_user(user)
except ValueError as e:
    logger.warning(f"Validation error: {e}")
    bot.reply_to(message, f"❌ {e}")
```

### Rate-limiting

```python
from utils.rate_limiter import message_limiter

if not message_limiter.is_allowed(message.from_user.id):
    retry = message_limiter.get_retry_after(message.from_user.id)
    bot.reply_to(message, f"⏱️ Попробуйте через {retry}с")
    return
```

### Проверка прав

```python
from utils.decorators import require_role

@require_role(['engineer_technologist'])
@bot.message_handler(commands=['stats'])
def handle_stats(message):
    bot.reply_to(message, "📊 Статистика")
```

### Логирование

```python
import logging

logger = logging.getLogger(__name__)

try:
    result = operation()
    logger.info(f"Success: {result}")
except Exception as e:
    logger.error(f"Error: {e}", exc_info=True)
    bot.reply_to(message, "❌ Ошибка")
```

---

## 5️⃣ Файлы

| Файл | Назначение |
|------|-----------|
| `schemas.py` | Pydantic модели |
| `config.py` | Конфигурация + логирование |
| `utils/rate_limiter.py` | Rate-limiting |
| `utils/decorators.py` | Декораторы |

---

## 🔗 Полная документация

- **SECURITY_IMPLEMENTATION.md** — подробное описание
- **INTEGRATION_CHECKLIST.md** — чек-лист интеграции
- **WEEK1_SECURITY_REPORT.md** — итоговый отчёт

---

**Готово к использованию!** ✅
