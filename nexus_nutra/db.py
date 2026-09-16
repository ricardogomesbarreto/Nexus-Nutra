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


MIGRATIONS = (
    (1, "v1.1.0_catalogo_inteligente", _migration_001_catalog),
    (2, "v1.2.0_agenda_segura", _migration_002_secure_agenda),
    (3, "v1.2.1_identidade_segura", _migration_003_secure_identity),
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
