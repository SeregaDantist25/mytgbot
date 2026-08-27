# -*- coding: utf-8 -*-

import os
from pathlib import Path
import subprocess
import sys


def test_application_imports_and_registers_handlers(tmp_path):
    env = os.environ.copy()
    env.update({
        "TELEGRAM_BOT_TOKEN": "123456789:TEST_TOKEN_FOR_SMOKE",
        "ADMIN_IDS": "123456789",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'smoke.db'}",
        "DATA_DIR": str(tmp_path / "data"),
        "LOG_FILE": "",
    })
    code = (
        "import bot; "
        "assert len(bot.bot.message_handlers) >= 20; "
        "assert len(bot.bot.callback_query_handlers) >= 15; "
        "assert bot.bot_context.DOCUMENT_MANAGER_AVAILABLE"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
