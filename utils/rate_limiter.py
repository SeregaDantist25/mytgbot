"""
Rate limiter для защиты от спама.
"""

from collections import defaultdict
from datetime import datetime, timedelta
import threading
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Класс для ограничения частоты запросов от пользователей.
    
    Использует in-memory хранилище (словарь) для простоты.
    Потокобезопасен благодаря threading.Lock.
    """
    
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """
        Инициализирует rate limiter.
        
        Args:
            max_requests: Максимальное количество запросов в окне времени
            window_seconds: Размер окна времени в секундах
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)  # user_id -> [timestamp1, timestamp2, ...]
        self.lock = threading.Lock()
        logger.info(f"RateLimiter инициализирован: {max_requests} запросов за {window_seconds}с")
    
    def is_allowed(self, user_id: int) -> bool:
        """
        Проверяет, разрешён ли запрос для пользователя.
        
        Args:
            user_id: ID пользователя (Telegram ID)
        
        Returns:
            True если запрос разрешён, False если превышен лимит
        """
        with self.lock:
            now = datetime.now()
            cutoff = now - timedelta(seconds=self.window_seconds)
            
            # Удаляем старые запросы (старше окна времени)
            self.requests[user_id] = [
                req_time for req_time in self.requests[user_id]
                if req_time > cutoff
            ]
            
            # Проверяем лимит
            if len(self.requests[user_id]) >= self.max_requests:
                logger.warning(f"Rate limit exceeded for user {user_id}")
                return False
            
            # Добавляем новый запрос
            self.requests[user_id].append(now)
            return True
    
    def get_retry_after(self, user_id: int) -> int:
        """
        Возвращает количество секунд до следующего разрешённого запроса.
        
        Args:
            user_id: ID пользователя
        
        Returns:
            Количество секунд до следующего запроса (0 если запрос разрешён)
        """
        with self.lock:
            if not self.requests[user_id]:
                return 0
            
            oldest = self.requests[user_id][0]
            retry_after = (oldest + timedelta(seconds=self.window_seconds) - datetime.now()).total_seconds()
            return max(0, int(retry_after) + 1)
    
    def reset(self, user_id: int = None) -> None:
        """
        Сбрасывает счётчик запросов.
        
        Args:
            user_id: ID пользователя (если None, сбрасывает для всех)
        """
        with self.lock:
            if user_id is None:
                self.requests.clear()
                logger.info("Rate limiter сброшен для всех пользователей")
            else:
                self.requests.pop(user_id, None)
                logger.info(f"Rate limiter сброшен для пользователя {user_id}")
    
    def get_stats(self, user_id: int) -> dict:
        """
        Возвращает статистику запросов пользователя.
        
        Args:
            user_id: ID пользователя
        
        Returns:
            Словарь со статистикой
        """
        with self.lock:
            now = datetime.now()
            cutoff = now - timedelta(seconds=self.window_seconds)
            
            # Удаляем старые запросы
            self.requests[user_id] = [
                req_time for req_time in self.requests[user_id]
                if req_time > cutoff
            ]
            
            current_requests = len(self.requests[user_id])
            remaining = self.max_requests - current_requests
            retry_after = self.get_retry_after(user_id)
            
            return {
                'current_requests': current_requests,
                'max_requests': self.max_requests,
                'remaining': remaining,
                'retry_after': retry_after,
                'window_seconds': self.window_seconds
            }


# Глобальные rate limiters для разных операций
message_limiter = RateLimiter(max_requests=30, window_seconds=60)  # 30 сообщений в минуту
file_limiter = RateLimiter(max_requests=5, window_seconds=60)      # 5 файлов в минуту
approve_limiter = RateLimiter(max_requests=10, window_seconds=60)  # 10 утверждений в минуту
command_limiter = RateLimiter(max_requests=20, window_seconds=60)  # 20 команд в минуту
