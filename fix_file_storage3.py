#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Скрипт для исправления file_storage.py — исправляем создание папок"""

with open('file_storage.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Заменяем логику создания папок
old_logic = '''            # Сохраняем на диск
            dir_path = os.path.dirname(abs_path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
            with open(abs_path, "wb") as f:
                f.write(file_content)'''

new_logic = '''            # Сохраняем на диск
            dir_path = os.path.dirname(abs_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(abs_path, "wb") as f:
                f.write(file_content)'''

content = content.replace(old_logic, new_logic)

with open('file_storage.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed folder creation in file_storage.py")
