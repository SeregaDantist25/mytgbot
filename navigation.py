# -*- coding: utf-8 -*-
"""Навигация по категориям и версиям документов.

Навигация по ремонтной ведомости находится в ``document_manager.py`` и
``bot_handlers_new.py``. Здесь остаются только запросы и клавиатуры документов,
чтобы две реализации разделов/пунктов не расходились.
"""

from telebot import types
from models import SessionLocal, StatementItem, Document


# Категории документов
DOCUMENT_CATEGORIES = {
    "defect_act": "📋 Акты дефектации",
    "avr": "⚙️ АВР",
    "other": "📄 Прочее"
}


def get_item_details(item_id):
    """Получить детали пункта."""
    session = SessionLocal()
    try:
        item = session.query(StatementItem).filter_by(id=item_id).first()
        return item
    finally:
        session.close()


def format_item_details(item):
    """Форматировать детали пункта для вывода."""
    if not item:
        return "❌ Пункт не найден"
    
    text = f"📋 **Пункт {item.item_number}**\n\n"
    text += f"**Раздел:** {item.section}\n"
    text += f"**Описание:** {item.description}\n"
    text += f"**Количество:** {item.quantity or 'не указано'}\n"
    text += f"**Статус:** {item.status}\n"
    return text


# ============================================================================
# Функции для работы с категориями документов
# ============================================================================

def get_categories_for_item(item_id):
    """Получить категории документов для пункта."""
    session = SessionLocal()
    try:
        categories = session.query(Document.category).filter_by(
            item_id=item_id
        ).distinct().all()
        return [c[0] for c in categories if c[0]]
    finally:
        session.close()


def get_documents_for_category(item_id, category, page=0, items_per_page=10):
    """Получить документы по категории с пагинацией."""
    session = SessionLocal()
    try:
        docs = session.query(Document).filter_by(
            item_id=item_id,
            category=category
        ).order_by(Document.version.desc()).all()
        
        # Пагинация
        start = page * items_per_page
        end = start + items_per_page
        page_docs = docs[start:end]
        
        # Копируем данные перед закрытием сессии
        result = []
        for doc in page_docs:
            result.append({
                'id': doc.id,
                'version': doc.version,
                'status': doc.status,
                'file_type': doc.file_type,
                'uploaded_at': doc.uploaded_at
            })
        
        return result, len(docs)
    finally:
        session.close()


def build_categories_keyboard(item_id):
    """Построить InlineKeyboardMarkup со списком категорий."""
    categories = get_categories_for_item(item_id)
    
    if not categories:
        return None
    
    keyboard = types.InlineKeyboardMarkup()
    for cat in categories:
        label = DOCUMENT_CATEGORIES.get(cat, cat)
        callback = f"docs_{item_id}_{cat}_0"
        keyboard.add(types.InlineKeyboardButton(label, callback_data=callback))
    
    # Кнопка "Загрузить документ"
    keyboard.add(types.InlineKeyboardButton("📤 Загрузить документ", callback_data=f"upload_{item_id}"))
    
    return keyboard


def build_documents_keyboard(item_id, category, page=0, items_per_page=10):
    """Построить InlineKeyboardMarkup со списком документов категории."""
    docs, total = get_documents_for_category(item_id, category, page, items_per_page)
    
    if not docs:
        return None
    
    keyboard = types.InlineKeyboardMarkup()
    
    for doc in docs:
        status_emoji = "✅" if doc['status'] == "approved" else "📝" if doc['status'] == "draft" else "📦"
        label = f"{status_emoji} v{doc['version']} ({doc['status']})"
        callback = f"doc_{doc['id']}"
        keyboard.add(types.InlineKeyboardButton(label, callback_data=callback))
    
    # Кнопки пагинации
    if page > 0:
        keyboard.add(types.InlineKeyboardButton("◀ Назад", callback_data=f"docs_{item_id}_{category}_{page-1}"))
    if (page + 1) * items_per_page < total:
        keyboard.add(types.InlineKeyboardButton("Далее ▶", callback_data=f"docs_{item_id}_{category}_{page+1}"))
    
    # Кнопка "Назад к категориям"
    keyboard.add(types.InlineKeyboardButton("◀ К категориям", callback_data=f"categories_{item_id}"))
    
    return keyboard


def format_document_details(doc_id):
    """Форматировать детали документа для вывода."""
    session = SessionLocal()
    try:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return "❌ Документ не найден"
        
        item = session.query(StatementItem).filter_by(id=doc.item_id).first()
        
        text = f"📄 **Документ v{doc.version}**\n\n"
        text += f"**Статус:** {doc.status}\n"
        text += f"**Категория:** {DOCUMENT_CATEGORIES.get(doc.category, doc.category)}\n"
        text += f"**Тип файла:** {doc.file_type}\n"
        text += f"**Загружен:** {doc.uploaded_at.strftime('%d.%m.%Y %H:%M') if doc.uploaded_at else 'неизвестно'}\n"
        if item:
            text += f"**Пункт:** {item.item_number}\n"
        
        return text
    finally:
        session.close()
