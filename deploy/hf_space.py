"""Despliega Profe Digital en un Hugging Face Space (Docker), gratis y sin tarjeta.

Lo ejecuta la persona dueña de las credenciales; ningún secreto se imprime.

Variables de entorno:
  HF_TOKEN            token de escritura de huggingface.co/settings/tokens (obligatorio)
  HF_SPACE            "usuario/nombre" del Space (por defecto: <tu usuario>/profe-digital)
  ACCESS_CODES        códigos de acceso separados por coma (obligatorio: el demo gasta tu cuota de Gemini)
  FIRESTORE_SA_KEY    ruta al JSON de la cuenta de servicio de Firestore (opcional; sin él la memoria
                      vive en SQLite dentro del contenedor y se pierde al reiniciarse el Space)
La key de Gemini se lee de backend/.env (GOOGLE_API_KEY).

Uso (PowerShell):
  $env:HF_TOKEN="hf_..."; $env:ACCESS_CODES="tu-codigo"; backend\\.venv\\Scripts\\python deploy\\hf_space.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent

SPACE_CARD = """---
title: Profe Digital
emoji: 🧮
colorFrom: blue
colorTo: yellow
sdk: docker
app_port: 7860
license: apache-2.0
short_description: Tutor de voz de matemáticas y física con pizarra en vivo
---

# Profe Digital

Un profesor de matemáticas y física 100 % digital: le hablas, te responde con voz, dibuja en una pizarra
mientras explica, te recuerda entre clases, celebra cada logro y prepara el taller que le traes.

Gemini Live (`gemini-3.8-live`) + Google ADK 2.14 + tldraw. Código y demo en video:
https://github.com/Leonsang/profe-digital

Se entra con un código de acceso, porque cada clase usa un modelo de voz en tiempo real.
"""


def need(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        sys.exit(f"Falta la variable {name}. Lee las instrucciones al inicio de deploy/hf_space.py.")
    return value


def main() -> None:
    token = need("HF_TOKEN")
    codes = need("ACCESS_CODES")
    gemini_key = (dotenv_values(ROOT / "backend" / ".env").get("GOOGLE_API_KEY") or "").strip()
    if not gemini_key:
        sys.exit("No encontré GOOGLE_API_KEY en backend/.env.")

    hf = HfApi(token=token)
    user = hf.whoami()["name"]
    space = os.getenv("HF_SPACE", f"{user}/profe-digital")
    print(f"Space: {space}")

    hf.create_repo(space, repo_type="space", space_sdk="docker", exist_ok=True)

    # Secretos (cifrados en Hugging Face, no visibles en el repo del Space).
    hf.add_space_secret(space, "GOOGLE_API_KEY", gemini_key)
    hf.add_space_secret(space, "ACCESS_CODES", codes)
    sa_path = os.getenv("FIRESTORE_SA_KEY", "").strip()
    store = "sqlite"
    if sa_path:
        hf.add_space_secret(space, "GOOGLE_APPLICATION_CREDENTIALS_JSON", Path(sa_path).read_text(encoding="utf-8"))
        store = "firestore"
    print(f"Secretos cargados. Memoria: {store}.")

    # Variables públicas de configuración.
    for key, value in {
        "GOOGLE_GENAI_USE_VERTEXAI": "FALSE",
        "LIVE_MODEL": "gemini-3.8-live",
        "TEXT_MODEL": "gemini-3.5-flash-lite",
        "PROFE_STORE": store,
        "MAX_SESSIONS_PER_HOUR": "6",
        "MAX_SESSION_MIN": "20",
    }.items():
        hf.add_space_variable(space, key, value)

    hf.upload_folder(
        repo_id=space,
        repo_type="space",
        folder_path=ROOT,
        allow_patterns=["Dockerfile", ".dockerignore", "backend/**", "frontend/**"],
        ignore_patterns=[
            "**/node_modules/**", "**/.venv/**", "**/__pycache__/**", "**/dist/**",
            "**/.env", "**/*.db", "**/*.log", "backend/scripts/**",
        ],
        commit_message="Deploy Profe Digital",
    )
    hf.upload_file(
        path_or_fileobj=SPACE_CARD.encode("utf-8"),
        path_in_repo="README.md",
        repo_id=space,
        repo_type="space",
        commit_message="Space card",
    )
    host = space.replace("/", "-").lower().replace("_", "-")
    print(f"Listo. El Space se está construyendo (unos minutos): https://huggingface.co/spaces/{space}")
    print(f"App: https://{host}.hf.space")


if __name__ == "__main__":
    main()
