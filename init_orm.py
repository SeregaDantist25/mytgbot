# -*- coding: utf-8 -*-
"""
Инициализация ORM моделей при старте бота.
Вызывается из bot.py в main.
"""

def init_orm():
    """Инициализирует таблицы ORM."""
    try:
        from models import init_models
        init_models()
        print("✅ ORM таблицы инициализированы (documents.db)")
    except Exception as e:
        print(f"⚠️ Ошибка при инициализации ORM: {e}")
