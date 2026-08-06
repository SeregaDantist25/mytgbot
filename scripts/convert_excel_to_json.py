# scripts/convert_excel_all.py
import os
import json
import re
import pandas as pd
from pathlib import Path

def smart_parse(file_path):
    """Умный парсинг — определяет тип файла и извлекает данные"""
    
    try:
        xl = pd.ExcelFile(file_path)
        results = []
        
        # Перебираем все листы
        for sheet_name in xl.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
            
            # Определяем тип файла по содержимому
            has_table = False
            has_defects = False
            equipment = "Не указано"
            ship = "Не указано"
            repair_type = "Текущий ремонт"
            
            # Ищем заголовки таблицы
            header_row = None
            for idx, row in df.iterrows():
                row_text = " ".join([str(v).lower() for v in row if pd.notna(v)])
                
                # Ищем судно
                if "бк" in row_text or "т/х" in row_text:
                    match = re.search(r'(бк|т/х)\s*["\']?([^"\'\n,]+)', row_text, re.IGNORECASE)
                    if match:
                        ship = match.group(2).strip()
                
                # Ищем оборудование
                if any(w in row_text for w in ["насос", "двигател", "компрессор", "генератор"]):
                    match = re.search(r'([А-Яа-я0-9\s\.\/\-]+?)(?:\s*\.\s*|$)', row_text)
                    if match and len(match.group(1).strip()) > 5:
                        equipment_candidate = match.group(1).strip()
                        if len(equipment_candidate) > 3:
                            equipment = equipment_candidate
                
                # Ищем тип ремонта
                if "категория ремонта" in row_text:
                    match = re.search(r'категория ремонта[:\-]?\s*([^\n]+)', row_text, re.IGNORECASE)
                    if match:
                        repair_type = match.group(1).strip()
                
                # Ищем заголовки таблицы
                if "№ п/п" in row_text and "наименование" in row_text:
                    header_row = idx
                    has_table = True
                    break
            
            # Если есть таблица — парсим как акт
            if has_table:
                df_data = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)
                
                # Определяем колонки
                col_map = {}
                for col in df_data.columns:
                    col_lower = str(col).lower().strip()
                    if any(w in col_lower for w in ["наименование", "узел", "детал"]):
                        col_map["part"] = col
                    elif any(w in col_lower for w in ["описание", "дефект"]):
                        col_map["defect"] = col
                    elif any(w in col_lower for w in ["ремонт", "работ"]):
                        col_map["work"] = col
                    elif "ед" in col_lower:
                        col_map["unit"] = col
                    elif "кол" in col_lower:
                        col_map["qty"] = col
                
                defects = []
                work_volume = []
                
                for idx, row in df_data.iterrows():
                    part = str(row.get(col_map.get("part"), "")).strip() if col_map.get("part") else ""
                    defect = str(row.get(col_map.get("defect"), "")).strip() if col_map.get("defect") else ""
                    work = str(row.get(col_map.get("work"), "")).strip() if col_map.get("work") else ""
                    
                    if not part or part == "nan" or len(part) < 2:
                        continue
                    if re.match(r'^\d+\.?\d*$', part):
                        continue
                    
                    if defect and defect != "nan" and defect != "—":
                        defects.append(f"{part}: {defect}")
                    else:
                        defects.append(part)
                    
                    if work and work != "nan" and work != "—":
                        work_volume.append(f"{part}: {work}")
                
                if defects:
                    results.append({
                        "ship": ship if ship != "Не указано" else "АЛЕУТ",
                        "equipment": equipment if equipment != "Не указано" else file_path.stem,
                        "repair_type": repair_type,
                        "defects": defects,
                        "work_volume": "\n".join(work_volume) if work_volume else "\n".join([f"{i+1}. {d}" for i, d in enumerate(defects)]),
                        "conclusion": "Детали подлежат замене/восстановлению согласно указанному объёму работ."
                    })
                    return results
            
            # Если нет таблицы — пробуем извлечь из "доп.работ"
            # Ищем строки с дефектами
            defects = []
            work_volume = []
            
            for idx, row in df.iterrows():
                row_text = " ".join([str(v) for v in row if pd.notna(v)])
                
                # Ищем строки с описанием дефектов
                if any(w in row_text.lower() for w in ["износ", "течь", "трещин", "коррози", "зазор", "замена", "ремонт"]):
                    if len(row_text) > 10:
                        defects.append(row_text.strip())
                
                # Ищем строки с работами
                if any(w in row_text.lower() for w in ["демонтаж", "разборк", "сборк", "монтаж", "замен"]):
                    if len(row_text) > 10 and row_text not in work_volume:
                        work_volume.append(row_text.strip())
            
            # Если нашли дефекты — сохраняем
            if defects:
                results.append({
                    "ship": ship if ship != "Не указано" else "АЛЕУТ",
                    "equipment": equipment if equipment != "Не указано" else file_path.stem,
                    "repair_type": repair_type,
                    "defects": defects[:15],
                    "work_volume": "\n".join(work_volume[:10]) if work_volume else "\n".join([f"{i+1}. {d}" for i, d in enumerate(defects[:8])]),
                    "conclusion": "Детали подлежат замене/восстановлению согласно указанному объёму работ."
                })
                return results
        
        return results
        
    except Exception as e:
        print(f"❌ Ошибка {file_path.name}: {e}")
        return []

def convert_all():
    input_dir = Path("data/acts_excel")
    output_dir = Path("data/act_examples")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    total = 0
    errors = []
    
    for file in input_dir.glob("*.xlsx"):
        print(f"📄 {file.name}")
        results = smart_parse(file)
        if results:
            for i, act in enumerate(results, 1):
                out_file = output_dir / f"{file.stem}_{i}.json"
                with open(out_file, 'w', encoding='utf-8') as f:
                    json.dump(act, f, ensure_ascii=False, indent=2)
                total += 1
            print(f"  ✅ {len(results)} актов, судно: {results[0].get('ship', '?')}")
        else:
            errors.append(file.name)
            print(f"  ⚠️ Нет данных")
    
    print(f"\n🎉 Всего сохранено: {total} актов")
    if errors:
        print(f"\n⚠️ Не обработаны ({len(errors)}):")
        for name in errors[:10]:
            print(f"   • {name}")

if __name__ == "__main__":
    convert_all()