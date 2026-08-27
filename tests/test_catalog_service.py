# -*- coding: utf-8 -*-

import json

from services.catalog_service import CatalogRepository, DEFAULT_COMPANIES


def test_missing_or_corrupt_catalogs_return_safe_defaults(tmp_path):
    repository = CatalogRepository(tmp_path)
    assert repository.load_ships() == {}
    assert repository.load_employees() == []
    assert repository.load_companies() == DEFAULT_COMPANIES

    (tmp_path / "ships.json").write_text("{broken", encoding="utf-8")
    assert repository.load_ships() == {}


def test_catalog_types_are_validated(tmp_path):
    (tmp_path / "ships.json").write_text("[]", encoding="utf-8")
    (tmp_path / "employees.json").write_text(
        json.dumps({"employees": {"name": "Иванов"}}), encoding="utf-8"
    )

    repository = CatalogRepository(tmp_path)
    assert repository.load_ships() == {}
    assert repository.load_employees() == []


def test_employee_role_lookup_normalizes_case_and_spaces(tmp_path):
    (tmp_path / "employees.json").write_text(
        json.dumps(
            {"employees": [{"name": "Иванов Иван Иванович", "role": "engineer"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    repository = CatalogRepository(tmp_path)
    assert repository.find_employee_role("  ИВАНОВ   Иван Иванович ") == "engineer"
    assert repository.find_employee_role("Петров Пётр") is None


def test_company_values_override_defaults(tmp_path):
    (tmp_path / "companies.json").write_text(
        json.dumps({"customer": "Заказчик"}, ensure_ascii=False), encoding="utf-8"
    )

    companies = CatalogRepository(tmp_path).load_companies()
    assert companies["customer"] == "Заказчик"
    assert companies["executor"] == DEFAULT_COMPANIES["executor"]


def test_legacy_extra_imports_point_to_catalog_service():
    from services import catalog_service, extra

    assert extra.load_ships is catalog_service.load_ships
    assert extra.load_companies is catalog_service.load_companies
    assert extra.find_employee_role is catalog_service.find_employee_role


def test_ship_addition_is_atomic_and_rejects_duplicate(tmp_path):
    repository = CatalogRepository(tmp_path)
    assert repository.add_ship("  Новое   судно ")[0] is True
    assert repository.load_ships() == {"новое судно": "Новое судно"}
    assert repository.add_ship("Новое судно")[0] is False
    assert not (tmp_path / "ships.json.tmp").exists()


def test_company_update_validates_field(tmp_path):
    repository = CatalogRepository(tmp_path)
    assert repository.update_company("customer", " Новый заказчик ")[0] is True
    assert repository.load_companies()["customer"] == "Новый заказчик"
    assert repository.update_company("token", "secret")[0] is False
