# gost_checker.py
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional

class GOSTChecker:
    def __init__(self, data_file: str = "gost_data.json"):
        self.data_file = Path(data_file)
        self.gost_data = self._load_data()
        self._build_index()
    
    def _load_data(self) -> Dict:
        """Загрузка объединённой базы ГОСТов"""
        if not self.data_file.exists():
            print(f"⚠️ Файл {self.data_file} не найден! Запустите merge_gosts.py")
            return {}
        
        with open(self.data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("gosts", {})
    
    def _build_index(self):
        """Построение индекса для быстрого поиска"""
        self.index = {}
        for gost_id, gost_data in self.gost_data.items():
            gost_type = gost_data.get("section") or gost_data.get("type") or "общие"
            if gost_type not in self.index:
                self.index[gost_type] = []
            self.index[gost_type].append(gost_id)
    
    def get_all_gosts(self) -> Dict:
        """Получение всех ГОСТов"""
        return self.gost_data
    
    def get_gost(self, gost_id: str) -> Optional[Dict]:
        """Получение данных по ГОСТу"""
        return self.gost_data.get(gost_id)
    
    def search(self, query: str) -> Dict:
        """Поиск по ГОСТам"""
        results = {}
        query_lower = query.lower()
        
        for gost_id, data in self.gost_data.items():
            if query_lower in gost_id.lower():
                results[gost_id] = data
                continue
            title = data.get("title", "")
            if query_lower in title.lower():
                results[gost_id] = data
                continue
            section = data.get("section", "")
            if query_lower in section.lower():
                results[gost_id] = data
                continue
            for param_name in data.get("parameters", {}).keys():
                if query_lower in param_name.lower():
                    results[gost_id] = data
                    break
        
        return results
    
    def check_parameter(self, gost_id: str, param_name: str, value: float) -> Dict:
        """Проверка параметра по указанному ГОСТу"""
        gost = self.get_gost(gost_id)
        if not gost:
            return {
                "status": "error",
                "message": f"❌ ГОСТ {gost_id} не найден",
                "action": "Проверьте правильность написания ГОСТа"
            }
        
        params = gost.get("parameters", {})
        
        # Проверяем в основной секции parameters
        if param_name not in params:
            # Ищем вложенные параметры
            for key, value_data in params.items():
                if isinstance(value_data, dict) and "values" in value_data:
                    if param_name in value_data["values"]:
                        return self._evaluate_parameter(value_data["values"][param_name], value, param_name)
                elif isinstance(value_data, dict) and param_name in value_data:
                    return self._evaluate_parameter(value_data[param_name], value, param_name)
            
            return {
                "status": "error",
                "message": f"❌ Параметр '{param_name}' не найден в ГОСТ {gost_id}",
                "action": f"Доступные параметры: {', '.join(list(params.keys())[:10])}"
            }
        
        param_data = params[param_name]
        return self._evaluate_parameter(param_data, value, param_name)
    
    def _evaluate_parameter(self, spec: Any, value: float, param_name: str = "") -> Dict:
        """Оценка значения параметра по спецификации"""
        
        # Если спецификация — это диапазон (dict с min/max)
        if isinstance(spec, dict) and "min" in spec and "max" in spec:
            min_val = spec["min"]
            max_val = spec["max"]
            unit = spec.get("unit", "")
            
            if min_val <= value <= max_val:
                return {
                    "status": "ok",
                    "message": f"✅ Значение {value}{unit} в пределах нормы ({min_val}-{max_val}{unit})",
                    "action": "Деталь работоспособна"
                }
            else:
                return {
                    "status": "failed",
                    "message": f"❌ Значение {value}{unit} вне диапазона ({min_val}-{max_val}{unit})",
                    "action": f"Рекомендуемое значение: {min_val}-{max_val}{unit}"
                }
        
        # Если спецификация — это список допустимых значений
        elif isinstance(spec, list):
            if value in spec:
                return {
                    "status": "ok",
                    "message": f"✅ Значение {value} соответствует ГОСТ",
                    "action": "Деталь работоспособна"
                }
            else:
                return {
                    "status": "failed",
                    "message": f"❌ Значение {value} не соответствует ГОСТ",
                    "action": f"Допустимые значения: {', '.join(map(str, spec))}"
                }
        
        # Если спецификация — это число (предельное значение)
        elif isinstance(spec, (int, float)):
            if value <= spec:
                return {
                    "status": "ok",
                    "message": f"✅ Значение {value} ≤ {spec} (в пределах нормы)",
                    "action": "Деталь работоспособна"
                }
            else:
                return {
                    "status": "failed",
                    "message": f"❌ Значение {value} > {spec} (превышает норму)",
                    "action": "Требуется ремонт или замена"
                }
        
        # Если спецификация — это строка с описанием
        elif isinstance(spec, str):
            return {
                "status": "info",
                "message": f"ℹ️ {spec}",
                "action": "Смотрите полное описание в ГОСТе"
            }
        
        return {
            "status": "unknown",
            "message": f"⚠️ Не удалось проверить параметр '{param_name}'",
            "action": "Проверьте формат данных в ГОСТе"
        }