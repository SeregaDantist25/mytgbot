# -*- coding: utf-8 -*-

import bot_context
from handlers.message_handlers import _build_welcome_text


class FakeRouter:
    def __init__(self, configured):
        self.configured = configured

    def is_configured(self):
        return self.configured


def test_welcome_does_not_claim_ai_when_keys_are_missing(monkeypatch):
    monkeypatch.setattr(bot_context, "alisa_router", FakeRouter(False))
    text = _build_welcome_text()
    assert "внешний AI пока не подключён" in text
    assert "YandexGPT подключён" not in text
    assert "утверждённом XLSX-шаблоне" in text


def test_welcome_reports_configured_ai(monkeypatch):
    monkeypatch.setattr(bot_context, "alisa_router", FakeRouter(True))
    text = _build_welcome_text()
    assert "YandexGPT подключён" in text


def test_handlers_package_does_not_eagerly_import_modules():
    import subprocess
    import sys

    code = (
        "import sys, handlers; "
        "assert 'handlers.message_handlers' not in sys.modules; "
        "assert 'handlers.document_handlers' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
