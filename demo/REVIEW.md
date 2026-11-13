# Revisión — demo de Profe Digital

**Archivo:** `renders/profe-digital-demo.mp4` · 96.5 s · 1920×1080 · 30 fps · 10.2 MB

## Decisiones creativas
- Una sola historia (Ana, de estudiante nueva a «al día siguiente»), construida con una sesión real grabada para la demo: capturas de la app y la voz real de Gemini 3.8 Live. No se exploraron otras historias porque el pedido era «graba un demo del mismo».
- La voz del profe marca el ritmo y lleva subtítulos literales, verificados transcribiendo cada clip.
- Para los acercamientos al panel lateral, la ventana se recorta hasta la columna del panel (modo «panel»). Así no aparece la paleta de colores de tldraw, que ocupaba medio encuadre.
- Única pieza reconstruida en HTML: la tarjeta «¡Nuevo logro! Perfil listo», con el mismo estilo y texto que la app. El hito ocurrió en la sesión, pero la tarjeta se cerró antes de capturarla.

## Qué se midió y qué solo se miró
- `hyperframes check`: sin errores ni advertencias. Los tramos quietos de «Te conoce», «Lleva tu avance» y «Y te recuerda» llevan `data-hold`: son pausas para leer.
- Audio medido, no escuchado: voz de 5.26 s a 89.95 s, −15.4 LUFS integrados, pico real −2 dBTP.
- Se miraron las hojas de fotogramas por escena y las costuras entre escenas. La hoja de teléfono no se revisó en detalle: el video está pensado para verse en escritorio desde GitHub.

## Plano más débil
- «Celebra cada hito» (52 s): el acercamiento 2.4× a la tarjeta «Primer acierto» amplía una captura JPEG de 1568 px y se ve algo suave. Con más tiempo: capturas con mayor escala de dispositivo (2×), o grabar la pantalla en video en lugar de capturas.

## Pendiente / sin música
- No hay música: no hay una fuente configurada (`/media-use`, `bgm`). Para agregarla, poner un `<audio id="bgm">` en `index.html` a volumen ≈ 0.14 bajo la voz.
- Un efecto real de la sesión: después de lanzar la simulación, el profe repitió su introducción del taller. La demo usa solo el tramo sin repetir, y el prompt quedó corregido para que no vuelva a pasar.
