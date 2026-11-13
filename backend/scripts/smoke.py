"""Prueba de punta a punta: abre el WS, pide un tema por texto y resume lo que llega."""
import asyncio, json, sys, time
import websockets

URL = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8000/ws/smoke"
PROMPT = sys.argv[2] if len(sys.argv) > 2 else "Explícame el teorema de Pitágoras con un dibujo y una fórmula, cortito."

async def main():
    audio = 0; kinds = {}; profe = []; t0 = time.time()
    async with websockets.connect(URL, max_size=None) as ws:
        sent = False; turns = 0
        while time.time() - t0 < 60:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=12)
            except asyncio.TimeoutError:
                break
            if isinstance(msg, bytes):
                audio += len(msg); continue
            data = json.loads(msg); k = data["type"]
            key = k + (":" + data["kind"] if k == "board" else "")
            kinds[key] = kinds.get(key, 0) + 1
            if k == "transcript" and data["role"] == "profe" and data["final"]: profe.append(data["text"])
            if k == "error": print("ERROR", data); return
            if k == "turn_complete":
                turns += 1
                if not sent:
                    await ws.send(json.dumps({"type": "text", "text": PROMPT})); sent = True
    print(f"audio: {audio/48000:.1f}s ({audio} bytes)")
    print("eventos:", kinds)
    print("profe dijo:", "".join(profe)[:600])

asyncio.run(main())
