# 📋 КОНКРЕТНЫЕ РЕКОМЕНДАЦИИ И ПРИМЕРЫ КОДА

---

## 1️⃣ БЕЗОПАСНОСТЬ: Валидация входных данных

### Проблема
```python
# ❌ ПЛОХО: Нет валидации
def add_user(user_id, name, role):
    session = SessionLocal()
    try:
        user = User(telegram_id=user_id, role=role)
        session.add(user)
        session.commit()
    finally:
        session.close()

# Пользователь может передать:
# - user_id = "admin" (строка вместо int)
# - name = "'; DROP TABLE users; --" (SQL-инъекция)
# - role = "superadmin" (несуществующая роль)
```

### Решение
```python
# ✅ ХОРОШО: С валидацией через Pydantic
from pydantic import BaseModel, validator, Field
from enum import Enum
from typing import Optional

class UserRole(str, Enum):
    ENGINEER = "engineer_technologist"
    DIRECTOR = "director"
    BUILDER = "builder"
    CUSTOMER = "customer"

class UserCreate(BaseModel):
    telegram_id: int = Field(..., gt=0, description="Telegram ID должен быть положительным")
    name: str = Field(..., min_length=1, max_length=255, description="Имя 1-255 символов")
    role: UserRole = Field(default=UserRole.CUSTOMER, description="Роль пользователя")
    
    @validator('telegram_id')
    def validate_telegram_id(cls, v):
        if v > 9999999999:  # Telegram ID не может быть больше
            raise ValueError('Invalid Telegram ID')
        return v
    
    @validator('name')
    def validate_name(cls, v):
        # Проверяем, что имя не содержит опасных символов
        if any(char in v for char in ['<', '>', '"', "'", ';', '--']):
            raise ValueError('Name contains invalid characters')
        return v

def add_user(user_data: UserCreate) -> User:
    """Добавляет пользователя с валидацией"""
    session = SessionLocal()
    try:
        user = User(
            telegram_id=user_data.telegram_id,
            name=user_data.name,
            role=user_data.role.value
        )
        session.add(user)
        session.commit()
        return user
    except Exception as e:
        session.rollback()
        logger.error(f"Error adding user: {e}")
        raise
    finally:
        session.close()

# Использование:
try:
    user_data = UserCreate(telegram_id=123456789, name="John Doe", role=UserRole.ENGINEER)
    user = add_user(user_data)
except ValueError as e:
    logger.warning(f"Validation error: {e}")
    bot.reply_to(message, f"❌ Ошибка: {e}")
```

### Установка Pydantic
```bash
pip install pydantic==2.0.0
```

---

## 2️⃣ БЕЗОПАСНОСТЬ: Rate-limiting

### Проблема
```python
# ❌ ПЛОХО: Нет защиты от спама
@bot.message_handler(commands=['start'])
def handle_start(message):
    # Пользователь может отправить 1000 сообщений в секунду
    # Бот будет обрабатывать все
    ...
```

### Решение
```python
# ✅ ХОРОШО: С rate-limiting
from collections import defaultdict
from datetime import datetime, timedelta
import threading

class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
        self.lock = threading.Lock()
    
    def is_allowed(self, user_id: int) -> bool:
        """Проверяет, разрешён ли запрос"""
        with self.lock:
            now = datetime.now()
            cutoff = now - timedelta(seconds=self.window_seconds)
            
            # Удаляем старые запросы
            self.requests[user_id] = [
                req_time for req_time in self.requests[user_id]
                if req_time > cutoff
            ]
            
            # Проверяем лимит
            if len(self.requests[user_id]) >= self.max_requests:
                return False
            
            self.requests[user_id].append(now)
            return True
    
    def get_retry_after(self, user_id: int) -> int:
        """Возвращает количество секунд до следующего запроса"""
        with self.lock:
            if not self.requests[user_id]:
                return 0
            
            oldest = self.requests[user_id][0]
            retry_after = (oldest + timedelta(seconds=self.window_seconds) - datetime.now()).total_seconds()
            return max(0, int(retry_after) + 1)

# Создаём rate limiter
rate_limiter = RateLimiter(max_requests=10, window_seconds=60)

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    
    if not rate_limiter.is_allowed(user_id):
        retry_after = rate_limiter.get_retry_after(user_id)
        bot.reply_to(
            message,
            f"⏱️ Слишком много запросов. Попробуйте через {retry_after} секунд."
        )
        return
    
    # Обработка команды
    bot.reply_to(message, "👋 Добро пожаловать!")

# Разные лимиты для разных операций
message_limiter = RateLimiter(max_requests=30, window_seconds=60)  # 30 сообщений в минуту
file_limiter = RateLimiter(max_requests=5, window_seconds=60)      # 5 файлов в минуту
approve_limiter = RateLimiter(max_requests=10, window_seconds=60)  # 10 утверждений в минуту
```

