# Profe Digital

Un profesor de matemáticas y física **100 % digital**: le hablas, te responde con voz, dibuja en una pizarra mientras explica y puedes interrumpirlo cuando quieras. Es empático: nota la frustración en tu voz, celebra el intento y te guía con preguntas en vez de soltarte la respuesta.

Construido con **Google ADK 2.14** y **Gemini Live** (`gemini-3.8-live`, audio nativo), FastAPI y una pizarra **tldraw**.

## Qué hace

- **Conversación de voz en ambos sentidos.** El audio del micrófono entra continuo y el VAD de Gemini decide los turnos. Si hablas encima del profe, se calla al instante y te escucha.
- **Pizarra en vivo.** Mientras habla, escribe fórmulas (KaTeX), grafica funciones (math.js), dibuja diagramas en SVG, trae fotos de Wikimedia Commons y lanza simulaciones físicas: tiro parabólico, péndulo, resorte, plano inclinado y choque elástico.
- **Ve lo que escribes.** Escribe tu intento con el lápiz y pulsa *Revisa lo que escribí*. El profe recibe la imagen, lee tu razonamiento y señala el paso exacto donde algo se torció.
- **Preguntas y retos.** Cada pocas ideas abre una pregunta en el panel y espera tu respuesta. Al cerrar un tema te propone un reto de varios pasos.
- **Empatía.** Usa *affective dialog* (lee la emoción en la voz) y *proactive audio* (no contesta a ruidos ni cuando piensas en voz alta), más una instrucción socrática.

## Arquitectura

```
navegador                                   backend (FastAPI + ADK)                  Gemini Live
─────────                                   ───────────────────────                  ───────────
micrófono ─ AudioWorklet PCM16 16 kHz ──►  WS /ws/{id} ── send_realtime ──►  LiveRequestQueue ──► gemini-3.8-live
texto / respuestas / captura pizarra ───►              ── send_content  ──►        │
                                                                                runner.run_live()
altavoz ◄─ AudioWorklet PCM16 24 kHz ◄──── audio ◄─────────────────────────────────┤
transcripción, "interrupted" ◄─────────── eventos ◄────────────────────────────────┤
tldraw + panel de quests ◄──────────────── cola de pizarra ◄── herramientas NON_BLOCKING
```

**Herramientas que no detienen la voz.** Cada herramienta de pizarra (`write_formula`, `plot_functions`, `draw_diagram`, `run_simulation`, `show_image`…) solo publica un evento en la cola de la sesión y devuelve al instante. Se declaran `behavior=NON_BLOCKING` con `response_scheduling=WHEN_IDLE`. El modelo sigue hablando mientras aparece el trazo y retoma la explicación al terminar la frase. Con `SILENT`, el profe se quedaba callado después de dibujar; `ask_question` es la única herramienta bloqueante, a propósito: el profe debe callar y esperar tu respuesta.

**Interrupción.** Gemini detecta la voz del estudiante y emite `interrupted`. El frontend vacía al instante la cola de reproducción del AudioWorklet.

## Correr en local

Requisitos: Python 3.12 y Node 22 o superior, más una API key de [Google AI Studio](https://aistudio.google.com/apikey). El nivel gratuito sirve: los modelos Live no tienen límite de solicitudes, solo 65K tokens por minuto.

```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/activate      # en macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                # pega tu GOOGLE_API_KEY
python main.py                                      # http://localhost:8000/health

# frontend
cd frontend
npm install
npm run dev                                         # http://localhost:5173
```

Prueba de punta a punta sin navegador (texto en lugar de voz):

```bash
cd backend && python scripts/smoke.py ws://localhost:8000/ws/test "Explícame el tiro parabólico con una simulación"
```

### Variables

| Variable | Por defecto | Qué hace |
|---|---|---|
| `LIVE_MODEL` | `gemini-3.8-live` | Modelo de voz. Alternativas: `gemini-3-flash-live`, `gemini-2.5-flash-native-audio-latest` |
| `VOICE` / `LANGUAGE` | `Aoede` / `es-US` | Voz y acento del profe |
| `AFFECTIVE_DIALOG` / `PROACTIVE_AUDIO` | `1` | Empatía por la voz y silencio ante ruidos |
| `IMAGE_MODEL` | vacío | Activa `generate_illustration` con Nano Banana (requiere facturación; en el nivel gratuito la cuota es 0) |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | CORS del frontend |

## Desplegar

- **Backend:** `backend/Dockerfile` está listo para Cloud Run. Pon `GOOGLE_API_KEY` como secreto y deja una sola instancia por sesión de WebSocket, con *session affinity*.
- **Frontend:** es estático (`npm run build`). Configura `VITE_BACKEND_WS=wss://…`.
- **tldraw:** funciona sin clave en localhost; en producción pide una [licencia](https://tldraw.dev/pricing) (`VITE_TLDRAW_LICENSE_KEY`).

## Notas

- En el nivel gratuito de AI Studio, Google puede usar el contenido enviado para mejorar sus productos. Si lo usan estudiantes reales, activa la facturación.
- La arquitectura de la cola bidireccional se inspiró en [FashionMind](https://github.com/cuppibla/fashionmind), con otro objetivo: enseñar.

## Licencia

Apache-2.0
