"""Avance del estudiante: reglas de hitos, contexto para el profe y resumen para el panel."""

from __future__ import annotations

from typing import Any

from . import store

MASTERED = 80


def _new(student_id: str, key: str, title: str, detail: str = "") -> list[dict[str, str]]:
    return [{"key": key, "title": title, "detail": detail}] if store.award(student_id, key, title, detail) else []


# ---------------------------------------------------------------- reglas


def on_session_start(student_id: str, streak: int, sessions: int) -> list[dict[str, str]]:
    won = _new(student_id, "first_session", "Primera clase", "Empezaste tu camino con el profe.")
    if sessions >= 5:
        won += _new(student_id, "sessions_5", "5 clases", "Ya llevas cinco clases. La constancia se nota.")
    if sessions >= 20:
        won += _new(student_id, "sessions_20", "20 clases", "Veinte clases: esto ya es un hábito.")
    for days in (3, 7, 30):
        if streak >= days:
            won += _new(student_id, f"streak_{days}", f"Racha de {days} días", f"{days} días seguidos estudiando.")
    return won


def on_attempt(student_id: str, skill: str, topic: str, correct: bool) -> tuple[dict[str, Any], list[dict[str, str]]]:
    change = store.record_attempt(student_id, skill, topic, correct)
    run = store.bump_streak(student_id, correct)
    won: list[dict[str, str]] = []
    if correct:
        won += _new(student_id, "first_correct", "Primer acierto", "Tu primera respuesta correcta.")
    for n in (3, 5, 10):
        if run == n:
            won += _new(student_id, f"answers_{n}", f"{n} aciertos seguidos", f"{n} respuestas correctas sin fallar.")
    if change["before"] < MASTERED <= change["after"]:
        won += _new(
            student_id,
            f"mastered:{change['skill']}",
            f"Dominaste: {change['skill']}",
            f"Llegaste a {change['after']}% en {change['skill']}.",
        )
        mastered = sum(1 for s in store.skills(student_id) if s["mastery"] >= MASTERED)
        for n in (3, 10):
            if mastered >= n:
                won += _new(student_id, f"mastered_{n}", f"{n} habilidades dominadas", "Tu mapa de habilidades crece.")
    return change, won


def on_quest_done(student_id: str, title: str) -> list[dict[str, str]]:
    return _new(student_id, f"quest:{title.lower()}", f"Reto superado: {title}", "Completaste todos los pasos.")


def on_profile(student_id: str) -> list[dict[str, str]]:
    s = store.get_student(student_id)
    if s.get("name") and s.get("grade") and s.get("goals"):
        return _new(student_id, "profile", "Perfil listo", "El profe ya sabe quién eres y qué quieres lograr.")
    return []


def on_workshop(student_id: str, workshop: dict[str, Any]) -> list[dict[str, str]]:
    exercises = workshop["plan"].get("exercises", [])
    done = sum(1 for e in exercises if e.get("status") == "done")
    wid = workshop["id"]
    won: list[dict[str, str]] = []
    if done >= 1:
        won += _new(student_id, f"workshop_first:{wid}", "Primer ejercicio del taller", workshop["title"])
    if exercises and done * 2 >= len(exercises):
        won += _new(student_id, f"workshop_half:{wid}", "Mitad del taller", f"{done} de {len(exercises)} ejercicios.")
    if exercises and done == len(exercises):
        won += _new(student_id, f"workshop_done:{wid}", "¡Taller completo!", workshop["title"])
    return won


def celebration_note(won: list[dict[str, str]]) -> str:
    """Instrucción para que el profe felicite en voz alta, con calidez y sin exagerar."""
    items = "; ".join(f"{m['title']} ({m['detail']})" if m["detail"] else m["title"] for m in won)
    return (
        f"[Sistema] El estudiante acaba de lograr: {items}. Felicítalo en voz alta con una frase cálida y concreta "
        "que mencione el logro, y sigue con la clase."
    )


# ---------------------------------------------------------------- contexto y panel


def context_for_profe(student_id: str) -> str:
    s = store.get_student(student_id)
    lines = ["[Contexto privado del estudiante — no lo leas en voz alta, úsalo para personalizar la clase]"]
    if s.get("name"):
        lines.append(f"Nombre: {s['name']}. Curso/nivel: {s.get('grade') or 'sin dato'}.")
        lines.append(f"Metas: {s.get('goals') or 'sin dato'}. Cómo aprende mejor: {s.get('preferences') or 'sin dato'}.")
    else:
        lines.append(
            "Estudiante nuevo, sin perfil. Preséntate y, conversando con naturalidad (no como formulario), averigua "
            "su nombre, curso o nivel, qué quiere lograr y cómo le gusta aprender. Guarda cada dato con update_profile."
        )
    lines.append(f"Clases tomadas: {s.get('sessions', 0)}. Racha: {s.get('streak', 0)} días.")
    skills = store.skills(student_id)
    if skills:
        strong = [f"{k['skill']} ({k['mastery']}%)" for k in skills if k["mastery"] >= MASTERED][:6]
        weak = [f"{k['skill']} ({k['mastery']}%)" for k in skills if k["mastery"] < 50][:6]
        if strong:
            lines.append("Domina: " + ", ".join(strong) + ".")
        if weak:
            lines.append("Le cuesta: " + ", ".join(weak) + ".")
    mems = store.memories(student_id, 15)
    if mems:
        lines.append("Lo que recuerdas de clases anteriores:")
        lines += [f"- ({m['category']}) {m['fact']}" for m in mems]
    workshop = store.active_workshop(student_id)
    if workshop and workshop["status"] == "active":
        lines.append(workshop_brief(workshop))
    lines.append(
        "Saluda por su nombre si lo sabes, retoma algo concreto de la última clase y pregunta qué quiere hacer hoy."
    )
    return "\n".join(lines)


def workshop_brief(workshop: dict[str, Any]) -> str:
    plan = workshop["plan"]
    out = [
        f"TALLER ACTIVO: «{workshop['title']}» (tema: {workshop['topic']}). Guíalo ejercicio por ejercicio SIN dar la respuesta:",
        f"Plan de enseñanza: {plan.get('teaching_plan', '')}",
    ]
    if plan.get("prerequisites"):
        out.append("Prerrequisitos a repasar si hace falta: " + ", ".join(plan["prerequisites"]) + ".")
    for i, ex in enumerate(plan.get("exercises", [])):
        out.append(
            f"  [{i}] ({ex.get('status', 'pending')}) {ex.get('statement', '')} | habilidad: {ex.get('skill', '')} "
            f"| pista: {ex.get('hint', '')} | respuesta esperada (secreta): {ex.get('answer', '')}"
        )
    out.append("Marca el estado de cada ejercicio con update_workshop.")
    return "\n".join(out)


def snapshot(student_id: str) -> dict[str, Any]:
    s = store.get_student(student_id)
    workshop = store.active_workshop(student_id)
    if workshop:
        for ex in workshop["plan"].get("exercises", []):
            ex.pop("answer", None)  # la respuesta nunca llega al navegador
    return {
        "type": "progress",
        "profile": {k: s.get(k, "") for k in ("name", "grade", "goals", "preferences")},
        "streak": s.get("streak", 0),
        "sessions": s.get("sessions", 0),
        "skills": store.skills(student_id),
        "milestones": store.milestones(student_id),
        "memories": store.memories(student_id, 8),
        "workshop": workshop,
    }
