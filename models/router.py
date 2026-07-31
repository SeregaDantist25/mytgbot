import os
import httpx
import json
import re
from difflib import get_close_matches

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
        
        self.stats = {
            "alice": {"calls": 0, "errors": 0}
        }
        
        # Загружаем базу знаний
        self.knowledge_base = self._load_knowledge_base()
    
    def _load_knowledge_base(self):
        """Загружает базу знаний из index.json"""
        try:
            kb_path = os.path.join("data", "vector_store", "index.json")
            if os.path.exists(kb_path):
                with open(kb_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                print("⚠️ База знаний не найдена, использую только AI")
                return {"samples": [], "keywords": {}}
        except Exception as e:
            print(f"⚠️ Ошибка загрузки базы знаний: {e}")
            return {"samples": [], "keywords": {}}
    
    def _find_work_by_defect(self, defect_text):
        """Ищет объём работ по дефекту в базе знаний"""
        if not self.knowledge_base:
            return None
        
        defect_lower = defect_text.lower()
        
        # 1. Проверяем ключевые слова
        keywords = self.knowledge_base.get("keywords", {})
        for keyword, work in keywords.items():
            if keyword in defect_lower:
                return work
        
        # 2. Ищем по образцам (точное совпадение)
        samples = self.knowledge_base.get("samples", [])
        for sample in samples:
            for sample_defect in sample.get("defects", []):
                if sample_defect in defect_lower:
                    return sample.get("work", "")
        
        # 3. Ищем по близости (fuzzy match)
        all_defects = []
        for sample in samples:
            for defect in sample.get("defects", []):
                all_defects.append(defect)
        
        if all_defects:
            matches = get_close_matches(defect_lower, all_defects, n=1, cutoff=0.7)
            if matches:
                for sample in samples:
                    if matches[0] in sample.get("defects", []):
                        return sample.get("work", "")
        
        return None
    
    def get_model_config(self, model_name):
        return self.models.get(model_name)
    
    def call_model(self, model_name, prompt, temperature=0.1, max_tokens=500):
        model_config = self.get_model_config(model_name)
        if not model_config or not model_config.get('api_key'):
            print(f"❌ Модель {model_name} не настроена")
            return None
        
        try:
            client = httpx.Client(timeout=30.0)
            
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
                if 'result' in result and 'alternatives' in result['result']:
                    return result['result']['alternatives'][0]['message']['text']
                else:
                    return None
            else:
                self.stats[model_name]["errors"] += 1
                print(f"❌ Ошибка {model_name}: {response.status_code}")
                return None
                
        except Exception as e:
            self.stats[model_name]["errors"] += 1
            print(f"❌ Ошибка {model_name}: {e}")
            return None
    
    def analyze_query(self, text):
        """Анализ запроса через базу знаний + AI"""
        # Сначала ищем в базе
        defects = self._extract_defects(text)
        if defects:
            work = self._find_work_by_defect(defects[0])
            if work:
                return {
                    "ship": self._extract_ship(text),
                    "equipment": self._extract_equipment(text),
                    "defects": defects,
                    "work_volume": work,
                    "source": "local"
                }
        
        # Если не найдено — используем AI
        prompt = f"""Разбери запрос и верни JSON.
Запрос: {text}
Ответь: {{"ship": "...", "equipment": "...", "equipment_type": "pump/engine/compressor/other", "pump_type": "centrifugal/gear/piston/null", "defects": [...], "clearances": []}}"""
        
        result = self.call_model("alice", prompt, temperature=0.1, max_tokens=300)
        if result:
            return self._parse_json(result)
        return None
    
    def generate_work_volume(self, defects, equipment_type, pump_type=None):
        """Генерация объёма работ через базу знаний или AI"""
        if defects:
            # Ищем в базе знаний
            work = self._find_work_by_defect(defects[0])
            if work:
                return work
        
        # Если не найдено — используем AI
        equip_name = "оборудования"
        if equipment_type == "pump":
            equip_name = "насоса"
        elif equipment_type == "engine":
            equip_name = "двигателя"
        
        prompt = f"""Составь краткий объём работ для ремонта судового {equip_name}.

Дефекты: {chr(10).join(defects)}

Ответь нумерованным списком (1., 2., 3., 4., 5., 6.):
1. Демонтаж узла
2. Разборка и дефектация
3. Замена/восстановление деталей
4. Сборка с проверкой зазоров
5. Монтаж
6. Предъявление лицу сдающему

Без лишних слов."""
        
        result = self.call_model("alice", prompt, temperature=0.3, max_tokens=300)
        if result:
            return result
        return None
    
    def _extract_defects(self, text):
        """Извлекает дефекты из текста (локальный парсер)"""
        text_lower = text.lower()
        defects = []
        
        defect_keywords = [
            "износ", "течь", "коррози", "трещин", "разруш", "выкрашиван",
            "задир", "деформац", "ржав", "люфт", "биение", "стук", "вибрац",
            "зазор", "перегрев", "заедание", "загрязнен", "неплотн", "протечк"
        ]
        
        sentences = re.split(r'[,.!?;]', text)
        for sentence in sentences:
            sentence_lower = sentence.lower().strip()
            if not sentence_lower:
                continue
            for kw in defect_keywords:
                if kw in sentence_lower:
                    defects.append(sentence.strip())
                    break
        
        return defects
    
    def _extract_ship(self, text):
        ships = ["аргака", "пластун", "славянская", "первоуральск", "керчь", "краснодар"]
        for ship in ships:
            if ship in text.lower():
                return ship.capitalize()
        return None
    
    def _extract_equipment(self, text):
        equipment_keywords = ["насос", "двигатель", "компрессор", "вентилятор", 
                             "генератор", "кран", "лебедка", "редуктор", "гидромотор",
                             "брашпиль", "котёл", "водонагреватель", "дизель", "мотор"]
        for kw in equipment_keywords:
            if kw in text.lower():
                pattern = r'(\w+\s+){0,2}' + kw + r'(\s+\w+){0,2}'
                match = re.search(pattern, text)
                if match:
                    return match.group(0).strip()
        return None
    
    def _parse_json(self, text):
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