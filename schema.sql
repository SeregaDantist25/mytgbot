-- Схема базы данных системы документооборота (SQLAlchemy / PostgreSQL-совместимый DDL).
-- Предназначена для новой версии хранилища; текущая рабочая база — SQLite (data/counters.db).

CREATE TABLE users (
    telegram_id BIGINT PRIMARY KEY,
    role TEXT NOT NULL DEFAULT 'user'
);

CREATE TABLE ships (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'в работе',
    year INTEGER
);

CREATE TABLE repair_statements (
    id SERIAL PRIMARY KEY,
    ship_id INTEGER REFERENCES ships(id),
    source_excel_file_ref TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE statement_items (
    id SERIAL PRIMARY KEY,
    statement_id INTEGER REFERENCES repair_statements(id),
    item_number TEXT,
    description TEXT,
    quantity TEXT,
    section TEXT,
    status TEXT DEFAULT 'active'
);

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    item_id INTEGER REFERENCES statement_items(id),
    category TEXT NOT NULL, -- defect_act_draft, defect_act_approved, avr, other
    file_ref TEXT NOT NULL,
    file_type TEXT,
    version INTEGER DEFAULT 1,
    status TEXT DEFAULT 'draft',
    uploaded_by BIGINT REFERENCES users(telegram_id),
    uploaded_at TIMESTAMP DEFAULT NOW()
);

-- Индексы для производительности
CREATE INDEX idx_documents_item_id ON documents(item_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_statement_items_statement_id ON statement_items(statement_id);
