"""Acesso ao SQLite, criação do esquema e migrations versionadas."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        database = Path(current_app.config["DATABASE"])
        database.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(database)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    schema_path = Path(current_app.root_path).parent / "schema.sql"
    db = get_db()
    db.executescript(schema_path.read_text(encoding="utf-8"))
    _apply_migrations(db)
    db.commit()


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column(db: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    if name not in _columns(db, table):
        db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _migration_001_catalog(db: sqlite3.Connection) -> None:
    """Compatibilidade da v1.1.0 com bancos criados pelo LifeTrack/v1.0.0."""
    for column in (
        "target_calories REAL NOT NULL DEFAULT 0",
        "target_protein REAL NOT NULL DEFAULT 0",
        "target_carbs REAL NOT NULL DEFAULT 0",
        "target_fat REAL NOT NULL DEFAULT 0",
        "target_fiber REAL NOT NULL DEFAULT 0",
        "target_calcium REAL NOT NULL DEFAULT 0",
        "target_iron REAL NOT NULL DEFAULT 0",
    ):
        _add_column(db, "meal_plans", column)
    _add_column(db, "meal_items", "food_id INTEGER")
    _add_column(db, "meal_items", "amount_g REAL")
    db.execute("CREATE INDEX IF NOT EXISTS idx_meal_items_food ON meal_items(food_id)")


def _migration_002_secure_agenda(db: sqlite3.Connection) -> None:
    """Agenda segura, histórico e fundação de auditoria da v1.2.0."""
    for column in (
        "duration_minutes INTEGER NOT NULL DEFAULT 50",
        "reminder_minutes INTEGER NOT NULL DEFAULT 1440",
        "cancellation_reason TEXT",
        "updated_at TEXT",
    ):
        _add_column(db, "appointments", column)
    for column in (
        "failed_login_attempts INTEGER NOT NULL DEFAULT 0",
        "locked_until TEXT",
        "session_version INTEGER NOT NULL DEFAULT 1",
        "privacy_policy_version TEXT",
        "privacy_accepted_at TEXT",
        "email_verified_at TEXT",
    ):
        _add_column(db, "users", column)

    db.executescript(
        """
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

        CREATE INDEX IF NOT EXISTS idx_appointments_professional_start
            ON appointments(nutritionist_id, starts_at, status);
        CREATE INDEX IF NOT EXISTS idx_appointment_history_appointment
            ON appointment_history(appointment_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_availability_professional_weekday
            ON availability_slots(nutritionist_id, weekday, active);
        CREATE INDEX IF NOT EXISTS idx_schedule_blocks_professional_start
            ON schedule_blocks(nutritionist_id, starts_at);
        CREATE INDEX IF NOT EXISTS idx_audit_entity
            ON audit_log(entity_type, entity_id, created_at);
        """
    )


def _migration_003_secure_identity(db: sqlite3.Connection) -> None:
    """Tokens de identidade e compatibilidade para contas anteriores à v1.2.1."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS identity_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            purpose TEXT NOT NULL CHECK (purpose IN ('verify_email', 'reset_password')),
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_identity_tokens_lookup
            ON identity_tokens(token_hash, purpose, expires_at);
        CREATE INDEX IF NOT EXISTS idx_identity_tokens_user
            ON identity_tokens(user_id, purpose, used_at);
        """
    )
    db.execute(
        """UPDATE users SET email_verified_at = CURRENT_TIMESTAMP
           WHERE email_verified_at IS NULL"""
    )


def _migration_004_clinical_record(db: sqlite3.Connection) -> None:
    """Prontuário clínico imutável e rastreável da v1.3.0."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS anamnesis_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nutritionist_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            medical_history TEXT,
            family_history TEXT,
            dietary_history TEXT,
            activity_history TEXT,
            allergies TEXT,
            intolerances TEXT,
            preferences TEXT,
            restrictions TEXT,
            medications TEXT,
            supplements TEXT,
            symptoms TEXT,
            sleep_notes TEXT,
            water_intake_liters REAL,
            bowel_habits TEXT,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (nutritionist_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
            UNIQUE (nutritionist_id, patient_id, version)
        );

        CREATE TABLE IF NOT EXISTS anthropometric_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nutritionist_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            assessed_on TEXT NOT NULL,
            weight_kg REAL NOT NULL CHECK (weight_kg > 0),
            height_cm REAL NOT NULL CHECK (height_cm > 0),
            bmi REAL NOT NULL CHECK (bmi > 0),
            waist_cm REAL,
            abdomen_cm REAL,
            hip_cm REAL,
            arm_cm REAL,
            thigh_cm REAL,
            calf_cm REAL,
            body_fat_percent REAL,
            muscle_mass_kg REAL,
            visceral_fat REAL,
            waist_hip_ratio REAL,
            notes TEXT,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (nutritionist_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS clinical_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nutritionist_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            note_type TEXT NOT NULL CHECK (note_type IN ('evolution', 'goal', 'observation')),
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            author_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (nutritionist_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS clinical_consents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nutritionist_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            purpose TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('granted', 'revoked', 'pending')),
            recorded_by INTEGER NOT NULL,
            recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (nutritionist_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS clinical_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nutritionist_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            mime_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 5242880),
            uploaded_by INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (nutritionist_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_anamnesis_patient_version
            ON anamnesis_versions(nutritionist_id, patient_id, version DESC);
        CREATE INDEX IF NOT EXISTS idx_assessments_patient_date
            ON anthropometric_assessments(nutritionist_id, patient_id, assessed_on DESC);
        CREATE INDEX IF NOT EXISTS idx_clinical_notes_patient_date
            ON clinical_notes(nutritionist_id, patient_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_consents_patient_date
            ON clinical_consents(nutritionist_id, patient_id, recorded_at DESC);
        CREATE INDEX IF NOT EXISTS idx_attachments_patient_date
            ON clinical_attachments(nutritionist_id, patient_id, created_at DESC);
        """
    )


def _migration_005_nutrition_intelligence(db: sqlite3.Connection) -> None:
    """Receitas, alimentos próprios e nutrientes ampliados da v1.4.0."""
    for table in ("foods", "meal_items"):
        for column in (
            "sodium REAL NOT NULL DEFAULT 0",
            "saturated_fat REAL NOT NULL DEFAULT 0",
            "sugars REAL NOT NULL DEFAULT 0",
        ):
            _add_column(db, table, column)
    for prefix in ("", "target_"):
        for name in ("sodium", "saturated_fat", "sugars"):
            _add_column(db, "meal_plans", f"{prefix}{name} REAL NOT NULL DEFAULT 0")
    for column in (
        "nutritionist_id INTEGER REFERENCES users(id) ON DELETE CASCADE",
        "allergens TEXT",
        "recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL",
        "created_at TEXT",
    ):
        _add_column(db, "foods", column)
    _add_column(db, "meal_plans", "revision_of INTEGER REFERENCES meal_plans(id) ON DELETE SET NULL")
    _add_column(db, "meal_plans", "version_number INTEGER NOT NULL DEFAULT 1")

    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nutritionist_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Receitas',
            yield_g REAL NOT NULL CHECK (yield_g > 0),
            servings INTEGER NOT NULL CHECK (servings > 0),
            instructions TEXT,
            allergens TEXT,
            calories REAL NOT NULL DEFAULT 0,
            protein REAL NOT NULL DEFAULT 0,
            carbs REAL NOT NULL DEFAULT 0,
            fat REAL NOT NULL DEFAULT 0,
            fiber REAL NOT NULL DEFAULT 0,
            calcium REAL NOT NULL DEFAULT 0,
            iron REAL NOT NULL DEFAULT 0,
            sodium REAL NOT NULL DEFAULT 0,
            saturated_fat REAL NOT NULL DEFAULT 0,
            sugars REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (nutritionist_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE (nutritionist_id, name)
        );

        CREATE TABLE IF NOT EXISTS recipe_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL,
            food_id INTEGER NOT NULL,
            amount_g REAL NOT NULL CHECK (amount_g > 0),
            FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
            FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_foods_owner_active
            ON foods(nutritionist_id, active, category);
        CREATE INDEX IF NOT EXISTS idx_recipes_owner_name
            ON recipes(nutritionist_id, name);
        CREATE INDEX IF NOT EXISTS idx_recipe_items_recipe
            ON recipe_items(recipe_id);
        CREATE INDEX IF NOT EXISTS idx_meal_plans_revision
            ON meal_plans(revision_of, version_number);
        """
    )
    db.execute("UPDATE foods SET allergens = 'glúten' WHERE name = 'Pão francês'")
    db.execute("UPDATE foods SET allergens = 'leite, lactose' WHERE category = 'Leites e derivados'")
    db.execute("UPDATE foods SET allergens = 'ovo' WHERE name = 'Ovo de galinha, cozido'")


def _migration_006_patient_journey(db: sqlite3.Connection) -> None:
    """PWA, diário enriquecido, hábitos e check-ins da v1.5.0."""
    for column in (
        "mood INTEGER",
        "satiety INTEGER",
        "water_ml INTEGER NOT NULL DEFAULT 0",
        "symptoms TEXT",
        "photo_stored_name TEXT",
        "photo_mime TEXT",
        "photo_size_bytes INTEGER",
    ):
        _add_column(db, "food_diary", column)

    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS weekly_checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            week_start TEXT NOT NULL,
            energy INTEGER NOT NULL CHECK (energy BETWEEN 1 AND 5),
            sleep_quality INTEGER NOT NULL CHECK (sleep_quality BETWEEN 1 AND 5),
            confidence INTEGER NOT NULL CHECK (confidence BETWEEN 1 AND 5),
            wins TEXT,
            challenges TEXT,
            support_needed TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE (patient_id, week_start)
        );

        CREATE TABLE IF NOT EXISTS habit_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nutritionist_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            target_value REAL NOT NULL CHECK (target_value > 0),
            unit TEXT NOT NULL,
            frequency TEXT NOT NULL DEFAULT 'daily' CHECK (frequency IN ('daily', 'weekly')),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (nutritionist_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            value REAL NOT NULL CHECK (value >= 0),
            recorded_on TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (goal_id) REFERENCES habit_goals(id) ON DELETE CASCADE,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE (goal_id, recorded_on)
        );

        CREATE TABLE IF NOT EXISTS diary_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            diary_id INTEGER NOT NULL,
            nutritionist_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (diary_id) REFERENCES food_diary(id) ON DELETE CASCADE,
            FOREIGN KEY (nutritionist_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_checkins_patient_week
            ON weekly_checkins(patient_id, week_start DESC);
        CREATE INDEX IF NOT EXISTS idx_habit_goals_patient_active
            ON habit_goals(patient_id, active);
        CREATE INDEX IF NOT EXISTS idx_habit_logs_patient_date
            ON habit_logs(patient_id, recorded_on DESC);
        CREATE INDEX IF NOT EXISTS idx_diary_comments_entry
            ON diary_comments(diary_id, created_at);
        """
    )


MIGRATIONS = (
    (1, "v1.1.0_catalogo_inteligente", _migration_001_catalog),
    (2, "v1.2.0_agenda_segura", _migration_002_secure_agenda),
    (3, "v1.2.1_identidade_segura", _migration_003_secure_identity),
    (4, "v1.3.0_prontuario_clinico", _migration_004_clinical_record),
    (5, "v1.4.0_inteligencia_nutricional", _migration_005_nutrition_intelligence),
    (6, "v1.5.0_jornada_do_paciente", _migration_006_patient_journey),
)


def _apply_migrations(db: sqlite3.Connection) -> None:
    db.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version INTEGER PRIMARY KEY,
               name TEXT NOT NULL,
               applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    applied = {
        row["version"] for row in db.execute("SELECT version FROM schema_migrations")
    }
    for version, name, migration in MIGRATIONS:
        if version in applied:
            continue
        migration(db)
        db.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
            (version, name),
        )
