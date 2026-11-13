"""Genera las escenas basadas en capturas (compositions/*.html) con la misma ventana y cámara.

Uso: python tools/build_scenes.py   (desde demo/)
Cada escena: título, capturas que se cortan dentro de la escena y movimientos de cámara a
rectángulos de la captura (en píxeles de la captura). La cámara escala un envoltorio, nunca la imagen.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = {"x": 233, "y": 170, "w": 1454, "h": 720}
IMG_W = 1568
SIZES = {"empty": 777, "intro": 777, "reading": 731, "workshop": 777, "board-sim": 777, "board-example": 777,
         "correct": 731, "progress": 731, "memory": 731}
BASE = STAGE["w"] / IMG_W
MAX_SCALE = 2.4


PANEL_X, PANEL_W, PANEL_SCALE = 1262, 306, 2.3


def view_inset(move: dict) -> str:
    """Recorte de la ventana: en modo panel se estrecha hasta la columna del panel lateral."""
    side = 0.0
    if move.get("panel") is not None:
        side = (STAGE["w"] - PANEL_W * PANEL_SCALE) / 2
    return f"inset(0px {side:.1f}px 0px {side:.1f}px round 18px)"


def frame_for(move: dict, img_h: int) -> dict[str, float]:
    if move.get("panel") is not None:
        s = PANEL_SCALE
        vw = PANEL_W * s
        x = STAGE["w"] / 2 - vw / 2 - s * PANEL_X
        y = min(0.0, max(STAGE["h"] - s * img_h, -s * move["panel"]))
        return {"scale": s, "x": round(x, 1), "y": round(y, 1)}
    return camera(move.get("rect"), img_h)


def camera(rect: list[float] | None, img_h: int) -> dict[str, float]:
    """Escala y desplazamiento del envoltorio para centrar `rect` en la ventana."""
    if rect is None:
        return {"scale": BASE, "x": 0.0, "y": 0.0}
    rx, ry, rw, rh = rect
    s = min(STAGE["w"] / rw, STAGE["h"] / rh) * 0.92
    s = max(BASE, min(MAX_SCALE, s))
    x = STAGE["w"] / 2 - s * (rx + rw / 2)
    y = STAGE["h"] / 2 - s * (ry + rh / 2)
    x = min(0.0, max(STAGE["w"] - s * IMG_W, x))
    y = min(0.0, max(STAGE["h"] - s * img_h, y))
    return {"scale": round(s, 4), "x": round(x, 1), "y": round(y, 1)}


CELEBRATION_CSS = """
#{p}-cel { position:absolute; left:0; top:0; width:1920px; height:1080px; z-index:20; pointer-events:none; }
#{p}-cel-veil { position:absolute; inset:0; background:rgba(29,42,63,.18); opacity:0; }
#{p}-cel-card { position:absolute; left:50%; top:50%; width:620px; margin-left:-310px; margin-top:-120px;
  padding:40px 48px; border-radius:30px; background:#fff; box-shadow:0 36px 90px rgba(29,42,63,.28);
  text-align:center; display:flex; flex-direction:column; gap:10px; opacity:0; }
