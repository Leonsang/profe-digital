import { useEffect, useRef, useState } from 'react';
import type { SimKind } from '../lib/live';

const W = 460;
const H = 300;
const G = 9.81;

type Frame = (ctx: CanvasRenderingContext2D, t: number) => { done: boolean; readout: string };

/** Simulaciones con las ecuaciones exactas (no un motor de juego): lo que ve el estudiante es la física real. */
export function Simulation({ kind, a, b, caption }: { kind: SimKind; a: number; b: number; caption?: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [run, setRun] = useState(0);
  const [readout, setReadout] = useState('');

  useEffect(() => {
    const ctx = canvas.current?.getContext('2d');
    if (!ctx) return;
    const frame = builders[kind](a, b);
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = (now - start) / 1000;
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = '#fbfaf6';
      ctx.fillRect(0, 0, W, H);
      const state = frame(ctx, t);
      setReadout(state.readout);
      if (!state.done && t < 30) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [kind, a, b, run]);

  return (
    <figure className="card-figure">
      <canvas ref={canvas} width={W} height={H} className="sim-canvas" />
      <figcaption className="sim-bar">
        <span className="card-caption">{caption}</span>
        <span className="sim-readout">{readout}</span>
        <button
          className="sim-replay"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => setRun((r) => r + 1)}
        >
          ↻ Repetir
        </button>
      </figcaption>
    </figure>
  );
}

const ink = '#22324a';
const accent = '#e2552b';

function ball(ctx: CanvasRenderingContext2D, x: number, y: number, r = 9, color = accent) {
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
}

function label(ctx: CanvasRenderingContext2D, text: string, x: number, y: number) {
  ctx.fillStyle = ink;
  ctx.font = '13px system-ui';
  ctx.fillText(text, x, y);
}

const builders: Record<SimKind, (a: number, b: number) => Frame> = {
  projectile(v0 = 20, deg = 45) {
    v0 = v0 || 20;
    deg = deg || 45;
    const th = (deg * Math.PI) / 180;
    const vx = v0 * Math.cos(th);
    const vy = v0 * Math.sin(th);
    const tFlight = (2 * vy) / G;
    const range = vx * tFlight;
    const hMax = (vy * vy) / (2 * G);
    const scale = Math.min((W - 40) / Math.max(range, 1), (H - 50) / Math.max(hMax, 1));
    const X = (x: number) => 20 + x * scale;
    const Y = (y: number) => H - 24 - y * scale;
    return (ctx, t) => {
      const tt = Math.min(t, tFlight);
      ctx.strokeStyle = ink;
      ctx.beginPath();
      ctx.moveTo(0, Y(0));
      ctx.lineTo(W, Y(0));
      ctx.stroke();
      ctx.setLineDash([4, 5]);
      ctx.strokeStyle = '#2f6fed';
      ctx.beginPath();
      for (let s = 0; s <= tt; s += tFlight / 120) ctx.lineTo(X(vx * s), Y(vy * s - 0.5 * G * s * s));
      ctx.stroke();
      ctx.setLineDash([]);
      const x = vx * tt;
      const y = vy * tt - 0.5 * G * tt * tt;
      ball(ctx, X(x), Y(y));
      label(ctx, `v₀ = ${v0} m/s · θ = ${deg}°`, 12, 18);
      label(ctx, `alcance ${range.toFixed(1)} m · altura máx ${hMax.toFixed(1)} m`, 12, 36);
      return { done: t > tFlight + 1.5, readout: `t = ${tt.toFixed(2)} s · x = ${x.toFixed(1)} m · y = ${Math.max(y, 0).toFixed(1)} m` };
    };
  },

  pendulum(L = 2, deg = 30) {
    L = L || 2;
    deg = deg || 30;
    let th = (deg * Math.PI) / 180;
    let w = 0;
    let last = 0;
    const scale = (H - 70) / L;
    const period = 2 * Math.PI * Math.sqrt(L / G);
    return (ctx, t) => {
      // integración semi-implícita (ecuación no lineal completa)
      const steps = Math.max(1, Math.round((t - last) / 0.002));
      const dt = (t - last) / steps;
      for (let i = 0; i < steps; i++) {
        w += (-G / L) * Math.sin(th) * dt;
        th += w * dt;
      }
      last = t;
      const ox = W / 2;
      const oy = 30;
      const x = ox + L * scale * Math.sin(th);
      const y = oy + L * scale * Math.cos(th);
      ctx.strokeStyle = ink;
      ctx.beginPath();
      ctx.moveTo(ox - 40, oy);
      ctx.lineTo(ox + 40, oy);
      ctx.moveTo(ox, oy);
      ctx.lineTo(x, y);
      ctx.stroke();
      ball(ctx, x, y, 12);
      label(ctx, `L = ${L} m · T ≈ 2π√(L/g) = ${period.toFixed(2)} s`, 12, 18);
      return { done: false, readout: `t = ${t.toFixed(1)} s · θ = ${((th * 180) / Math.PI).toFixed(1)}°` };
    };
  },

  spring(k = 20, m = 1) {
    k = k || 20;
    m = m || 1;
    const w = Math.sqrt(k / m);
    const A = 0.5;
    const period = (2 * Math.PI) / w;
    return (ctx, t) => {
      const x = A * Math.cos(w * t);
      const wall = 30;
      const rest = W / 2;
      const px = rest + x * 260;
      ctx.strokeStyle = ink;
      ctx.beginPath();
      ctx.moveTo(wall, 80);
      ctx.lineTo(wall, 220);
      ctx.moveTo(0, 220);
      ctx.lineTo(W, 220);
      ctx.stroke();
      ctx.beginPath();
      const coils = 14;
      for (let i = 0; i <= coils; i++) {
        const sx = wall + ((px - 30 - wall) * i) / coils;
        ctx.lineTo(sx, 170 + (i % 2 === 0 ? -14 : 14) * (i > 0 && i < coils ? 1 : 0));
      }
      ctx.stroke();
      ctx.fillStyle = accent;
      ctx.fillRect(px - 30, 140, 60, 60);
      ctx.setLineDash([3, 4]);
      ctx.beginPath();
      ctx.moveTo(rest, 120);
      ctx.lineTo(rest, 220);
      ctx.stroke();
      ctx.setLineDash([]);
      label(ctx, `k = ${k} N/m · m = ${m} kg · T = 2π√(m/k) = ${period.toFixed(2)} s`, 12, 18);
      return { done: false, readout: `x = ${x.toFixed(2)} m · F = ${(-k * x).toFixed(1)} N` };
    };
  },

  incline(deg = 30, mu = 0.2) {
    deg = deg || 30;
    const th = (deg * Math.PI) / 180;
    const acc = G * (Math.sin(th) - mu * Math.cos(th));
    const len = 9;
    const base = { x: 40, y: H - 30 };
    const top = { x: base.x + (W - 80) * 1, y: base.y - (W - 80) * Math.tan(th) };
    const clampTop = top.y < 40 ? { x: base.x + (base.y - 40) / Math.tan(th), y: 40 } : top;
    const pxPerM = Math.hypot(clampTop.x - base.x, clampTop.y - base.y) / len;
    return (ctx, t) => {
      const s = acc > 0 ? Math.min(0.5 * acc * t * t, len) : 0;
      const d = len - s;
      const bx = base.x + d * pxPerM * Math.cos(th);
      const by = base.y - d * pxPerM * Math.sin(th);
      ctx.strokeStyle = ink;
      ctx.fillStyle = '#e8e4da';
      ctx.beginPath();
      ctx.moveTo(base.x, base.y);
      ctx.lineTo(clampTop.x, clampTop.y);
      ctx.lineTo(clampTop.x, base.y);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.save();
      ctx.translate(bx, by);
      ctx.rotate(-th);
      ctx.fillStyle = accent;
      ctx.fillRect(-18, -30, 36, 30);
      ctx.restore();
      label(ctx, `θ = ${deg}° · μ = ${mu} · a = g(sinθ − μcosθ) = ${acc.toFixed(2)} m/s²`, 12, 18);
      if (acc <= 0) label(ctx, 'La fricción gana: el bloque no se mueve.', 12, 36);
      return { done: s >= len || acc <= 0, readout: `t = ${t.toFixed(2)} s · v = ${(Math.max(acc, 0) * t).toFixed(2)} m/s` };
    };
  },

  collision(m1 = 2, m2 = 1) {
    m1 = m1 || 2;
    m2 = m2 || 1;
    const u1 = 3;
    const u2 = -1;
    const v1 = ((m1 - m2) * u1 + 2 * m2 * u2) / (m1 + m2);
    const v2 = ((m2 - m1) * u2 + 2 * m1 * u1) / (m1 + m2);
    const scale = 40;
    const r1 = 12 + 6 * Math.cbrt(m1);
    const r2 = 12 + 6 * Math.cbrt(m2);
    // los centros arrancan a 160 px; chocan cuando la distancia entre centros es r1 + r2
    const tHit = (160 - r1 - r2) / scale / (u1 - u2);
    return (ctx, t) => {
      const x1 = t < tHit ? W / 2 - 80 + u1 * scale * t : W / 2 - 80 + u1 * scale * tHit + v1 * scale * (t - tHit);
      const x2 = t < tHit ? W / 2 + 80 + u2 * scale * t : W / 2 + 80 + u2 * scale * tHit + v2 * scale * (t - tHit);
      ctx.strokeStyle = ink;
      ctx.beginPath();
      ctx.moveTo(0, 200);
      ctx.lineTo(W, 200);
      ctx.stroke();
      ball(ctx, x1, 200 - r1, r1, accent);
      ball(ctx, x2, 200 - r2, r2, '#2f6fed');
      label(ctx, `m₁ = ${m1} kg, m₂ = ${m2} kg · choque elástico`, 12, 18);
      label(ctx, `antes: ${u1} y ${u2} m/s → después: ${v1.toFixed(2)} y ${v2.toFixed(2)} m/s`, 12, 36);
      const p = t < tHit ? m1 * u1 + m2 * u2 : m1 * v1 + m2 * v2;
      return { done: x1 < -40 || x2 > W + 40 || t > tHit + 4, readout: `p total = ${p.toFixed(2)} kg·m/s` };
    };
  },
};
