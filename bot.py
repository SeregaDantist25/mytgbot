@bot.message_handler(func=lambda message: True)
def handle_intelligent_input(message):
    user_text = message.text
    text_lower = user_text.lower()
    
    if user_text.startswith('/'):
        return
    
    # ---- 1. ПРОВЕРКА ЗАЗОРОВ ----
    if any(word in text_lower for word in ['зазор', 'допуск', 'проверь', 'норма']):
        # Проверяем, есть ли конкретные значения
        clearances = extract_clearances_from_text(user_text)
        if clearances:
            responses = []
            for c in clearances:
                if c['type'] != 'unknown':
                    # Определяем тип насоса
                    pump_type = detect_pump_type(user_text)
                    if not pump_type:
                        pump_type = "gear" if "шестерен" in text_lower else "centrifugal"
                    
                    result = pump_db.check_clearance(pump_type, c['type'], c['value'])
                    responses.append(f"🔹 {c['type']}: {c['value']} мм → {result['message']}")
            
            if responses:
                response = "📊 **Результаты проверки зазоров:**\n\n" + "\n".join(responses)
                bot.reply_to(message, response, parse_mode='Markdown')
                return
        
        # Если не нашли конкретные значения - просим уточнить
        bot.reply_to(message,
            "🔧 Чтобы проверить зазор, напишите в формате:\n"
            "`зазор радиальный 0.25`\n"
            "`шестерёнчатый осевой 0.4`\n\n"
            "Доступные зазоры: radial, axial, bearing, seal",
            parse_mode='Markdown'
        )
        return
    
    # ---- 2. СОЗДАНИЕ АКТА ДЕФЕКТАЦИИ ----
    if any(word in text_lower for word in ['акт', 'дефектовк', 'сделай акт', 'оформи', 'составь']):
        # Полный анализ
        analysis = analyze_query(user_text)
        
        ship = analysis.get('ship')
        equipment = analysis.get('equipment')
        defects = analysis.get('defects', [])
        pump_type = analysis.get('pump_type')
        clearances = analysis.get('clearances', [])
        
        # Если есть зазоры - добавляем их в дефекты
        for c in clearances:
            defect_text = f"зазор {c['type']}: {c['value']} мм"
            if defect_text not in defects:
                defects.append(defect_text)
        
        # Если нет дефектов - пробуем извлечь из текста
        if not defects:
            # Ищем по ключевым словам
            defect_keywords = ["износ", "течь", "коррози", "трещин", "разруш", 
                              "выкрашиван", "задир", "деформац", "ржав", "люфт"]
            for kw in defect_keywords:
                if kw in text_lower:
                    defects.append(f"{kw} (требуется уточнение)")
            
            if not defects:
                bot.reply_to(message,
                    "🤔 Я не нашёл дефектов в вашем сообщении.\n"
                    "Пожалуйста, опишите дефекты подробнее.\n\n"
                    "Пример: 'Судно Аргака, насос центробежный, износ подшипников и течь сальника'"
                )
                return
        
        # Формируем Equipment
        if not equipment:
            pump_name = "шестерёнчатый" if pump_type == "gear" else "центробежный" if pump_type else ""
            equipment = f"насос {pump_name}".strip() if pump_name else "насос"
        
        # Генерируем объём работ
        work_volume = generate_work_volume(defects, user_text, pump_type)
        
        # Создаём документ
        file_stream = create_defect_document(ship, equipment, defects, work_volume)
        bot.send_document(
            message.chat.id, 
            file_stream, 
            visible_file_name=f'Акт_дефектации_{ship or "судна"}.docx'
        )
        bot.send_message(message.chat.id, "📄 Акт дефектации в Word отправлен!")
        return
    
    # Остальные обработчики без изменений...