---

## 3️⃣ АРХИТЕКТУРА: Разбиение bot.py на модули

### Текущая структура (ПЛОХО)
```
bot.py (2424 строк)
├── Импорты
├── Конфигурация
├── Обработчики сообщений (27 функций)
├── Обработчики callback'ов (15+ функций)
├── Логика парсинга Excel
├── Логика создания документов
├── Логика версионирования
└── Логика ролей и прав доступа
```

### Новая структура (ХОРОШО)
```
bot.py (200 строк)
├── Импорты
├── Конфигурация
├── Инициализация бота
└── Регистрация обработчиков

handlers/
├── __init__.py
├── message_handlers.py (обработчики сообщений)
├── callback_handlers.py (обработчики callback'ов)
├── document_handlers.py (работа с документами)
├── admin_handlers.py (админ-функции)
└── error_handlers.py (обработка ошибок)

services/
├── __init__.py
├── user_service.py (работа с пользователями)
├── document_service.py (работа с документами)
├── file_service.py (работа с файлами)
└── excel_service.py (парсинг Excel)

utils/
├── __init__.py
├── validators.py (валидация)
├── formatters.py (форматирование)
├── decorators.py (декораторы)
└── constants.py (константы)

config.py (конфигурация)
```

### Пример: handlers/message_handlers.py
```python
# handlers/message_handlers.py
import logging
from typing import Optional
from telebot import TeleBot, types
from services.user_service import UserService
from utils.decorators import require_role, rate_limit

logger = logging.getLogger(__name__)

class MessageHandlers:
    def __init__(self, bot: TeleBot, user_service: UserService):
        self.bot = bot
        self.user_service = user_service
    
    @rate_limit(max_requests=30, window_seconds=60)
    def handle_start(self, message: types.Message) -> None:
        """Обработчик команды /start"""
        try:
            user_id = message.from_user.id
            user = self.user_service.get_or_create_user(user_id, message.from_user.first_name)
            
            welcome_text = f"👋 Добро пожаловать, {user.name}!\n\nВаша роль: {user.role}"
            self.bot.reply_to(message, welcome_text)
            
            logger.info(f"User {user_id} started bot")
        except Exception as e:
            logger._error(f"Error in handle_start: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Произошла ошибка. Администратор уведомлен.")
    
    @require_role(['engineer_technologist', 'director'])
    def handle_stats(self, message: types.Message) -> None:
        """Обработчик команды /stats"""
        try:
            stats = self.user_service.get_stats()
            self.bot.reply_to(message, f"📊 Статистика:\n{stats}")
        except Exception as e:
            logger.error(f"Error in handle_stats: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Произошла ошибка.")

def register_message_handlers(bot: TeleBot, user_service: UserService) -> None:
    """Регистрирует обработчики сообщений"""
    handlers = MessageHandlers(bot, user_service)
    
    bot.register_message_handler(
        handlers.handle_start,
        commands=['start']
    )
    
    bot.register_message_handler(
        handlers.handle_stats,
        commands=['stats']
    )
```

