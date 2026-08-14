# -*- coding: utf-8 -*-
"""
AI-сервис для генерации контента документов.

Интеграция с YandexGPT (Алиса) для умной генерации описаний работ.
"""

import logging
import re
import json
from typing import Dict, List, Optional, Any
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AIService:
    """Сервис для работы с YandexGPT."""
    
    # Типы актов и их описания
    ACT_TYPES = {
        "defect_act": "Акт дефектации",
        "work_act": "Акт выполненных работ",
        "technical_act": "Технический акт",
        "repair_statement": "Ремонтная ведомость",
    }
    
    def __init__(self):
        self.api_key = settings.YANDEX_API_KEY
        self.folder_id = settings.YANDEX_FOLDER_ID
        self._initialized = bool(self.api_key and self.folder_id)
        
        if not self._initialized:
            logger.warning("YandexGPT не настроен (нет API ключа или folder ID)")
    
    async def generate_act_content(
        self,
        act_type: str,
        user_input: str,
        item_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Генерирует содержание акта через ИИ.
        
        Args:
            act_type: Тип акта (defect_act, work_act, etc.)
            user_input: Описание от пользователя
            item_data: Данные пункта ведомости
        
        Returns:
            Dict с полями: success, data (или error)
        """
        if not self._initialized:
            return self._fallback_generate(act_type, user_input, item_data)
        
        try:
            prompt = self._build_prompt(act_type, user_input, item_data)
            response_text = await self._call_yandex_gpt(prompt)
            
            if not response_text:
                logger.warning("YandexGPT не вернул ответ, используем fallback")
                return self._fallback_generate(act_type, user_input, item_data)
            
            # Парсим JSON из ответа
            data = self._parse_response(response_text)
            
            if data and "equipment" in data and "defects" in data:
                return {"success": True, "data": data}
            else:
                logger.warning("Некорректный формат ответа ИИ")
                return self._fallback_generate(act_type, user_input, item_data)
                
        except Exception as e:
            logger.error(f"Ошибка генерации через ИИ: {e}")
            return self._fallback_generate(act_type, user_input, item_data)
    
    def _build_prompt(
        self,
        act_type: str,
        user_input: str,
        item_data: Dict[str, Any],
    ) -> str:
        """Строит промпт для YandexGPT."""
        
        act_name = self.ACT_TYPES.get(act_type, "Документ")
        
        prompt = f"""Ты — инженер-технолог судоремонтного предприятия. 
Твоя задача — проанализировать запрос и сгенерировать данные для документа: {act_name}.

## ДАННЫЕ ПУНКТА ВЕДОМОСТИ:
- Номер пункта: {item_data.get('item_number', 'Н/Д')}
- Описание работ: {item_data.get('description', 'Н/Д')}
- Количество/объём: {item_data.get('quantity', 'Н/Д')}

## ЗАПРОС ПОЛЬЗОВАТЕЛЯ:
{user_input}

## ТРЕБОВАНИЯ К ОТВЕТУ:
1. Извлеки название судна (если указано)
2. Определи оборудование (насос, двигатель, компрессор и т.д.)
3. Выдели дефекты (износ, течь, коррозия, трещины, зазоры и т.п.)
4. Сгенерируй объём работ — нумерованный список с техническими деталями
5. Добавь заключение о необходимости замены/восстановления

## ФОРМАТ ОТВЕТА:
Ответь ТОЛЬКО JSON-объектом без лишнего текста:

{{
  "ship": "Название судна",
  "equipment": "Тип и название оборудования",
  "equipment_type": "насос/двигатель/компрессор",
  "repair_type": "текущий/капитальный/средний",
  "defects": ["дефект 1", "дефект 2"],
  "work_volume": "1. Демонтаж...\\n2. Разборка...\\n3. ...",
  "conclusion": "Заключение о ремонтопригодности",
  "gosts": ["ГОСТ XXXX-XXXX раздел X.X"],
  "tools_required": ["инструмент 1", "инструмент 2"],
  "spare_parts": ["запчасть 1", "запчасть 2"]
}}

ОТВЕЧАЙ ТОЛЬКО JSON!"""

        return prompt
    
    async def _call_yandex_gpt(self, prompt: str) -> Optional[str]:
        """Вызывает YandexGPT API."""
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
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
                                "text": "Ты — инженер-технолог судоремонтного предприятия. Отвечай только JSON."
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
                    return (
                        result.get("result", {})
                        .get("alternatives", [{}])[0]
                        .get("message", {})
                        .get("text", "")
                    )
                else:
                    logger.warning(f"YandexGPT error: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Ошибка вызова YandexGPT: {e}")
            return None
    
    def _parse_response(self, response_text: str) -> Optional[Dict]:
        """Извлекает JSON из ответа."""
        try:
            # Ищем JSON в тексте
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                data = json.loads(json_match.group())
                return data
        except Exception as e:
            logger.warning(f"Ошибка парсинга JSON: {e}")
        
        return None
    
    def _fallback_generate(
        self,
        act_type: str,
        user_input: str,
        item_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Локальная генерация без ИИ (fallback)."""
        
        # Определяем судно по ключевым словам
        ships = [
            "аргака", "пластун", "славянская", "первоуральск",
            "керчь", "краснодар", "алеут"
        ]
        ship = "Не указано"
        for s in ships:
            if s in user_input.lower():
                ship = s.capitalize()
                break
        
        # Определяем оборудование
        equipment_keywords = {
            "насос": "Насос",
            "двигатель": "Двигатель",
            "компрессор": "Компрессор",
            "вентилятор": "Вентилятор",
            "генератор": "Генератор",
            "редуктор": "Редуктор",
            "турбина": "Турбина",
        }
        equipment = "Оборудование"
        equipment_type = "other"
        for kw, label in equipment_keywords.items():
            if kw in user_input.lower():
                equipment = label
                equipment_type = kw
                break
        
        # Извлекаем дефекты
        defects = []
        defect_keywords = [
            "износ", "течь", "коррози", "трещин", "зазор",
            "люфт", "биение", "поврежд", "разруш", "полом"
        ]
        sentences = re.split(r'[,.!?;]', user_input)
        for sentence in sentences:
            sentence = sentence.strip()
            for kw in defect_keywords:
                if kw in sentence.lower() and sentence not in defects:
                    defects.append(sentence)
                    break
        
        if not defects:
            defects = ["Дефекты не указаны"]
        
        # Генерируем объём работ
        work_lines = self._generate_work_volume(equipment_type, defects)
        
        return {
            "success": True,
            "data": {
                "ship": ship,
                "equipment": equipment,
                "equipment_type": equipment_type,
                "repair_type": "Текущий ремонт",
                "defects": defects,
                "work_volume": "\n".join(work_lines),
                "conclusion": "Детали подлежат замене/восстановлению согласно объёму работ.",
                "gosts": [],
                "tools_required": ["Набор ключей", "Съёмник"],
                "spare_parts": ["Комплект запчастей"]
            }
        }
    
    def _generate_work_volume(
        self,
        equipment_type: str,
        defects: List[str],
    ) -> List[str]:
        """Генерирует стандартный объём работ по типу оборудования."""
        
        base_works = {
            "насос": [
                "1. Демонтаж насоса с фундамента",
                "2. Разборка насоса на узлы",
                "3. Дефектация деталей",
                "4. Замена/восстановление изношенных деталей",
                "5. Сборка насоса с регулировкой зазоров",
                "6. Монтаж на место",
                "7. Испытания под нагрузкой"
            ],
            "двигатель": [
                "1. Демонтаж двигателя",
                "2. Разборка ЦПГ",
                "3. Дефектация поршневой группы",
                "4. Замена колец/вкладышей",
                "5. Сборка с затяжкой динамометрическим ключом",
                "6. Монтаж",
                "7. Обкатка и настройка"
            ],
            "компрессор": [
                "1. Демонтаж компрессора",
                "2. Разборка компрессорной головки",
                "3. Замена клапанов/колец",
                "4. Проверка зазоров",
                "5. Сборка",
                "6. Монтаж",
                "7. Испытания давлением"
            ],
        }
        
        works = base_works.get(equipment_type, [
            "1. Демонтаж узла",
            "2. Разборка и дефектация",
            "3. Замена изношенных деталей",
            "4. Сборка",
            "5. Монтаж",
            "6. Испытания"
        ])
        
        # Добавляем специфику по дефектам
        for defect in defects:
            if "течь" in defect.lower() and "Замена уплотнений" not in works:
                works.insert(-1, "Замена уплотнительных колец/прокладок")
            if "коррози" in defect.lower() and "Антикоррозийная обработка" not in works:
                works.insert(-1, "Антикоррозийная обработка корпуса")
        
        works.append("8. Предъявление лицу, сдающему работу")
        
        return works
