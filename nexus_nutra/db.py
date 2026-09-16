"""Acesso ao SQLite e criação idempotente do esquema."""

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
    _migrate_existing_database(db)
    db.commit()


def _migrate_existing_database(db: sqlite3.Connection) -> None:
    """Adiciona campos da versão atual sem apagar dados de instalações anteriores."""
    plan_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(meal_plans)").fetchall()
    }
    for column in (
        "target_calories",
        "target_protein",
        "target_carbs",
        "target_fat",
        "target_fiber",
        "target_calcium",
        "target_iron",
    ):
        if column not in plan_columns:
            db.execute(
                f"ALTER TABLE meal_plans ADD COLUMN {column} REAL NOT NULL DEFAULT 0"
            )

    item_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(meal_items)").fetchall()
    }
    if "food_id" not in item_columns:
        db.execute("ALTER TABLE meal_items ADD COLUMN food_id INTEGER")
    if "amount_g" not in item_columns:
        db.execute("ALTER TABLE meal_items ADD COLUMN amount_g REAL")
    db.execute("CREATE INDEX IF NOT EXISTS idx_meal_items_food ON meal_items(food_id)")