### Пример: bot.py (новый, компактный)
```python
# bot.py
import os
import logging
from telebot import TeleBot, custom_filters

from config import Config
from handlers.message_handlers import register_message_handlers
from handlers.callback_handlers import register_callback_handlers
from handlers.error_handlers import register_error_handlers
from services.user_service import UserService

# Конфигурация логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загружаем конфигурацию
config = Config()
config.validate()

# Инициализируем бот
bot = TeleBot(config.BOT_TOKEN)
bot.add_custom_filter(custom_filters.StateFilter(bot))

# Инициализируем сервисы
user_service = UserService()

# Регистрируем обработчики
register_message_handlers(bot, user_service)
register_callback_handlers(bot, user_service)
register_error_handlers(bot)

if __name__ == '__main__':
    logger.info("Bot started")
    bot.infinity_polling(skip_pending=True, timeout=30)
```

---

## 4️⃣ КАЧЕСТВО КОДА: Type hints

### Проблема
```python
# ❌ ПЛОХО: Без type hints
def get_user(user_id):
    session = SessionLocal()
    try:
        return session.query(User).filter(User.telegram_id == user_id).first()
    finally:
        session.close()

# IDE не знает, что возвращает функция
# Сложнее отлаживать
```

### Решение
```python
# ✅ ХОРОШО: С type hints
from typing import Optional
from sqlalchemy.orm import Session

def get_user(user_id: int) -> Optional[User]:
    """
    Получает пользователя по telegram_id.
    
    Args:
        user_id: Telegram ID пользователя
    
    Returns:
        Объект User или None, если не найден
    
    Raises:
        ValueError: Если user_id некорректен
    """
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError(f"Invalid user_id: {user_id}")
    
    session = SessionLocal()
    try:
        return session.query(User).filter(User.telegram_id == user_id).first()
    finally:
        session.close()

# Другие примеры
def create_document(
    item_id: int,
    category: str,
    file_data: bytes,
    user_id: int
) -> Document:
    """Создаёт новый документ"""
    ...

def get_documents(
    item_id: int,
    category: Optional[str] = None,
    status: Optional[str] = None
) -> list[Document]:
    """Получает документы с фильтрацией"""
    ...

def format_document_info(doc: Document) -> str:
    """Форматирует информацию о документе"""
    ...
```

### Проверка типов с mypy
```bash
# Установка
pip install mypy==1.0.0

# Проверка
mypy bot.py handlers/ services/ utils/

# Конфигурация (mypy.ini)
[mypy]
python_version = 3.8
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True
```

---

## 5️⃣ КАЧЕСТВО КОДА: Логирование

### Проблема
```python
# ❌ ПЛОХО: Используется print
print(f"✅ ГОСТ чекер загружен. Доступно ГОСТов: {len(gost_checker.get_all_gosts())}")
print(f"⚠️ Ошибка при загрузке ГОСТ чекера: {e}")

# Нельзя отключить
# Нет уровней логирования
# Сложно отлаживать на production
```

### Решение
```python
# ✅ ХОРОШО: Используется logging
import logging

logger = logging.getLogger(__name__)

try:
    from gost_checker import GOSTChecker
    gost_checker = GOSTChecker()
    logger.info(f"ГОСТ чекер загружен. Доступно ГОСТов: {len(gost_checker.get_all_gosts())}")
except ImportError as e:
    logger.warning(f"Модуль ГОСТ чекера не найден: {e}")
except Exception as e:
    logger.error(f"Ошибка при загрузке ГОСТ чекера: {e}", exc_info=True)

# Конфигурация логирования (config.py)
import logging
import logging.handlers
import os

def setup_logging(log_level: str = "INFO", log_file: str = "bot.log"):
    """Настраивает логирование"""
    # Создаём логгер
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level))
    
    # Форматер
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Обработчик для файла
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

# Использование в bot.py
if __name__ == '__main__':
    setup_logging(log_level=os.getenv('LOG_LEVEL', 'INFO'))
    logger = logging.getLogger(__name__)
    logger.info("Bot started")
    bot.infinity_polling()
```

