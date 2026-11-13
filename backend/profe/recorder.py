"""Grabación opcional de una clase (para demos): voz del profe alineada al reloj real + eventos.

Se activa con RECORD_DIR. Escribe <dir>/<session>.wav (PCM16 24 kHz, con los silencios reales)
y <dir>/<session>.jsonl (segundo, tipo y resumen de cada evento).
"""

from __future__ import annotations

import json
import os
import time
import wave
from pathlib import Path
from typing import Any

RATE = 24000


class Recorder:
    def __init__(self, session_id: str) -> None:
        root = os.getenv("RECORD_DIR")
        self.enabled = bool(root)
        if not self.enabled:
            return
        self.dir = Path(root)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.t0 = time.monotonic()
        self.pcm = bytearray()
        self.session_id = session_id
        self.log = (self.dir / f"{session_id}.jsonl").open("w", encoding="utf-8")

    def now(self) -> float:
        return time.monotonic() - self.t0

    def audio(self, chunk: bytes) -> None:
        if not self.enabled:
            return
        target = int(self.now() * RATE) * 2
        if len(self.pcm) < target:  # rellena el silencio real entre frases
            self.pcm.extend(b"\x00" * (target - len(self.pcm)))
        self.pcm.extend(chunk)

    def event(self, name: str, /, **data: Any) -> None:
        if self.enabled:
            self.log.write(json.dumps({"t": round(self.now(), 2), "event": name, **data}, ensure_ascii=False) + "\n")
            self.log.flush()

    def close(self) -> None:
        if not self.enabled:
            return
        self.log.close()
        with wave.open(str(self.dir / f"{self.session_id}.wav"), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(bytes(self.pcm))
