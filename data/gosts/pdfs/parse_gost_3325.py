import os
import re
import json
import pdfplumber
from datetime import datetime

class Gost3325Parser:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.gost_id = "3325-85"
        self.title = "Подшипники качения. Поля допусков и технические требования к посадочным поверхностям валов и корпусов. Посадки"
        self.data = {
            "gost_id": self.gost_id,
            "title": self.title,
            "sections": [],
            "tables": [],
            "parameters": {}
        }
    
    def parse(self):
        """Основной метод парсинга"""
        print(f"🔄 Начинаю парсинг {self.pdf_path}...")
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"  📄 Обработка страницы {page_num}...")
                
                # Извлекаем текст
                text = page.extract_text()
                if text:
                    self._parse_text(text, page_num)
                
                # Извлекаем таблицы
                tables = page.extract_tables()
                for table in tables:
                    if table and len(table) > 1:
                        self._parse_table(table, page_num)
        
        # Постобработка: структурируем параметры
        self._structure_parameters()
        
        return self.data
    
    def _parse_text(self, text, page_num):
        """Парсит текст страницы"""
        lines = text.split('\n')
        
        current_section = None
        current_subsection = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Ищем заголовки разделов (1., 2., 3. и т.д.)
            section_match = re.match(r'^(\d+)\.\s+(.+)$', line)
            if section_match:
                num = section_match.group(1)
                title = section_match.group(2).strip()
                current_section = {
                    "num": num,
                    "title": title,
                    "content": [],
                    "subsections": []
                }
                self.data["sections"].append(current_section)
                current_subsection = None
                continue
            
            # Ищем подразделы (1.1., 1.2. и т.д.)
            subsection_match = re.match(r'^(\d+\.\d+)\.?\s+(.+)$', line)
            if subsection_match:
                num = subsection_match.group(1)
                title = subsection_match.group(2).strip()
                if current_section:
                    current_subsection = {
                        "num": num,
                        "title": title,
                        "content": []
                    }
                    current_section["subsections"].append(current_subsection)
                continue
            
            # Если есть текущий раздел или подраздел — добавляем строку
            if current_subsection:
                current_subsection["content"].append(line)
            elif current_section:
                current_section["content"].append(line)
    
    def _parse_table(self, table, page_num):
        """Парсит таблицу из PDF"""
        if not table or len(table) < 2:
            return
        
        # Определяем заголовки
        headers = []
        for cell in table[0]:
            if cell:
                headers.append(str(cell).strip())
            else:
                headers.append("")
        
        # Если заголовков мало — пытаемся найти их в первой строке с данными
        if len(headers) < 2:
            for row in table[1:]:
                if row and any(cell for cell in row):
                    headers = [str(cell).strip() if cell else "" for cell in row]
                    break
        
        # Если заголовков нет — создаём стандартные
        if len(headers) < 2:
            headers = [f"col_{i}" for i in range(len(table[0]))]
        
        # Извлекаем данные
        rows = []
        for row in table[1:]:
            if not row or all(cell is None or str(cell).strip() == "" for cell in row):
                continue
            row_data = {}
            for i, cell in enumerate(row):
                if i < len(headers):
                    key = headers[i] or f"col_{i}"
                    value = str(cell).strip() if cell else ""
                    row_data[key] = value
            if row_data:
                rows.append(row_data)
        
        if rows:
            self.data["tables"].append({
                "page": page_num,
                "headers": headers,
                "rows": rows
            })
    
    def _structure_parameters(self):
        """Структурирует извлечённые параметры"""
        
        # Извлекаем параметры из таблиц
        for table in self.data["tables"]:
            for row in table["rows"]:
                # Ищем параметры шероховатости
                if "Ra" in row or "шероховатость" in str(row):
                    self._extract_roughness_params(row)
                
                # Ищем параметры допусков
                if "допуск" in str(row) or "круглости" in str(row):
                    self._extract_tolerance_params(row)
                
                # Ищем параметры зазоров
                if "зазор" in str(row) or "натяг" in str(row):
                    self._extract_clearance_params(row)
    
    def _extract_roughness_params(self, row):
        """Извлекает параметры шероховатости"""
        params = {}
        for key, value in row.items():
            if "Ra" in key:
                params["roughness_ra"] = value
            elif "Rz" in key:
                params["roughness_rz"] = value
            elif "класс" in key.lower():
                params["roughness_class"] = value
            elif "диаметр" in key.lower():
                params["diameter_range"] = value
        
        if params:
            self.data["parameters"]["roughness"] = self.data["parameters"].get("roughness", [])
            self.data["parameters"]["roughness"].append(params)
    
    def _extract_tolerance_params(self, row):
        """Извлекает параметры допусков"""
        params = {}
        for key, value in row.items():
            if "допуск" in key.lower():
                params["tolerance"] = value
            elif "круглости" in key.lower():
                params["roundness"] = value
            elif "профиля" in key.lower():
                params["profile"] = value
            elif "диаметр" in key.lower():
                params["diameter_range"] = value
        
        if params:
            self.data["parameters"]["tolerances"] = self.data["parameters"].get("tolerances", [])
            self.data["parameters"]["tolerances"].append(params)
    
    def _extract_clearance_params(self, row):
        """Извлекает параметры зазоров"""
        params = {}
        for key, value in row.items():
            if "зазор" in key.lower():
                params["clearance"] = value
            elif "натяг" in key.lower():
                params["interference"] = value
            elif "диаметр" in key.lower():
                params["diameter_range"] = value
        
        if params:
            self.data["parameters"]["clearances"] = self.data["parameters"].get("clearances", [])
            self.data["parameters"]["clearances"].append(params)
    
    def save(self, output_path=None):
        """Сохраняет результат в JSON"""
        if not output_path:
            output_path = f"gost_{self.gost_id}_parsed.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Результат сохранён в {output_path}")
        return output_path


def main():
    """Запуск парсера"""
    # Путь к PDF-файлу
    pdf_path = input("Введите путь к файлу ГОСТ 3325-85.pdf: ")
    
    if not os.path.exists(pdf_path):
        print(f"❌ Файл {pdf_path} не найден!")
        return
    
    # Создаём парсер
    parser = Gost3325Parser(pdf_path)
    
    # Парсим
    data = parser.parse()
    
    # Сохраняем
    output = parser.save()
    
    # Выводим статистику
    print(f"\n📊 СТАТИСТИКА:")
    print(f"  • Разделов: {len(data['sections'])}")
    print(f"  • Таблиц: {len(data['tables'])}")
    print(f"  • Параметров шероховатости: {len(data['parameters'].get('roughness', []))}")
    print(f"  • Параметров допусков: {len(data['parameters'].get('tolerances', []))}")
    print(f"  • Параметров зазоров: {len(data['parameters'].get('clearances', []))}")


if __name__ == "__main__":
    main()