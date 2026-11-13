import type { Progress } from '../lib/live';

const MASTERED = 80;

const BADGES: Record<string, string> = {
  first_session: '🎒',
  profile: '🪪',
  first_correct: '✅',
  answers: '🔥',
  streak: '📅',
  sessions: '🏫',
  mastered: '🏅',
  quest: '🗺️',
  workshop: '📝',
};

function badge(key: string): string {
  const base = key.split(/[:_]\d*/)[0];
  const match = Object.keys(BADGES).find((k) => key.startsWith(k) || base === k);
  return match ? BADGES[match] : '⭐';
}

export function ProgressPanel({ progress }: { progress: Progress | null }) {
  if (!progress) return <p className="quests-empty">Cargando tu avance…</p>;
  const { profile, skills, milestones, memories } = progress;
  const mastered = skills.filter((s) => s.mastery >= MASTERED).length;

  return (
    <section className="progress" aria-label="Mi avance">
      <article className="qcard profile-card">
        <header className="qcard-head">Tu perfil</header>
        {profile.name ? (
          <>
            <p className="profile-name">{profile.name}</p>
            <dl className="profile-list">
              {profile.grade && (
                <>
                  <dt>Nivel</dt>
                  <dd>{profile.grade}</dd>
                </>
              )}
              {profile.goals && (
                <>
                  <dt>Meta</dt>
                  <dd>{profile.goals}</dd>
                </>
              )}
              {profile.preferences && (
                <>
                  <dt>Aprende mejor</dt>
                  <dd>{profile.preferences}</dd>
                </>
              )}
            </dl>
          </>
        ) : (
          <p className="qcard-hint">El profe te conocerá conversando: tu nombre, tu nivel y qué quieres lograr.</p>
        )}
      </article>

      <div className="stats">
        <Stat value={progress.streak} label={progress.streak === 1 ? 'día de racha' : 'días de racha'} />
        <Stat value={progress.sessions} label="clases" />
        <Stat value={mastered} label="dominadas" />
        <Stat value={milestones.length} label="logros" />
      </div>

      <article className="qcard">
        <header className="qcard-head">Habilidades</header>
        {skills.length === 0 ? (
          <p className="qcard-hint">Responde preguntas y resuelve ejercicios: aquí verás cómo crece cada habilidad.</p>
        ) : (
          <ul className="skills">
            {skills.map((s) => (
              <li key={s.skill}>
                <div className="skill-row">
                  <span className="skill-name">{s.skill}</span>
                  <span className="skill-pct">{s.mastery}%</span>
                </div>
                <div className={`skill-bar ${s.mastery >= MASTERED ? 'is-mastered' : ''}`}>
                  <span style={{ width: `${s.mastery}%` }} />
                </div>
                <small className="skill-meta">
                  {s.topic && `${s.topic} · `}
                  {s.correct}/{s.attempts} aciertos
                </small>
              </li>
            ))}
          </ul>
        )}
      </article>

      <article className="qcard">
        <header className="qcard-head">Logros</header>
        {milestones.length === 0 ? (
          <p className="qcard-hint">Tu primer logro llega muy pronto.</p>
        ) : (
          <ul className="badges">
            {milestones.map((m) => (
              <li key={m.key} title={m.detail}>
                <span className="badge-icon" aria-hidden>
                  {badge(m.key)}
                </span>
                <span>
                  <strong>{m.title}</strong>
                  {m.detail && <small>{m.detail}</small>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </article>

      {memories.length > 0 && (
        <article className="qcard">
          <header className="qcard-head">Lo que el profe recuerda de ti</header>
          <ul className="memories">
            {memories.map((m, i) => (
              <li key={i}>
                <span className="memory-tag">{m.category}</span> {m.fact}
              </li>
            ))}
          </ul>
        </article>
      )}
    </section>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
