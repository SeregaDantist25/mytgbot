#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Скрипт для исправления get_file в file_storage.py"""

with open('file_storage.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Заменяем get_file на версию, которая поддерживает оба варианта
old_get_file = '''    def get_file(self, document_id=None, file_ref=None):
        """
        Возвращает содержимое файла (bytes).
        
        Args:
            document_id: ID документа (int) — приоритет
            file_ref: file_ref документа (str) — если document_id не указан
        
        Returns:
            bytes или None
        """
        session = SessionLocal()
        try:
            if document_id:
                doc = session.query(Document).filter_by(id=document_id).first()
            elif file_ref:
                doc = session.query(Document).filter_by(file_ref=file_ref).first()
            else:
                return None
            
            if not doc:
                return None
            
            # Сначала пытаемся получить из БД
            if doc.file_data:
                return doc.file_data
            
            # Если в БД нет — пытаемся прочитать с диска (для совместимости)
            if self.use_disk and doc.file_ref:
                abs_path = os.path.join(self.data_dir, doc.file_ref)
                if os.path.exists(abs_path):
                    with open(abs_path, "rb") as f:
                        return f.read()
            
            return None
        finally:
            session.close()'''

new_get_file = '''    def get_file(self, document_id=None, file_ref=None):
        """
        Возвращает содержимое файла (bytes).
        
        Поддерживает оба варианта вызова:
        - get_file(document_id=1) — по ID документа
        - get_file(file_ref="documents/1/defect_act/file.pdf") — по file_ref
        - get_file("documents/1/defect_act/file.pdf") — старый API (file_ref как первый аргумент)
        
        Args:
            document_id: ID документа (int) — приоритет
            file_ref: file_ref документа (str) — если document_id не указан
        
        Returns:
            bytes или None
        """
        # Если document_id — это строка, то это старый API (file_ref передан как первый аргумент)
        if isinstance(document_id, str) and file_ref is None:
            file_ref = document_id
            document_id = None
        
        session = SessionLocal()
        try:
            if document_id:
                doc = session.query(Document).filter_by(id=document_id).first()
            elif file_ref:
                doc = session.query(Document).filter_by(file_ref=file_ref).first()
            else:
                return None
            
            if not doc:
                return None
            
            # Сначала пытаемся получить из БД
            if doc.file_data:
                return doc.file_data
            
            # Если в БД нет — пытаемся прочитать с диска (для совместимости)
            if self.use_disk and doc.file_ref:
                abs_path = os.path.join(self.data_dir, doc.file_ref)
                if os.path.exists(abs_path):
                    with open(abs_path, "rb") as f:
                        return f.read()
            
            return None
        finally:
            session.close()'''

content = content.replace(old_get_file, new_get_file)

with open('file_storage.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed get_file in file_storage.py")
