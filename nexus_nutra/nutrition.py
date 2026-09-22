"""Inteligência nutricional: alimentos próprios, receitas e cálculos verificáveis."""

from __future__ import annotations

import sqlite3

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .db import get_db
from .routes import NUTRIENT_FIELDS, role_required

bp = Blueprint("nutrition", __name__, url_prefix="/nutricao")


def _number(value: str | None, *, required: bool = False) -> float:
    raw = (value or "").strip().replace(",", ".")
    if not raw:
        if required:
            raise ValueError
        return 0.0
    number = float(raw)
    if number < 0 or (required and number == 0):
        raise ValueError
    return number


def _foods():
    return get_db().execute(
        """SELECT * FROM foods
           WHERE active = 1 AND (nutritionist_id IS NULL OR nutritionist_id = ?)
           ORDER BY category, name""",
        (g.user["id"],),
    ).fetchall()


def _audit(action: str, entity_type: str, entity_id: int, details: str) -> None:
    get_db().execute(
        """INSERT INTO audit_log (actor_id, action, entity_type, entity_id, details)
           VALUES (?, ?, ?, ?, ?)""",
        (g.user["id"], action, entity_type, entity_id, details[:1000]),
    )


@bp.route("", methods=["GET", "POST"])
@role_required("nutritionist")
def workspace():
    db = get_db()
    if request.method == "POST":
        kind = request.form.get("kind")
        if kind == "food":
            return _create_food()
        if kind == "recipe":
            return _create_recipe()
        flash("Operação nutricional inválida.", "error")
        return redirect(url_for("nutrition.workspace"))

    foods = _foods()
    recipes = db.execute(
        """SELECT r.*, f.id AS food_id FROM recipes r
           LEFT JOIN foods f ON f.recipe_id = r.id
           WHERE r.nutritionist_id = ? ORDER BY r.created_at DESC""",
        (g.user["id"],),
    ).fetchall()
    custom_foods = db.execute(
        """SELECT * FROM foods WHERE nutritionist_id = ? AND recipe_id IS NULL
           AND active = 1 ORDER BY created_at DESC, name""",
        (g.user["id"],),
    ).fetchall()
    return render_template(
        "nutrition_workspace.html",
        foods=foods,
        foods_payload=[dict(food) for food in foods],
        recipes=recipes,
        custom_foods=custom_foods,
    )


def _create_food():
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    measure = request.form.get("household_measure", "").strip()
    if len(name) < 2 or not category or not measure:
        flash("Informe nome, categoria e medida caseira do alimento.", "error")
        return redirect(url_for("nutrition.workspace") + "#alimento")
    try:
        nutrients = {field: _number(request.form.get(field)) for field in NUTRIENT_FIELDS}
    except ValueError:
        flash("Os nutrientes devem ser números iguais ou maiores que zero.", "error")
        return redirect(url_for("nutrition.workspace") + "#alimento")
    db = get_db()
    try:
        cursor = db.execute(
            """INSERT INTO foods
               (name, category, household_measure, calories, protein, carbs, fat,
                fiber, calcium, iron, sodium, saturated_fat, sugars, source,
                nutritionist_id, allergens, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (
                name, category, measure,
                *[nutrients[field] for field in NUTRIENT_FIELDS],
                "Cadastro profissional · Nexus Nutra", g.user["id"],
                request.form.get("allergens", "").strip(),
            ),
        )
    except sqlite3.IntegrityError:
        flash("Já existe um alimento ou receita com esse nome.", "error")
        return redirect(url_for("nutrition.workspace") + "#alimento")
    _audit("nutrition.food_created", "food", cursor.lastrowid, name)
    db.commit()
    flash("Alimento personalizado adicionado ao catálogo.", "success")
    return redirect(url_for("nutrition.workspace") + "#biblioteca")


def _create_recipe():
    name = request.form.get("recipe_name", "").strip()
    try:
        yield_g = _number(request.form.get("yield_g"), required=True)
        servings = int(_number(request.form.get("servings"), required=True))
    except (TypeError, ValueError):
        flash("Informe rendimento e número de porções válidos.", "error")
        return redirect(url_for("nutrition.workspace") + "#receita")
    food_ids = request.form.getlist("recipe_food_id[]")
    amounts = request.form.getlist("recipe_amount_g[]")
    items = []
    totals = {field: 0.0 for field in NUTRIENT_FIELDS}
    allergens = set()
    db = get_db()
    for index, raw_id in enumerate(food_ids):
        if not raw_id.isdigit():
            continue
        try:
            amount = _number(amounts[index] if index < len(amounts) else "", required=True)
        except ValueError:
            continue
        food = db.execute(
            """SELECT * FROM foods WHERE id = ? AND active = 1
               AND (nutritionist_id IS NULL OR nutritionist_id = ?)""",
            (int(raw_id), g.user["id"]),
        ).fetchone()
        if not food:
            continue
        for field in NUTRIENT_FIELDS:
            totals[field] += float(food[field] or 0) * amount / 100
        allergens.update(
            item.strip().lower() for item in (food["allergens"] or "").split(",") if item.strip()
        )
        items.append((food["id"], amount))
    if len(name) < 2 or not items:
        flash("Informe o nome e pelo menos um ingrediente válido.", "error")
        return redirect(url_for("nutrition.workspace") + "#receita")
    declared = {
        item.strip().lower()
        for item in request.form.get("recipe_allergens", "").split(",")
        if item.strip()
    }
    allergens.update(declared)
    allergens_text = ", ".join(sorted(allergens))
    try:
        cursor = db.execute(
            """INSERT INTO recipes
               (nutritionist_id, name, yield_g, servings, instructions, allergens,
                calories, protein, carbs, fat, fiber, calcium, iron, sodium,
                saturated_fat, sugars)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                g.user["id"], name, yield_g, servings,
                request.form.get("instructions", "").strip(), allergens_text,
                *[round(totals[field], 2) for field in NUTRIENT_FIELDS],
            ),
        )
        recipe_id = cursor.lastrowid
        db.executemany(
            "INSERT INTO recipe_items (recipe_id, food_id, amount_g) VALUES (?, ?, ?)",
            [(recipe_id, food_id, amount) for food_id, amount in items],
        )
        per_100g = {field: round(totals[field] / yield_g * 100, 2) for field in NUTRIENT_FIELDS}
        portion_g = yield_g / servings
        db.execute(
            """INSERT INTO foods
               (name, category, household_measure, calories, protein, carbs, fat,
                fiber, calcium, iron, sodium, saturated_fat, sugars, source,
                nutritionist_id, allergens, recipe_id, created_at)
               VALUES (?, 'Receitas', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (
                name, f"1 porção ({portion_g:g} g)",
                *[per_100g[field] for field in NUTRIENT_FIELDS],
                "Receita própria calculada · Nexus Nutra", g.user["id"],
                allergens_text, recipe_id,
            ),
        )
    except sqlite3.IntegrityError:
        db.rollback()
        flash("Já existe um alimento ou receita com esse nome.", "error")
        return redirect(url_for("nutrition.workspace") + "#receita")
    _audit("nutrition.recipe_created", "recipe", recipe_id, name)
    db.commit()
    flash("Receita calculada e disponibilizada no catálogo para prescrição.", "success")
    return redirect(url_for("nutrition.workspace") + "#biblioteca")
