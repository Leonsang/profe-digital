"""Servidor del Profe Digital: WebSocket bidireccional entre el navegador y Gemini Live (ADK).

Protocolo del WebSocket /ws/{session_id}?student=<id>
  navegador -> servidor
    binario                 PCM16 mono 16 kHz del micrófono (send_realtime, el VAD decide los turnos)
    {"type":"text"}         mensaje escrito (send_content)
    {"type":"board_snapshot","data":<png base64>,"note":...}  lo que el estudiante escribió
    {"type":"answer", question, choice, correct, skill, topic}  respuesta del panel
    {"type":"quest_done", title}                                reto completado
  servidor -> navegador
    binario                 PCM16 mono 24 kHz con la voz del profe
    {"type":"transcript","role":"user|profe","text":...,"final":bool}
    {"type":"interrupted"} / {"type":"turn_complete"}
    {"type":"board"|"board_clear"|"board_remove"|"question"|"quest", ...}
    {"type":"progress", ...} / {"type":"milestone", key, title, detail}

REST
  GET  /api/students/{id}/progress   perfil, dominio, hitos, memoria y taller
  POST /api/students/{id}/workshop   sube un taller (PDF, foto o texto) y lo prepara
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import hmac
import re
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"))

# En Hugging Face Spaces la cuenta de servicio de Firestore llega como secreto con el JSON completo.
if os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON") and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    _sa = Path("/tmp/firestore-sa.json")
    _sa.write_text(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"], encoding="utf-8")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_sa)

from fastapi import FastAPI, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from google.adk.agents.live_request_queue import LiveRequestQueue  # noqa: E402
from google.adk.agents.run_config import RunConfig, StreamingMode  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from profe import progress, store  # noqa: E402
from profe.agent import app as profe_app  # noqa: E402
from profe.board import close_board, open_board  # noqa: E402
from profe.coach import publish  # noqa: E402
from profe.prep import prepare_workshop, summarize_session  # noqa: E402
from profe.recorder import Recorder  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("profe")

store.init()
session_service = InMemorySessionService()
runner = Runner(app=profe_app, session_service=session_service)

VOICE = os.getenv("VOICE", "Aoede")
LANGUAGE = os.getenv("LANGUAGE", "es-US")
NOISE = re.compile(r"<[^>]*>")  # p. ej. "<no speech detected>"
STUDENT_ID = re.compile(r"^[A-Za-z0-9_-]{4,40}$")
WORKSHOP_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp", "text/plain", "text/markdown"}

# student_id -> (session_id, cola Live) de la clase abierta: así un taller subido por REST llega a la clase.
_LIVE: dict[str, tuple[str, LiveRequestQueue]] = {}
_background: set[asyncio.Task] = set()


# ---------------------------------------------------------------- acceso
# Con ACCESS_CODES definido, cada clase y cada taller exigen un código válido (como en los labs del portfolio).
ACCESS_CODES = [c.strip() for c in os.getenv("ACCESS_CODES", "").split(",") if c.strip()]
MAX_SESSIONS_PER_HOUR = int(os.getenv("MAX_SESSIONS_PER_HOUR", "6"))
MAX_SESSION_MIN = float(os.getenv("MAX_SESSION_MIN", "20"))
_starts: dict[str, deque[float]] = defaultdict(deque)


def code_ok(code: str | None) -> bool:
    if not ACCESS_CODES:
        return True
    return any(hmac.compare_digest((code or "").encode(), c.encode()) for c in ACCESS_CODES)


def client_ip(headers, fallback: str) -> str:
    forwarded = headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or fallback


def rate_limited(ip: str) -> bool:
    now = time.time()
    window = _starts[ip]
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= MAX_SESSIONS_PER_HOUR:
        return True
    window.append(now)
    return False


def _require(code: str | None) -> None:
    if not code_ok(code):
        raise HTTPException(401, "Código de acceso inválido.")


def _flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() not in {"0", "false", "no", ""}


def run_config() -> RunConfig:
    cfg: dict = dict(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE)),
            language_code=LANGUAGE,
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        session_resumption=types.SessionResumptionConfig(),
        context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()),
    )
    if _flag("AFFECTIVE_DIALOG"):
        cfg["enable_affective_dialog"] = True
    if _flag("PROACTIVE_AUDIO"):
        cfg["proactivity"] = types.ProactivityConfig(proactive_audio=True)
    return RunConfig(**cfg)


def _say(queue: LiveRequestQueue, text: str) -> None:
    queue.send_content(types.Content(role="user", parts=[types.Part(text=text)]))


def _check(student_id: str) -> str:
    if not STUDENT_ID.match(student_id):
        raise HTTPException(400, "id de estudiante inválido")
    return student_id


api = FastAPI(title="Profe Digital")
api.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": profe_app.root_agent.model}


class AccessCheck(BaseModel):
    code: str = ""


@api.get("/api/access")
async def access_info() -> dict:
    return {"required": bool(ACCESS_CODES), "max_minutes": MAX_SESSION_MIN}


@api.post("/api/access")
async def access_check(body: AccessCheck) -> dict:
    _require(body.code)
    return {"ok": True}


@api.get("/api/students/{student_id}/progress")
async def get_progress(student_id: str, x_access_code: str | None = Header(default=None)) -> dict:
    _require(x_access_code)
    store.ensure_student(_check(student_id))
    return progress.snapshot(student_id)


@api.post("/api/students/{student_id}/workshop")
async def upload_workshop(
    student_id: str, file: UploadFile, x_access_code: str | None = Header(default=None)
) -> dict:
    """Recibe el taller, lo prepara con el modelo de texto y lo deja activo (y avisa a la clase abierta)."""
    _require(x_access_code)
    store.ensure_student(_check(student_id))
    mime = (file.content_type or "").split(";")[0]
    if mime not in WORKSHOP_TYPES:
        raise HTTPException(415, "Sube un PDF, una foto (PNG, JPG o WebP) o un texto.")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "El archivo supera 10 MB.")
    profile = store.get_student(student_id)
    try:
        plan = await prepare_workshop(data, mime, f"{profile.get('grade', '')} · {profile.get('preferences', '')}")
    except Exception as exc:
        log.exception("no se pudo preparar el taller")
        raise HTTPException(502, f"No pude leer el taller: {str(exc)[:200]}") from exc
    if not plan.exercises:
        raise HTTPException(422, "No encontré ejercicios en el archivo.")
    workshop_id = store.save_workshop(student_id, plan.title, plan.topic, plan.model_dump())
    won = []
    if store.award(student_id, f"workshop_new:{workshop_id}", "Trajiste un taller", plan.title):
        won = [{"key": f"workshop_new:{workshop_id}", "title": "Trajiste un taller", "detail": plan.title}]
    live = _LIVE.get(student_id)
    if live:
        session_id, queue = live
        workshop = store.active_workshop(student_id)
        note = "[Taller] El estudiante acaba de subir su taller. " + progress.workshop_brief(workshop)
        if won:
            note += "\n" + progress.celebration_note(won)
        _say(queue, note)
        publish(session_id, student_id, won)
    return progress.snapshot(student_id)


async def _remember_session(student_id: str, transcript: list[str]) -> None:
    summary = await summarize_session("\n".join(transcript))
    if not summary:
        return
    store.remember(student_id, "sesión", f"{summary.summary} Próximo paso: {summary.next_step}")
    for fact in summary.facts:
        store.remember(student_id, fact.category, fact.fact)
    log.info("memoria de la clase guardada para %s", student_id)


@api.websocket("/ws/{session_id}")
async def live(websocket: WebSocket, session_id: str, student: str = "", code: str = "") -> None:
    await websocket.accept()
    if not code_ok(code):
        await websocket.close(code=4401, reason="codigo invalido")
        return
    if rate_limited(client_ip(websocket.headers, websocket.client.host if websocket.client else "?")):
        await websocket.close(code=4429, reason="demasiadas clases")
        return
    student_id = student if STUDENT_ID.match(student or "") else f"anon-{session_id}"
    store.ensure_student(student_id)
    user_id = f"student-{student_id}"
    session = await session_service.get_session(app_name=profe_app.name, user_id=user_id, session_id=session_id)
    if session is None:
        await session_service.create_session(
            app_name=profe_app.name, user_id=user_id, session_id=session_id, state={"student_id": student_id}
        )

    board_queue = open_board(session_id)
    queue = LiveRequestQueue()
    _LIVE[student_id] = (session_id, queue)
    transcript: list[str] = []
    rec = Recorder(session_id)

    # Arranque: el profe recibe perfil, memoria, avance y taller, y saluda sin esperar.
    visit = store.touch_session(student_id)
    won = progress.on_session_start(student_id, visit["streak"], visit["sessions"])
    opening = progress.context_for_profe(student_id) + "\n\n(El estudiante acaba de entrar a la clase.)"
    if won:
        opening += "\n" + progress.celebration_note(won)
    _say(queue, opening)
    publish(session_id, student_id, won)

    def answer(text: str, won: list[dict[str, str]]) -> None:
        publish(session_id, student_id, won)
        if won:
            text += "\n" + progress.celebration_note(won)
        transcript.append(text)
        _say(queue, text)

    async def upstream() -> None:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
            if (chunk := message.get("bytes")) is not None:
                queue.send_realtime(types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
                continue
            data = json.loads(message.get("text") or "{}")
            kind = data.get("type")
            rec.event(f"student:{kind}", **{k: v for k, v in data.items() if k not in ("type", "data")})
            if kind == "text":
                transcript.append(f"Estudiante: {data['text']}")
                _say(queue, data["text"])
            elif kind == "board_snapshot":
                image = base64.b64decode(data["data"])
                note = data.get("note") or "Esto es lo que escribí en la pizarra. ¿Lo revisas?"
                transcript.append("Estudiante: (mostró lo que escribió en la pizarra)")
                queue.send_content(
                    types.Content(
                        role="user",
                        parts=[types.Part(inline_data=types.Blob(data=image, mime_type="image/png")), types.Part(text=note)],
                    )
                )
            elif kind == "answer" and data.get("question"):
                correct = bool(data.get("correct"))
                _, won = progress.on_attempt(student_id, data.get("skill") or "general", data.get("topic") or "", correct)
                verdict = "correcta" if correct else "incorrecta"
                answer(f"[Panel] Respondí '{data.get('choice')}' a la pregunta '{data.get('question')}' ({verdict}).", won)
            elif kind == "quest_done":
                title = str(data.get("title", "reto"))
                answer(f"[Panel] Terminé el reto «{title}».", progress.on_quest_done(student_id, title))

    async def downstream() -> None:
        async for event in runner.run_live(
            user_id=user_id, session_id=session_id, live_request_queue=queue, run_config=run_config()
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    blob = part.inline_data
                    if blob and blob.data and (blob.mime_type or "").startswith("audio/pcm"):
                        rec.audio(blob.data)
                        await websocket.send_bytes(blob.data)
            for role, chunk in (("user", event.input_transcription), ("profe", event.output_transcription)):
                if chunk and chunk.text and not NOISE.fullmatch(chunk.text.strip()):
                    if not event.partial:
                        rec.event("say", role=role, text=chunk.text)
                        transcript.append(f"{'Estudiante' if role == 'user' else 'Profe'}: {chunk.text}")
                    await websocket.send_json({"type": "transcript", "role": role, "text": chunk.text, "final": not event.partial})
            if event.interrupted:
                await websocket.send_json({"type": "interrupted"})
            if event.turn_complete:
                await websocket.send_json({"type": "turn_complete"})

    async def time_limit() -> None:
        await asyncio.sleep(MAX_SESSION_MIN * 60)
        await websocket.send_json(
            {"type": "error", "message": f"La clase llegó a su límite de {MAX_SESSION_MIN:g} minutos. ¡Buen trabajo! Empieza otra cuando quieras."}
        )

    async def board() -> None:
        while True:
            payload = await board_queue.get()
            if payload.get("type") != "progress":
                rec.event(payload.get("type", "?"), **{k: v for k, v in payload.items() if k in ("kind", "title", "latex", "question")})
            await websocket.send_json(payload)

    tasks = [asyncio.create_task(t()) for t in (upstream, downstream, board, time_limit)]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if (exc := task.exception()) and not isinstance(exc, WebSocketDisconnect):
                log.exception("sesión %s terminó con error", session_id, exc_info=exc)
                try:
                    await websocket.send_json({"type": "error", "message": str(exc)[:300]})
                except Exception:
                    pass
    finally:
        queue.close()
        for task in tasks:
            task.cancel()
        close_board(session_id)
        rec.close()
        if _LIVE.get(student_id, ("", None))[0] == session_id:
            _LIVE.pop(student_id, None)
        # La memoria de la clase se escribe en segundo plano, sin bloquear el cierre.
        job = asyncio.create_task(_remember_session(student_id, transcript))
        _background.add(job)
        job.add_done_callback(_background.discard)


# El frontend compilado (Docker de producción) se sirve desde el mismo servidor: mismo dominio que el WebSocket.
_static = Path(os.getenv("STATIC_DIR", Path(__file__).resolve().parent / "static"))
if _static.is_dir():
    from fastapi.staticfiles import StaticFiles

    api.mount("/", StaticFiles(directory=_static, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:api", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
