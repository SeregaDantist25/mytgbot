#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Скрипт для обновления services/document_service.py"""

import re

with open('services/document_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Заменяем вызовы storage.save_file на storage.save_document
# Паттерн 1: в create_document
pattern1 = r'file_ref = storage\.save_file\(file_data, f"documents/\{item_id\}/\{category\}"\)'
replacement1 = '''result = storage.save_document(
        file_name=f'document{file_type or ".bin"}',
        file_content=file_data,
        item_id=item_id,
        category=category,
        user_id=user_id
    )
    if not result['success']:
        return None
    file_ref = result['file_ref']
    file_data_to_save = file_data'''

content = re.sub(pattern1, replacement1, content)

# Паттерн 2: в replace_document (строка ~222)
pattern2 = r'new_ref = storage\.save_file\(file_data, f"documents/\{doc\.item_id\}/\{doc\.category\}"\)'
replacement2 = '''result = storage.replace_document(
            document_id=document_id,
            new_file_content=file_data,
            new_file_name=None
        )
        if result['success']:
            new_ref = doc.file_ref
        else:
            return None'''

content = re.sub(pattern2, replacement2, content)

with open('services/document_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated services/document_service.py")
