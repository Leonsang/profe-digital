# Profe Digital — demo (96.5 s, 1920×1080, 30 fps)

**Historia:** Ana entra por primera vez → el profe la conoce y arma su perfil → ella trae su taller y el profe lo prepara → la guía con la pizarra → celebra su primer acierto → su avance queda guardado → al día siguiente el profe la recuerda.

**Sonido:** la voz real del profe (Gemini 3.8 Live, grabada de la sesión) marca el ritmo; sin música (no hay fuente de música configurada). Subtítulos literales de cada frase.

## Material real (nada inventado)
- `assets/shots/*.jpg`: capturas de la app corriendo en localhost:5173 (1568×777 y 1568×731).
- `assets/voice/*.mp3`: cortes de la grabación de esa misma sesión, verificados con transcripción.
- Lo único reconstruido en HTML: la tarjeta «¡Nuevo logro! Perfil listo» (mismo estilo y texto que la app; el hito ocurrió en la sesión pero la tarjeta se cerró antes de capturarla) y la marca ∑.

## Números
- Paleta de la app: papel `#f6f3ec`, tinta `#1d2a3f`, azul `#2f6fed`, naranja `#e2552b`, verde `#1f9d63`. Tipografía Inter 400/700/900.
- Ventana de la app: 1454×720 en (233, 170), radio 18 px, sombra 0 30px 80px rgba(29,42,63,.18).
- Título de escena: kicker naranja 22 px + título 44 px/700 en (233, 96). Subtítulos: 34 px/600, banda 900–975 px.
- Cámara: punch-ins de 0.6 s `power2.inOut`, escala máx. 2.4 (el texto de la app, 13 px, queda ≥ 28 px).
- Llegadas `expo.out` 0.5–0.7 s; salidas 0.25 s `power3.in`. Tarjeta de logro: `back.out(1.6)` 0.45 s.

## Escenas (inicio global)
| # | id | inicio | dur | voz |
|---|---|---|---|---|
| 1 | intro | 0 | 4.5 | — |
| 2 | conoce | 4.5 | 13.5 | hola @ 5.2 |
| 3 | perfil | 18.0 | 8.5 | perfil @ 18.8 |
| 4 | taller | 26.5 | 13.0 | taller @ 27.3 |
| 5 | pizarra | 39.5 | 12.5 | ejemplo @ 40.3 |
| 6 | acierto | 52.0 | 14.5 | acierto @ 52.6 |
| 7 | avance | 66.5 | 8.0 | — |
| 8 | memoria | 74.5 | 15.5 | memoria @ 76.3 |
| 9 | cierre | 90.0 | 6.5 | — |

**Prohibido:** mockups de UI, botones inventados, títulos sobre capturas oscurecidas, flotar/pulsar en bucle, el mismo fade+slide en cada escena.
