#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Патч для добавления инициализации ORM в bot.py"""

with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

search_str = 'if __name__ == \'__main__\':\n    print("🤖 Бот-ассистент запущен!")'
replace_str = '''if __name__ == '__main__':
    # Инициализируем ORM таблицы
    if DOCUMENT_MANAGER_AVAILABLE:
        try:
            from models import init_models
            init_models()
            print("✅ ORM таблицы инициализированы (documents.db)")
        except Exception as e:
            print(f"⚠️ Ошибка при инициализации ORM: {e}")
    
    print("🤖 Бот-ассистент запущен!")'''

if search_str in content:
    content = content.replace(search_str, replace_str)
    with open('bot.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ Инициализация ORM добавлена в bot.py")
else:
    print("❌ Не найдена точка вставки")