---

## 6️⃣ ПРОИЗВОДИТЕЛЬНОСТЬ: Индексы в БД

### Проблема
```python
# ❌ ПЛОХО: Нет индексов
# Запрос будет медленным при 10000+ документов
docs = session.query(Document).filter(
    Document.item_id == item_id,
    Document.category == category
).all()
```

### Решение
```python
# ✅ ХОРОШО: С индексами
from sqlalchemy import Index

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("repair_items.id"), nullable=False)
    category = Column(String, nullable=False)
    status = Column(String, default="draft")
    uploader_id = Column(BigInteger, ForeignKey("users.telegram_id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Добавляем индексы
    __table_args__ = (
        Index('idx_item_category', 'item_id', 'category'),  # Для фильтрации
        Index('idx_status', 'status'),                       # Для поиска по статусу
        Index('idx_uploader', 'uploader_id'),                # Для поиска по автору
        Index('idx_created_at', 'created_at'),               # Для сортировки по дате
    )

# Миграция (если используется Alembic)
# alembic revision --autogenerate -m "Add indexes to documents"
# alembic upgrade head
```

---

## 7️⃣ ПРОИЗВОДИТЕЛЬНОСТЬ: Кэширование

### Проблема
```python
# ❌ ПЛОХО: Каждый раз загружаем из БД
def get_ships():
    session = SessionLocal()
    try:
        return session.query(Ship).all()  # Медленно при 100+ судах
    finally:
        session.close()
```

### Решение
```python
# ✅ ХОРОШО: С кэшированием
from functools import lru_cache
from datetime import datetime, timedelta
import threading

class CachedRepository:
    def __init__(self, cache_ttl_seconds: int = 300):
        self.cache_ttl = cache_ttl_seconds
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
    
    def _is_cache_valid(self, key: str) -> bool:
        """Проверяет, что кэш ещё свежий"""
        if key not in self._cache_time:
            return False
        
        age = (datetime.now() - self._cache_time[key]).total_seconds()
        return age < self.cache_ttl
    
    def get_ships(self) -> list[Ship]:
        """Получает суда с кэшированием"""
        with self._lock:
            if self._is_cache_valid('ships'):
                return self._cache['ships']
        
        # Загружаем из БД
        session = SessionLocal()
        try:
            ships = session.query(Ship).all()
            
            with self._lock:
                self._cache['ships'] = ships
                self._cache_time['ships'] = datetime.now()
            
            return ships
        finally:
            session.close()
    
    def invalidate(self, key: str = None):
        """Инвалидирует кэш"""
        with self._lock:
            if key:
                self._cache.pop(key, None)
                self._cache_time.pop(key, None)
            else:
                self._cache.clear()
                self._cache_time.clear()

# Использование
repo = CachedRepository(cache_ttl_seconds=300)

# Получаем суда (первый раз из БД, потом из кэша)
ships = repo.get_ships()

# Инвалидируем кэш после изменения
repo.invalidate('ships')
```

---

## 8️⃣ ТЕСТИРОВАНИЕ: Юнит-тесты

### Структура
```
tests/
├── __init__.py
├── conftest.py (фикстуры)
├── test_models.py
├── test_services.py
├── test_handlers.py
└── test_validators.py
```

