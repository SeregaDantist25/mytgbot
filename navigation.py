# -*- coding: utf-8 -*-
"""
Функции навигации по пунктам ремонтной ведомости и документам.
Используют ORM (models.py) для получения данных из БД.
"""

from telebot import types
from models import SessionLocal, Ship, StatementItem, RepairStatement, Document


# Категории документов
DOCUMENT_CATEGORIES = {
    "defect_act": "📋 Акты дефектации",
    "avr": "⚙️ АВР",
    "other": "📄 Прочее"
}


def get_sections_for_ship(ship_id):
    """Получить уникальные разделы для судна."""
    session = SessionLocal()
    try:
        items = session.query(StatementItem.section).filter(
            StatementItem.statement_id.in_(
                session.query(RepairStatement.id).filter_by(ship_id=ship_id)
            )
        ).distinct().all()
        return [s[0] for s in items if s[0]]
    finally:
        session.close()


def get_items_for_section(ship_id, section):
    """Получить пункты в разделе."""
    session = SessionLocal()
    try:
        items = session.query(StatementItem).filter(
            StatementItem.statement_id.in_(
                session.query(RepairStatement.id).filter_by(ship_id=ship_id)
            ),
            StatementItem.section == section
        ).all()
        return items
    finally:
        session.close()


def build_sections_keyboard(ship_id, page=0, items_per_page=10):
    """Построить InlineKeyboardMarkup со списком разделов (с пагинацией)."""
    sections = get_sections_for_ship(ship_id)
    
    if not sections:
        return None
    
    # Пагинация
    start = page * items_per_page
    end = start + items_per_page
    page_sections = sections[start:end]
    
    keyboard = types.InlineKeyboardMarkup()
    for section in page_sections:
        # Callback: sections_<ship_id>_<section_hash>
        # Используем хеш раздела, чтобы не превышать 64 байта
        section_hash = str(hash(section) & 0x7fffffff)  # Положительное число
        callback = f"section_{ship_id}_{section_hash}"
        keyboard.add(types.InlineKeyboardButton(section, callback_data=callback))
    
    # Кнопки пагинации
    if page > 0:
        keyboard.add(types.InlineKeyboardButton("◀ Назад", callback_data=f"sections_{ship_id}_{page-1}"))
    if end < len(sections):
        keyboard.add(types.InlineKeyboardButton("Далее ▶", callback_data=f"sections_{ship_id}_{page+1}"))
    
    return keyboard


def build_items_keyboard(ship_id, section, page=0, items_per_page=10):
    """Построить InlineKeyboardMarkup со списком пунктов в разделе."""
    items = get_items_for_section(ship_id, section)
    
    if not items:
        return None
    
    # Пагинация
    start = page * items_per_page
    end = start + items_per_page
    page_items = items[start:end]
    
    keyboard = types.InlineKeyboardMarkup()
    for item in page_items:
        # Callback: item_<item_id>
        callback = f"item_{item.id}"
        label = f"{item.item_number}: {item.description[:30]}..."
        keyboard.add(types.InlineKeyboardButton(label, callback_data=callback))
    
    # Кнопки пагинации
    if page > 0:
        section_hash = str(hash(section) & 0x7fffffff)
        keyboard.add(types.InlineKeyboardButton("◀ Назад", callback_data=f"items_{ship_id}_{section_hash}_{page-1}"))
    if end < len(items):
        section_hash = str(hash(section) & 0x7fffffff)
        keyboard.add(types.InlineKeyboardButton("Далее ▶", callback_data=f"items_{ship_id}_{section_hash}_{page+1}"))
    
    return keyboard


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
