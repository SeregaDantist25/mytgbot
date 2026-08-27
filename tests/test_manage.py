# -*- coding: utf-8 -*-

from manage import check_environment, load_env


def test_load_env_does_not_override_existing_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=123456789:abcdefghijklmnopqrstuvwxyz\n"
        "ADMIN_IDS=123456789\n",
        encoding="utf-8",
    )
    env = {"ADMIN_IDS": "777"}
    load_env(env_file, env)
    assert env["ADMIN_IDS"] == "777"
    assert env["TELEGRAM_BOT_TOKEN"].startswith("123456789:")


def test_check_environment_accepts_valid_local_configuration(tmp_path):
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "defect_act_template.xlsx").write_bytes(b"template")
    env = {
        "TELEGRAM_BOT_TOKEN": "123456789:abcdefghijklmnopqrstuvwxyz",
        "ADMIN_IDS": "123456789,987654321",
    }
    errors, warnings = check_environment(env, tmp_path)
    assert errors == []
    assert warnings == []


def test_check_environment_never_returns_token_in_messages(tmp_path):
    secret = "123456789:abcdefghijklmnopqrstuvwxyz"
    errors, warnings = check_environment(
        {"TELEGRAM_BOT_TOKEN": secret, "ADMIN_IDS": "not-a-number"},
        tmp_path,
    )
    assert errors
    assert secret not in " ".join(errors + warnings)