#{p}-cel-card .k { font-size:28px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#e2552b; }
#{p}-cel-card .t { font-size:46px; font-weight:900; color:#1d2a3f; }
#{p}-cel-card .d { font-size:28px; color:#66707f; }
"""


def scene(spec: dict) -> str:
    p = spec["id"]
    dur = spec["duration"]
    shots = spec["shots"]
    imgs, tl = [], []
    for i, shot in enumerate(shots):
        h = SIZES[shot["src"]]
        sid = f"{p}-shot{i}"
        end = shots[i + 1]["at"] if i + 1 < len(shots) else dur
        imgs.append(
            f'<div id="{sid}" class="clip shot" data-start="{shot["at"]}" data-duration="{round(end - shot["at"], 3)}"'
            + (' data-hold' if shot.get("hold") else '') + '>'
            f'<div id="{sid}-cam" class="cam"><img src="assets/shots/{shot["src"]}.jpg" alt="" width="{IMG_W}" height="{h}" /></div></div>'
        )
        moves = shot.get("moves", [])
        tl.append(f'tl.set("#{sid}-cam", {json.dumps(frame_for(shot, h))}, {shot["at"]});')
        tl.append(f'tl.set("#{p}-view", {{clipPath: "{view_inset(shot)}"}}, {shot["at"]});')
        for mv in moves:
            target = frame_for(mv, h)
            d = mv.get("dur", 0.6)
            tl.append(f'tl.to("#{sid}-cam", {{...{json.dumps(target)}, duration: {d}, ease: "power2.inOut"}}, {mv["t"]});')
            tl.append(f'tl.to("#{p}-view", {{clipPath: "{view_inset(mv)}", duration: {d}, ease: "power2.inOut"}}, {mv["t"]});')

    title_html = (
        f'<div id="{p}-title" class="clip title" data-start="0" data-duration="{dur}">'
        f'<span id="{p}-kicker" class="kicker">{spec["kicker"]}</span><h2 id="{p}-h">{spec["title"]}</h2></div>'
    )
    tl.insert(0, f'tl.fromTo("#{p}-h", {{opacity:0, filter:"blur(8px)"}}, {{opacity:1, filter:"blur(0px)", duration:0.2, ease:"power4.out"}}, 0.15);')
    tl.insert(0, f'tl.fromTo("#{p}-kicker", {{opacity:0}}, {{opacity:1, duration:0.2}}, 0.05);')
    if spec.get("enter") == "rise":
        tl.insert(0, f'tl.fromTo("#{p}-frame", {{y:60, opacity:0}}, {{y:0, opacity:1, duration:0.7, ease:"expo.out"}}, 0);')
    elif spec.get("enter") == "whip":
        tl.insert(0, f'tl.fromTo("#{p}-frame", {{x:420, opacity:0, filter:"blur(14px)"}}, {{x:0, opacity:1, filter:"blur(0px)", duration:0.45, ease:"expo.out"}}, 0);')
    elif spec.get("enter") == "iris":
        tl.insert(0, f'tl.fromTo("#{p}-frame", {{clipPath:"circle(0% at 50% 50%)"}}, {{clipPath:"circle(75% at 50% 50%)", duration:0.6, ease:"power2.inOut"}}, 0);')
    # salida: la ventana se va más rápido de lo que llegó
    tl.append(f'tl.to("#{p}-frame", {{opacity:0, filter:"blur(6px)", duration:0.25, ease:"power3.in"}}, {round(dur - 0.27, 3)});')
    tl.append(f'tl.to("#{p}-title", {{opacity:0, duration:0.2, ease:"power3.in"}}, {round(dur - 0.25, 3)});')

    extra_css, extra_html = "", ""
    cel = spec.get("celebration")
    if cel:
        extra_css = CELEBRATION_CSS.replace("{p}", p)
        extra_html = (
            f'<div id="{p}-cel" class="clip" data-start="{cel["at"]}" data-duration="{cel["dur"]}" data-layout-allow-overlap>'
            f'<div id="{p}-cel-veil"></div><div id="{p}-cel-card"><span class="k">¡Nuevo logro!</span>'
            f'<span class="t">{cel["title"]}</span><span class="d">{cel["detail"]}</span></div></div>'
        )
        a = cel["at"]
        tl.append(f'tl.fromTo("#{p}-cel-veil", {{opacity:0}}, {{opacity:1, duration:0.25}}, {a});')
        tl.append(f'tl.fromTo("#{p}-cel-card", {{opacity:0, y:24, scale:0.9}}, {{opacity:1, y:0, scale:1, duration:0.45, ease:"back.out(1.6)"}}, {a});')
        out = round(a + cel["dur"] - 0.3, 3)
        tl.append(f'tl.to("#{p}-cel-card", {{opacity:0, y:-12, duration:0.22, ease:"power3.in"}}, {out});')
        tl.append(f'tl.to("#{p}-cel-veil", {{opacity:0, duration:0.22}}, {out});')

    timeline = "\n    ".join(tl)
    return f"""<template>
  <style>
    #root {{ position:absolute; inset:0; background:#f6f3ec; font-family:Inter, sans-serif; overflow:hidden; }}
    #{p}-plate {{ position:absolute; left:{STAGE['x']}px; top:{STAGE['y']}px; width:{STAGE['w']}px; height:{STAGE['h']}px;
      filter: drop-shadow(0 24px 40px rgba(29,42,63,.16)); }}
    #{p}-frame {{ position:absolute; inset:0; }}
    #{p}-view {{ position:absolute; inset:0; overflow:hidden; background:#f8f9fb; clip-path: inset(0px 0px 0px 0px round 18px); }}
    #root .shot {{ position:absolute; left:0; top:0; width:{STAGE['w']}px; height:{STAGE['h']}px; overflow:hidden; }}
    #root .cam {{ position:absolute; left:0; top:0; width:{IMG_W}px; transform-origin:0 0; }}
    #root .cam img {{ display:block; width:{IMG_W}px; height:auto; }}
    #root .title {{ position:absolute; left:{STAGE['x']}px; top:92px; display:flex; align-items:baseline; gap:16px; }}
    #root .kicker {{ font-size:30px; font-weight:700; color:#e2552b; letter-spacing:.06em; }}
    #root .title h2 {{ margin:0; font-size:44px; font-weight:700; color:#1d2a3f; letter-spacing:-.01em; }}
    {extra_css}
  </style>
  <div id="root" data-composition-id="{p}" data-width="1920" data-height="1080">
    {title_html}
    <div id="{p}-plate"><div id="{p}-frame"><div id="{p}-view">
      {''.join(imgs)}
    </div></div></div>
    {extra_html}
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    {timeline}
    window.__timelines["{p}"] = tl;
  </script>
