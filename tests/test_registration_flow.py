# -*- coding: utf-8 -*-

from types import SimpleNamespace

import bot_context
from handlers.message_handlers import register_message_handlers
from services.extra import get_chat_state, set_chat_state
from services.user_service import (
    add_pending_user,
    create_user,
    get_pending_user,
    get_user,
)


class FakeBot:
    """Минимальный бот для вызова зарегистрированных message handlers."""

    def __init__(self):
        self.handlers = {}
        self.replies = []
        self.sent_messages = []

    def message_handler(self, *args, **kwargs):
        def decorator(func):
            self.handlers[func.__name__] = func
            return func
        return decorator

    def reply_to(self, message, text, **kwargs):
        self.replies.append((message.chat.id, text))

    def send_message(self, chat_id, text, **kwargs):
        self.sent_messages.append((chat_id, text))

    def send_document(self, *args, **kwargs):
        raise AssertionError("Отправка документа не ожидается в тесте регистрации")


def _message(user_id, text):
    user = SimpleNamespace(id=user_id, first_name="Тест")
    return SimpleNamespace(
        text=text,
        chat=SimpleNamespace(id=user_id),
        from_user=user,
    )


def _registered_bot(monkeypatch):
    monkeypatch.setattr(bot_context, "ENGINEER_CODE", "engineer-secret")
    monkeypatch.setattr(bot_context, "DOCUMENT_MANAGER_AVAILABLE", False)
    bot = FakeBot()
    register_message_handlers(bot)
    return bot


def test_login_name_role_creates_pending_request(monkeypatch):
    user_id = 9201
    set_chat_state(user_id, "reg_step", None)
    set_chat_state(user_id, "reg_name", None)
    bot = _registered_bot(monkeypatch)

    bot.handlers["cmd_login"](_message(user_id, "/login"))
    assert get_chat_state(user_id, "reg_step") == "name"

    bot.handlers["handle_message"](_message(user_id, "Тестовый Пользователь"))
    assert get_chat_state(user_id, "reg_step") == "role"
    assert get_chat_state(user_id, "reg_name") == "Тестовый Пользователь"

    bot.handlers["handle_message"](_message(user_id, "1"))
    assert get_chat_state(user_id, "reg_step") is None
    assert get_pending_user(user_id)["role_requested"] == "builder"
    assert "отправлена на одобрение" in bot.replies[-1][1]

    bot.handlers["cmd_login"](_message(user_id, "/login"))
    assert "уже отправлена" in bot.replies[-1][1]


def test_engineer_alias_can_approve_pending_registration(monkeypatch):
    engineer_id = 9202
    applicant_id = 9203
    create_user(engineer_id, "Инженер", "engineer_technologist", approved=1)
    add_pending_user(applicant_id, "Строитель", "builder")
    bot = _registered_bot(monkeypatch)

    bot.handlers["cmd_approve_yes"](
        _message(engineer_id, f"/approve_yes {applicant_id}")
    )

    approved = get_user(applicant_id)
    assert approved is not None
    assert approved.approved == 1
    assert approved.role == "builder"
    assert get_pending_user(applicant_id) is None
    assert any(chat_id == applicant_id for chat_id, _ in bot.sent_messages)
