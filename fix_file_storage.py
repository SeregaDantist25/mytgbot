#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Скрипт для исправления file_storage.py"""

with open('file_storage.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Заменяем логику в save_document
old_logic = '''        file_type = os.path.splitext(file_name)[1].lower()
        
        # Относительный путь (для file_ref и совместимости с диском)
        rel_dir = os.path.join("documents", str(item_id), category)
        rel_path = os.path.join(rel_dir, file_name)
        
        # Если файл с таким именем уже есть — добавляем суффикс времени
        if self.use_disk:
            abs_path = os.path.join(self.data_dir, rel_path)
            if os.path.exists(abs_path):
                base, ext = os.path.splitext(file_name)
                rel_path = os.path.join(rel_dir, f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}")
                abs_path = os.path.join(self.data_dir, rel_path)
            
            # Сохраняем на диск
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "wb") as f:
                f.write(file_content)'''

new_logic = '''        # Убедимся, что file_name содержит расширение
        if not os.path.splitext(file_name)[1]:
            file_name = f"{file_name}.bin"
        
        file_type = os.path.splitext(file_name)[1].lower()
        
        # Относительный путь (для file_ref и совместимости с диском)
        rel_dir = os.path.join("documents", str(item_id), category)
        rel_path = os.path.join(rel_dir, file_name)
        
        # Если файл с таким именем уже есть — добавляем суффикс времени
        if self.use_disk:
            abs_path = os.path.join(self.data_dir, rel_path)
            if os.path.exists(abs_path):
                base, ext = os.path.splitext(file_name)
                rel_path = os.path.join(rel_dir, f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}")
                abs_path = os.path.join(self.data_dir, rel_path)
            
            # Сохраняем на диск
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "wb") as f:
                f.write(file_content)'''

content = content.replace(old_logic, new_logic)

with open('file_storage.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed file_storage.py")
