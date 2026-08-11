# -*- coding: utf-8 -*-
"""
Сервис работы с документами.

Содержит функции создания, получения, утверждения, архивирования,
удаления и замены документов. Работает через ORM-модель Document
(models.py) и FileStorage (file_storage.py).

Обратная совместимость с bot.py сохранена: сигнатуры функций совпадают
с теми, что были в монолитном bot.py.
"""

from typing import List, Optional, Tuple

from models import SessionLocal, Document
from file_storage import storage


def create_document(
    item_id: int,
    category: str,
    file_data: bytes,
    user_id: int,
    file_type: Optional[str] = None,
) -> Document:
    """Создаёт документ и сохраняет файл в хранилище.

    Args:
        item_id: ID пункта ремонтной ведомости.
        category: Категория документа.
        file_data: Содержимое файла (bytes).
        user_id: Telegram ID загрузившего пользователя.
        file_type: Тип файла (расширение).

    Returns:
        Созданный объект Document.
    """
    file_ref = storage.save_file(file_data, f"documents/{item_id}/{category}")
    session = SessionLocal()
    try:
        doc = Document(
            item_id=item_id,
            category=category,
            file_ref=file_ref,
            file_type=file_type,
            uploaded_by=user_id,
            status="draft",
            version=1,
        )
        session.add(doc)
        session.commit()
        return doc
    finally:
        session.close()


def get_document(document_id: int) -> Optional[Document]:
    """Возвращает документ по ID.

    Args:
        document_id: ID документа.

    Returns:
        Объект Document или None.
    """
    session = SessionLocal()
    try:
        return session.query(Document).filter_by(id=document_id).first()
    finally:
        session.close()


def get_documents(
    item_id: int,
    category: str,
    status: Optional[str] = None,
) -> List[Document]:
    """Возвращает документы пункта по категории и статусу.

    Args:
        item_id: ID пункта ремонтной ведомости.
        category: Категория документа.
        status: Статус документа (опционально).

    Returns:
        Список объектов Document.
    """
    session = SessionLocal()
    try:
        query = session.query(Document).filter(
            Document.item_id == item_id,
            Document.category == category,
        )
        if status:
            query = query.filter(Document.status == status)
        return query.order_by(Document.uploaded_at.desc()).all()
    finally:
        session.close()


def approve_document(document_id: int, user_id: int) -> Tuple[bool, str]:
    """Утверждает документ: draft → approved.

    Args:
        document_id: ID документа.
        user_id: Telegram ID пользователя.

    Returns:
        Кортеж (success, message).
    """
    session = SessionLocal()
    try:
        doc = session.query(Document).filter_by(id=document_id).first()
        if not doc:
            return False, "❌ Документ не найден"
        if doc.status != "draft":
            return False, f"❌ Документ уже {doc.status}"
        doc.status = "approved"
        session.commit()
        return True, "✅ Документ утверждён"
    except Exception as e:
        session.rollback()
        return False, f"❌ Ошибка: {str(e)}"
    finally:
        session.close()


def archive_document(document_id: int, user_id: int, admin_ids=None) -> Tuple[bool, str]:
    """Архивирует документ: approved → archived.

    Только для администраторов (admin_ids).

    Args:
        document_id: ID документа.
        user_id: Telegram ID пользователя.
        admin_ids: Список ID администраторов.

    Returns:
        Кортеж (success, message).
    """
    admin_ids = admin_ids or []
    if user_id not in admin_ids:
        return False, "🚫 Только админы могут архивировать документы"

    session = SessionLocal()
    try:
        doc = session.query(Document).filter_by(id=document_id).first()
        if not doc:
            return False, "❌ Документ не найден"
        if doc.status != "approved":
            return False, f"❌ Можно архивировать только approved документы (текущий: {doc.status})"
        doc.status = "archived"
        session.commit()
        return True, "✅ Документ архивирован"
    except Exception as e:
        session.rollback()
        return False, f"❌ Ошибка: {str(e)}"
    finally:
        session.close()


def delete_document(document_id: int, user_id: int, admin_ids=None) -> Tuple[bool, str]:
    """Удаляет документ.

    - draft: может удалить любой пользователь.
    - approved: только администраторы (admin_ids).

    Args:
        document_id: ID документа.
        user_id: Telegram ID пользователя.
        admin_ids: Список ID администраторов.

    Returns:
        Кортеж (success, message).
    """
    admin_ids = admin_ids or []
    session = SessionLocal()
    try:
        doc = session.query(Document).filter_by(id=document_id).first()
        if not doc:
            return False, "❌ Документ не найден"
        if doc.status == "approved" and user_id not in admin_ids:
            return False, "🚫 Только админы могут удалять approved документы"
        if doc.file_ref:
            storage.delete_file(doc.file_ref)
        session.delete(doc)
        session.commit()
        return True, "✅ Документ удалён"
    except Exception as e:
        session.rollback()
        return False, f"❌ Ошибка: {str(e)}"
    finally:
        session.close()


def replace_document(
    document_id: int,
    file_data: bytes,
    user_id: int,
    file_type: Optional[str] = None,
) -> Tuple[bool, str]:
    """Заменяет файл draft-документа.

    Args:
        document_id: ID документа.
        file_data: Новое содержимое файла (bytes).
        user_id: Telegram ID пользователя.
        file_type: Тип файла (расширение).

    Returns:
        Кортеж (success, message).
    """
    session = SessionLocal()
    try:
        doc = session.query(Document).filter_by(id=document_id).first()
        if not doc:
            return False, "❌ Документ не найден"
        if doc.status != "draft":
            return False, "❌ Можно заменять только черновики"
        if doc.file_ref:
            storage.delete_file(doc.file_ref)
        new_ref = storage.save_file(file_data, f"documents/{doc.item_id}/{doc.category}")
        doc.file_ref = new_ref
        doc.file_type = file_type
        session.commit()
        return True, "✅ Документ заменён"
    except Exception as e:
        session.rollback()
        return False, f"❌ Ошибка: {str(e)}"
    finally:
        session.close()


def count_drafts_for_item(item_id: int, category: str = "defect_act_draft") -> int:
    """Возвращает количество черновиков для пункта и категории.

    Args:
        item_id: ID пункта ремонтной ведомости.
        category: Категория документа.

    Returns:
        Количество черновиков.
    """
    session = SessionLocal()
    try:
        return (
            session.query(Document)
            .filter(
                Document.item_id == item_id,
                Document.category == category,
                Document.status == "draft",
            )
            .count()
        )
    finally:
        session.close()


def get_oldest_draft(item_id: int, category: str = "defect_act_draft") -> Optional[Document]:
    """Возвращает старейший черновик для пункта и категории.

    Args:
        item_id: ID пункта ремонтной ведомости.
        category: Категория документа.

    Returns:
        Объект Document или None.
    """
    session = SessionLocal()
    try:
        return (
            session.query(Document)
            .filter(
                Document.item_id == item_id,
                Document.category == category,
                Document.status == "draft",
            )
            .order_by(Document.uploaded_at.asc())
            .first()
        )
    finally:
        session.close()
