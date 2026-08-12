#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Скрипт для полного обновления services/document_service.py"""

with open('services/document_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Находим и заменяем create_document (строки 19-64)
new_lines = []
i = 0
while i < len(lines):
    if i == 18 and 'def create_document(' in lines[i]:
        # Пропускаем старую функцию до следующей функции
        while i < len(lines) and not (lines[i].startswith('def ') and i > 18):
            i += 1
        # Вставляем новую функцию
        new_lines.extend([
            'def create_document(\n',
            '    item_id: int,\n',
            '    category: str,\n',
            '    file_data: bytes,\n',
            '    user_id: int,\n',
            '    file_type: Optional[str] = None,\n',
            ') -> Document:\n',
            '    """Создаёт документ и сохраняет файл в хранилище.\n',
            '\n',
            '    Args:\n',
            '        item_id: ID пункта ремонтной ведомости.\n',
            '        category: Категория документа.\n',
            '        file_data: Содержимое файла (bytes).\n',
            '        user_id: Telegram ID загрузившего пользователя.\n',
            '        file_type: Тип файла (расширение).\n',
            '\n',
            '    Returns:\n',
            '        Созданный объект Document.\n',
            '    """\n',
            '    result = storage.save_document(\n',
            '        file_name=f\'document{file_type or ".bin"}\',\n',
            '        file_content=file_data,\n',
            '        item_id=item_id,\n',
            '        category=category,\n',
            '        user_id=user_id\n',
            '    )\n',
            '    if not result["success"]:\n',
            '        return None\n',
            '    session = SessionLocal()\n',
            '    try:\n',
            '        doc = session.query(Document).filter_by(id=result["document_id"]).first()\n',
            '        return doc\n',
            '    finally:\n',
            '        session.close()\n',
            '\n',
            '\n',
        ])
    else:
        new_lines.append(lines[i])
        i += 1

with open('services/document_service.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Fixed create_document")
