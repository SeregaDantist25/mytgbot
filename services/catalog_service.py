# -*- coding: utf-8 -*-
"""Чтение локальных справочников приложения из JSON."""

from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_COMPANIES = {
    "executor": "ООО «Новое время»",
    "customer": "АО «Бункерная компания»",
    "location": "Рейд 4ый район, г. Находка",
}


class CatalogRepository:
    """Доступ к справочникам в одном каталоге данных."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    def _read_json(self, filename: str, fallback):
        path = self.data_dir / filename
        if not path.exists():
            return fallback
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return fallback

    def load_checklists(self) -> dict:
        data = self._read_json("checklists.json", {})
        return data if isinstance(data, dict) else {}

    def load_ships(self) -> dict:
        data = self._read_json("ships.json", {})
        return data if isinstance(data, dict) else {}

    def load_employees(self) -> list:
        data = self._read_json("employees.json", {})
        if not isinstance(data, dict):
            return []
        employees = data.get("employees", [])
        return employees if isinstance(employees, list) else []

    def find_employee_role(self, name: str) -> str | None:
        if not name:
            return None
        normalized = " ".join(name.strip().lower().split())
        for employee in self.load_employees():
            if not isinstance(employee, dict):
                continue
            employee_name = " ".join(
                str(employee.get("name", "")).strip().lower().split()
            )
            if employee_name == normalized:
                return employee.get("role")
        return None

    def load_companies(self) -> dict:
        result = dict(DEFAULT_COMPANIES)
        data = self._read_json("companies.json", {})
        if isinstance(data, dict):
            result.update(data)
        return result


DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
repository = CatalogRepository(DATA_DIR)
CHECKLISTS_FILE = DATA_DIR / "checklists.json"
SHIPS_FILE = DATA_DIR / "ships.json"
COMPANIES_FILE = DATA_DIR / "companies.json"
EMPLOYEES_FILE = DATA_DIR / "employees.json"


def load_checklists() -> dict:
    return repository.load_checklists()


def load_ships() -> dict:
    return repository.load_ships()


def load_employees() -> list:
    return repository.load_employees()


def find_employee_role(name: str) -> str | None:
    return repository.find_employee_role(name)


def load_companies() -> dict:
    return repository.load_companies()
