# scripts/update_knowledge_from_acts.py
import os
import json
from pathlib import Path
from collections import defaultdict

def update_knowledge_from_acts():
    """Обновляет базу знаний на основе актов"""
    
    acts_dir = Path("data/act_examples")
    kb_path = Path("data/knowledge_base.json")
    
    # Загружаем текущую базу
    if kb_path.exists():
        with open(kb_path, 'r', encoding='utf-8') as f:
            kb = json.load(f)
    else:
        kb = {"defects": {}, "tips": {}, "statistics": {}}
    
    # Собираем статистику
    stats = {
        "total_acts": 0,
        "by_equipment": defaultdict(int),
        "by_defect": defaultdict(int),
        "by_repair_type": defaultdict(int),
        "common_defects": defaultdict(int)
    }
    
    all_defects = []
    
    for file in acts_dir.glob("*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            stats["total_acts"] += 1
            
            equipment = data.get("equipment", "Неизвестно")
            stats["by_equipment"][equipment] += 1
            
            repair_type = data.get("repair_type", "Текущий")
            stats["by_repair_type"][repair_type] += 1
            
            for defect in data.get("defects", []):
                # Определяем тип дефекта
                defect_lower = defect.lower()
                if "подшипн" in defect_lower:
                    stats["by_defect"]["подшипник"] += 1
                elif "сальн" in defect_lower:
                    stats["by_defect"]["сальник"] += 1
                elif "износ" in defect_lower:
                    stats["by_defect"]["износ"] += 1
                elif "течь" in defect_lower:
                    stats["by_defect"]["течь"] += 1
                elif "коррози" in defect_lower:
                    stats["by_defect"]["коррозия"] += 1
                elif "трещин" in defect_lower:
                    stats["by_defect"]["трещина"] += 1
                elif "зазор" in defect_lower:
                    stats["by_defect"]["зазор"] += 1
                else:
                    stats["by_defect"]["другое"] += 1
                
                # Сохраняем для анализа частых сочетаний
                all_defects.append(defect)
        
        except Exception as e:
            print(f"⚠️ Ошибка {file.name}: {e}")
    
    # Находим самые частые дефекты
    from collections import Counter
    defect_counter = Counter()
    for file in acts_dir.glob("*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for defect in data.get("defects", []):
                defect_counter[defect[:50]] += 1
        except:
            pass
    
    stats["common_defects"] = dict(defect_counter.most_common(20))
    
    # Обновляем базу знаний
    kb["statistics"] = dict(stats)
    kb["statistics"]["by_equipment"] = dict(stats["by_equipment"])
    kb["statistics"]["by_defect"] = dict(stats["by_defect"])
    
    # Сохраняем
    with open(kb_path, 'w', encoding='utf-8') as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)
    
    print(f"\n📊 СТАТИСТИКА:")
    print(f"   ✅ Всего актов: {stats['total_acts']}")
    print(f"   🏷️ Типы ремонтов: {dict(stats['by_repair_type'])}")
    print(f"\n🔧 ТОП-5 ОБОРУДОВАНИЯ:")
    for equip, count in sorted(stats["by_equipment"].items(), key=lambda x: -x[1])[:5]:
        print(f"   • {equip[:40]}: {count}")
    print(f"\n🔍 ЧАСТЫЕ ДЕФЕКТЫ:")
    for defect, count in stats["by_defect"].items():
        print(f"   • {defect}: {count}")
    
    print(f"\n✅ База знаний обновлена: {kb_path}")

if __name__ == "__main__":
    update_knowledge_from_acts()