import { useRef, useState } from 'react';
import { API, studentId, type Progress, type Workshop } from '../lib/live';

const STATUS: Record<string, string> = {
  pending: 'Pendiente',
  in_progress: 'En curso',
  done: 'Resuelto',
  skipped: 'Para después',
};

interface Props {
  workshop: Workshop | null;
  live: boolean;
  onUploaded: (progress: Progress) => void;
}

export function WorkshopPanel({ workshop, live, onUploaded }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const upload = async (file: File) => {
    setBusy(true);
    setError('');
    try {
      const body = new FormData();
      body.append('file', file);
      const res = await fetch(`${API}/api/students/${studentId()}/workshop`, { method: 'POST', body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'No pude leer el taller.');
      onUploaded(data as Progress);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  };

  const exercises = workshop?.plan.exercises ?? [];
  const done = exercises.filter((e) => e.status === 'done').length;

  return (
    <section className="workshop" aria-label="Taller">
      <label className={`dropzone ${busy ? 'is-busy' : ''}`}>
        <input
          ref={input}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.md"
          disabled={busy}
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
        />
        <strong>{busy ? 'El profe está leyendo tu taller…' : workshop ? 'Subir otro taller' : 'Sube tu taller'}</strong>
        <small>{busy ? 'Extrae los ejercicios y prepara la clase.' : 'PDF, foto o texto. El profe lo prepara y te guía sin darte las respuestas.'}</small>
      </label>
      {error && <p className="detail">{error}</p>}

      {workshop && (
        <article className={`qcard ${workshop.status === 'done' ? 'quest is-complete' : ''}`}>
          <header className="qcard-head">
            Taller activo <span className="quest-count">{done}/{exercises.length}</span>
          </header>
          <p className="qcard-question">{workshop.title}</p>
          <p className="qcard-hint">{workshop.plan.summary}</p>
          <div className="quest-bar">
            <span style={{ width: `${exercises.length ? (done / exercises.length) * 100 : 0}%` }} />
          </div>
          {workshop.plan.prerequisites.length > 0 && (
            <p className="prereq">
              <strong>Antes de empezar:</strong> {workshop.plan.prerequisites.join(' · ')}
            </p>
          )}
          <ol className="exercises">
            {exercises.map((ex, i) => (
              <li key={i} className={`exercise is-${ex.status}`}>
                <div className="exercise-head">
                  <span className="exercise-n">{i + 1}</span>
                  <span className={`chip ${ex.status}`}>{STATUS[ex.status] ?? ex.status}</span>
                  <span className="chip level">{ex.difficulty}</span>
                </div>
                <p>{ex.statement}</p>
                {ex.note && <small className="exercise-note">{ex.note}</small>}
              </li>
            ))}
          </ol>
          {!live && workshop.status !== 'done' && (
            <p className="qcard-hint">Empieza la clase y el profe arrancará con este taller.</p>
          )}
        </article>
      )}
    </section>
  );
}
