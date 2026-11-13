"""Mismo contrato que store.py, sobre Firestore (para Cloud Run, donde el disco no persiste).

Se activa con PROFE_STORE=firestore. Estructura:
  students/{id}                       perfil, racha, clases, active_workshop
  students/{id}/memories/{auto}       category, fact, fact_lower, created_at
  students/{id}/skills/{slug}         skill, topic, mastery, attempts, correct, updated_at
  students/{id}/milestones/{slug}     key, title, detail, created_at   (create(): se otorga una sola vez)
  students/{id}/workshops/{auto}      title, topic, plan, status, created_at
"""

from __future__ import annotations

import re
import time
from datetime import date, timedelta
from typing import Any

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

PROFILE_FIELDS = {"name", "grade", "goals", "preferences"}
_db: firestore.Client | None = None


def _client() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def _slug(text: str) -> str:
    return re.sub(r"[/\s]+", "_", text.strip().lower())[:200] or "_"


def _student_ref(student_id: str) -> firestore.DocumentReference:
    return _client().collection("students").document(student_id)


def init() -> None:
    _client()


# ---------------------------------------------------------------- estudiantes

_DEFAULTS = {"name": "", "grade": "", "goals": "", "preferences": "", "last_seen": "", "streak": 0, "sessions": 0}


def ensure_student(student_id: str) -> dict[str, Any]:
    ref = _student_ref(student_id)
    try:
        ref.create({**_DEFAULTS, "created_at": time.time()})
    except AlreadyExists:
        pass
    return get_student(student_id)


def get_student(student_id: str) -> dict[str, Any]:
    snap = _student_ref(student_id).get()
    if not snap.exists:
        return {}
    return {"id": student_id, **_DEFAULTS, **(snap.to_dict() or {})}


def update_profile(student_id: str, field: str, value: str) -> None:
    if field not in PROFILE_FIELDS:
        raise ValueError(field)
    _student_ref(student_id).set({field: value.strip()}, merge=True)


def touch_session(student_id: str) -> dict[str, int]:
    student = ensure_student(student_id)
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    streak = student.get("streak") or 0
    if student.get("last_seen") == today:
        pass
    elif student.get("last_seen") == yesterday:
        streak += 1
    else:
        streak = 1
    sessions = (student.get("sessions") or 0) + 1
    _student_ref(student_id).set({"last_seen": today, "streak": streak, "sessions": sessions}, merge=True)
    return {"streak": streak, "sessions": sessions}


# ---------------------------------------------------------------- memoria


def remember(student_id: str, category: str, fact: str) -> None:
    fact = fact.strip()
    if not fact:
        return
    col = _student_ref(student_id).collection("memories")
    if list(col.where("fact_lower", "==", fact.lower()).limit(1).stream()):
        return
    col.add({"category": category, "fact": fact, "fact_lower": fact.lower(), "created_at": time.time()})


def memories(student_id: str, limit: int = 30) -> list[dict[str, Any]]:
    col = _student_ref(student_id).collection("memories")
    docs = col.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit).stream()
    return [{k: d.get(k) for k in ("category", "fact", "created_at")} for d in docs]


# ---------------------------------------------------------------- dominio


def record_attempt(student_id: str, skill: str, topic: str, correct: bool, weight: int = 1) -> dict[str, Any]:
    skill = skill.strip().lower()
    ref = _student_ref(student_id).collection("skills").document(_slug(skill))

    @firestore.transactional
    def apply(tx: firestore.Transaction) -> dict[str, Any]:
        snap = ref.get(transaction=tx)
        row = snap.to_dict() if snap.exists else {}
        before = row.get("mastery", 0)
        after = max(0, min(100, before + (15 * weight if correct else -5)))
        tx.set(
            ref,
            {
                "skill": skill,
                "topic": topic.strip() or row.get("topic", ""),
                "mastery": after,
                "attempts": row.get("attempts", 0) + 1,
                "correct": row.get("correct", 0) + int(correct),
                "updated_at": time.time(),
            },
        )
        return {"skill": skill, "before": before, "after": after}

    return apply(_client().transaction())


def skills(student_id: str) -> list[dict[str, Any]]:
    col = _student_ref(student_id).collection("skills")
    docs = col.order_by("updated_at", direction=firestore.Query.DESCENDING).stream()
    return [{k: d.get(k) for k in ("skill", "topic", "mastery", "attempts", "correct")} for d in docs]


_STREAKS: dict[str, int] = {}


def correct_streak(student_id: str) -> int:
    return _STREAKS.get(student_id, 0)


def bump_streak(student_id: str, correct: bool) -> int:
    _STREAKS[student_id] = _STREAKS.get(student_id, 0) + 1 if correct else 0
    return _STREAKS[student_id]


# ---------------------------------------------------------------- hitos


def award(student_id: str, key: str, title: str, detail: str = "") -> bool:
    ref = _student_ref(student_id).collection("milestones").document(_slug(key))
    try:
        ref.create({"key": key, "title": title, "detail": detail, "created_at": time.time()})
        return True
    except AlreadyExists:
        return False


def milestones(student_id: str) -> list[dict[str, Any]]:
    col = _student_ref(student_id).collection("milestones")
    docs = col.order_by("created_at", direction=firestore.Query.DESCENDING).stream()
    return [{k: d.get(k) for k in ("key", "title", "detail", "created_at")} for d in docs]


# ---------------------------------------------------------------- talleres


def save_workshop(student_id: str, title: str, topic: str, plan: dict[str, Any]) -> str:
    student = _student_ref(student_id)
    previous = (student.get().to_dict() or {}).get("active_workshop")
    if previous:
        student.collection("workshops").document(previous).set({"status": "archived"}, merge=True)
    _, ref = student.collection("workshops").add(
        {"title": title, "topic": topic, "plan": plan, "status": "active", "created_at": time.time()}
    )
    student.set({"active_workshop": ref.id}, merge=True)
    return ref.id


def active_workshop(student_id: str) -> dict[str, Any] | None:
    student = _student_ref(student_id)
    wid = (student.get().to_dict() or {}).get("active_workshop")
    if not wid:
        return None
    snap = student.collection("workshops").document(wid).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    if data.get("status") not in ("active", "done"):
        return None
    return {"id": wid, **data}


def update_workshop_plan(student_id: str, workshop_id: str, plan: dict[str, Any], status: str | None = None) -> None:
    ref = _student_ref(student_id).collection("workshops").document(str(workshop_id))
    ref.set({"plan": plan, **({"status": status} if status else {})}, merge=True)
