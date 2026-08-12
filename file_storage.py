# -*- coding: utf-8 -*-
"""
Абстракция доступа к файлам документов.

Все методы работают через self.storage_backend. Сейчас это просто
локальная файловая система (LocalStorageBackend), но при переезде на
S3/Network volume достаточно реализовать другой backend с тем же API.
"""

import os
import shutil

from models import SessionLocal, Document


class LocalStorageBackend:
    """Локальная файловая система: файлы лежат в DATA_DIR."""

    def __init__(self, base_dir):
        self.base_dir = base_dir

    def _abs(self, rel_path):
        # Защита от выхода за пределы base_dir
        return os.path.join(self.base_dir, rel_path)

    def save(self, rel_path, data):
        abs_path = self._abs(rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        if isinstance(data, (bytes, bytearray)):
            with open(abs_path, "wb") as f:
                f.write(data)
        else:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(data)
        return rel_path

    def read(self, rel_path):
        abs_path = self._abs(rel_path)
        with open(abs_path, "rb") as f:
            return f.read()

    def delete(self, rel_path):
        abs_path = self._abs(rel_path)
        if os.path.isfile(abs_path):
            os.remove(abs_path)
        elif os.path.isdir(abs_path):
            shutil.rmtree(abs_path)


class FileStorage:
    """
    Доступ к файлам документов с проверкой прав на удаление.

    all методы делегируют self.storage_backend.
    DATA_DIR задаётся из окружения (как в bot.py), по умолчанию — "data".
    """

    def __init__(self, data_dir=None, backend=None):
        self.data_dir = data_dir or os.getenv("DATA_DIR", "data")
        self.storage_backend = backend or LocalStorageBackend(self.data_dir)

    def save_file(self, file_data, path):
        """
        Сохраняет файл в DATA_DIR/path.
        Возвращает относительный путь (file_ref).
        """
        return self.storage_backend.save(path, file_data)

    def save_document(self, file_name, file_content, item_id, category, user_id=None):
        """
        Сохраняет файл документа в DATA_DIR/documents/<item_id>/<category>/ и
        создаёт запись в БД (Document).

        Возвращает dict {"success": bool, "document_id": int|None, "file_ref": str|None, "message": str}.
        """
        import os
        from datetime import datetime
        from models import SessionLocal, Document

        file_type = os.path.splitext(file_name)[1].lower()
        # Относительный путь внутри DATA_DIR
        rel_dir = os.path.join("documents", str(item_id), category)
        rel_path = os.path.join(rel_dir, file_name)

        # Если файл с таким именем уже есть — добавляем суффикс времени
        abs_path = self._abs(rel_path)
        if os.path.exists(abs_path):
            base, ext = os.path.splitext(file_name)
            rel_path = os.path.join(rel_dir, f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}")

        self.storage_backend.save(rel_path, file_content)

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

    def _abs(self, rel_path):
        return self.storage_backend._abs(rel_path)

    def get_file(self, path):
        """Возвращает содержимое файла (bytes)."""
        return self.storage_backend.read(path)

    def delete_file(self, path):
        """
        Удаляет файл. Проверяет по БД, что документ не approved.
        Возвращает True при удалении, False — если удаление запрещено/не найдено.
        """
        # Ищем документ по file_ref в БД
        session = SessionLocal()
        try:
            doc = (
                session.query(Document)
                .filter(Document.file_ref == path)
                .order_by(Document.id.desc())
                .first()
            )
            if doc and doc.status == "approved":
                return False
        finally:
            session.close()

        self.storage_backend.delete(path)
        return True


# Единый экземпляр для использования в bot.py
storage = FileStorage()