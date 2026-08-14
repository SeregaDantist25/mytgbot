# -*- coding: utf-8 -*-
"""
Сервис работы с документами.

CRUD операции для документов + генерация через ИИ.
"""

import logging
from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.schemas import Document, StatementItem, User, AuditLog
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


class DocumentService:
    """Сервис для управления документами."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.ai_service = AIService()
    
    async def create_document(
        self,
        item_id: int,
        category: str,
        file_data: bytes,
        uploaded_by: int,
        file_type: str = "bin",
        ai_generated: bool = False,
    ) -> Tuple[bool, Optional[Document], str]:
        """
        Создаёт новый документ.
        
        Args:
            item_id: ID пункта ремонтной ведомости
            category: Категория (defect_act, work_act, contract, technical_act)
            file_data: Содержимое файла
            uploaded_by: Telegram ID пользователя
            file_type: Расширение файла
            ai_generated: Сгенерирован ли документ ИИ
        
        Returns:
            (success, document, message)
        """
        try:
            # Проверяем существование пункта
            result = await self.session.execute(
                select(StatementItem).where(StatementItem.id == item_id)
            )
            item = result.scalar_one_or_none()
            
            if not item:
                return False, None, f"Пункт ведомости #{item_id} не найден"
            
            # Создаём документ
            doc = Document(
                item_id=item_id,
                category=category,
                file_ref=f"documents/{item_id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_type}",
                file_type=file_type,
                file_data=file_data,
                version=1,
                status="draft",
                uploaded_by=uploaded_by,
                ai_generated=ai_generated,
            )
            
            self.session.add(doc)
            await self.session.flush()  # Получаем ID
            
            # Логгируем действие
            await self._log_action(
                user_id=uploaded_by,
                action="create",
                entity_type="document",
                entity_id=doc.id,
                details=f"Создан документ {category} для пункта #{item_id}"
            )
            
            logger.info(f"Документ #{doc.id} создан (категория: {category}, AI: {ai_generated})")
            return True, doc, f"✅ Документ создан"
            
        except Exception as e:
            logger.error(f"Ошибка создания документа: {e}")
            return False, None, f"❌ Ошибка: {str(e)}"
    
    async def get_document(self, doc_id: int) -> Optional[Document]:
        """Возвращает документ по ID."""
        result = await self.session.execute(
            select(Document)
            .options(selectinload(Document.uploader))
            .where(Document.id == doc_id)
        )
        return result.scalar_one_or_none()
    
    async def get_documents_by_item(
        self,
        item_id: int,
        category: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Document]:
        """Возвращает документы пункта по фильтру."""
        query = select(Document).where(Document.item_id == item_id)
        
        if category:
            query = query.where(Document.category == category)
        if status:
            query = query.where(Document.status == status)
        
        query = query.order_by(Document.uploaded_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def approve_document(
        self,
        doc_id: int,
        approved_by: int,
    ) -> Tuple[bool, str]:
        """Утверждает документ."""
        try:
            doc = await self.get_document(doc_id)
            
            if not doc:
                return False, "❌ Документ не найден"
            
            if doc.status != "draft":
                return False, f"❌ Документ уже в статусе {doc.status}"
            
            doc.status = "approved"
            doc.approved_by = approved_by
            doc.approved_at = datetime.now()
            
            await self._log_action(
                user_id=approved_by,
                action="approve",
                entity_type="document",
                entity_id=doc_id,
                details=f"Докукт утверждён"
            )
            
            logger.info(f"Документ #{doc_id} утверждён пользователем #{approved_by}")
            return True, "✅ Документ утверждён"
            
        except Exception as e:
            logger.error(f"Ошибка утверждения документа: {e}")
            return False, f"❌ Ошибка: {str(e)}"
    
    async def reject_document(
        self,
        doc_id: int,
        rejected_by: int,
        reason: str,
    ) -> Tuple[bool, str]:
        """Отклоняет документ с указанием причины."""
        try:
            doc = await self.get_document(doc_id)
            
            if not doc:
                return False, "❌ Документ не найден"
            
            doc.status = "rejected"
            doc.rejection_reason = reason
            
            await self._log_action(
                user_id=rejected_by,
                action="reject",
                entity_type="document",
                entity_id=doc_id,
                details=f"Отклонён: {reason}"
            )
            
            logger.info(f"Документ #{doc_id} отклонён: {reason}")
            return True, "📝 Документ отклонён"
            
        except Exception as e:
            logger.error(f"Ошибка отклонения документа: {e}")
            return False, f"❌ Ошибка: {str(e)}"
    
    async def archive_document(
        self,
        doc_id: int,
        archived_by: int,
    ) -> Tuple[bool, str]:
        """Архивирует документ (только утверждённые)."""
        try:
            doc = await self.get_document(doc_id)
            
            if not doc:
                return False, "❌ Документ не найден"
            
            if doc.status != "approved":
                return False, f"❌ Можно архивировать только approved (текущий: {doc.status})"
            
            doc.status = "archived"
            
            await self._log_action(
                user_id=archived_by,
                action="archive",
                entity_type="document",
                entity_id=doc_id,
            )
            
            logger.info(f"Документ #{doc_id} архивирован")
            return True, "📦 Документ архивирован"
            
        except Exception as e:
            logger.error(f"Ошибка архивации документа: {e}")
            return False, f"❌ Ошибка: {str(e)}"
    
    async def delete_document(
        self,
        doc_id: int,
        deleted_by: int,
    ) -> Tuple[bool, str]:
        """Удаляет документ (физически)."""
        try:
            doc = await self.get_document(doc_id)
            
            if not doc:
                return False, "❌ Документ не найден"
            
            await self.session.delete(doc)
            
            await self._log_action(
                user_id=deleted_by,
                action="delete",
                entity_type="document",
                entity_id=doc_id,
            )
            
            logger.info(f"Документ #{doc_id} удалён")
            return True, "🗑️ Документ удалён"
            
        except Exception as e:
            logger.error(f"Ошибка удаления документа: {e}")
            return False, f"❌ Ошибка: {str(e)}"
    
    async def generate_ai_document(
        self,
        item_id: int,
        category: str,
        user_input: str,
        user_id: int,
    ) -> Tuple[bool, Optional[bytes], str]:
        """
        Генерирует документ через ИИ.
        
        Args:
            item_id: ID пункта ведомости
            category: Тип документа
            user_input: Описание от пользователя
            user_id: ID пользователя
        
        Returns:
            (success, file_bytes, message)
        """
        try:
            # Получаем данные пункта
            result = await self.session.execute(
                select(StatementItem)
                .options(selectinload(StatementItem.statement))
                .where(StatementItem.id == item_id)
            )
            item = result.scalar_one_or_none()
            
            if not item:
                return False, None, "❌ Пункт ведомости не найден"
            
            # Генерируем контент через ИИ
            ai_result = await self.ai_service.generate_act_content(
                act_type=category,
                user_input=user_input,
                item_data={
                    "item_number": item.item_number,
                    "description": item.description,
                    "quantity": item.quantity,
                }
            )
            
            if not ai_result["success"]:
                return False, None, f"❌ Ошибка ИИ: {ai_result.get('error', 'Неизвестная ошибка')}"
            
            # TODO: Здесь будет генерация DOCX/PDF из шаблона
            # Пока возвращаем заглушку
            file_bytes = b"AI-generated document placeholder"
            
            logger.info(f"AI документ сгенерирован для пункта #{item_id}")
            return True, file_bytes, "✅ Документ сгенерирован через ИИ"
            
        except Exception as e:
            logger.error(f"Ошибка генерации AI документа: {e}")
            return False, None, f"❌ Ошибка: {str(e)}"
    
    async def _log_action(
        self,
        user_id: int,
        action: str,
        entity_type: str,
        entity_id: int,
        details: Optional[str] = None,
    ) -> None:
        """Логирует действие в audit_log."""
        try:
            log_entry = AuditLog(
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details,
            )
            self.session.add(log_entry)
        except Exception as e:
            logger.error(f"Ошибка логгирования аудита: {e}")