### Пример: tests/test_services.py
```python
# tests/test_services.py
import pytest
from unittest.mock import Mock, patch
from services.user_service import UserService
from models import User

@pytest.fixture
def user_service():
    """Фикстура для UserService"""
    return UserService()

@pytest.fixture
def mock_session():
    """Фикстура для mock сессии"""
    return Mock()

class TestUserService:
    def test_get_user_success(self, user_service, mock_session):
        """Тест успешного получения пользователя"""
        # Arrange
        user_id = 123456789
        expected_user = User(telegram_id=user_id, role="engineer_technologist")
        
        with patch('services.user_service.SessionLocal', return_value=mock_session):
            mock_session.query.return_value.filter.return_value.first.return_value = expected_user
            
            # Act
            result = user_service.get_user(user_id)
            
            # Assert
            assert result == expected_user
            assert result.telegram_id == user_id
    
    def test_get_user_not_found(self, user_service, mock_session):
        """Тест получения несуществующего пользователя"""
        # Arrange
        user_id = 999999999
        
        with patch('services.user_service.SessionLocal', return_value=mock_session):
            mock_session.query.return_value.filter.return_value.first.return_value = None
            
            # Act
            result = user_service.get_user(user_id)
            
            # Assert
            assert result is None
    
    def test_get_user_invalid_id(self, user_service):
        """Тест с некорректным ID"""
        # Act & Assert
        with pytest.raises(ValueError):
            user_service.get_user(-1)
    
    def test_create_user_success(self, user_service, mock_session):
        """Тест успешного создания пользователя"""
        # Arrange
        user_data = {
            'telegram_id': 123456789,
            'name': 'John Doe',
            'role': 'engineer_technologist'
        }
        
        with patch('services.user_service.SessionLocal', return_value=mock_session):
            # Act
            result = user_service.create_user(**user_data)
            
            # Assert
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()

# Запуск тестов
# pytest tests/test_services.py -v
# pytest tests/ --cov=services --cov-report=html
```

### Конфигурация pytest (pytest.ini)
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

---

## 9️⃣ CI/CD: GitHub Actions

### Файл: .github/workflows/tests.yml
```yaml
name: Tests

on:
  push:
    branches: [ master, develop ]
  pull_request:
    branches: [ master, develop ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        python-version: ['3.8', '3.9', '3.10', '3.11']
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest pytest-cov flake8 mypy black isort
    
    - name: Lint with flake8
      run: |
        flake8 bot.py handlers/ services/ utils/ --count --select=E9,F63,F7,F82 --show-source --statistics
        flake8 bot.py handlers/ services/ utils/ --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
    
    - name: Check formatting with black
      run: black --check bot.py handlers/ services/ utils/
    
    - name: Check imports with isort
      run: isort --check-only bot.py handlers/ services/ utils/
    
    - name: Type check with mypy
      run: mypy bot.py handlers/ services/ utils/ --ignore-missing-imports
    
    - name: Run tests with pytest
      run: pytest tests/ --cov=. --cov-report=xml
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        flags: unittests
        name: codecov-umbrella
```

### Файл: .github/workflows/lint.yml
```yaml
name: Lint

on:
  push:
    branches: [ master, develop ]
  pull_request:
    branches: [ master, develop ]

jobs:
  lint:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install flake8 black isort mypy
    
    - name: Format with black
      run: black bot.py handlers/ services/ utils/
    
    - name: Sort imports with isort
      run: isort bot.py handlers/ services/ utils/
    
    - name: Commit changes
      run: |
        git config --local user.email "action@github.com"
        git config --local user.name "GitHub Action"
        git add -A
        git commit -m "style: format code with black and isort" || true
    
    - name: Push changes
      uses: ad-m/github-push-action@master
      with:
        github_token: ${{ secrets.GITHUB_TOKEN }}
```

---

## 🔟 КОНФИГУРАЦИЯ: config.py

