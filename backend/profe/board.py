"""Herramientas de pizarra del profe.

Cada herramienta solo publica un evento en la cola de la sesión (el WebSocket lo
reenvía al frontend, que lo dibuja en tldraw) y devuelve al instante. Se marcan
NON_BLOCKING + WHEN_IDLE: el modelo sigue hablando mientras aparece el trazo y
retoma la explicación cuando termina la frase en curso.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import os
from typing import Any, Callable, List

import httpx
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

log = logging.getLogger("profe.board")

# session_id -> cola de eventos hacia el navegador
_QUEUES: dict[str, asyncio.Queue[dict[str, Any]]] = {}
_ids = itertools.count(1)


def open_board(session_id: str) -> asyncio.Queue[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    _QUEUES[session_id] = queue
    return queue


def close_board(session_id: str) -> None:
    _QUEUES.pop(session_id, None)


def _emit(tool_context: ToolContext, kind: str, **payload: Any) -> dict[str, str]:
    queue = _QUEUES.get(tool_context.session.id)
    if queue is None:
        return {"status": "error", "message": "pizarra desconectada"}
    element_id = f"el{next(_ids)}"
    queue.put_nowait({"type": "board", "kind": kind, "id": element_id, **payload})
    return {"status": "success", "id": element_id}


# --------------------------------------------------------------------------- tools


def write_text(tool_context: ToolContext, text: str) -> dict[str, str]:
    """Escribe una nota corta en la pizarra (título, paso, idea clave).

    Args:
        text: texto breve, máximo dos líneas.
    """
    return _emit(tool_context, "text", text=text)


def write_formula(tool_context: ToolContext, latex: str, caption: str = "") -> dict[str, str]:
    """Escribe una fórmula matemática en la pizarra con LaTeX.

    Args:
        latex: la fórmula en LaTeX, sin signos $ (ej. "x = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}").
        caption: explicación corta opcional debajo de la fórmula.
    """
    return _emit(tool_context, "formula", latex=latex, caption=caption)


def plot_functions(
    tool_context: ToolContext,
    expressions: List[str],
    x_min: float = -10,
    x_max: float = 10,
    title: str = "",
) -> dict[str, str]:
    """Grafica una o varias funciones de x en un plano cartesiano.

    Args:
        expressions: funciones en sintaxis math.js, una por elemento (ej. ["x^2 - 4", "sin(x)", "2*x + 1"]).
        x_min: inicio del eje x.
        x_max: fin del eje x.
        title: título opcional de la gráfica.
    """
    return _emit(tool_context, "plot", expressions=expressions, x_min=x_min, x_max=x_max, title=title)


def draw_diagram(tool_context: ToolContext, svg: str, caption: str = "") -> dict[str, str]:
    """Dibuja un diagrama propio en SVG: vectores de fuerza, triángulos, circuitos, esquemas.

    Args:
        svg: un elemento <svg> completo con viewBox, trazos claros y etiquetas de texto grandes. Sin scripts.
        caption: explicación corta opcional debajo del diagrama.
    """
    return _emit(tool_context, "svg", svg=svg, caption=caption)


def run_simulation(
    tool_context: ToolContext,
    kind: str,
    param_a: float = 0,
    param_b: float = 0,
    caption: str = "",
) -> dict[str, str]:
    """Lanza una simulación física interactiva en la pizarra.

    Args:
        kind: una de "projectile" (a=velocidad m/s, b=ángulo grados), "pendulum" (a=longitud m, b=ángulo inicial grados),
            "spring" (a=constante k N/m, b=masa kg), "incline" (a=ángulo grados, b=coeficiente de fricción),
            "collision" (a=masa 1 kg, b=masa 2 kg).
        param_a: primer parámetro según el tipo.
        param_b: segundo parámetro según el tipo.
        caption: qué debe observar el estudiante.
    """
    allowed = {"projectile", "pendulum", "spring", "incline", "collision"}
    if kind not in allowed:
        return {"status": "error", "message": f"kind debe ser uno de {sorted(allowed)}"}
    return _emit(tool_context, "sim", sim=kind, a=param_a, b=param_b, caption=caption)


async def show_image(tool_context: ToolContext, query: str, caption: str = "") -> dict[str, str]:
    """Busca una imagen real en Wikimedia Commons y la pone en la pizarra (científicos, fenómenos, objetos).

    Args:
        query: búsqueda en inglés, concreta (ej. "Isaac Newton portrait", "double slit interference pattern").
        caption: texto corto debajo de la imagen.
    """
    url = await _wikimedia_image(query)
    if not url:
        return {"status": "error", "message": f"sin imagen para '{query}', dibújalo con draw_diagram"}
    return _emit(tool_context, "image", url=url, caption=caption or query, source="Wikimedia Commons")


async def generate_illustration(tool_context: ToolContext, prompt: str, caption: str = "") -> dict[str, str]:
    """Genera una ilustración con IA (Nano Banana) cuando un diagrama o una foto no bastan.

    Args:
        prompt: descripción visual detallada, estilo ilustración educativa clara sobre fondo blanco.
        caption: texto corto debajo de la imagen.
    """
    placeholder = _emit(tool_context, "pending", text=f"Dibujando: {caption or prompt[:60]}…")
    data_url = await _nano_banana(prompt)
    queue = _QUEUES.get(tool_context.session.id)
    if queue is not None:
        queue.put_nowait({"type": "board_remove", "id": placeholder.get("id")})
    if not data_url:
        return {"status": "error", "message": "la generación de imágenes no está disponible; usa draw_diagram"}
    return _emit(tool_context, "image", url=data_url, caption=caption, source="Nano Banana")


def ask_question(
    tool_context: ToolContext,
    question: str,
    options: List[str],
    correct_index: int,
    hint: str = "",
) -> dict[str, str]:
    """Abre en el panel de quests una pregunta de opción múltiple para comprobar comprensión.

    Args:
        question: la pregunta.
        options: entre 2 y 4 opciones.
        correct_index: índice (desde 0) de la opción correcta.
        hint: pista que se muestra si el estudiante falla.
    """
    if not 2 <= len(options) <= 4 or not 0 <= correct_index < len(options):
        return {"status": "error", "message": "2-4 opciones y correct_index válido"}
    queue = _QUEUES.get(tool_context.session.id)
    if queue is None:
        return {"status": "error", "message": "pizarra desconectada"}
    qid = f"q{next(_ids)}"
    queue.put_nowait(
        {"type": "question", "id": qid, "question": question, "options": options, "correct": correct_index, "hint": hint}
    )
    return {"status": "success", "id": qid, "note": "espera la respuesta del estudiante antes de seguir"}


def launch_quest(tool_context: ToolContext, title: str, steps: List[str], reward: str = "") -> dict[str, str]:
    """Abre un reto (quest) de varios pasos en el panel para que el estudiante practique por su cuenta.

    Args:
        title: nombre corto y motivador del reto.
        steps: de 2 a 5 pasos concretos que el estudiante debe resolver, en orden.
        reward: frase de logro al completarlo.
    """
    queue = _QUEUES.get(tool_context.session.id)
    if queue is None:
        return {"status": "error", "message": "pizarra desconectada"}
    qid = f"quest{next(_ids)}"
    queue.put_nowait({"type": "quest", "id": qid, "title": title, "steps": steps[:5], "reward": reward})
    return {"status": "success", "id": qid}


def clear_board(tool_context: ToolContext) -> dict[str, str]:
    """Borra todo lo que el profe escribió en la pizarra para empezar un tema nuevo."""
    queue = _QUEUES.get(tool_context.session.id)
    if queue is None:
        return {"status": "error", "message": "pizarra desconectada"}
    queue.put_nowait({"type": "board_clear"})
    return {"status": "success"}


# ------------------------------------------------------------------------ helpers


async def _wikimedia_image(query: str) -> str | None:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": 6,
        "gsrlimit": 5,
        "prop": "imageinfo",
        "iiprop": "url|mime",
        "iiurlwidth": 640,
    }
    headers = {"User-Agent": "profe-digital/0.1 (educational demo)"}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            res = await client.get("https://commons.wikimedia.org/w/api.php", params=params, headers=headers)
            pages = res.json().get("query", {}).get("pages", {})
    except Exception as exc:  # red caída: el profe dibuja en su lugar
        log.warning("wikimedia: %s", exc)
        return None
    for page in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("mime") in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
            return info.get("thumburl") or info.get("url")
    return None


async def _nano_banana(prompt: str) -> str | None:
    model = os.getenv("IMAGE_MODEL", "")
    if not model:
        return None
    from google import genai

    try:
        client = genai.Client()
        res = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
        for part in res.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                import base64

                b64 = base64.b64encode(part.inline_data.data).decode()
                return f"data:{part.inline_data.mime_type};base64,{b64}"
    except Exception as exc:  # nivel gratuito: cuota 0 para modelos de imagen
        log.warning("nano banana: %s", exc)
    return None


def _background(func: Callable[..., Any]) -> FunctionTool:
    tool = FunctionTool(func)
    tool.behavior = types.Behavior.NON_BLOCKING
    tool.response_scheduling = types.FunctionResponseScheduling.WHEN_IDLE
    return tool


def board_tools() -> list[FunctionTool]:
    tools = [write_text, write_formula, plot_functions, draw_diagram, run_simulation, show_image, clear_board, launch_quest]
    if os.getenv("IMAGE_MODEL"):
        tools.append(generate_illustration)
    built = [_background(t) for t in tools]
    # ask_question bloquea: el profe debe callar y esperar la respuesta.
    built.append(FunctionTool(ask_question))
    return built
