# -*- coding: utf-8 -*-

from services.pump_knowledge_service import PumpDatabase


DATA = {
    "centrifugal": {
        "name": "Центробежный насос",
        "items": ["корпус"],
        "clearances": {"radial": {"min": 0.1, "max": 0.3, "unit": "мм"}},
        "defects": ["износ колеса"],
        "repair_methods": {"колес": "Замена колеса"},
    }
}


def test_clearance_statuses():
    database = PumpDatabase(DATA)
    assert database.check_clearance("centrifugal", "radial", 0.05)["status"] == "warning"
    assert database.check_clearance("centrifugal", "radial", 0.2)["status"] == "ok"
    assert database.check_clearance("centrifugal", "radial", 0.4)["status"] == "critical"
    assert database.check_clearance("centrifugal", "axial", 0.2)["status"] == "unknown"


def test_knowledge_lookup():
    database = PumpDatabase(DATA)
    assert database.get_pump_types() == ["centrifugal"]
    assert database.get_pump_name("centrifugal") == "Центробежный насос"
    assert database.get_checklist("centrifugal") == ["корпус"]
    assert database.get_common_defects("centrifugal") == ["износ колеса"]
    assert database.get_repair_method("centrifugal", "износ рабочего колеса") == "Замена колеса"


def test_legacy_extra_imports_point_to_pump_service():
    from services import extra, pump_knowledge_service

    assert extra.PumpDatabase is pump_knowledge_service.PumpDatabase
    assert extra.pump_db is pump_knowledge_service.pump_db
