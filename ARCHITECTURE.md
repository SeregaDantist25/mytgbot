# -*- coding: utf-8 -*-
"""
АРХИТЕКТУРА БОТА СУДОРЕМОНТА

## 1. АНАЛИЗ ТРЕБОВАНИЙ

### Входные данные:
- Суда: название, тип, регистровый номер, год постройки
- Заказчики: компания, ИНН, контакты
- Заявки на ремонт: дата, тип работ, статус, стоимость
- Сотрудники: ФИО, должность, квалификация

### Выходные данные:
- CRUD операции для всех сущностей
- Поиск/фильтрация
- История изменений (audit log)
- Генерация актов (PDF/DOCX/Excel) через ИИ

### Роли:
- director: директор (утверждение документов, доступ ко всему)
- engineer_technologist: инженер-технолог (создание/редактирование документов)
- master: мастер (просмотр, комментирование)
- customer: заказчик (только просмотр своих судов, без редактирования)

---

## 2. АРХИТЕКТУРНОЕ РЕШЕНИЕ

### Стек технологий:
- **Язык**: Python 3.11+
- **Telegram Bot**: pyTelegramBotAPI (telebot) — синхронный, проверенный
- **ORM**: SQLAlchemy 2.0 (sync для SQLite, async для PostgreSQL)
- **БД**: PostgreSQL (prod) / SQLite (dev/prototype)
- **AI**: YandexGPT (Алиса) для генерации текстов актов
- **Генерация документов**: python-docx (DOCX), openpyxl (XLSX), reportlab (PDF)

### Структура папок:
```
/workspace
├── app/                      # Новое ядро (модульная архитектура)
│   ├── core/                 # Конфигурация, утилиты
│   │   ├── config.py        # Настройки через pydantic-settings
│   │   └── __init__.py
│   ├── models/              # ORM-модели
│   │   ├── schemas.py       # SQLAlchemy модели
│   │   └── __init__.py
│   ├── services/            # Бизнес-логика
│   │   ├── document_service.py  # CRUD документов + AI
│   │   ├── ai_service.py    # Интеграция с YandexGPT
│   │   └── __init__.py
│   ├── db/                  # Работа с БД
│   │   ├── session.py       # Сессии, connection pool
│   │   └── __init__.py
│   ├── api/                 # API endpoints (будущее)
│   └── utils/               # Утилиты
├── handlers/                # Обработчики Telegram (существующие)
├── services/                # Сервисы (существующие)
├── ai/                      # AI-модули (существующие)
├── models.py                # Старые ORM-модели (обратная совместимость)
├── db.py                    # Старый DB-слой (SQLite)
├── bot.py                   # Точка входа
└── config.py                # Старый конфиг
```

### Паттерны:
- **Repository Pattern**: Доступ к данным через сервисы
- **Dependency Injection**: Сессии БД через get_db_session()
- **Strategy Pattern**: AI-сервис с fallback на локальную генерацию
- **Unit of Work**: Транзакции через context manager

---

## 3. МОДЕЛЬ ДАННЫХ

### Схема БД (PostgreSQL/SQLite):

```sql
users
├── id (PK)
├── telegram_id (unique)
├── name
├── role (director/engineer/master/customer)
├── phone
├── inn (для заказчиков)
├── approved (bool)
└── timestamps

ships
├── id (PK)
├── name (unique)
├── type
├── registry_number
├── year_built
├── status (in_work/completed/archived)
├── customer_name
├── customer_inn
├── customer_contact
├── builder_id (FK → users)
└── timestamps

repair_statements
├── id (PK)
├── ship_id (FK → ships)
├── source_excel_file_ref
└── timestamps

statement_items
├── id (PK)
├── statement_id (FK → repair_statements)
├── item_number (например, "4.56.2")
├── description
├── quantity
├── section
├── status (active/completed/cancelled)
├── unit_price (опционально)
├── total_price (опционально)
└── timestamps

documents
├── id (PK)
├── item_id (FK → statement_items)
├── category (defect_act/work_act/contract/technical_act)
├── file_ref (путь к файлу)
├── file_type (pdf/docx/xlsx)
├── file_data (BLOB для PostgreSQL)
├── version
├── status (draft/approved/archived/rejected)
├── uploaded_by (FK → users)
├── approved_by (FK → users)
├── rejection_reason
├── ai_generated (bool)
└── timestamps

companies
├── id (PK)
├── name (unique)
├── inn (unique)
├── kpp
├── address
├── contact_person
├── phone
├── email
└── timestamps

employees
├── id (PK)
├── full_name
├── position
├── qualification
├── department
├── user_id (FK → users)
└── timestamps

audit_log
├── id (PK)
├── user_id (FK → users)
├── action (create/update/delete/approve/reject)
├── entity_type (ship/document/statement_item)
├── entity_id
├── details (JSON)
└── created_at

act_templates
├── id (PK)
├── name
├── act_type
├── template_path
├── fields_json (JSON)
├── prompt_template
├── is_active
└── timestamps
```

---

## 4. РИСКИ И ПОДВОДНЫЕ КАМНИ

### Edge Cases:
1. **Пустые данные**: Проверка на None перед доступом к полям
2. **Обрыв соединения**: pool_pre_ping=True для PostgreSQL
3. **Невалидный JSON**: try/except при парсинге ответа ИИ
4. **Превышение лимитов**: Rate limiting (30 сообщений/мин)
5. **Параллельные запросы**: Транзакции с isolation_level
6. **Большие файлы**: MAX_FILE_SIZE=50MB, стриминг для >10MB
7. **Паника бота**: infinity_polling с retry logic

### Безопасность:
- SQL-инъекции: SQLAlchemy ORM (параметризованные запросы)
- Права доступа: can_edit(), can_approve() проверки
- Секреты: .env файл, не в коде
- Транзакции: commit/rollback в сервисах

### Масштабируемость:
- Connection pool: pool_size=10, max_overflow=20
- Индексы: на telegram_id, status, item_id
- Pagination: PAGE_SIZE=20, MAX_PAGE_SIZE=100

---

## 5. ПРИМЕР РАБОТЫ

### Сценарий 1: Создание акта дефектации через ИИ
```
Пользователь: "Судно Славянская, насос масляный, износ зубьев шестерни"
Бот:
  1. Определяет судно → "Славянская"
  2. Определяет оборудование → "Насос масляный"
  3. Отправляет промпт в YandexGPT
  4. Получает JSON с defects, work_volume, conclusion
  5. Генерирует DOCX из шаблона
  6. Сохраняет как draft
  7. Отправляет пользователю на проверку
```

### Сценарий 2: Утверждение документа директором
```
Директор: /approve 123
Бот:
  1. Проверяет роль пользователя (director)
  2. Находит документ #123
  3. Меняет status: draft → approved
  4. Логирует в audit_log
  5. Отправляет уведомление автору
```

### Сценарий 3: Поиск по ГОСТам
```
Пользователь: "проверь по ГОСТ 520-2011 диаметр=50"
Бот:
  1. Парсит запрос → gost_id=520-2011, param=диаметр, value=50
  2. Ищет в базе ГОСТов
  3. Возвращает таблицу с допусками
```

---

## 6. TEST CASES

### Тест 1: CRUD документа
```python
# Создание
doc = await doc_service.create_document(
    item_id=1,
    category="defect_act",
    file_data=b"...bytes...",
    uploaded_by=123456789,
)
assert doc.status == "draft"

# Утверждение
success, msg = await doc_service.approve_document(doc.id, approved_by=987654321)
assert success and doc.status == "approved"

# Архивация
success, msg = await doc_service.archive_document(doc.id, archived_by=987654321)
assert success and doc.status == "archived"
```

### Тест 2: AI генерация с fallback
```python
# Без API ключа (fallback)
result = await ai_service.generate_act_content(
    act_type="defect_act",
    user_input="насос течёт",
    item_data={"item_number": "4.56", "description": "Насос"}
)
assert result["success"] == True
assert "defects" in result["data"]
```

### Тест 3: Ролевая модель
```python
# Инженер может редактировать
assert can_edit(engineer_user, ship) == True

# Заказчик не может редактировать
assert can_edit(customer_user, ship) == False

# Только директор утверждает
assert can_approve(director_user) == True
assert can_approve(customer_user) == False
```

---

## 7. СЛЕДУЮЩИЕ ШАГИ

1. ✅ Создана новая модульная структура app/
2. ✅ Реализованы ORM-модели (app/models/schemas.py)
3. ✅ Настроен async DB менеджер (app/db/session.py)
4. ✅ DocumentService с CRUD операциями
5. ✅ AIService с YandexGPT интеграцией и fallback
6. ⏳ Нужно: DocumentGenerator (DOCX/PDF из шаблонов)
7. ⏳ Нужно: Telegram handlers для новых сервисов
8. ⏳ Нужно: Миграция данных из старой схемы
9. ⏳ Нужно: Тесты (pytest)
10. ⏳ Нужно: .env.example с переменными окружения
"""

print(__doc__)
