#!/usr/bin/env python3
"""Локальное управление ботом: диагностика, тесты и запуск."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
TOKEN_PATTERN = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{20,}$")


def load_env(path: Path, environ=None) -> dict:
    """Загрузить простой KEY=VALUE файл, не перезаписывая заданное окружение."""
    target = os.environ if environ is None else environ
    if not path.exists():
        return target
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value[:1] == value[-1:] and value.startswith(("'", '"')):
            value = value[1:-1]
        target.setdefault(key, value)
    return target


def check_environment(environ=None, project_root: Path = PROJECT_ROOT):
    """Вернуть списки ошибок и предупреждений без раскрытия секретов."""
    env = os.environ if environ is None else environ
    errors = []
    warnings = []

    token = env.get("TELEGRAM_BOT_TOKEN", "")
    if not token or token == "replace_with_test_bot_token":
        errors.append("TELEGRAM_BOT_TOKEN не заполнен")
    elif not TOKEN_PATTERN.fullmatch(token):
        errors.append("TELEGRAM_BOT_TOKEN имеет неверный формат")

    admin_ids = env.get("ADMIN_IDS", "")
    if not admin_ids:
        warnings.append("ADMIN_IDS пуст: запустите бота, получите ID командой /myid и заполните .env")
    else:
        try:
            [int(value.strip()) for value in admin_ids.split(",") if value.strip()]
        except ValueError:
            errors.append("ADMIN_IDS должен содержать числа через запятую")

    if not (project_root / "templates" / "defect_act_template.xlsx").exists():
        errors.append("не найден утверждённый шаблон templates/defect_act_template.xlsx")
    if sys.version_info < (3, 10):
        errors.append("требуется Python 3.10 или новее")

    return errors, warnings


def print_diagnostics(errors, warnings):
    for warning in warnings:
        print(f"[ПРЕДУПРЕЖДЕНИЕ] {warning}")
    for error in errors:
        print(f"[ОШИБКА] {error}")
    if not errors:
        print("[OK] Конфигурация готова. Секреты в вывод не включены.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "test", "run"))
    args = parser.parse_args(argv)

    env_file = PROJECT_ROOT / ".env"
    load_env(env_file)

    if args.command == "test":
        return subprocess.call(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=PROJECT_ROOT,
            env=os.environ.copy(),
        )

    errors, warnings = check_environment()
    print_diagnostics(errors, warnings)
    if errors:
        if not env_file.exists():
            print("Создайте .env копированием .env.example и заполните токен.")
        return 1
    if args.command == "check":
        return 0

    return subprocess.call(
        [sys.executable, "bot.py"],
        cwd=PROJECT_ROOT,
        env=os.environ.copy(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
