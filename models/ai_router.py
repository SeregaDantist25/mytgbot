# models/ai_router.py
import os
import json
import httpx
import re
from datetime import datetime
from typing import Dict, Any, Optional, List

class AIRouter:
    def __init__(self):
        self.api_key = os.environ.get('YANDEX_API_KEY')
        self.folder_id = os.environ.get('YANDEX_FOLDER_ID')
        self.model = "yandexgpt"
        
        # Загружаем базу знаний
        self.gost_data = self._load_gosts()
        self.pump_data = self._load_pumps()
        
        # Статистика
        self.stats = {"calls": 0, "errors": 0}
    
    def _load_gosts(self) -> Dict:
        """Загрузка базы ГОСТов"""
        try:
            with open("gost_data.json", 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("gosts", {})
        except:
            return {}
    
    def _load_pumps(self) -> Dict:
        """Загрузка базы насосов"""
        try:
            with open("data/checklists.json", 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def _build_context(self) -> str:
        """Сборка контекста для Алисы (вся база знаний)"""
        context = []
        
        # 1. Информация о ГОСТах
        context.append("📋 ДОСТУПНЫЕ ГОСТЫ ДЛЯ ПРОВЕРКИ:")
        for gost_id, data in list(self.gost_data.items())[:20]:
            title = data.get("title", "")[:60]
            context.append(f"• {gost_id}: {title}")
            params = data.get("parameters", {})
            if params:
                param_list = ", ".join(list(params.keys())[:5])
                context.append(f"  Параметры: {param_list}")
        context.append("")
        
        # 2. Информация о насосах
        context.append("🔧 ТИПЫ НАСОСОВ И ИХ ЗАЗОРЫ:")
        for pump_type, data in self.pump_data.items():
            name = data.get("name", pump_type)
            context.append(f"• {name}:")
            clearances = data.get("clearances", {})
            for ct, values in clearances.items():
                min_val = values.get("min", 0)
                max_val = values.get("max", 0)
                unit = values.get("unit", "мм")
                context.append(f"  - {ct}: {min_val}-{max_val} {unit}")
        context.append("")
        
        # 3. Информация о функциях бота
        context.append("⚙️ ДОСТУПНЫЕ ФУНКЦИИ:")
        context.append("• Создать Акт дефектации — скажи 'сделай акт' или опиши дефекты")
        context.append("• Создать Акт выполненных работ — скажи 'сделай АВР'")
        context.append("• Проверить зазор — скажи 'проверь зазор'")
        context.append("• Проверить по ГОСТу — скажи 'проверь по ГОСТ {номер} {параметр}={значение}'")
        context.append("• Показать ГОСТы — скажи 'покажи ГОСТы'")
        context.append("• Поиск по ГОСТам — скажи 'найди ГОСТ по {запрос}'")
        
        return "\n".join(context)
    
    def _build_prompt(self, user_text: str, history: List[str] = None) -> str:
        """Сборка полного промпта для Алисы"""
        context = self._build_context()
        
        history_text = ""
        if history:
            history_text = "ИСТОРИЯ ДИАЛОГА:\n" + "\n".join(history[-5:]) + "\n"
        
        prompt = f"""Ты — инженерный ассистент для судоремонта. Твоя задача — помогать пользователю с ремонтом судового оборудования.

Твои ОБЯЗАННОСТИ:
1. Отвечать на ВСЕ вопросы пользователя, даже если они не связаны напрямую с судоремонтом
2. Использовать базу знаний для проверки параметров по ГОСТам
3. Создавать документы (Акты дефектации, АВР) по запросу
4. Проверять зазоры и параметры по ТУ
5. Давать рекомендации по ремонту

{context}

{history_text}

ПОЛЬЗОВАТЕЛЬ: {user_text}

ОТВЕТЬ на вопрос пользователя. Если нужно создать документ — скажи об этом и спроси недостающие данные. Если нужно проверить параметр — сделай это по ГОСТам. Если пользователь просто спрашивает — ответь дружелюбно и профессионально.

Твой ответ:"""
        
        return prompt
    
    def process_query(self, user_text: str, history: List[str] = None) -> Dict:
        """Обработка запроса через Алису"""
        self.stats["calls"] += 1
        
        # 1. Проверяем, не является ли запрос прямой командой (для быстрых ответов)
        quick_result = self._check_quick_commands(user_text)
        if quick_result:
            return quick_result
        
        # 2. Отправляем запрос в Алису
        try:
            response = self._call_alisa(user_text, history)
            return {
                "status": "ok",
                "response": response,
                "source": "alisa",
                "calls": self.stats["calls"]
            }
        except Exception as e:
            self.stats["errors"] += 1
            return {
                "status": "error",
                "response": f"Извините, произошла ошибка: {str(e)}. Попробуйте переформулировать запрос.",
                "source": "error",
                "calls": self.stats["calls"]
            }
    
    def _check_quick_commands(self, text: str) -> Optional[Dict]:
        """Быстрая проверка команд без вызова Алисы"""
        text_lower = text.lower()
        
        # Команда для создания акта
        if any(word in text_lower for word in ['сделай акт', 'акт дефектации', 'оформи акт']):
            return {
                "status": "action",
                "action": "create_act",
                "response": "📄 Для создания Акта дефектации опишите:\n- Судно\n- Оборудование\n- Дефекты\n\nПример: 'Судно Аргака, насос центробежный, износ подшипников'"
            }
        
        # Команда для АВР
        if any(word in text_lower for word in ['сделай авр', 'акт выполненных', 'оформи авр']):
            return {
                "status": "action",
                "action": "create_avr",
                "response": "📋 Для создания Акта выполненных работ опишите:\n- Выполненные работы\n- Количество и единицы измерения\n\nПример: 'АВР: замена уголков 44 шт, болтов 194 шт'"
            }
        
        # Команда для проверки по ГОСТу
        gost_match = re.search(r'проверь по ГОСТ\s*([\d-]+)', text_lower)
        if gost_match:
            return None  # Отправляем в Алису, она разберётся
        
        return None
    
    def _call_alisa(self, user_text: str, history: List[str] = None) -> str:
        """Вызов YandexGPT"""
        if not self.api_key:
            return self._fallback_response(user_text)
        
        prompt = self._build_prompt(user_text, history)
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                    headers={
                        "Authorization": f"Api-Key {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "modelUri": f"gpt://{self.folder_id}/yandexgpt/latest",
                        "completionOptions": {
                            "stream": False,
                            "temperature": 0.3,
                            "maxTokens": 2000
                        },
                        "messages": [
                            {
                                "role": "system",
                                "text": "Ты — инженерный ассистент для судоремонта. Отвечай дружелюбно и профессионально."
                            },
                            {
                                "role": "user",
                                "text": prompt
                            }
                        ]
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text", "Извините, не удалось получить ответ.")
                else:
                    return self._fallback_response(user_text)
                    
        except Exception as e:
            print(f"⚠️ Ошибка при вызове Алисы: {e}")
            return self._fallback_response(user_text)
    
    def _fallback_response(self, user_text: str) -> str:
        """Запасной ответ, если Алиса недоступна"""
        text_lower = user_text.lower()
        
        # Проверяем зазоры локально
        if "проверь зазор" in text_lower:
            from bot import extract_clearances_from_text, detect_pump_type, pump_db
            clearances = extract_clearances_from_text(user_text)
            if clearances:
                responses = []
                for c in clearances:
                    pump_type = detect_pump_type(user_text) or "centrifugal"
                    result = pump_db.check_clearance(pump_type, c['type'], c['value'])
                    responses.append(f"• {c['type']}: {c['value']} мм → {result['message']}")
                return "📊 Результаты проверки зазоров:\n\n" + "\n".join(responses)
        
        # Проверяем ГОСТы локально
        if "гост" in text_lower or "проверь по" in text_lower:
            return self._local_gost_check(user_text)
        
        return "🤔 Я не совсем понял запрос. Могу:\n- Создать Акт дефектации ('сделай акт')\n- Создать АВР ('сделай АВР')\n- Проверить зазор ('проверь зазор')\n- Проверить по ГОСТу ('проверь по ГОСТ 520-2011 диаметр=50')\n\nИли просто задайте вопрос на русском языке."
    
    def _local_gost_check(self, text: str) -> str:
        """Локальная проверка по ГОСТам"""
        try:
            from gost_checker import GOSTChecker
            checker = GOSTChecker()
            
            gost_match = re.search(r'гост\s*([\d-]+)', text, re.IGNORECASE)
            if gost_match:
                gost_id = gost_match.group(1)
                param_match = re.search(r'(\w+)\s*[=:]\s*([\d.]+)', text)
                if param_match:
                    param_name = param_match.group(1)
                    value = float(param_match.group(2))
                    result = checker.check_parameter(gost_id, param_name, value)
                    return f"📊 Проверка по ГОСТ {gost_id}:\n\n{result.get('message', '')}"
            
            return "Не удалось распознать запрос для проверки по ГОСТу."
        except:
            return "Ошибка при проверке по ГОСТам."
    
    def get_stats(self) -> Dict:
        """Статистика использования"""
        return self.stats

# Создаём глобальный экземпляр
router = AIRouter()