import os
import re
import json
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import numpy as np
import cv2

class OCRGostParser:
    def __init__(self, pdf_path, output_dir="ocr_output"):
        self.pdf_path = pdf_path
        self.output_dir = output_dir
        self.gost_id = "3325-85"
        self.data = {
            "gost_id": self.gost_id,
            "title": "Подшипники качения. Поля допусков и технические требования",
            "tables": [],
            "structured_data": {
                "roughness": [],
                "tolerances": [],
                "clearances": [],
                "fits": []
            },
            "full_text": ""
        }
        
        os.makedirs(output_dir, exist_ok=True)
        self.tesseract_cmd = self._find_tesseract()
    
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
        print("⚠️ Tesseract не найден.")
        return "tesseract"
    
    def parse(self):
        print(f"🔄 Начинаю OCR-парсинг {self.pdf_path}...")
        pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
        
        print("  📄 Конвертируем PDF в изображения (dpi=150)...")
        try:
            images = convert_from_path(
                self.pdf_path, 
                dpi=150, 
                poppler_path=r"C:\poppler\Library\bin"
            )
        except Exception as e:
            print(f"❌ Ошибка конвертации PDF: {e}")
            return self.data
        
        for page_num, image in enumerate(images, 1):
            print(f"  📄 Обработка страницы {page_num} из {len(images)}...")
            
            image_path = os.path.join(self.output_dir, f"page_{page_num}.png")
            image.save(image_path)
            
            text = pytesseract.image_to_string(image, lang="rus")
            self.data["full_text"] += f"\n\n--- СТРАНИЦА {page_num} ---\n{text}"
            
            tables = self._extract_tables_from_image(image)
            if tables:
                for table_data in tables:
                    self.data["tables"].append({
                        "page": page_num,
                        "data": table_data
                    })
                    self._classify_table_data(table_data)
        
        self._save_result()
        return self.data
    
    def _extract_tables_from_image(self, image):
        img_array = np.array(image)
        gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY) if len(img_array.shape) == 3 else img_array
        
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 15, 5
        )
        
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        tables = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 10000:
                continue
            
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            
            if len(approx) >= 4:
                x, y, w, h = cv2.boundingRect(contour)
                if w > h * 1.5:
                    table_region = image.crop((x, y, x + w, y + h))
                    table_text = pytesseract.image_to_string(table_region, lang="rus")
                    parsed_table = self._parse_table_text(table_text)
                    if parsed_table:
                        tables.append(parsed_table)
        
        return tables
    
    def _parse_table_text(self, table_text):
        lines = [line.strip() for line in table_text.split('\n') if line.strip()]
        if len(lines) < 2:
            return None
        
        headers = []
        data_rows = []
        
        for line in lines:
            if re.search(r'[А-Я]{2,}', line) and any(word in line for word in ['ПОСАДК', 'ДОПУСК', 'ЗАЗОР', 'НАХЯГ', 'ШЕРОХОВАТОСТ']):
                headers = re.split(r'\s{2,}', line)
                break
        
        if not headers:
            for line in lines:
                parts = re.split(r'\s{2,}', line)
                if len(parts) >= 2 and any(re.search(r'\d', part) for part in parts):
                    headers = parts[:len(parts)]
                    break
        
        for line in lines:
            if line in headers or any(h in line for h in headers):
                continue
            parts = re.split(r'\s{2,}', line)
            if len(parts) >= 2 and len(parts) <= len(headers) + 2:
                if any(re.search(r'\d', part) for part in parts):
                    data_rows.append(parts)
        
        if not data_rows:
            return None
        
        return {"headers": headers, "rows": data_rows}
    
    def _classify_table_data(self, table_data):
        headers_text = " ".join(table_data.get("headers", []))
        rows_text = " ".join([" ".join(row) for row in table_data.get("rows", [])])
        combined_text = (headers_text + " " + rows_text).lower()
        
        if "шероховатост" in combined_text or "ra" in combined_text or "rz" in combined_text:
            self.data["structured_data"]["roughness"].extend(table_data["rows"])
        elif "допуск" in combined_text or "круглост" in combined_text or "профил" in combined_text:
            self.data["structured_data"]["tolerances"].extend(table_data["rows"])
        elif "зазор" in combined_text or "натяг" in combined_text:
            self.data["structured_data"]["clearances"].extend(table_data["rows"])
        elif "посадк" in combined_text or "вал" in combined_text and "корпус" in combined_text:
            self.data["structured_data"]["fits"].extend(table_data["rows"])
    
    def _save_result(self):
        output_path = os.path.join(self.output_dir, f"gost_{self.gost_id}_ocr.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        print(f"✅ Результат сохранён в {output_path}")
        
        text_path = os.path.join(self.output_dir, f"gost_{self.gost_id}_full_text.txt")
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(self.data["full_text"])
        print(f"✅ Полный текст сохранён в {text_path}")


def main():
    pdf_path = input("Введите путь к файлу ГОСТ 3325-85.pdf: ")
    
    if not os.path.exists(pdf_path):
        print(f"❌ Файл {pdf_path} не найден!")
        return
    
    parser = OCRGostParser(pdf_path)
    data = parser.parse()
    
    print(f"\n📊 СТАТИСТИКА:")
    print(f"  • Таблиц найдено: {len(data['tables'])}")
    print(f"  • Шероховатость: {len(data['structured_data']['roughness'])} записей")
    print(f"  • Допуски: {len(data['structured_data']['tolerances'])} записей")
    print(f"  • Зазоры: {len(data['structured_data']['clearances'])} записей")
    print(f"  • Посадки: {len(data['structured_data']['fits'])} записей")


if __name__ == "__main__":
    main()