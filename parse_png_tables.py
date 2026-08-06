import os
import json
import pytesseract
import cv2
import numpy as np
from PIL import Image
import re

class PngTableParser:
    def __init__(self, input_dir="ocr_output", output_dir="data/gosts/parsed"):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.gost_id = "3325-85"
        self.data = {
            "gost_id": self.gost_id,
            "title": "Подшипники качения. Поля допусков и технические требования",
            "tables": []
        }
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Настройка Tesseract
        self.tesseract_cmd = self._find_tesseract()
        pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
    
    def _find_tesseract(self):
        possible_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract"
        ]
        for path in possible_paths:
            if os.path.exists(path):
                print(f"✅ Tesseract найден: {path}")
                return path
        return "tesseract"
    
    def parse_all_pngs(self):
        """Парсит все PNG-файлы в папке"""
        print(f"🔄 Сканируем папку: {self.input_dir}")
        
        png_files = sorted([f for f in os.listdir(self.input_dir) if f.endswith('.png')])
        
        if not png_files:
            print("❌ PNG-файлы не найдены!")
            return
        
        print(f"📄 Найдено {len(png_files)} PNG-файлов")
        
        for png_file in png_files:
            print(f"\n📄 Обработка: {png_file}")
            page_num = int(re.search(r'page_(\d+)', png_file).group(1))
            
            png_path = os.path.join(self.input_dir, png_file)
            tables = self._extract_tables_from_png(png_path)
            
            if tables:
                print(f"   ✅ Найдено {len(tables)} таблиц на странице {page_num}")
                for table in tables:
                    self.data["tables"].append({
                        "page": page_num,
                        "data": table
                    })
            else:
                print(f"   ⚠️ Таблицы не найдены")
        
        self._save_result()
        return self.data
    
    def _extract_tables_from_png(self, png_path):
        """Извлекает таблицы из PNG-файла"""
        # Загружаем изображение
        image = cv2.imread(png_path)
        if image is None:
            return []
        
        # Преобразуем в оттенки серого
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Улучшаем контраст
        gray = cv2.equalizeHist(gray)
        
        # Бинаризация
        _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        
        # Находим контуры
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        tables = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 5000:  # Минимальная площадь таблицы
                continue
            
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            
            if len(approx) >= 4:
                x, y, w, h = cv2.boundingRect(contour)
                if w > h * 1.5:  # Таблица обычно широкая
                    # Вырезаем область таблицы
                    table_region = image[y:y+h, x:x+w]
                    table_pil = Image.fromarray(cv2.cvtColor(table_region, cv2.COLOR_BGR2RGB))
                    
                    # Распознаём текст с улучшенными настройками
                    table_text = pytesseract.image_to_string(
                        table_pil, 
                        lang="rus",
                        config="--psm 6 --oem 3"
                    )
                    
                    # Парсим таблицу
                    parsed_table = self._parse_table_text(table_text)
                    if parsed_table and len(parsed_table["rows"]) > 1:
                        tables.append(parsed_table)
        
        return tables
    
    def _parse_table_text(self, table_text):
        """Парсит текст таблицы"""
        lines = [line.strip() for line in table_text.split('\n') if line.strip()]
        if len(lines) < 2:
            return None
        
        # Ищем заголовки
        headers = []
        data_rows = []
        
        # Пробуем найти заголовки в первых строках
        for i, line in enumerate(lines[:5]):
            # Заголовки обычно содержат слова в верхнем регистре
            if re.search(r'[А-Я]{2,}', line) and any(word in line for word in ['ПОСАДК', 'ДОПУСК', 'ЗАЗОР', 'НАХЯГ', 'ШЕРОХОВАТОСТ', 'КЛАСС']):
                headers = re.split(r'\s{2,}', line)
                lines = lines[i+1:]
                break
        
        if not headers:
            # Если заголовки не найдены, пробуем распознать по структуре
            for line in lines:
                parts = re.split(r'\s{2,}', line)
                if len(parts) >= 2:
                    headers = parts[:len(parts)]
                    break
        
        # Извлекаем данные
        for line in lines:
            if not line:
                continue
            
            parts = re.split(r'\s{2,}', line)
            
            # Проверяем, что это строка с данными
            if len(parts) >= 2 and any(re.search(r'\d', part) for part in parts):
                data_rows.append(parts)
        
        if not data_rows:
            return None
        
        return {"headers": headers, "rows": data_rows}
    
    def _save_result(self):
        """Сохраняет результат"""
        output_path = os.path.join(self.output_dir, f"gost_{self.gost_id}_tables.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Результат сохранён в {output_path}")
        
        # Статистика
        print(f"\n📊 СТАТИСТИКА:")
        print(f"  • Таблиц найдено: {len(self.data['tables'])}")


def main():
    parser = PngTableParser()
    parser.parse_all_pngs()


if __name__ == "__main__":
    main()