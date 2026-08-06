# merge_gosts.py
import json
import os
from pathlib import Path

def merge_gosts():
    """Объединяет все JSON-файлы ГОСТов в один gost_data.json"""
    
    merged = {"gosts": {}}
    
    # Ищем все JSON-файлы в текущей папке
    current_dir = Path(".")
    
    # Список файлов, которые нужно пропустить
    skip_files = ["gost_data.json", "checklists.json", "counters.json"]
    
    print("🔍 Поиск JSON-файлов с ГОСТами...")
    
    # Ищем JSON-файлы с ГОСТами в текущей папке
    for file in current_dir.glob("*.json"):
        if file.name in skip_files:
            continue
        
        if file.name.startswith("gost_") or file.name.startswith("ГОСТ") or "gost" in file.name.lower():
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Если файл содержит один ГОСТ
                    if "gost_id" in data:
                        gost_id = data.get("gost_id", file.stem.replace("gost_", ""))
                        merged["gosts"][gost_id] = data
                        print(f"✅ Добавлен ГОСТ {gost_id} из {file.name}")
                    
                    # Если файл уже содержит коллекцию
                    elif "gosts" in data:
                        for gost_id, gost_data in data["gosts"].items():
                            merged["gosts"][gost_id] = gost_data
                            print(f"✅ Добавлен ГОСТ {gost_id} из {file.name}")
                    
                    else:
                        print(f"⚠ Неизвестный формат: {file.name}")
                        
            except Exception as e:
                print(f"❌ Ошибка при чтении {file.name}: {e}")
    
    # Ищем в папке gost_jsons (если есть)
    gost_folder = Path("gost_jsons")
    if gost_folder.exists():
        for file in gost_folder.glob("*.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    if "gost_id" in data:
                        gost_id = data.get("gost_id", file.stem)
                        merged["gosts"][gost_id] = data
                        print(f"✅ Добавлен ГОСТ {gost_id} из {file.name}")
                    
                    elif "gosts" in data:
                        for gost_id, gost_data in data["gosts"].items():
                            merged["gosts"][gost_id] = gost_data
                            print(f"✅ Добавлен ГОСТ {gost_id} из {file.name}")
                    
            except Exception as e:
                print(f"❌ Ошибка при чтении {file.name}: {e}")
    
    print(f"\n📊 Всего загружено ГОСТов: {len(merged['gosts'])}")
    
    if not merged["gosts"]:
        print("❌ Не найдено ни одного ГОСТа!")
        print("💡 Убедитесь, что JSON-файлы с ГОСТами находятся в текущей папке или в папке gost_jsons")
        return
    
    # Сохраняем объединённый файл
    with open("gost_data.json", 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Сохранено в gost_data.json")
    print(f"📁 Путь: {os.path.abspath('gost_data.json')}")
    
    # Показываем список загруженных ГОСТов
    print("\n📋 Список загруженных ГОСТов:")
    for gost_id in sorted(merged["gosts"].keys()):
        title = merged["gosts"][gost_id].get("title", "Без названия")[:50]
        print(f"   • {gost_id} — {title}...")

if __name__ == "__main__":
    merge_gosts()