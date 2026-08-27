# -*- coding: utf-8 -*-
"""Локальная база знаний по насосам и их зазорам."""

from services.catalog_service import load_checklists


class PumpDatabase:
    def __init__(self, data: dict | None = None) -> None:
        self.data = load_checklists() if data is None else data

    def get_pump_types(self) -> list:
        return list(self.data.keys())

    def get_pump_name(self, pump_type: str) -> str:
        return self.data.get(pump_type, {}).get("name", pump_type)

    def get_checklist(self, pump_type: str) -> list:
        return self.data.get(pump_type, {}).get("items", [])

    def get_clearances(self, pump_type: str, clearance_type: str):
        return self.data.get(pump_type, {}).get("clearances", {}).get(clearance_type)

    def check_clearance(
        self, pump_type: str, clearance_type: str, measured_value: float
    ) -> dict:
        clearance = self.get_clearances(pump_type, clearance_type)
        if not clearance:
            return {
                "status": "unknown",
                "message": f"Данные по зазору '{clearance_type}' для '{pump_type}' отсутствуют",
                "action": "Проверьте правильность ввода",
            }

        minimum = clearance.get("min", 0)
        maximum = clearance.get("max", 0)
        unit = clearance.get("unit", "мм")
        if "мм/мм" in unit:
            return {
                "status": "info",
                "message": f"📌 Зазор зависит от диаметра: {minimum}-{maximum} {unit}",
                "action": "Уточните диаметр для точного расчёта",
            }
        if measured_value < minimum:
            return {
                "status": "warning",
                "message": f"⚠️ Зазор МЕНЬШЕ нормы: {measured_value} мм (норма: {minimum}-{maximum} мм)",
                "action": "Проверьте точность измерения",
            }
        if measured_value <= maximum:
            return {
                "status": "ok",
                "message": f"✅ Зазор В НОРМЕ: {measured_value} мм (норма: {minimum}-{maximum} мм)",
                "action": "Деталь работоспособна",
            }
        return {
            "status": "critical",
            "message": f"🔴 Зазор ПРЕВЫШЕН: {measured_value} мм (норма: {minimum}-{maximum} мм)",
            "action": "Требуется ремонт",
        }

    def get_common_defects(self, pump_type: str) -> list:
        return self.data.get(pump_type, {}).get("defects", [])

    def get_repair_method(self, pump_type: str, defect_text: str):
        methods = self.data.get(pump_type, {}).get("repair_methods", {})
        defect_lower = defect_text.lower()
        return next(
            (method for key, method in methods.items() if key in defect_lower),
            None,
        )


pump_db = PumpDatabase()
