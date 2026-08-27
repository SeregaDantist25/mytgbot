# -*- coding: utf-8 -*-
"""Совместимый импорт: реализация перенесена в handlers.category_handlers."""

from handlers.category_handlers import (
    _build_document_actions_keyboard,
    _parse_documents_callback,
    register_category_handlers,
)

__all__ = ["register_category_handlers"]
