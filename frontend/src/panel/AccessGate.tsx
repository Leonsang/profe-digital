import { useState } from 'react';
import { API, saveAccessCode } from '../lib/live';

/** Pide el código de acceso cuando el backend lo exige (el demo público gasta la cuota de Gemini). */
export function AccessGate({ onUnlocked }: { onUnlocked: () => void }) {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await fetch(`${API}/api/access`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ code: code.trim() }),
      });
      if (!res.ok) throw new Error('Ese código no es válido.');
      saveAccessCode(code.trim());
      onUnlocked();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No pude verificar el código.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="gate" role="dialog" aria-modal="true" aria-labelledby="gate-title">
      <form
        className="gate-card"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <span className="brand-mark" aria-hidden>
          ∑
        </span>
        <h2 id="gate-title">Profe Digital</h2>
        <p>Este lab usa un modelo de voz en tiempo real. Para entrar, escribe tu código de acceso.</p>
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="Código de acceso"
          autoFocus
          autoComplete="off"
          aria-label="Código de acceso"
        />
        <button className="btn primary wide" disabled={busy || !code.trim()}>
          {busy ? 'Verificando…' : 'Entrar'}
        </button>
        {error && <p className="detail">{error}</p>}
        <a className="gate-link" href="https://github.com/Leonsang/profe-digital" target="_blank" rel="noreferrer">
          ¿Sin código? Mira el demo en GitHub ↗
        </a>
      </form>
    </div>
  );
}
