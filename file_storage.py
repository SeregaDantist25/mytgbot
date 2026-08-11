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