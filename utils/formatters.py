# -*- coding: utf-8 -*-
"""
Форматирование сообщений для пользователя.

Содержит функции, которые превращают объекты БД (документы, пункты
ремонтной ведомости) в человекочитаемые текстовые сообщения.
"""

from typing import Optional

from models import Document, User


def format_document_info(doc: Document) -> str:
    """Форматирует информацию о документе.

    Args:
        doc: Объект документа (ORM-модель).

    Returns:
        Строка с информацией о документе.
    """
    status_emoji = {
        "draft": "📝",
        "approved": "✅",
        "archived": "📦",
    }

    status_text = {
        "draft": "Черновик",
        "approved": "Утверждён",
        "archived": "Архивирован",
    }

    info = f"""
{status_emoji.get(doc.status, '❓')} {status_text.get(doc.status, 'Неизвестно')}

📄 Категория: {doc.category}
📅 Создан: {doc.uploaded_at.strftime('%d.%m.%Y %H:%M')}
👤 Автор: {doc.uploader.name if doc.uploader else 'Неизвестно'}
"""
    return info


def format_item_details(item) -> str:
    """Форматирует детали пункта ремонтной ведомости.

    Args:
        item: Объект пункта ремонтной ведомости.

    Returns:
        Строка с деталями пункта.
    """
    return f"""
📌 {item.item_number}. {item.description}
📊 Кол-во: {item.quantity or 'не указано'}
📂 Раздел: {item.section or 'не указан'}
"""
