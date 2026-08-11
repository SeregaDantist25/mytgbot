# -*- coding: utf-8 -*-
"""
Pytest-фикстуры для тестов.

Устанавливает DATABASE_URL на временную SQLite-базу ДО импорта models,
чтобы тесты не трогали боевую data/documents.db.
"""

import os
import tempfile

import pytest

# ВАЖНО: задаём тестовую БД до импорта models (модуль читает переменную
# при импорте). Для этого подменяем в sys.modules уже загруженный
# модуль, если он был импортирован ранее.
_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "test_documents.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["DATA_DIR"] = tempfile.gettempdir()

# Удаляем старую тестовую БД, если есть
if os.path.exists(_TEST_DB_PATH):
    os.remove(_TEST_DB_PATH)

# Засеиваем тестовый ships.json (для detect_ship и load_ships)
_TEST_SHIPS = {
    "аргака": "Аргака",
    "пластун": "Пластун",
    "славянская": "Славянская",
    "первоуральск": "Первоуральск",
    "керчь": "Керчь",
    "краснодар": "Краснодар",
}
_TEST_SHIPS_PATH = os.path.join(tempfile.gettempdir(), "ships.json")
with open(_TEST_SHIPS_PATH, "w", encoding="utf-8") as f:
    import json
    json.dump(_TEST_SHIPS, f, ensure_ascii=False)


@pytest.fixture(autouse=True)
def clean_db():
    """Очищает таблицы БД перед каждым тестом."""
    from models import Base, engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
