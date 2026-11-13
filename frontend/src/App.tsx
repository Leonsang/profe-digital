import { useCallback, useEffect, useRef, useState } from 'react';
import { Tldraw, createShapeId, type Editor, type TLShapeId } from 'tldraw';
import 'tldraw/tldraw.css';
import 'katex/dist/katex.min.css';
import { CARD, CardShapeUtil, cardSize } from './board/CardShape';
import { LiveSession, type BoardEvent, type Quest, type Question, type ServerEvent, type Status } from './lib/live';
import { QuestPanel } from './panel/QuestPanel';

const shapeUtils = [CardShapeUtil];
const COLUMN_W = 520;
const COLUMN_H = 1500;
const LICENSE = import.meta.env.VITE_TLDRAW_LICENSE_KEY as string | undefined;

interface Line {
  role: 'user' | 'profe';
  text: string;
}

export default function App() {
  const editorRef = useRef<Editor | null>(null);
  const session = useRef<LiveSession | null>(null);
  const cursor = useRef({ x: 0, y: 0 });
  const placed = useRef(new Map<string, TLShapeId>());

  const [status, setStatus] = useState<Status>('idle');
  const [detail, setDetail] = useState('');
  const [speaking, setSpeaking] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [muted, setMuted] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [draft, setDraft] = useState<Line | null>(null);
  const [question, setQuestion] = useState<Question | null>(null);
  const [quests, setQuests] = useState<Quest[]>([]);
  const [typed, setTyped] = useState('');
  const [sending, setSending] = useState(false);
  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = transcriptRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines, draft]);

  // ---------------------------------------------------------------- pizarra
  const placeCard = useCallback((event: Extract<BoardEvent, { type: 'board' }>) => {
    const editor = editorRef.current;
    if (!editor) return;
    const { w, h } = cardSize(event);
    if (cursor.current.y + h > COLUMN_H && cursor.current.y > 0) {
      cursor.current = { x: cursor.current.x + COLUMN_W, y: 0 };
    }
    const id = createShapeId(event.id);
    const { type: _type, id: _id, ...payload } = event;
    editor.createShape({
      id,
      type: CARD,
      x: cursor.current.x,
      y: cursor.current.y,
      props: { w, h, payload: JSON.stringify(payload) },
    });
    placed.current.set(event.id, id);
    cursor.current.y += h + 28;
    const bounds = editor.getShapePageBounds(id);
    if (bounds) {
      editor.zoomToBounds(bounds.clone().expandBy(80), { targetZoom: 1, animation: { duration: 450 } });
    }
  }, []);

  const handleBoard = useCallback(
    (event: BoardEvent) => {
      const editor = editorRef.current;
      if (!editor) return;
      if (event.type === 'board') placeCard(event);
      else if (event.type === 'board_remove') {
        const id = placed.current.get(event.id);
        if (id) editor.deleteShapes([id]);
      } else if (event.type === 'board_clear') {
        const ids = editor
          .getCurrentPageShapes()
          .filter((s) => s.type === CARD)
          .map((s) => s.id);
        editor.deleteShapes(ids);
        placed.current.clear();
        cursor.current = { x: 0, y: 0 };
      }
    },
    [placeCard],
  );

  // ---------------------------------------------------------------- eventos del profe
  const draftRef = useRef<Line | null>(null);
  const onTranscript = useCallback((role: Line['role'], text: string, final: boolean) => {
    const current = draftRef.current;
    let next: Line | null;
    if (final) {
      const clean = text.trim();
      if (current && current.role !== role) setLines((l) => [...l, current].slice(-40));
      if (clean) setLines((l) => [...l, { role, text: clean }].slice(-40));
      next = null;
    } else if (current && current.role !== role) {
      setLines((l) => [...l, current].slice(-40));
      next = { role, text };
    } else {
      next = { role, text: (current?.text ?? '') + text };
    }
    draftRef.current = next;
    setDraft(next);
  }, []);

  const onEvent = useCallback(
    (event: ServerEvent) => {
      switch (event.type) {
        case 'board':
        case 'board_clear':
        case 'board_remove':
          handleBoard(event);
          break;
        case 'question':
          setQuestion(event);
          break;
        case 'quest':
          setQuests((q) => [event, ...q].slice(0, 4));
          break;
        case 'transcript':
          onTranscript(event.role, event.text, event.final);
          break;
        case 'error':
          setDetail(event.message);
          break;
      }
    },
    [handleBoard, onTranscript],
  );

  const start = async () => {
    setLines([]);
    draftRef.current = null;
    setDraft(null);
    setDetail('');
    const live = new LiveSession({
      onEvent,
      onStatus: (s, d) => {
        setStatus(s);
        if (d) setDetail(d);
      },
      onSpeaking: setSpeaking,
      onMicLevel: setMicLevel,
      onNotice: setDetail,
    });
    session.current = live;
    live.setMuted(muted);
    await live.start();
  };

  const stop = async () => {
    await session.current?.stop();
    session.current = null;
    setStatus('idle');
    setSpeaking(false);
  };

  useEffect(() => () => void session.current?.stop(), []);
  useEffect(() => session.current?.setMuted(muted), [muted]);

  // ---------------------------------------------------------------- acciones del estudiante
  const sendSnapshot = async () => {
    const editor = editorRef.current;
    if (!editor || !session.current) return;
    const mine = editor.getCurrentPageShapes().filter((s) => s.type !== CARD);
    if (mine.length === 0) {
      setDetail('Escribe o dibuja algo en la pizarra primero (lápiz: tecla D).');
      return;
    }
    setSending(true);
    try {
      const { blob } = await editor.toImage(mine, { format: 'png', background: true, padding: 24, scale: 1 });
      session.current.send({ type: 'board_snapshot', data: await blobToBase64(blob) });
      setDetail('');
    } finally {
      setSending(false);
    }
  };

  const sendText = () => {
    const text = typed.trim();
    if (!text || !session.current) return;
    session.current.send({ type: 'text', text });
    setLines((l) => [...l, { role: 'user' as const, text }].slice(-40));
    setTyped('');
  };

  const onAnswer = (q: Question, choice: number) => {
    session.current?.send({ type: 'answer', question: q.question, choice: q.options[choice], correct: choice === q.correct });
  };

  const onQuestProgress = (quest: Quest, done: number) => {
    if (done === quest.steps.length) session.current?.send({ type: 'answer', text: `Terminé el reto "${quest.title}".` });
  };

  const live = status === 'live';

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">∑</span>
          <div>
            <h1>Profe Digital</h1>
            <p>Matemáticas y física, en voz alta y con pizarra</p>
          </div>
        </div>
        <div className="controls">
          <StatusPill status={status} speaking={speaking} />
          {live && (
            <button className={`btn ghost ${muted ? 'is-on' : ''}`} onClick={() => setMuted((m) => !m)}>
              {muted ? 'Micrófono apagado' : 'Silenciar micrófono'}
            </button>
          )}
          {live || status === 'connecting' ? (
            <button className="btn" onClick={stop}>
              Terminar clase
            </button>
          ) : (
            <button className="btn primary" onClick={start}>
              Empezar clase
            </button>
          )}
        </div>
      </header>

      <main className="stage">
        <div className="board">
          <Tldraw
            shapeUtils={shapeUtils}
            licenseKey={LICENSE}
            onMount={(editor) => {
              editorRef.current = editor;
              editor.user.updateUserPreferences({ colorScheme: 'light' });
            }}
          />
          {!live && (
            <div className="board-hint">
              <p>
                Pulsa <strong>Empezar clase</strong> y habla con el profe. Puedes interrumpirlo cuando quieras.
              </p>
              <p>Escribe tu intento con el lápiz (tecla D) y pulsa «Revisa lo que escribí».</p>
            </div>
          )}
        </div>

        <aside className="side">
          <div className="profe">
            <div
              className={`orb ${speaking ? 'is-speaking' : ''} ${live ? 'is-live' : ''}`}
              style={{ ['--mic' as string]: muted ? 0 : Math.min(1, micLevel * 3) }}
            >
              <span>∑</span>
            </div>
            <div className="profe-state">
              <strong>{speaking ? 'El profe está hablando' : live ? 'Te escucho' : 'Profe'}</strong>
              <small>
                {speaking ? 'Habla encima para interrumpirlo' : live ? 'Pregunta, piensa en voz alta, equivócate' : 'Sin conexión'}
              </small>
            </div>
          </div>

          <div className="transcript" aria-live="polite" ref={transcriptRef}>
            {[...lines, ...(draft ? [draft] : [])].slice(-12).map((line, i) => (
              <p key={i} className={`line ${line.role}`}>
                <span>{line.role === 'profe' ? 'Profe' : 'Tú'}</span>
                {line.text}
              </p>
            ))}
          </div>

          <QuestPanel question={question} quests={quests} onAnswer={onAnswer} onQuestProgress={onQuestProgress} />

          <div className="composer">
            <button className="btn wide" disabled={!live || sending} onClick={sendSnapshot}>
              {sending ? 'Enviando…' : 'Revisa lo que escribí'}
            </button>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                sendText();
              }}
            >
              <input
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder={live ? 'O escríbele al profe…' : 'Empieza la clase para escribir'}
                disabled={!live}
              />
            </form>
            {detail && <p className="detail">{detail}</p>}
          </div>
        </aside>
      </main>
    </div>
  );
}

function StatusPill({ status, speaking }: { status: Status; speaking: boolean }) {
  const label =
    status === 'live'
      ? speaking
        ? 'Hablando'
        : 'En vivo'
      : status === 'connecting'
        ? 'Conectando…'
        : status === 'error'
          ? 'Error'
          : 'Desconectado';
  return <span className={`pill ${status}`}>{label}</span>;
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '');
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}
