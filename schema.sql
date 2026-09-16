PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('nutritionist', 'patient')),
    crn TEXT,
    phone TEXT,
    birth_date TEXT,
    goal TEXT,
    height_cm REAL,
    active INTEGER NOT NULL DEFAULT 1,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    session_version INTEGER NOT NULL DEFAULT 1,
    privacy_policy_version TEXT,
    privacy_accepted_at TEXT,
    email_verified_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS professional_patients (
    nutritionist_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (nutritionist_id, patient_id),
    FOREIGN KEY (nutritionist_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS meal_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nutritionist_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    objective TEXT,
    guidance TEXT,
    calories REAL NOT NULL DEFAULT 0,
    protein REAL NOT NULL DEFAULT 0,
    carbs REAL NOT NULL DEFAULT 0,
    fat REAL NOT NULL DEFAULT 0,
    fiber REAL NOT NULL DEFAULT 0,
    calcium REAL NOT NULL DEFAULT 0,
    iron REAL NOT NULL DEFAULT 0,
    target_calories REAL NOT NULL DEFAULT 0,
    target_protein REAL NOT NULL DEFAULT 0,
    target_carbs REAL NOT NULL DEFAULT 0,
    target_fat REAL NOT NULL DEFAULT 0,
    target_fiber REAL NOT NULL DEFAULT 0,
    target_calcium REAL NOT NULL DEFAULT 0,
    target_iron REAL NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (nutritionist_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS foods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    category TEXT NOT NULL,
    household_measure TEXT,
    calories REAL NOT NULL DEFAULT 0,
    protein REAL NOT NULL DEFAULT 0,
    carbs REAL NOT NULL DEFAULT 0,
    fat REAL NOT NULL DEFAULT 0,
    fiber REAL NOT NULL DEFAULT 0,
    calcium REAL NOT NULL DEFAULT 0,
    iron REAL NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS meal_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    meal_name TEXT NOT NULL,
    food_name TEXT NOT NULL,
    quantity TEXT NOT NULL,
    calories REAL NOT NULL DEFAULT 0,
    protein REAL NOT NULL DEFAULT 0,
    carbs REAL NOT NULL DEFAULT 0,
    fat REAL NOT NULL DEFAULT 0,
    fiber REAL NOT NULL DEFAULT 0,
    calcium REAL NOT NULL DEFAULT 0,
    iron REAL NOT NULL DEFAULT 0,
    food_id INTEGER,
    amount_g REAL,
    FOREIGN KEY (plan_id) REFERENCES meal_plans(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS weight_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    weight REAL NOT NULL CHECK (weight > 0),
    recorded_on TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (patient_id, recorded_on)
);

CREATE TABLE IF NOT EXISTS food_diary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    meal_name TEXT NOT NULL,
    description TEXT NOT NULL,
    adherence INTEGER NOT NULL DEFAULT 1,
    hunger INTEGER,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nutritionist_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    starts_at TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('online', 'in_person')),
    status TEXT NOT NULL DEFAULT 'scheduled',
    meeting_url TEXT,
    notes TEXT,
    duration_minutes INTEGER NOT NULL DEFAULT 50,
    reminder_minutes INTEGER NOT NULL DEFAULT 1440,
    cancellation_reason TEXT,
    updated_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (nutritionist_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS availability_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nutritionist_id INTEGER NOT NULL,
    weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (nutritionist_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (nutritionist_id, weekday, start_time, end_time)
);

CREATE TABLE IF NOT EXISTS schedule_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nutritionist_id INTEGER NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (nutritionist_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS appointment_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id INTEGER NOT NULL,
    actor_id INTEGER NOT NULL,
    event TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    old_starts_at TEXT,
    new_starts_at TEXT,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
    FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    recipient_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    read_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    remind_at TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_plans_patient ON meal_plans(patient_id, active);
CREATE INDEX IF NOT EXISTS idx_weight_patient_date ON weight_records(patient_id, recorded_on);
CREATE INDEX IF NOT EXISTS idx_diary_patient_date ON food_diary(patient_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_appointments_start ON appointments(starts_at);
CREATE INDEX IF NOT EXISTS idx_appointments_professional_start ON appointments(nutritionist_id, starts_at, status);
CREATE INDEX IF NOT EXISTS idx_appointment_history_appointment ON appointment_history(appointment_id, created_at);
CREATE INDEX IF NOT EXISTS idx_availability_professional_weekday ON availability_slots(nutritionist_id, weekday, active);
CREATE INDEX IF NOT EXISTS idx_schedule_blocks_professional_start ON schedule_blocks(nutritionist_id, starts_at);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_pair ON messages(sender_id, recipient_id, created_at);

INSERT OR IGNORE INTO foods
    (name, category, household_measure, calories, protein, carbs, fat, fiber, calcium, iron, source)
VALUES
    ('Arroz integral, cozido', 'Cereais', '4 colheres de sopa (100 g)', 124, 2.6, 25.8, 1.0, 2.7, 5, 0.3, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Arroz tipo 1, cozido', 'Cereais', '4 colheres de sopa (100 g)', 128, 2.5, 28.1, 0.2, 1.6, 4, 0.1, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Aveia em flocos, crua', 'Cereais', '3 colheres de sopa (30 g)', 394, 13.9, 66.6, 8.5, 9.1, 48, 4.4, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Pão francês', 'Cereais', '1 unidade (50 g)', 300, 8.0, 58.6, 3.1, 2.3, 16, 1.0, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Feijão carioca, cozido', 'Leguminosas', '1 concha média (100 g)', 76, 4.8, 13.6, 0.5, 8.5, 27, 1.3, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Feijão preto, cozido', 'Leguminosas', '1 concha média (100 g)', 77, 4.5, 14.0, 0.5, 8.4, 29, 1.5, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Peito de frango, grelhado', 'Carnes e ovos', '1 filé médio (100 g)', 159, 32.0, 0, 2.5, 0, 5, 0.3, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Ovo de galinha, cozido', 'Carnes e ovos', '2 unidades (100 g)', 146, 13.3, 0.6, 9.5, 0, 49, 1.5, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Patinho bovino, grelhado', 'Carnes e ovos', '1 bife médio (100 g)', 219, 35.9, 0, 7.3, 0, 4, 3.0, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Leite de vaca integral', 'Leites e derivados', '1 copo (200 ml)', 61, 2.9, 4.3, 3.2, 0, 123, 0.1, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Iogurte natural integral', 'Leites e derivados', '1 pote (170 g)', 51, 4.1, 1.9, 3.0, 0, 143, 0.1, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Banana prata, crua', 'Frutas', '1 unidade média (40 g)', 98, 1.3, 26.0, 0.1, 2.0, 8, 0.4, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Maçã Fuji com casca, crua', 'Frutas', '1 unidade média (130 g)', 56, 0.3, 15.2, 0, 1.3, 2, 0.1, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Mamão Formosa, cru', 'Frutas', '1 fatia média (100 g)', 45, 0.8, 11.6, 0.1, 1.8, 25, 0.2, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Batata-doce, cozida', 'Raízes e tubérculos', '1 porção (100 g)', 77, 0.6, 18.4, 0.1, 2.2, 17, 0.2, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Mandioca, cozida', 'Raízes e tubérculos', '1 porção (100 g)', 125, 0.6, 30.1, 0.3, 1.6, 19, 0.1, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Brócolis, cozido', 'Hortaliças', '1 xícara (100 g)', 25, 2.1, 4.4, 0.5, 3.4, 51, 0.5, 'TACO 4ª ed. — NEPA/UNICAMP'),
    ('Cenoura, cozida', 'Hortaliças', '1 porção (100 g)', 30, 0.8, 6.7, 0.2, 2.6, 26, 0.1, 'TACO 4ª ed. — NEPA/UNICAMP');
