"""
Декораторы для обработчиков команд и callback'ов.
"""

import logging
from functools import wraps
from typing import Callable, List, Optional
from telebot import types

from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


def require_role(allowed_roles: List[str]):
    """
    Декоратор для проверки роли пользователя.
    
    Использование:
        @require_role(['engineer_technologist', 'director'])
        def handle_stats(message):
            ...
    
    Args:
        allowed_roles: Список разрешённых ролей
    
    Returns:
        Декоратор функции
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(message: types.Message, *args, **kwargs):
            try:
                from db import get_user_role
                
                user_id = message.from_user.id
                user_role = get_user_role(user_id)
                
                if user_role not in allowed_roles:
                    logger.warning(
                        f"Access denied for user {user_id} with role '{user_role}' "
                        f"to function '{func.__name__}'. Allowed roles: {allowed_roles}"
                    )
                    # Отправляем сообщение об ошибке
                    from bot import bot
                    bot.reply_to(
                        message,
                        f"❌ У вас нет прав доступа к этой функции.\n"
                        f"Требуемые роли: {', '.join(allowed_roles)}"
                    )
                    return
                
                logger.info(f"Access granted for user {user_id} to function '{func.__name__}'")
                return func(message, *args, **kwargs)
            
            except Exception as e:
                logger.error(f"Error in require_role decorator: {e}", exc_info=True)
                from bot import bot
                bot.reply_to(message, "❌ Произошла ошибка при проверке прав доступа.")
                return
        
        return wrapper
    return decorator


def require_admin(func: Callable) -> Callable:
    """
    Декоратор для проверки, что пользователь администратор.
    
    Использование:
        @require_admin
        def handle_admin_command(message):
            ...
    
    Args:
        func: Функция-обработчик
    
    Returns:
        Обёрнутая функция
    """
    @wraps(func)
    def wrapper(message: types.Message, *args, **kwargs):
        try:
            from config import Config
            
            config = Config()
            user_id = message.from_user.id
            
            if user_id not in config.ADMIN_IDS:
                logger.warning(f"Admin access denied for user {user_id} to function '{func.__name__}'")
                from bot import bot
                bot.reply_to(message, "❌ Эта команда доступна только администраторам.")
                return
            
            logger.info(f"Admin access granted for user {user_id} to function '{func.__name__}'")
            return func(message, *args, **kwargs)
        
        except Exception as e:
            logger.error(f"Error in require_admin decorator: {e}", exc_info=True)
            from bot import bot
            bot.reply_to(message, "❌ Произошла ошибка при проверке прав администратора.")
            return
    
    return wrapper


def rate_limit(
    max_requests: int = 10,
    window_seconds: int = 60,
    limiter: Optional[RateLimiter] = None
):
    """
    Декоратор для ограничения частоты запросов.
    
    Использование:
        @rate_limit(max_requests=10, window_seconds=60)
        def handle_start(message):
            ...
    
    Args:
        max_requests: Максимальное количество запросов
        window_seconds: Размер окна времени в секундах
        limiter: Экземпляр RateLimiter (если None, создаётся новый)
    
    Returns:
        Декоратор функции
    """
    # Создаём rate limiter если не передан
    _limiter = limiter or RateLimiter(max_requests=max_requests, window_seconds=window_seconds)
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(message: types.Message, *args, **kwargs):
            try:
                user_id = message.from_user.id
                
                if not _limiter.is_allowed(user_id):
                    retry_after = _limiter.get_retry_after(user_id)
                    logger.warning(
                        f"Rate limit exceeded for user {user_id} in function '{func.__name__}'. "
                        f"Retry after {retry_after}s"
                    )
                    from bot import bot
                    bot.reply_to(
                        message,
                        f"⏱️ Слишком много запросов. Попробуйте через {retry_after} секунд."
                    )
                    return
                
                logger.debug(f"Rate limit check passed for user {user_id} in function '{func.__name__}'")
                return func(message, *args, **kwargs)
            
            except Exception as e:
                logger.error(f"Error in rate_limit decorator: {e}", exc_info=True)
                from bot import bot
                bot.reply_to(message, "❌ Произошла ошибка при проверке лимита запросов.")
                return
        
        return wrapper
    return decorator


def handle_exceptions(func: Callable) -> Callable:
    """
    Декоратор для обработки исключений в обработчиках.
    
    Использование:
        @handle_exceptions
        def handle_command(message):
            ...
    
    Args:
        func: Функция-обработчик
    
    Returns:
        Обёрнутая функция
    """
    @wraps(func)
    def wrapper(message: types.Message, *args, **kwargs):
        try:
            return func(message, *args, **kwargs)
        
        except ValueError as e:
            logger.warning(f"Validation error in '{func.__name__}': {e}")
            from bot import bot
            bot.reply_to(message, f"❌ Ошибка валидации: {e}")
        
        except KeyError as e:
            logger.error(f"Key error in '{func.__name__}': {e}", exc_info=True)
            from bot import bot
            bot.reply_to(message, "❌ Ошибка: требуемые данные не найдены.")
        
        except Exception as e:
            logger.error(f"Unexpected error in '{func.__name__}': {e}", exc_info=True)
            from bot import bot
            bot.reply_to(message, "❌ Произошла неожиданная ошибка. Администратор уведомлен.")
    
    return wrapper


def validate_input(schema_class):
    """
    Декоратор для валидации входных данных через Pydantic.
    
    Использование:
        @validate_input(UserCreate)
        def handle_create_user(message, user_data):
            ...
    
    Args:
        schema_class: Pydantic модель для валидации
    
    Returns:
        Декоратор функции
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(message: types.Message, data: dict, *args, **kwargs):
            try:
                # Валидируем данные через Pydantic
                validated_data = schema_class(**data)
                logger.debug(f"Input validation passed for function '{func.__name__}'")
                return func(message, validated_data, *args, **kwargs)
            
            except ValueError as e:
                logger.warning(f"Validation error in '{func.__name__}': {e}")
                from bot import bot
                bot.reply_to(message, f"❌ Ошибка валидации: {e}")
            
            except Exception as e:
                logger.error(f"Error in validate_input decorator: {e}", exc_info=True)
                from bot import bot
                bot.reply_to(message, "❌ Произошла ошибка при валидации данных.")
        
        return wrapper
    return decorator


def log_execution(func: Callable) -> Callable:
    """
    Декоратор для логирования выполнения функции.
    
    Использование:
        @log_execution
        def handle_command(message):
            ...
    
    Args:
        func: Функция-обработчик
    
    Returns:
        Обёрнутая функция
    """
    @wraps(func)
    def wrapper(message: types.Message, *args, **kwargs):
        user_id = message.from_user.id
        user_name = message.from_user.first_name or "Unknown"
        
        logger.info(f"Executing '{func.__name__}' for user {user_id} ({user_name})")
        
        try:
            result = func(message, *args, **kwargs)
            logger.info(f"Successfully executed '{func.__name__}' for user {user_id}")
            return result
        
        except Exception as e:
            logger.error(f"Error executing '{func.__name__}' for user {user_id}: {e}", exc_info=True)
            raise
    
    return wrapper


def combine_decorators(*decorators):
    """
    Комбинирует несколько декораторов.
    
    Использование:
        @combine_decorators(
            require_role(['engineer_technologist']),
            rate_limit(max_requests=10),
            handle_exceptions
        )
        def handle_command(message):
            ...
    
    Args:
        decorators: Декораторы для применения
    
    Returns:
        Функция, которая применяет все декораторы
    """
    def decorator(func: Callable) -> Callable:
        for dec in reversed(decorators):
            func = dec(func)
        return func
    
    return decorator
