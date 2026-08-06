def generate_work_volume(self, defects, equipment_type, pump_type=None):
    """Генерация объёма работ через базу знаний + AI"""
    if not defects:
        return self._get_base_work()
    
    # 1. Ищем в базе знаний похожие примеры
    samples = self._find_samples(defects[0])
    
    # 2. Формируем промпт с примерами
    prompt = self._build_prompt_with_samples(defects, samples, equipment_type)
    
    # 3. Отправляем Алисе с примерами
    result = self.call_model("alice", prompt, temperature=0.2, max_tokens=300)
    if result:
        return result
    
    # 4. Если AI не ответил — базовый шаблон
    return self._get_base_work()

def _find_samples(self, defect_text, max_samples=3):
    """Находит похожие примеры из базы знаний"""
    if not self.knowledge_base:
        return []
    
    samples = self.knowledge_base.get("samples", [])
    found = []
    
    defect_lower = defect_text.lower()
    for sample in samples:
        for sample_defect in sample.get("defects", []):
            if sample_defect in defect_lower or defect_lower in sample_defect:
                found.append(sample)
                break
    
    # Если точных совпадений нет — берём первые 3 примера
    if not found:
        found = samples[:3]
    
    return found

def _build_prompt_with_samples(self, defects, samples, equipment_type):
    """Формирует промпт с примерами из базы знаний"""
    equip_name = "оборудования"
    if equipment_type == "pump":
        equip_name = "насоса"
    elif equipment_type == "engine":
        equip_name = "двигателя"
    
    # Формируем блок с примерами
    examples_text = ""
    if samples:
        examples_text = "\n**Примеры правильных объёмов работ:**\n"
        for sample in samples[:3]:
            examples_text += f"- Дефект: {sample.get('defects', [''])[0]}\n"
            examples_text += f"  Объём работ: {sample.get('work', '')}\n"
    
    prompt = f"""Ты — инженер-судоремонтник. Составь объём работ для дефектовочного акта.

Тип оборудования: {equip_name}
Дефекты: {chr(10).join(defects)}

{examples_text}

Правила:
1. Пиши КОРОТКО, как в примерах выше.
2. Каждый пункт — 3-7 слов.
3. Только список работ, без объяснений.

Ответь нумерованным списком (1., 2., 3., 4., 5., 6.):
1. Демонтаж
2. Разборка и дефектация
3. Замена/восстановление деталей
4. Сборка с проверкой зазоров
5. Монтаж
6. Предъявление лицу сдающему"""
    
    return prompt