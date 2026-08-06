# models/ai_router.py
import os
import httpx
from typing import Dict, List, Optional

class AIRouter:
    def __init__(self):
        self.api_key = os.environ.get('YANDEX_API_KEY')
        self.folder_id = os.environ.get('YANDEX_FOLDER_ID')
        self.stats = {"calls": 0, "errors": 0}
        print(f"🔧 AIRouter инициализирован. API Key: {'есть' if self.api_key else 'НЕТ'}")
    
    def process_query(self, user_text: str, history: List[str] = None) -> Dict:
        """Обработка запроса через Алису"""
        self.stats["calls"] += 1
        
        # Проверяем наличие ключей
        if not self.api_key or not self.folder_id:
            self.stats["errors"] += 1
            return {
                "status": "error",
                "response": "⚠️ Алиса не настроена. Добавьте YANDEX_API_KEY и YANDEX_FOLDER_ID в переменные окружения.",
                "source": "error"
            }
        
        try:
            prompt = self._build_prompt(user_text, history)
            response = self._call_yandex_gpt(prompt)
            
            if response:
                return {
                    "status": "ok",
                    "response": response,
                    "source": "alisa"
                }
            else:
                self.stats["errors"] += 1
                return {
                    "status": "error",
                    "response": "Извините, Алиса не смогла сформировать ответ. Попробуйте переформулировать запрос.",
                    "source": "error"
                }
                
        except Exception as e:
            self.stats["errors"] += 1
            print(f"⚠️ Ошибка при вызове Алисы: {e}")
            return {
                "status": "error",
                "response": f"⚠️ Произошла ошибка: {str(e)[:100]}",
                "source": "error"
            }
    
    def _build_prompt(self, user_text: str, history: List[str] = None) -> str:
        """Сборка промпта для Алисы"""
        prompt = """Ты — инженерный ассистент для судоремонта. Ты работаешь в компании ООО «Новое время» (Находка).

Твои ОБЯЗАННОСТИ:
1. Помогать с ремонтом судового оборудования
2. Проверять параметры по ГОСТам (у тебя есть 23 ГОСТа)
3. Создавать Акты дефектации и АВР
4. Проверять зазоры по ТУ
5. Давать рекомендации по ремонту

ПРАВИЛА ОТВЕТОВ:
- Отвечай кратко, по делу, профессионально
- Если запрос не по теме судоремонта — вежливо объясни, что ты специализируешься на судоремонте
- Не придумывай несуществующие ГОСТы и параметры
- Если не знаешь точного ответа — скажи об этом и предложи уточнить запрос

"""
        
        if history:
            prompt += "\nИСТОРИЯ ДИАЛОГА:\n"
            for msg in history[-5:]:
                prompt += f"{msg}\n"
        
        prompt += f"\nПОЛЬЗОВАТЕЛЬ: {user_text}\n\nОТВЕТ:"
        return prompt
    
    def _call_yandex_gpt(self, prompt: str) -> Optional[str]:
        """Вызов YandexGPT API"""
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
                            "maxTokens": 1500
                        },
                        "messages": [
                            {
                                "role": "system",
                                "text": "Ты инженерный ассистент для судоремонта. Отвечай профессионально и по делу."
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
                    answer = result.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text", "")
                    return answer
                else:
                    print(f"⚠️ Ошибка YandexGPT: {response.status_code} - {response.text[:200]}")
                    return None
                    
        except httpx.TimeoutException:
            print("⚠️ Таймаут при вызове YandexGPT")
            return None
        except Exception as e:
            print(f"⚠️ Ошибка при вызове YandexGPT: {e}")
            return None
    
    def get_stats(self) -> Dict:
        """Статистика использования"""
        return self.stats
    
    def generate_work_volume(self, defects: List[str], equipment_type: str = None, pump_type: str = None) -> Optional[str]:
        """Генерация объёма работ через Алису"""
        try:
            prompt = f"""Составь подробный объём работ для ремонта судового оборудования.

Тип оборудования: {equipment_type or 'не указан'}
Тип насоса: {pump_type or 'не указан'}
Дефекты: {', '.join(defects) if defects else 'не указаны'}

Обязательно включи:
1. Демонтаж узла
2. Разборку и дефектацию
3. Замену или восстановление деталей
4. Сборку с проверкой зазоров
5. Монтаж
6. Предъявление лицу сдающему

Отвечай в виде нумерованного списка, коротко и по делу."""

            result = self._call_yandex_gpt(prompt)
            return result
        except Exception as e:
            print(f"⚠️ Ошибка генерации объёма работ: {e}")
            return None

# Создаём глобальный экземпляр
router = AIRouter()