# pump_database.py - База данных насосов

class PumpDatabase:
    def __init__(self):
        # ===== ЦЕНТРОБЕЖНЫЕ НАСОСЫ =====
        self.centrifugal = {
            "clearances": {
                "radial": {
                    "description": "Радиальный зазор между валом и корпусом",
                    "standard": {"min": 0.1, "max": 0.3, "unit": "мм"},
                    "max_allowed": 0.5,
                    "repair_after": 0.4
                },
                "axial": {
                    "description": "Осевой зазор крыльчатки",
                    "standard": {"min": 0.2, "max": 0.5, "unit": "мм"},
                    "max_allowed": 1.0,
                    "repair_after": 0.8
                },
                "bearing": {
                    "description": "Зазор в подшипниках",
                    "standard": {"min": 0.02, "max": 0.08, "unit": "мм"},
                    "max_allowed": 0.15,
                    "repair_after": 0.12
                },
                "seal": {
                    "description": "Зазор в сальниковом уплотнении",
                    "standard": {"min": 0.1, "max": 0.2, "unit": "мм"},
                    "max_allowed": 0.4,
                    "repair_after": 0.35
                }
            },
            "common_defects": [
                "износ подшипников",
                "износ крыльчатки",
                "кавитационный износ",
                "повышенный радиальный зазор",
                "повышенный осевой зазор",
                "течь сальникового уплотнения",
                "коррозия корпуса",
                "трещины в корпусе",
                "деформация вала",
                "износ уплотнительных колец"
            ],
            "repair_methods": {
                "подшипники": "Замена подшипников на новые",
                "крыльчатка": "Восстановление наплавкой или замена",
                "вал": "Шлифовка или замена",
                "корпус": "Заварка трещин, механическая обработка",
                "сальник": "Замена набивки или установка новых колец",
                "уплотнительные кольца": "Замена"
            }
        }
        
        # ===== ШЕСТЕРЁНЧАТЫЕ НАСОСЫ ROTAN =====
        self.gear = {
            "clearances": {
                "radial": {
                    "description": "Радиальный зазор между шестернями и корпусом",
                    "standard": {"min": 0.05, "max": 0.15, "unit": "мм"},
                    "max_allowed": 0.3,
                    "repair_after": 0.25
                },
                "axial": {
                    "description": "Осевой зазор в шестернях",
                    "standard": {"min": 0.1, "max": 0.3, "unit": "мм"},
                    "max_allowed": 0.5,
                    "repair_after": 0.4
                },
                "bearing": {
                    "description": "Зазор в подшипниках",
                    "standard": {"min": 0.02, "max": 0.06, "unit": "мм"},
                    "max_allowed": 0.12,
                    "repair_after": 0.1
                },
                "seal": {
                    "description": "Зазор в уплотнении вала",
                    "standard": {"min": 0.1, "max": 0.2, "unit": "мм"},
                    "max_allowed": 0.35,
                    "repair_after": 0.3
                }
            },
            "common_defects": [
                "износ зубьев шестерен",
                "износ подшипников",
                "повышенный осевой зазор",
                "повышенный радиальный зазор",
                "течь уплотнения вала",
                "износ пальцев",
                "износ втулок",
                "заедание перепускного клапана"
            ],
            "repair_methods": {
                "шестерни": "Замена шестерен в сборе",
                "подшипники": "Замена подшипников",
                "вал": "Шлифовка или замена",
                "уплотнение": "Замена уплотнительных колец",
                "пальцы": "Замена пальцев",
                "втулки": "Замена втулок",
                "перепускной клапан": "Разборка, чистка, регулировка"
            }
        }
    
    def get_pump_types(self):
        """Возвращает список доступных типов насосов"""
        return ["centrifugal", "gear"]
    
    def get_clearances(self, pump_type, clearance_type):
        """Возвращает нормативные зазоры для указанного типа"""
        if pump_type in self.centrifugal:
            return self.centrifugal["clearances"].get(clearance_type)
        elif pump_type in self.gear:
            return self.gear["clearances"].get(clearance_type)
        return None
    
    def check_clearance(self, pump_type, clearance_type, measured_value):
        """Проверяет, соответствует ли измеренный зазор норме"""
        clearance_data = self.get_clearances(pump_type, clearance_type)
        if not clearance_data:
            return {"status": "unknown", "message": "Данные отсутствуют"}
        
        standard = clearance_data["standard"]
        max_allowed = clearance_data["max_allowed"]
        
        if measured_value < standard["min"]:
            return {
                "status": "warning",
                "message": f"⚠️ Зазор меньше нормы: {measured_value}{standard['unit']} (норма: {standard['min']}-{standard['max']}{standard['unit']})",
                "value": measured_value,
                "norm": standard,
                "action": "Проверить измерение, возможно ошибка"
            }
        elif measured_value <= standard["max"]:
            return {
                "status": "ok",
                "message": f"✅ Зазор в норме: {measured_value}{standard['unit']} (норма: {standard['min']}-{standard['max']}{standard['unit']})",
                "value": measured_value,
                "norm": standard,
                "action": "Работа допускается"
            }
        elif measured_value <= max_allowed:
            return {
                "status": "critical",
                "message": f"🔴 Зазор превышен до критического: {measured_value}{standard['unit']} (допустим до {max_allowed}{standard['unit']})",
                "value": measured_value,
                "norm": standard,
                "action": f"Требуется ремонт. Рекомендация: {clearance_data.get('repair_after', 'замена детали')}"
            }
        else:
            return {
                "status": "fatal",
                "message": f"❌ Зазор превышен критически: {measured_value}{standard['unit']} (допустим до {max_allowed}{standard['unit']})",
                "value": measured_value,
                "norm": standard,
                "action": "Деталь подлежит обязательной замене!"
            }
    
    def get_common_defects(self, pump_type):
        """Возвращает список частых дефектов для типа насоса"""
        if pump_type in self.centrifugal:
            return self.centrifugal["common_defects"]
        elif pump_type in self.gear:
            return self.gear["common_defects"]
        return []
    
    def get_repair_method(self, pump_type, defect_description):
        """Возвращает рекомендуемый метод ремонта по описанию дефекта"""
        if pump_type in self.centrifugal:
            for key, method in self.centrifugal["repair_methods"].items():
                if key in defect_description.lower():
                    return method
        elif pump_type in self.gear:
            for key, method in self.gear["repair_methods"].items():
                if key in defect_description.lower():
                    return method
        return "Требуется дополнительная дефектация"

# Создаём глобальный экземпляр базы
pump_db = PumpDatabase()