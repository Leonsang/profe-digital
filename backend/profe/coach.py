"""Herramientas de memoria y avance: perfil, recuerdos, dominio por habilidad y taller.

El id del estudiante viaja en el estado de la sesión ADK (`student_id`). Cada cambio se refleja
al instante en el panel «Mi avance» y, si desbloquea un hito, el resultado de la herramienta le
pide al profe que felicite en voz alta (las herramientas responden WHEN_IDLE: termina su frase y
luego celebra).
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from . import progress, store
from .board import send_to_browser


def _student(tool_context: ToolContext) -> str:
    return str(tool_context.state.get("student_id", ""))


def publish(session_id: str, student_id: str, won: list[dict[str, str]] | None = None) -> None:
    """Manda al navegador el avance actualizado y los hitos nuevos (para la celebración visual)."""
    send_to_browser(session_id, progress.snapshot(student_id))
    for milestone in won or []:
        send_to_browser(session_id, {"type": "milestone", **milestone})


def _result(won: list[dict[str, str]], **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "success", **extra}
    if won:
        out["celebrate"] = progress.celebration_note(won)
    return out


# ---------------------------------------------------------------- tools


def update_profile(tool_context: ToolContext, field: str, value: str) -> dict[str, Any]:
    """Guarda un dato del perfil del estudiante en cuanto lo menciona.

    Args:
        field: uno de "name" (cómo quiere que le digan), "grade" (curso o nivel), "goals" (qué quiere lograr,
            por ejemplo un examen), "preferences" (cómo aprende mejor: ejemplos, dibujos, ritmo, etc.).
        value: el dato en pocas palabras.
    """
    student_id = _student(tool_context)
    try:
        store.update_profile(student_id, field, value)
    except ValueError:
        return {"status": "error", "message": "field debe ser name, grade, goals o preferences"}
    won = progress.on_profile(student_id)
    publish(tool_context.session.id, student_id, won)
    return _result(won)


def remember(tool_context: ToolContext, fact: str, category: str = "aprendizaje") -> dict[str, Any]:
    """Guarda algo que vale la pena recordar en las próximas clases: una dificultad, un error típico,
    un interés, una emoción ("se frustra con las fracciones"), algo que lo motivó.

    Args:
        fact: el recuerdo en una frase corta y concreta.
        category: "dificultad", "fortaleza", "interés", "emoción" o "aprendizaje".
    """
    student_id = _student(tool_context)
    store.remember(student_id, category, fact)
    publish(tool_context.session.id, student_id)
    return {"status": "success"}


def record_progress(
    tool_context: ToolContext, skill: str, topic: str, correct: bool, evidence: str = ""
) -> dict[str, Any]:
    """Registra evidencia de dominio cuando el estudiante resuelve (o falla) algo por voz o en la pizarra.
    No lo uses para las preguntas del panel: esas se registran solas.

    Args:
        skill: habilidad concreta, corta y estable (ej. "factorizar trinomios").
        topic: tema general (ej. "álgebra").
        correct: True si lo resolvió bien por sí mismo; False si se equivocó o necesitó la respuesta.
        evidence: qué hizo, en una frase.
    """
    student_id = _student(tool_context)
    change, won = progress.on_attempt(student_id, skill, topic, correct)
    if evidence:
        store.remember(student_id, "fortaleza" if correct else "dificultad", f"{change['skill']}: {evidence}")
    publish(tool_context.session.id, student_id, won)
    return _result(won, mastery=change["after"])


def update_workshop(tool_context: ToolContext, exercise_index: int, status: str, note: str = "") -> dict[str, Any]:
    """Actualiza el estado de un ejercicio del taller activo.

    Args:
        exercise_index: índice del ejercicio (empieza en 0).
        status: "in_progress" al empezarlo, "done" cuando el estudiante lo resolvió, "skipped" si lo dejan para después.
        note: observación corta sobre cómo le fue.
    """
    student_id = _student(tool_context)
    workshop = store.active_workshop(student_id)
    if not workshop:
        return {"status": "error", "message": "no hay taller activo"}
    exercises = workshop["plan"].get("exercises", [])
    if not 0 <= exercise_index < len(exercises):
        return {"status": "error", "message": f"índice entre 0 y {len(exercises) - 1}"}
    if status not in {"in_progress", "done", "skipped"}:
        return {"status": "error", "message": "status inválido"}
    exercise = exercises[exercise_index]
    was_done = exercise.get("status") == "done"
    exercise["status"] = status
    if note:
        exercise["note"] = note
    all_done = all(e.get("status") == "done" for e in exercises)
    store.update_workshop_plan(workshop["id"], workshop["plan"], "done" if all_done else "active")
    won: list[dict[str, str]] = []
    if status == "done" and not was_done:
        _, won = progress.on_attempt(student_id, exercise.get("skill") or workshop["topic"], workshop["topic"], True)
        won += progress.on_workshop(student_id, workshop)
    publish(tool_context.session.id, student_id, won)
    pending = [i for i, e in enumerate(exercises) if e.get("status") != "done"]
    return _result(won, pending=pending)


def _scheduled(func: Any, scheduling: types.FunctionResponseScheduling) -> FunctionTool:
    tool = FunctionTool(func)
    tool.behavior = types.Behavior.NON_BLOCKING
    tool.response_scheduling = scheduling
    return tool


def coach_tools() -> list[FunctionTool]:
    return [
        # Guardar recuerdos no debe hacer que el profe hable de nuevo.
        _scheduled(remember, types.FunctionResponseScheduling.SILENT),
        # Estos pueden desbloquear hitos: el profe termina la frase y felicita.
        _scheduled(update_profile, types.FunctionResponseScheduling.WHEN_IDLE),
        _scheduled(record_progress, types.FunctionResponseScheduling.WHEN_IDLE),
        _scheduled(update_workshop, types.FunctionResponseScheduling.WHEN_IDLE),
    ]
