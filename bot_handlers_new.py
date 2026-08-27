# -*- coding: utf-8 -*-
"""Совместимый импорт: реализация перенесена в handlers.repair_handlers."""

from handlers.repair_handlers import (
    DocumentStates,
    _approved_role,
    _can_edit_repair_list,
    _can_upload_repair_list,
    _can_view_repair_list,
    _show_ships_menu,
    register_navigation_handlers,
    register_upload_handlers,
)

__all__ = [
    "DocumentStates",
    "register_upload_handlers",
    "register_navigation_handlers",
]
