# scripts/convert_word_to_json.py
import os
import json
import re
from pathlib import Path
from docx import Document

def parse_word_act(file_path):
    """Парсит Word-файл с актом дефектации"""
    
    try:
        doc = Document(file_path)
        
        # Извлекаем весь текст
        full_text = []
        tables_data = []
        
        # Сначала собираем текст из параграфов
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                full_text.append(paragraph.text.strip())
        
        # Потом собираем таблицы
        for table in doc.tables:
            table_rows = []
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    cell_text = cell.text.strip()
                    if cell_text:
                        row_text.append(cell_text)
                if row_text:
                    table_rows.append(row_text)
            if table_rows:
                tables_data.append(table_rows)
        
        full_text_str = "\n".join(full_text)
        
        # Извлекаем информацию
        ship = "Не указано"
        equipment = "Не указано"
        repair_type = "Текущий ремонт"
        defects = []
        work_volume = []
        
        # Ищем судно
        ship_patterns = [
            r'(Судно|т/х|бк)[:]\s*["\']?([^"\'\n]+)["\']?',
            r'Судно[:]\s*([^\n]+)',
            r'бк\s*["\']?([^"\'\n]+)["\']?',
            r'т/х\s*["\']?([^"\'\n]+)["\']?'
        ]
        for pattern in ship_patterns:
            match = re.search(pattern, full_text_str, re.IGNORECASE)
            if match:
                ship = match.group(2).strip() if len(match.groups()) > 1 else match.group(1).strip()
                break
        
        # Ищем оборудование
        equip_patterns = [
            r'Оборудование[:]\s*([^\n]+)',
            r'Механизм[:]\s*([^\n]+)',
            r'Наименование\s*\([^)]+\)[:]\s*([^\n]+)',
            r'([А-Яа-я0-9\s\.\/\-]{5,}?)\s*(?:насос|двигател|компрессор|генератор)',
        ]
        for pattern in equip_patterns:
            match = re.search(pattern, full_text_str, re.IGNORECASE)
            if match:
                equipment = match.group(1).strip()
                break
        
        # Ищем тип ремонта
        repair_match = re.search(r'Категория\s*ремонта[:]\s*([^\n]+)', full_text_str, re.IGNORECASE)
        if repair_match:
            repair_type = repair_match.group(1).strip()
        
        # Парсим таблицы
        for table in tables_data:
            # Ищем заголовки таблицы
            header_row = None
            for i, row in enumerate(table):
                row_text = " ".join(row).lower()
                if "№ п/п" in row_text or "наименование" in row_text:
                    header_row = i
                    break
            
            if header_row is None:
                continue
            
            # Определяем колонки
            headers = [h.strip().lower() for h in table[header_row]]
            col_map = {}
            for i, header in enumerate(headers):
                if "наименование" in header or "узел" in header or "детал" in header:
                    col_map["part"] = i
                elif "дефект" in header or "описание" in header or "состояние" in header:
                    col_map["defect"] = i
                elif "ремонт" in header or "работ" in header or "объём" in header:
                    col_map["work"] = i
                elif "ед" in header:
                    col_map["unit"] = i
                elif "кол" in header:
                    col_map["qty"] = i
            
            # Извлекаем данные из таблицы
            for row in table[header_row + 1:]:
                if not row or all(not cell for cell in row):
                    continue
                
                part = row[col_map["part"]].strip() if col_map.get("part") is not None and len(row) > col_map["part"] else ""
                defect = row[col_map["defect"]].strip() if col_map.get("defect") is not None and len(row) > col_map["defect"] else ""
                work = row[col_map["work"]].strip() if col_map.get("work") is not None and len(row) > col_map["work"] else ""
                
                if not part or len(part) < 2:
                    continue
                if re.match(r'^\d+\.?\d*$', part):
                    continue
                
                if defect:
                    defects.append(f"{part}: {defect}")
                else:
                    defects.append(part)
                
                if work:
                    work_volume.append(f"{part}: {work}")
        
        # Если таблиц нет или они пустые — парсим текст
        if not defects:
            # Ищем блоки с дефектами
            defect_section = re.search(r'(Дефект|Неисправность|Описание\s*дефекта)[^\n]*\n([\s\S]*?)(?=Объём|Работ|Заключение|Представитель)', full_text_str, re.IGNORECASE)
            if defect_section:
                lines = defect_section.group(2).split('\n')
                for line in lines:
                    if line.strip() and len(line.strip()) > 5:
                        defects.append(line.strip())
            
            # Ищем объём работ
            work_section = re.search(r'(Объём\s*работ|Работы|Ремонтные\s*работы)[^\n]*\n([\s\S]*?)(?=Заключение|Представитель|Согласовано)', full_text_str, re.IGNORECASE)
            if work_section:
                lines = work_section.group(2).split('\n')
                for line in lines:
                    if line.strip() and len(line.strip()) > 5:
                        work_volume.append(line.strip())
        
        # Если всё ещё пусто — ищем по ключевым словам
        if not defects:
            for line in full_text:
                if any(kw in line.lower() for kw in ["износ", "течь", "трещин", "коррози", "зазор", "поврежден"]):
                    if len(line) > 10:
                        defects.append(line.strip())
        
        if defects:
            act_data = {
                "ship": ship if ship != "Не указано" else "АЛЕУТ",
                "equipment": equipment if equipment != "Не указано" else file_path.stem,
                "repair_type": repair_type,
                "defects": defects[:20],
                "work_volume": "\n".join(work_volume[:15]) if work_volume else "\n".join([f"{i+1}. {d}" for i, d in enumerate(defects[:8])]),
                "conclusion": "Детали подлежат замене/восстановлению согласно указанному объёму работ."
            }
            return [act_data]
        
        return []
        
    except Exception as e:
        print(f"❌ Ошибка {file_path.name}: {e}")
        return []

def convert_all_word():
    input_dir = Path("data/acts_word")
    output_dir = Path("data/act_examples")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not input_dir.exists():
        print(f"⚠️ Папка {input_dir} не найдена. Создайте её и положите туда Word-файлы.")
        return
    
    total = 0
    for file in input_dir.glob("*.docx"):
        print(f"📄 {file.name}")
        results = parse_word_act(file)
        if results:
            for i, act in enumerate(results, 1):
                out_file = output_dir / f"{file.stem}_{i}.json"
                with open(out_file, 'w', encoding='utf-8') as f:
                    json.dump(act, f, ensure_ascii=False, indent=2)
                total += 1
            print(f"  ✅ {len(results)} актов")
        else:
            print(f"  ⚠️ Нет данных")
    
    print(f"\n🎉 Всего сохранено: {total} актов")

if __name__ == "__main__":
    convert_all_word()