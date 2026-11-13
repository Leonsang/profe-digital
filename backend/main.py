"""Servidor del Profe Digital: WebSocket bidireccional entre el navegador y Gemini Live (ADK).

Protocolo del WebSocket /ws/{session_id}
  navegador -> servidor
    binario                 PCM16 mono 16 kHz del micrófono (send_realtime, el VAD decide los turnos)
    {"type":"text"}         mensaje escrito (send_content)
    {"type":"board_snapshot","data":<png base64>,"note":...}  lo que el estudiante escribió
    {"type":"answer", ...}  respuesta del panel de quests
  servidor -> navegador
    binario                 PCM16 mono 24 kHz con la voz del profe
    {"type":"transcript","role":"user|profe","text":...,"final":bool}
    {"type":"interrupted"} / {"type":"turn_complete"}
    {"type":"board"|"board_clear"|"board_remove"|"question"|"quest", ...}
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from google.adk.agents.live_request_queue import LiveRequestQueue  # noqa: E402
from google.adk.agents.run_config import RunConfig, StreamingMode  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from profe.agent import app as profe_app  # noqa: E402
from profe.board import close_board, open_board  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("profe")

session_service = InMemorySessionService()
runner = Runner(app=profe_app, session_service=session_service)

VOICE = os.getenv("VOICE", "Aoede")
LANGUAGE = os.getenv("LANGUAGE", "es-US")


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


@api.websocket("/ws/{session_id}")
async def live(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    user_id = f"student-{session_id}"
    session = await session_service.get_session(app_name=profe_app.name, user_id=user_id, session_id=session_id)
    if session is None:
        await session_service.create_session(app_name=profe_app.name, user_id=user_id, session_id=session_id)

    board_queue = open_board(session_id)
    queue = LiveRequestQueue()
    # Arranque: el profe saluda sin esperar a que el estudiante hable.
    queue.send_content(types.Content(role="user", parts=[types.Part(text="(El estudiante acaba de entrar a la clase.)")]))

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
            if kind == "text":
                queue.send_content(types.Content(role="user", parts=[types.Part(text=data["text"])]))
            elif kind == "board_snapshot":
                image = base64.b64decode(data["data"])
                note = data.get("note") or "Esto es lo que escribí en la pizarra. ¿Lo revisas?"
                queue.send_content(
                    types.Content(
                        role="user",
                        parts=[types.Part(inline_data=types.Blob(data=image, mime_type="image/png")), types.Part(text=note)],
                    )
                )
            elif kind == "answer":
                verdict = "correcta" if data.get("correct") else "incorrecta"
                text = (
                    f"[Panel] Respondí '{data.get('choice')}' a la pregunta '{data.get('question')}' ({verdict})."
                    if data.get("question")
                    else f"[Panel] {data.get('text', '')}"
                )
                queue.send_content(types.Content(role="user", parts=[types.Part(text=text)]))

    async def downstream() -> None:
        async for event in runner.run_live(
            user_id=user_id, session_id=session_id, live_request_queue=queue, run_config=run_config()
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    blob = part.inline_data
                    if blob and blob.data and (blob.mime_type or "").startswith("audio/pcm"):
                        await websocket.send_bytes(blob.data)
            if event.input_transcription and event.input_transcription.text:
                await websocket.send_json(
                    {"type": "transcript", "role": "user", "text": event.input_transcription.text, "final": not event.partial}
                )
            if event.output_transcription and event.output_transcription.text:
                await websocket.send_json(
                    {"type": "transcript", "role": "profe", "text": event.output_transcription.text, "final": not event.partial}
                )
            if event.interrupted:
                await websocket.send_json({"type": "interrupted"})
            if event.turn_complete:
                await websocket.send_json({"type": "turn_complete"})

    async def board() -> None:
        while True:
            await websocket.send_json(await board_queue.get())

    tasks = [asyncio.create_task(t()) for t in (upstream, downstream, board)]
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:api", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
