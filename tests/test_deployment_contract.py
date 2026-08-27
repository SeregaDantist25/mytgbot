# -*- coding: utf-8 -*-

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_container_starts_through_validated_manage_command():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert 'CMD ["python", "manage.py", "run"]' in dockerfile
    assert "python -m compileall" in dockerfile


def test_worker_procfile_matches_container_entrypoint():
    procfile = (ROOT / "Procfile").read_text(encoding="utf-8").strip()
    assert procfile == "worker: python manage.py run"


def test_deployment_files_do_not_contain_secret_values():
    contents = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in ("Dockerfile", "Procfile", "docs/DEPLOYMENT.md")
    )
    assert "replace_with_test_bot_token" not in contents
    assert "api.telegram.org/bot" not in contents
