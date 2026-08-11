# -*- coding: utf-8 -*-
"""
Тесты для services/extra.py — чистые функции парсинга и детекции.
"""

from services.extra import (
    detect_equipment_type,
    detect_ship,
    detect_pump_type,
    extract_equipment,
    extract_clearances_from_text,
    extract_defects,
    parse_works_for_avr,
    analyze_query_local,
    generate_base_work_volume,
    build_defect_table_pump,
    build_defect_table_engine,
)


class TestDetectEquipmentType:
    """Тесты определения типа оборудования."""

    def test_engine(self):
        assert detect_equipment_type("главный двигатель MAN") == "engine"
        assert detect_equipment_type("дизель-генератор") == "engine"

    def test_pump(self):
        assert detect_equipment_type("пожарный насос") == "pump"

    def test_compressor(self):
        assert detect_equipment_type("воздушный компрессор") == "compressor"

    def test_unknown(self):
        assert detect_equipment_type("кран-балка") is None


class TestDetectShip:
    """Тесты определения судна."""

    def test_detect_known_ship(self):
        # Славянская есть в data/ships.json
        assert detect_ship("судно славянская, пожарный насос") == "Славянская"

    def test_detect_unknown(self):
        assert detect_ship("какой-то текст без судна") is None


class TestDetectPumpType:
    """Тесты определения типа насоса."""

    def test_piston(self):
        assert detect_pump_type("поршневой насос") == "piston"

    def test_gear(self):
        assert detect_pump_type("шестерёнчатый насос") == "gear"

    def test_centrifugal(self):
        assert detect_pump_type("центробежный насос") == "centrifugal"

    def test_unknown(self):
        assert detect_pump_type("двигатель") is None


class TestExtractEquipment:
    """Тесты извлечения оборудования."""

    def test_pump(self):
        assert "насос" in extract_equipment("пожарный насос сломан")

    def test_engine(self):
        assert "двигатель" in extract_equipment("главный двигатель не заводится")

    def test_none(self):
        assert extract_equipment("просто текст") is None


class TestExtractClearances:
    """Тесты извлечения зазоров."""

    def test_radial_clearance(self):
        clearances = extract_clearances_from_text("радиальный зазор 0.15 мм")
        assert len(clearances) >= 1
        assert clearances[0]["type"] == "radial"
        assert clearances[0]["value"] == 0.15

    def test_axial_clearance(self):
        clearances = extract_clearances_from_text("осевой зазор 0.3")
        assert len(clearances) >= 1
        assert clearances[0]["type"] == "axial"

    def test_no_clearance(self):
        assert extract_clearances_from_text("нет зазоров") == []


class TestExtractDefects:
    """Тесты извлечения дефектов."""

    def test_defect_keyword(self):
        defects = extract_defects("повреждена крыльчатка насоса")
        assert len(defects) >= 1
        assert "повреждена" in defects[0]

    def test_defect_section(self):
        defects = extract_defects("Дефекты: износ колеса, трещина корпуса")
        assert len(defects) == 2

    def test_no_defects(self):
        assert extract_defects("всё в порядке") == []


class TestParseWorksForAvr:
    """Тесты парсинга работ для АВР."""

    def test_parse_works(self):
        works = parse_works_for_avr("АВР: замена уголков 44 шт, болтов 194 шт")
        assert len(works) >= 1
        assert works[0]["quantity"] == "44"

    def test_empty(self):
        assert parse_works_for_avr("") == []


class TestAnalyzeQueryLocal:
    """Тесты локального анализа запроса."""

    def test_full_analysis(self):
        result = analyze_query_local("судно славянская, пожарный насос, повреждена крыльчатка")
        assert result["source"] == "local"
        assert result["ship"] == "Славянская"
        assert result["equipment_type"] == "pump"
        assert len(result["defects"]) >= 1


class TestGenerateBaseWorkVolume:
    """Тесты базового объёма работ."""

    def test_generates_lines(self):
        volume = generate_base_work_volume(["износ колеса"])
        assert "Демонтаж" in volume
        assert "изношенных деталей" in volume

    def test_empty_defects(self):
        volume = generate_base_work_volume([])
        assert "Замена/восстановление деталей" in volume


class TestBuildDefectTablePump:
    """Тесты построения таблицы для насосов."""

    def test_centrifugal_rows(self):
        rows = build_defect_table_pump("centrifugal", ["износ крыльчатки"], "Замена.")
        assert len(rows) > 10
        # Дефект должен попасть в строку 2.1 (крыльчатка)
        row_21 = next(r for r in rows if r["num"] == "2.1")
        assert row_21["defect"] == "износ крыльчатки"

    def test_no_defect_default(self):
        rows = build_defect_table_pump("gear", [], "Замена.")
        row_11 = next(r for r in rows if r["num"] == "1.1")
        assert "Дефектов не обнаружено" in row_11["defect"]


class TestBuildDefectTableEngine:
    """Тесты построения таблицы для двигателей."""

    def test_engine_rows(self):
        rows = build_defect_table_engine(["износ поршневых колец"], "Замена.")
        assert len(rows) == 1
        assert rows[0]["section"] == "Цилиндропоршневая группа"
        assert rows[0]["defect"] == "износ поршневых колец"