### Файл: config.py
```python
# config.py
import os
from dataclasses import dataclass, field
from typing import List
import logging

logger = logging.getLogger(__name__)

@dataclass
class Config:
    """Конфигурация бота"""
    
    # Telegram
    BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    ADMIN_IDS: List[int] = field(default_factory=lambda: [
        int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()
    ])
    
    # API
    GROQ_API_KEY: str = os.getenv('GROQ_API_KEY', '')
    ENGINEER_CODE: str = os.getenv('ENGINEER_CODE', '')
    
    # Database
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite:///data/documents.db')
    
    # Paths
    DATA_DIR: str = os.getenv('DATA_DIR', 'data')
    TEMPLATES_DIR: str = os.getenv('TEMPLATES_DIR', 'templates')
    
    # Logging
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE: str = os.getenv('LOG_FILE', 'bot.log')
    
    # Rate limiting
    RATE_LIMIT_MESSAGES: int = int(os.getenv('RATE_LIMIT_MESSAGES', '30'))
    RATE_LIMIT_FILES: int = int(os.getenv('RATE_LIMIT_FILES', '5'))
    RATE_LIMIT_WINDOW: int = int(os.getenv('RATE_LIMIT_WINDOW', '60'))
    
    # Cache
    CACHE_TTL: int = int(os.getenv('CACHE_TTL', '300'))
    
    # File upload
    MAX_FILE_SIZE: int = int(os.getenv('MAX_FILE_SIZE', '52428800'))  # 50 MB
    ALLOWED_EXTENSIONS: List[str] = field(default_factory=lambda: [
        '.pdf', '.docx', '.xlsx', '.jpg', '.png'
    ])
    
    def validate(self) -> None:
        """Валидирует конфигурацию"""
        errors = []
        
        if not self.BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN не установлен")
        
        if not self.GROQ_API_KEY:
            logger.warning("GROQ_API_KEY не установлен")
        
        if not self.ENGINEER_CODE:
            logger.warning("ENGINEER_CODE не установлен")
        
        if not os.path.exists(self.DATA_DIR):
            os.makedirs(self.DATA_DIR)
            logger.info(f"Создана папка {self.DATA_DIR}")
        
        if not os.path.exists(self.TEMPLATES_DIR):
            logger.warning(f"Папка {self.TEMPLATES_DIR} не найдена")
        
        if errors:
            raise ValueError('\n'.join(errors))
    
    def __repr__(self) -> str:
        """Возвращает строковое представление конфигурации"""
        return f"""
Config:
  BOT_TOKEN: {'*' * 10}
  ADMIN_IDS: {self.ADMIN_IDS}
  DATABASE_URL: {self.DATABASE_URL}
  DATA_DIR: {self.DATA_DIR}
  LOG_LEVEL: {self.LOG_LEVEL}
  RATE_LIMIT_MESSAGES: {self.RATE_LIMIT_MESSAGES}
  CACHE_TTL: {self.CACHE_TTL}
"""

# Использование
if __name__ == '__main__':
    config = Config()
    config.validate()
    print(config)
```

---

## 📊 ИТОГОВАЯ ТАБЛИЦА РЕКОМЕНДАЦИЙ

| Проблема | Решение | Время | Приоритет |
|----------|---------|-------|-----------|
| Отсутствие валидации | Pydantic | 10 ч | 🔴 КРИТИЧНЫЙ |
| Отсутствие rate-limiting | RateLimiter класс | 8 ч | 🔴 КРИТИЧНЫЙ |
| Монолитный bot.py | Разбиение на модули | 40 ч | 🔴 КРИТИЧНЫЙ |
| Отсутствие type hints | Добавить type hints | 30 ч | 🔴 КРИТИЧНЫЙ |
| Отсутствие логирования | logging модуль | 20 ч | 🔴 КРИТИЧНЫЙ |
| Отсутствие тестов | pytest | 40 ч | 🔴 КРИТИЧНЫЙ |
| Отсутствие индексов | SQLAlchemy Index | 10 ч | ⚠️ ВЫСОКИЙ |
| Отсутствие кэширования | CachedRepository | 15 ч | ⚠️ ВЫСОКИЙ |
| Отсутствие CI/CD | GitHub Actions | 15 ч | ⚠️ ВЫСОКИЙ |
| Отсутствие конфигурации | config.py | 10 ч | ⚠️ ВЫСОКИЙ |

**ИТОГО:** ~198 часов (~5 недель)

---

**Дата:** 2026-08-07  
**Версия:** commit 513e30a
