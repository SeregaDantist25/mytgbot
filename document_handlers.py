# -*- coding: utf-8 -*-
"""Совместимый импорт: реализация перенесена в handlers.document_handlers."""

from handlers.document_handlers import (
    _can_manage_documents,
    handle_document_approve,
    handle_document_archive,
    handle_document_delete,
    handle_document_replace,
    handle_document_upload,
    register_document_handlers,
)

__all__ = [
    "handle_document_upload",
    "handle_document_approve",
    "handle_document_archive",
    "handle_document_delete",
    "handle_document_replace",
    "register_document_handlers",
]
