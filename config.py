"""
Конфигурация бота.
"""

import os
import logging
import logging.handlers
from dataclasses import dataclass, field
from typing import List


def setup_logging(log_level: str = "INFO", log_file: str = "bot.log") -> logging.Logger:
    """
    Настраивает логирование для бота.
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Путь к файлу логов (если None, логирование только в консоль)
    
    Returns:
        Объект logger
    """
    # Создаём корневой логгер
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level))

    # Удаляем старые хендлеры, чтобы избежать дублирования записей
    # (config.py вызывает setup_logging при импорте, bot.py — повторно)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    # Форматер для логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Обработчик для файла (если указан)
    if log_file:
        # Создаём директорию для логов если её нет
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # Rotating file handler (максимум 10 MB на файл, 5 файлов)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        file_handler.setLevel(getattr(logging, log_level))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


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
        logger = logging.getLogger(__name__)
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


# Глобальная конфигурация
_config = None


def get_config() -> Config:
    """Получает глобальный объект конфигурации"""
    global _config
    if _config is None:
        _config = Config()
        _config.validate()
    return _config


# Инициализируем логирование при импорте модуля
_logger = setup_logging(
    log_level=os.getenv('LOG_LEVEL', 'INFO'),
    log_file=os.getenv('LOG_FILE', 'bot.log')
)
