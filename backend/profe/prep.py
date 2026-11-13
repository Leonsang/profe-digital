"""Trabajo de fondo con un modelo de texto: preparar talleres y resumir cada clase.

Usa `TEXT_MODEL` (por defecto gemini-3.5-flash-lite: 500 solicitudes/día en el nivel gratuito).
"""

from __future__ import annotations

import logging
import os
from typing import List, Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

log = logging.getLogger("profe.prep")
TEXT_MODEL = os.getenv("TEXT_MODEL", "gemini-3.5-flash-lite")

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


# ---------------------------------------------------------------- taller


class Exercise(BaseModel):
    statement: str = Field(description="Enunciado del ejercicio, completo y fiel al original (fórmulas en texto o LaTeX).")
    skill: str = Field(description="Habilidad concreta que practica, corta (ej. 'fórmula general').")
    difficulty: Literal["fácil", "media", "difícil"]
    hint: str = Field(description="Primera pista socrática: una pregunta que oriente sin resolver.")
    answer: str = Field(description="Respuesta final correcta, breve. Solo la verá el profe.")
    status: Literal["pending"] = "pending"


class WorkshopPlan(BaseModel):
    title: str = Field(description="Título corto del taller.")
    topic: str = Field(description="Tema principal (ej. 'ecuaciones cuadráticas').")
    summary: str = Field(description="Qué pide el taller, en una o dos frases para el estudiante.")
    prerequisites: List[str] = Field(description="Conceptos previos que conviene repasar (máx. 5).")
    teaching_plan: str = Field(
        description="Cómo enseñarlo en 3-5 pasos: calentamiento, ejemplo resuelto distinto a los ejercicios, "
        "luego guiar cada ejercicio con preguntas y sin dar la respuesta."
    )
    exercises: List[Exercise]


PREP_PROMPT = """Eres un profesor de matemáticas y física preparando la clase de un estudiante.
El estudiante te entrega su taller (tarea) en el archivo adjunto o el texto. Extrae TODOS los ejercicios en orden,
sin inventar ninguno, resuélvelos para tener la respuesta correcta y prepara un plan para enseñarlo.
Perfil del estudiante (para ajustar el nivel): {profile}
Responde en español."""


async def prepare_workshop(data: bytes, mime_type: str, profile: str) -> WorkshopPlan:
    parts: list[types.Part] = [types.Part(text=PREP_PROMPT.format(profile=profile or "sin datos"))]
    if mime_type.startswith("text/"):
        parts.append(types.Part(text=data.decode("utf-8", errors="replace")))
    else:
        parts.append(types.Part(inline_data=types.Blob(data=data, mime_type=mime_type)))
    res = await client().aio.models.generate_content(
        model=TEXT_MODEL,
        contents=[types.Content(role="user", parts=parts)],
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=WorkshopPlan),
    )
    if isinstance(res.parsed, WorkshopPlan):
        return res.parsed
    return WorkshopPlan.model_validate_json(res.text or "{}")


# ---------------------------------------------------------------- resumen de clase


class Fact(BaseModel):
    category: Literal["dificultad", "fortaleza", "interés", "emoción", "aprendizaje"]
    fact: str


class SessionSummary(BaseModel):
    summary: str = Field(description="Qué se trabajó y cómo le fue, en 1-2 frases, para retomarlo la próxima clase.")
    facts: List[Fact] = Field(description="Hasta 4 cosas nuevas y útiles de recordar sobre el estudiante.")
    next_step: str = Field(description="Qué conviene hacer en la próxima clase, en una frase.")


SUMMARY_PROMPT = """Resume esta clase entre un profesor digital y un estudiante para la memoria del profesor.
Sé concreto (temas, errores, logros, estado de ánimo). No inventes nada que no esté en la transcripción.

Transcripción:
{transcript}"""


async def summarize_session(transcript: str) -> SessionSummary | None:
    if len(transcript) < 200:
        return None
    try:
        res = await client().aio.models.generate_content(
            model=TEXT_MODEL,
            contents=SUMMARY_PROMPT.format(transcript=transcript[-20000:]),
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=SessionSummary),
        )
        if isinstance(res.parsed, SessionSummary):
            return res.parsed
        return SessionSummary.model_validate_json(res.text or "{}")
    except Exception as exc:
        log.warning("resumen de clase: %s", exc)
        return None
