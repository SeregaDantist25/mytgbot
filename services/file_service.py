# -*- coding: utf-8 -*-
"""
Сервис работы с файлами.

Обёртка над FileStorage (file_storage.py), предоставляющая простые
функции сохранения, чтения и удаления файлов.
"""

from typing import Optional, Union

from file_storage import storage


def save_file(file_data: Union[bytes, str], path: str) -> str:
    """Сохраняет файл в хранилище.

    Args:
        file_data: Содержимое файла (bytes или str).
        path: Относительный путь в хранилище.

    Returns:
        Относительный путь (file_ref) сохранённого файла.
    """
    return storage.save_file(file_data, path)


def get_file(path: str) -> bytes:
    """Возвращает содержимое файла.

    Args:
        path: Относительный путь в хранилище.

    Returns:
        Содержимое файла (bytes).
    """
    return storage.get_file(path)


def delete_file(path: str) -> bool:
    """Удаляет файл.

    Args:
        path: Относительный путь в хранилище.

    Returns:
        True при удалении, False — если удаление запрещено/не найдено.
    """
    return storage.delete_file(path)
