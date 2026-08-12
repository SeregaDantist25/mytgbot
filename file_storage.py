# -*- coding: utf-8 -*-
"""
Абстракция доступа к файлам документов.

Хранит файлы в PostgreSQL (поле bytea в таблице documents).
Для локальной разработки (SQLite) файлы также сохраняются на диск для совместимости.
"""

import os
import shutil
from datetime import datetime
from models import SessionLocal, Document


class FileStorage:
    """
    Доступ к файлам документов с проверкой прав на удаление.
    
    Новая версия: хранит файлы в БД (Document.file_data).
    Для SQLite также сохраняет на диск (для совместимости).
    """

    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.getenv("DATA_DIR", "data")
        self.use_disk = "sqlite" in os.getenv("DATABASE_URL", "sqlite:///data/documents.db").lower()

    def save_file(self, file_data, path):
        """
        Сохраняет файл на диск (для совместимости со старым API).
        
        Args:
            file_data: содержимое файла (bytes)
            path: относительный путь в DATA_DIR
        
        Returns:
            относительный путь (file_ref)
        """
        abs_path = os.path.join(self.data_dir, path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f:
            f.write(file_data)
        return path

    def save_document(self, file_name, file_content, item_id, category, user_id=None, source="bot"):
        """
        Сохраняет файл документа в БД (и на диск для SQLite).
        
        Args:
            file_name: имя файла (str)
            file_content: содержимое файла (bytes)
            item_id: ID пункта ведомости (int)
            category: категория документа (str)
            user_id: telegram_id загружающего пользователя (int)
            source: источник документа — "bot" (загрузка через бота) или "folder" (импорт из папки)
        
        Returns:
            dict {"success": bool, "document_id": int|None, "file_ref": str|None, "message": str}
        """
        # Убедимся, что file_name содержит расширение
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
            dir_path = os.path.dirname(abs_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(abs_path, "wb") as f:
                f.write(file_content)
        
        # Сохраняем в БД
        session = SessionLocal()
        try:
            doc = Document(
                item_id=item_id,
                category=category,
                file_ref=rel_path,
                file_type=file_type,
                status="draft",
                uploaded_by=user_id,
                version=1,
                file_data=file_content,  # Сохраняем содержимое в БД
                source=source,
            )
            session.add(doc)
            session.commit()
            return {
                "success": True,
                "document_id": doc.id,
                "file_ref": rel_path,
                "message": "Документ сохранён",
            }
        except Exception as e:
            session.rollback()
            return {
                "success": False,
                "document_id": None,
                "file_ref": None,
                "message": f"Ошибка при сохранении в БД: {e}",
            }
        finally:
            session.close()

    def get_file(self, document_id=None, file_ref=None):
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
            session.close()

    def delete_file(self, document_id=None, file_ref=None):
        """
        Удаляет файл. Проверяет по БД, что документ не approved.
        
        Args:
            document_id: ID документа (int) — приоритет
            file_ref: file_ref документа (str) — если document_id не указан
        
        Returns:
            True при удалении, False — если удаление запрещено/не найдено
        """
        session = SessionLocal()
        try:
            if document_id:
                doc = session.query(Document).filter_by(id=document_id).first()
            elif file_ref:
                doc = session.query(Document).filter_by(file_ref=file_ref).first()
            else:
                return False
            
            if not doc:
                return False
            
            # Не удаляем approved документы
            if doc.status == "approved":
                return False
            
            # Удаляем с диска (если есть)
            if self.use_disk and doc.file_ref:
                abs_path = os.path.join(self.data_dir, doc.file_ref)
                if os.path.isfile(abs_path):
                    os.remove(abs_path)
            
            # Удаляем из БД
            session.delete(doc)
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()

    def replace_document(self, document_id, new_file_content, new_file_name=None):
        """
        Заменяет содержимое документа (только для draft).
        
        Args:
            document_id: ID документа (int)
            new_file_content: новое содержимое (bytes)
            new_file_name: новое имя файла (опционально)
        
        Returns:
            dict {"success": bool, "message": str}
        """
        session = SessionLocal()
        try:
            doc = session.query(Document).filter_by(id=document_id).first()
            if not doc:
                return {"success": False, "message": "Документ не найден"}
            
            if doc.status != "draft":
                return {"success": False, "message": "Можно заменять только черновики"}
            
            # Обновляем содержимое в БД
            doc.file_data = new_file_content
            
            # Если указано новое имя — обновляем file_ref
            if new_file_name:
                old_file_type = doc.file_type
                new_file_type = os.path.splitext(new_file_name)[1].lower()
                
                # Обновляем file_ref
                rel_dir = os.path.dirname(doc.file_ref)
                doc.file_ref = os.path.join(rel_dir, new_file_name)
                doc.file_type = new_file_type
                
                # Обновляем на диске (если используется)
                if self.use_disk:
                    new_abs_path = os.path.join(self.data_dir, doc.file_ref)
                    os.makedirs(os.path.dirname(new_abs_path), exist_ok=True)
                    with open(new_abs_path, "wb") as f:
                        f.write(new_file_content)
            else:
                # Просто обновляем содержимое на диске
                if self.use_disk and doc.file_ref:
                    abs_path = os.path.join(self.data_dir, doc.file_ref)
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    with open(abs_path, "wb") as f:
                        f.write(new_file_content)
            
            session.commit()
            return {"success": True, "message": "Документ обновлён"}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"Ошибка: {e}"}
        finally:
            session.close()


# Единый экземпляр для использования в bot.py
storage = FileStorage()
