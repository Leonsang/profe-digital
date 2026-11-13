# Profe Digital

Un profesor de matemáticas y física **100 % digital**: le hablas, te responde con voz, dibuja en una pizarra mientras explica y puedes interrumpirlo cuando quieras. Es empático: nota la frustración en tu voz, celebra el intento y te guía con preguntas en vez de soltarte la respuesta.

Construido con **Google ADK 2.14** y **Gemini Live** (`gemini-3.8-live`, audio nativo), FastAPI y una pizarra **tldraw**.

## Demo

[![Demo de Profe Digital: el profe celebra el perfil de Ana](demo/renders/teaser.gif)](demo/renders/profe-digital-demo.mp4)

▶️ **[Ver el demo completo (1:36, con la voz real del profe)](demo/renders/profe-digital-demo.mp4)**

Ana entra por primera vez. El profe la conoce y arma su perfil conversando. Ella sube su taller de ecuaciones cuadráticas y el profe lo prepara, la guía en la pizarra sin darle las respuestas y celebra su primer acierto. Al día siguiente, el profe la recuerda. Todo lo que aparece en el video es la app real; la voz es la de Gemini 3.8 Live en esa sesión. El video está hecho con [HyperFrames](https://hyperframes.heygen.com) y su fuente está en [`demo/`](demo/).

## Qué hace

- **Conversación de voz en ambos sentidos.** El audio del micrófono entra continuo y el VAD de Gemini decide los turnos. Si hablas encima del profe, se calla al instante y te escucha.
- **Pizarra en vivo.** Mientras habla, escribe fórmulas (KaTeX), grafica funciones (math.js), dibuja diagramas en SVG, trae fotos de Wikimedia Commons y lanza simulaciones físicas: tiro parabólico, péndulo, resorte, plano inclinado y choque elástico.
- **Ve lo que escribes.** Escribe tu intento con el lápiz y pulsa *Revisa lo que escribí*. El profe recibe la imagen, lee tu razonamiento y señala el paso exacto donde algo se torció.
- **Preguntas y retos.** Cada pocas ideas abre una pregunta en el panel y espera tu respuesta. Al cerrar un tema te propone un reto de varios pasos.
- **Empatía.** Usa *affective dialog* (lee la emoción en la voz) y *proactive audio* (no contesta a ruidos ni cuando piensas en voz alta), más una instrucción socrática.
- **Perfil y memoria.** El profe arma tu perfil conversando (nombre, nivel, meta, cómo aprendes mejor) y guarda lo que vale la pena recordar: dificultades, intereses, cómo te sientes con un tema. Al cerrar cada clase, un modelo de texto la resume. Al abrir la siguiente, el profe recibe tu perfil, tu memoria y tu avance, y retoma donde quedaron: «La última vez factorizaste súper bien…».
- **Avance y logros.** Cada habilidad tiene un dominio de 0 a 100 que sube con las respuestas del panel, los retos y la evidencia que anota el profe. Los hitos (primera clase, perfil listo, primer acierto, rachas de aciertos y de días, habilidad dominada, mitad y final del taller) se detectan en el servidor: el profe te felicita en voz alta y la pantalla lo celebra. La pestaña **Mi avance** muestra perfil, racha, habilidades, logros y lo que el profe recuerda de ti.
- **Talleres.** Sube tu taller (PDF, foto o texto) en la pestaña **Taller**. Un modelo de texto extrae cada ejercicio, lo resuelve, le asigna habilidad, dificultad y una primera pista, y arma un plan de enseñanza. El profe lo trabaja contigo ejercicio por ejercicio **sin darte la respuesta**, y la respuesta nunca llega al navegador.

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

### Memoria y avance

```
navegador (id local del estudiante) ──► WS /ws/{sesión}?student=<id>
                                            │
   al abrir:  perfil + memoria + avance + taller ──► send_content([Contexto privado])
   en clase:  update_profile · remember · record_progress · update_workshop   (herramientas ADK)
              respuestas del panel / retos ──► progress.on_attempt ──► ¿hito nuevo?
                                                                     ├─► evento "milestone" → celebración en pantalla
                                                                     └─► "celebrate" / [Sistema] → el profe felicita en voz
   al cerrar: transcripción ──► gemini-3.5-flash-lite ──► resumen + hechos ──► memoria
                                            │
                                     SQLite (profe.db): students · memories · skills · milestones · workshops

POST /api/students/{id}/workshop ──► gemini-3.5-flash-lite (salida estructurada) ──► plan del taller
                                     └─► si hay clase abierta, se le pasa al profe al instante
```

- Los hitos los decide el servidor, no el modelo: así se celebran una sola vez y nunca por error.
- Las herramientas de memoria también son `NON_BLOCKING`. `remember` usa `SILENT` para no interrumpir la explicación; las que pueden desbloquear un logro usan `WHEN_IDLE`, así el profe termina la frase y luego felicita.
- La identidad es local (un id en `localStorage`), sin cuentas. Para producción hace falta autenticación.

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
| `TEXT_MODEL` | `gemini-3.5-flash-lite` | Prepara talleres y resume cada clase (500 solicitudes/día en el nivel gratuito) |
| `PROFE_DB` | `backend/profe.db` | SQLite con perfiles, memoria, avance, hitos y talleres |
| `RECORD_DIR` | vacío | Graba cada clase (voz del profe en WAV y eventos en JSONL) para hacer demos |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | CORS del frontend |

## Desplegar

El `Dockerfile` de la raíz construye una sola imagen: compila el frontend y lo sirve desde el backend, en el mismo dominio que el WebSocket.

**Hugging Face Spaces (gratis, sin tarjeta).** `deploy/hf_space.py` crea el Space, carga los secretos y sube el código. Lo ejecuta quien tiene las credenciales; el script no imprime ningún secreto.

```powershell
backend\.venv\Scripts\python -m pip install huggingface_hub
$env:HF_TOKEN="hf_..."            # token de escritura
$env:ACCESS_CODES="tu-codigo"     # el demo gasta tu cuota de Gemini: entra solo quien tenga el código
$env:FIRESTORE_SA_KEY="C:\ruta\cuenta-de-servicio.json"   # opcional: memoria persistente en Firestore
backend\.venv\Scripts\python deploy\hf_space.py
```

- **Sin `FIRESTORE_SA_KEY`**, la memoria vive en SQLite dentro del contenedor y se pierde cuando el Space se reinicia o se duerme.
- **Código de acceso y límites:** `ACCESS_CODES` exige un código para cada clase y cada taller. `MAX_SESSIONS_PER_HOUR` (6 por IP) y `MAX_SESSION_MIN` (20 minutos) cuidan la cuota.
- **Cloud Run:** `backend/Dockerfile` sigue sirviendo solo para el backend. Cloud Run exige una cuenta de facturación aunque el uso quede en la capa gratuita.
- **tldraw:** funciona sin clave en localhost; en producción muestra la marca «Get a license» si no se configura `VITE_TLDRAW_LICENSE_KEY`.

## Notas

- En el nivel gratuito de AI Studio, Google puede usar el contenido enviado para mejorar sus productos. Si lo usan estudiantes reales, activa la facturación.
- La arquitectura de la cola bidireccional se inspiró en [FashionMind](https://github.com/cuppibla/fashionmind), con otro objetivo: enseñar.

## Licencia

Apache-2.0
