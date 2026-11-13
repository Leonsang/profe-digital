"""Memoria persistente del estudiante: perfil, recuerdos, dominio por habilidad, hitos y talleres.

SQLite en un archivo (`PROFE_DB`, por defecto backend/profe.db). Las consultas son pequeñas y
síncronas; se llaman desde el loop de asyncio sin problema a esta escala.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("PROFE_DB", Path(__file__).resolve().parent.parent / "profe.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
  id TEXT PRIMARY KEY,
  name TEXT DEFAULT '',
  grade TEXT DEFAULT '',
  goals TEXT DEFAULT '',
  preferences TEXT DEFAULT '',
  created_at REAL,
  last_seen TEXT DEFAULT '',
  streak INTEGER DEFAULT 0,
  sessions INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id TEXT, category TEXT, fact TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS skills (
  student_id TEXT, skill TEXT, topic TEXT, mastery INTEGER DEFAULT 0,
  attempts INTEGER DEFAULT 0, correct INTEGER DEFAULT 0, updated_at REAL,
  PRIMARY KEY (student_id, skill)
);
CREATE TABLE IF NOT EXISTS milestones (
  student_id TEXT, key TEXT, title TEXT, detail TEXT, created_at REAL,
  PRIMARY KEY (student_id, key)
);
CREATE TABLE IF NOT EXISTS workshops (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id TEXT, title TEXT, topic TEXT, plan TEXT, status TEXT DEFAULT 'active', created_at REAL
);
"""

PROFILE_FIELDS = {"name", "grade", "goals", "preferences"}


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _db() as conn:
        conn.executescript(SCHEMA)


# ---------------------------------------------------------------- estudiantes


def ensure_student(student_id: str) -> dict[str, Any]:
    with _db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO students (id, created_at) VALUES (?, ?)", (student_id, time.time())
        )
    return get_student(student_id)


def get_student(student_id: str) -> dict[str, Any]:
    with _db() as conn:
        row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    return dict(row) if row else {}


def update_profile(student_id: str, field: str, value: str) -> None:
    if field not in PROFILE_FIELDS:
        raise ValueError(field)
    with _db() as conn:
        conn.execute(f"UPDATE students SET {field} = ? WHERE id = ?", (value.strip(), student_id))


def touch_session(student_id: str) -> dict[str, int]:
    """Registra una sesión nueva y actualiza la racha de días seguidos."""
    student = ensure_student(student_id)
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    streak = student["streak"] or 0
    if student["last_seen"] == today:
        pass
    elif student["last_seen"] == yesterday:
        streak += 1
    else:
        streak = 1
    with _db() as conn:
        conn.execute(
            "UPDATE students SET last_seen = ?, streak = ?, sessions = sessions + 1 WHERE id = ?",
            (today, streak, student_id),
        )
    return {"streak": streak, "sessions": (student["sessions"] or 0) + 1}


# ---------------------------------------------------------------- memoria


def remember(student_id: str, category: str, fact: str) -> None:
    fact = fact.strip()
    if not fact:
        return
    with _db() as conn:
        dup = conn.execute(
            "SELECT 1 FROM memories WHERE student_id = ? AND lower(fact) = lower(?)", (student_id, fact)
        ).fetchone()
        if not dup:
            conn.execute(
                "INSERT INTO memories (student_id, category, fact, created_at) VALUES (?, ?, ?, ?)",
                (student_id, category, fact, time.time()),
            )


def memories(student_id: str, limit: int = 30) -> list[dict[str, Any]]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT category, fact, created_at FROM memories WHERE student_id = ? ORDER BY created_at DESC LIMIT ?",
            (student_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- dominio


def record_attempt(student_id: str, skill: str, topic: str, correct: bool, weight: int = 1) -> dict[str, Any]:
    """Actualiza el dominio de una habilidad. Acierto: +15·peso; fallo: −5 (nunca baja de 0)."""
    skill = skill.strip().lower()
    with _db() as conn:
        row = conn.execute(
            "SELECT mastery, attempts, correct FROM skills WHERE student_id = ? AND skill = ?", (student_id, skill)
        ).fetchone()
        before = row["mastery"] if row else 0
        after = max(0, min(100, before + (15 * weight if correct else -5)))
        conn.execute(
            """INSERT INTO skills (student_id, skill, topic, mastery, attempts, correct, updated_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)
               ON CONFLICT(student_id, skill) DO UPDATE SET
                 mastery = excluded.mastery, attempts = attempts + 1,
                 correct = correct + excluded.correct, topic = COALESCE(NULLIF(excluded.topic, ''), topic),
                 updated_at = excluded.updated_at""",
            (student_id, skill, topic.strip(), after, int(correct), time.time()),
        )
    return {"skill": skill, "before": before, "after": after}


def skills(student_id: str) -> list[dict[str, Any]]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT skill, topic, mastery, attempts, correct FROM skills WHERE student_id = ? ORDER BY updated_at DESC",
            (student_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def correct_streak(student_id: str) -> int:
    """Aciertos seguidos en la sesión, guardado en memoria del proceso por simplicidad."""
    return _STREAKS.get(student_id, 0)


_STREAKS: dict[str, int] = {}


def bump_streak(student_id: str, correct: bool) -> int:
    _STREAKS[student_id] = _STREAKS.get(student_id, 0) + 1 if correct else 0
    return _STREAKS[student_id]


# ---------------------------------------------------------------- hitos


def award(student_id: str, key: str, title: str, detail: str = "") -> bool:
    """Guarda un hito. Devuelve False si ya lo tenía (cada hito se celebra una sola vez)."""
    with _db() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO milestones (student_id, key, title, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (student_id, key, title, detail, time.time()),
        )
    return cur.rowcount == 1


def milestones(student_id: str) -> list[dict[str, Any]]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT key, title, detail, created_at FROM milestones WHERE student_id = ? ORDER BY created_at DESC",
            (student_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- talleres


def save_workshop(student_id: str, title: str, topic: str, plan: dict[str, Any]) -> int:
    with _db() as conn:
        conn.execute("UPDATE workshops SET status = 'archived' WHERE student_id = ? AND status = 'active'", (student_id,))
        cur = conn.execute(
            "INSERT INTO workshops (student_id, title, topic, plan, created_at) VALUES (?, ?, ?, ?, ?)",
            (student_id, title, topic, json.dumps(plan, ensure_ascii=False), time.time()),
        )
    return int(cur.lastrowid)


def active_workshop(student_id: str) -> dict[str, Any] | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM workshops WHERE student_id = ? AND status IN ('active', 'done') ORDER BY created_at DESC LIMIT 1",
            (student_id,),
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["plan"] = json.loads(data["plan"])
    return data


def update_workshop_plan(workshop_id: int, plan: dict[str, Any], status: str | None = None) -> None:
    with _db() as conn:
        if status:
            conn.execute(
                "UPDATE workshops SET plan = ?, status = ? WHERE id = ?",
                (json.dumps(plan, ensure_ascii=False), status, workshop_id),
            )
        else:
            conn.execute("UPDATE workshops SET plan = ? WHERE id = ?", (json.dumps(plan, ensure_ascii=False), workshop_id))