</template>
"""


# Rectángulos en píxeles de la captura 1568 px de ancho.
PANEL_TOP = [1266, 165, 296, 300]
SCENES = [
    {"id": "conoce", "duration": 13.5, "kicker": "01", "title": "Te conoce", "enter": "rise",
     "shots": [{"src": "intro", "at": 0, "hold": True, "moves": [
         {"t": 1.4, "panel": 140, "dur": 0.8},
         {"t": 9.4, "rect": None, "dur": 0.8}]}]},
    {"id": "perfil", "duration": 8.5, "kicker": "02", "title": "Arma tu perfil conversando", "enter": "whip",
     "shots": [{"src": "progress", "at": 0, "panel": 160,
                "moves": [{"t": 5.6, "panel": 300, "dur": 0.7}]}],
     "celebration": {"at": 1.6, "dur": 3.6, "title": "Perfil listo", "detail": "El profe ya sabe quién eres y qué quieres lograr."}},
    {"id": "taller", "duration": 13.0, "kicker": "03", "title": "Prepara tu taller", "enter": "rise",
     "shots": [{"src": "reading", "at": 0, "panel": 120},
               {"src": "workshop", "at": 2.2, "moves": [
                   {"t": 6.0, "panel": 255, "dur": 0.8},
                   {"t": 9.4, "panel": 440, "dur": 0.8}]}]},
    {"id": "pizarra", "duration": 12.5, "kicker": "04", "title": "Dibuja mientras explica", "enter": "whip",
     "shots": [{"src": "board-example", "at": 0, "rect": [433, 170, 392, 150],
                "moves": [{"t": 3.6, "rect": [380, 40, 500, 430], "dur": 0.8}]},
               {"src": "board-sim", "at": 6.4, "rect": [433, 258, 392, 314],
                "moves": [{"t": 9.6, "rect": None, "dur": 0.8}]}]},
    {"id": "acierto", "duration": 14.5, "kicker": "05", "title": "Celebra cada hito", "enter": "rise",
     "shots": [{"src": "correct", "at": 0, "rect": [560, 230, 450, 260], "moves": [
         {"t": 4.6, "rect": None, "dur": 0.8},
         {"t": 7.4, "panel": 70, "dur": 0.8}]}]},
    {"id": "avance", "duration": 8.0, "kicker": "06", "title": "Lleva tu avance", "enter": "whip",
     "shots": [{"src": "progress", "at": 0, "panel": 300, "hold": True, "moves": [
         {"t": 3.6, "panel": 420, "dur": 0.7}]}]},
    {"id": "memoria", "duration": 13.7, "kicker": "07", "title": "Y te recuerda", "enter": "rise",
     "shots": [{"src": "memory", "at": 0, "hold": True, "moves": [
         {"t": 1.0, "panel": 60, "dur": 0.8},
         {"t": 8.6, "rect": None, "dur": 0.8}]}]},
]

if __name__ == "__main__":
    out = ROOT / "compositions"
    out.mkdir(exist_ok=True)
    for spec in SCENES:
        (out / f"{spec['id']}.html").write_text(scene(spec), encoding="utf-8")
        print("escena", spec["id"])
