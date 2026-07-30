import os
import httpx
import json
import re

class AIModelRouter:
    def __init__(self):
        # Настройка моделей
        self.models = {
            "alice": {
                "name": "Алиса",
                "api_key": os.environ.get('ALICE_API_KEY'),
                "url": "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                "model": "yandexgpt",
                "folder_id": os.environ.get('YANDEX_FOLDER_ID')
            }
        }
        
        # Статистика
        self.stats = {
            "alice": {"calls": 0, "errors": 0}
        }
        
        # Названия моделей для отображения
        self.model_names = {
            "alice": "Алиса (YandexGPT)"
        }
    
    def get_model_config(self, model_name):
        return self.models.get(model_name)
    
    def call_model(self, model_name, prompt, temperature=0.1, max_tokens=500):
        """Вызывает указанную модель с промптом"""
        model_config = self.get_model_config(model_name)
        if not model_config:
            print(f"❌ Модель {model_name} не найдена")
            return None
        
        if not model_config.get('api_key'):
            print(f"❌ API-ключ для {model_name} не найден")
            return None
        
        try:
            client = httpx.Client(timeout=30.0)
            
            # Формат запроса для YandexGPT
            payload = {
                "modelUri": f"gpt://{model_config['folder_id']}/{model_config['model']}/latest",
                "completionOptions": {
                    "stream": False,
                    "temperature": temperature,
                    "maxTokens": max_tokens
                },
                "messages": [
                    {"role": "user", "text": prompt}
                ]
            }
            
            response = client.post(
                model_config["url"],
                headers={
                    "Authorization": f"Api-Key {model_config['api_key']}",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            
            self.stats[model_name]["calls"] += 1
            
            if response.status_code == 200:
                result = response.json()
                # Извлекаем текст ответа
                if 'result' in result and 'alternatives' in result['result']:
                    return result['result']['alternatives'][0]['message']['text']
                else:
                    print(f"❌ Неожиданный формат ответа от {model_name}")
                    return None
            else:
                self.stats[model_name]["errors"] += 1
                print(f"❌ Ошибка {model_name}: {response.status_code}")
                print(f"Ответ: {response.text[:200]}")
                return None
                
        except Exception as e:
            self.stats[model_name]["errors"] += 1
            print(f"❌ Ошибка {model_name}: {e}")
            return None
    
    def analyze_query(self, text):
        """Анализ запроса через Алису"""
        prompt = f"""Разбери запрос пользователя и верни ответ строго в формате JSON.

Запрос: {text}

Ответ должен содержать поля:
- "ship": название судна или null
- "equipment": название оборудования
- "equipment_type": pump/engine/compressor/other
- "pump_type": centrifugal/gear/piston/null
- "defects": список дефектов
- "clearances": []

Ответь ТОЛЬКО JSON. Никакого лишнего текста."""

        result = self.call_model("alice", prompt, temperature=0.1, max_tokens=300)
        if result:
            return self._parse_json(result)
        return None
    
    def generate_work_volume(self, defects, equipment_type, pump_type=None):
        """Генерация объёма работ через Алису"""
        equip_name = "оборудования"
        if equipment_type == "pump":
            equip_name = "насоса"
            if pump_type:
                equip_name = f"{pump_type} насоса"
        elif equipment_type == "engine":
            equip_name = "двигателя"
        
        prompt = f"""Составь подробный объём работ для ремонта {equip_name} по следующим дефектам:
{chr(10).join(defects) if defects else 'дефекты не указаны'}

Ответь в виде нумерованного списка:
1. Демонтаж узла
2. Разборка и дефектация
3. Конкретные работы по замене/восстановлению деталей
4. Сборка с проверкой зазоров
5. Монтаж
6. Предъявление лицу сдающему

Пиши конкретно, указывай детали."""
        
        result = self.call_model("alice", prompt, temperature=0.3, max_tokens=400)
        if result:
            return result
        return None
    
    def check_clearance(self, clearance_type, value, pump_type):
        """Проверка зазоров через Алису"""
        prompt = f"""Проверь зазор для {pump_type} насоса:
Тип зазора: {clearance_type}
Измеренное значение: {value} мм

Ответь кратко: норма, превышение или занижение."""
        
        result = self.call_model("alice", prompt, temperature=0.1, max_tokens=200)
        if result:
            return result
        return None
    
    def _parse_json(self, text):
        """Извлекает JSON из текста"""
        try:
            json_start = text.find('{')
            json_end = text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                return json.loads(text[json_start:json_end])
        except:
            pass
        return None
    
    def get_stats(self):
        return self.stats
    
    def get_available_models(self):
        available = []
        for name, config in self.models.items():
            if config.get('api_key'):
                available.append(name)
        return available

# Создаём глобальный экземпляр
router = AIModelRouter()