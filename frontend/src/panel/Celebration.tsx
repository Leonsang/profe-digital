import { useEffect, useMemo } from 'react';
import type { Milestone } from '../lib/live';

const COLORS = ['#2f6fed', '#e2552b', '#1f9d63', '#f2b632', '#9b4ddb'];

/** Celebración de un hito: tarjeta central con confeti. Se cierra sola a los 5 s. */
export function Celebration({ milestone, onDone }: { milestone: Milestone; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 5000);
    return () => clearTimeout(t);
  }, [milestone, onDone]);

  const confetti = useMemo(
    () =>
      Array.from({ length: 36 }, (_, i) => ({
        left: Math.random() * 100,
        delay: Math.random() * 0.6,
        duration: 1.8 + Math.random() * 1.6,
        color: COLORS[i % COLORS.length],
        rotate: Math.random() * 360,
      })),
    [milestone],
  );

  return (
    // La capa no bloquea la clase: se puede seguir escribiendo o dibujando; solo la tarjeta se cierra al tocarla.
    <div className="celebration" role="status" aria-live="assertive">
      <div className="confetti" aria-hidden>
        {confetti.map((c, i) => (
          <span
            key={i}
            style={{
              left: `${c.left}%`,
              background: c.color,
              animationDelay: `${c.delay}s`,
              animationDuration: `${c.duration}s`,
              transform: `rotate(${c.rotate}deg)`,
            }}
          />
        ))}
      </div>
      <div className="celebration-card" onClick={onDone}>
        <span className="celebration-kicker">¡Nuevo logro!</span>
        <strong>{milestone.title}</strong>
        {milestone.detail && <p>{milestone.detail}</p>}
      </div>
    </div>
  );
}
