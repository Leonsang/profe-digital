/**
 * Sesión en vivo con el profe: micrófono -> WebSocket -> Gemini Live (ADK) -> voz + pizarra.
 */

export type BoardEvent =
  | { type: 'board'; id: string; kind: 'text'; text: string }
  | { type: 'board'; id: string; kind: 'formula'; latex: string; caption?: string }
  | { type: 'board'; id: string; kind: 'plot'; expressions: string[]; x_min: number; x_max: number; title?: string }
  | { type: 'board'; id: string; kind: 'svg'; svg: string; caption?: string }
  | { type: 'board'; id: string; kind: 'sim'; sim: SimKind; a: number; b: number; caption?: string }
  | { type: 'board'; id: string; kind: 'image'; url: string; caption?: string; source?: string }
  | { type: 'board'; id: string; kind: 'pending'; text: string }
  | { type: 'board_clear' }
  | { type: 'board_remove'; id: string };

export type SimKind = 'projectile' | 'pendulum' | 'spring' | 'incline' | 'collision';

export interface Question {
  type: 'question';
  id: string;
  question: string;
  options: string[];
  correct: number;
  hint: string;
  skill: string;
  topic: string;
}

export interface Quest {
  type: 'quest';
  id: string;
  title: string;
  steps: string[];
  reward: string;
}

export interface Skill {
  skill: string;
  topic: string;
  mastery: number;
  attempts: number;
  correct: number;
}

export interface Milestone {
  key: string;
  title: string;
  detail: string;
  created_at?: number;
}

export interface WorkshopExercise {
  statement: string;
  skill: string;
  difficulty: 'fácil' | 'media' | 'difícil';
  hint: string;
  status: 'pending' | 'in_progress' | 'done' | 'skipped';
  note?: string;
}

export interface Workshop {
  id: number;
  title: string;
  topic: string;
  status: 'active' | 'done' | 'archived';
  plan: { summary: string; prerequisites: string[]; teaching_plan: string; exercises: WorkshopExercise[] };
}

export interface Progress {
  type: 'progress';
  profile: { name: string; grade: string; goals: string; preferences: string };
  streak: number;
  sessions: number;
  skills: Skill[];
  milestones: Milestone[];
  memories: { category: string; fact: string }[];
  workshop: Workshop | null;
}

export type ServerEvent =
  | BoardEvent
  | Question
  | Quest
  | Progress
  | ({ type: 'milestone' } & Milestone)
  | { type: 'transcript'; role: 'user' | 'profe'; text: string; final: boolean }
  | { type: 'interrupted' }
  | { type: 'turn_complete' }
  | { type: 'error'; message: string };

export type Status = 'idle' | 'connecting' | 'live' | 'closed' | 'error';

export interface LiveHandlers {
  onEvent: (event: ServerEvent) => void;
  onStatus: (status: Status, detail?: string) => void;
  onSpeaking: (speaking: boolean) => void;
  onMicLevel: (level: number) => void;
  onNotice?: (message: string) => void;
}

const BACKEND = (import.meta.env.VITE_BACKEND_WS as string | undefined) ?? 'ws://localhost:8000';
/** Misma URL del backend, en http(s), para la API REST. */
export const API = BACKEND.replace(/^ws/, 'http');

/** Identidad local del estudiante: sin cuentas, el navegador recuerda quién es. */
export function studentId(): string {
  const KEY = 'profe-digital:student';
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = `st-${crypto.randomUUID().replace(/-/g, '').slice(0, 16)}`;
    localStorage.setItem(KEY, id);
  }
  return id;
}

export class LiveSession {
  private ws?: WebSocket;
  private micCtx?: AudioContext;
  private playCtx?: AudioContext;
  private player?: AudioWorkletNode;
  private stream?: MediaStream;
  private muted = false;
  private handlers: LiveHandlers;

  constructor(handlers: LiveHandlers) {
    this.handlers = handlers;
  }

  async start(): Promise<void> {
    this.handlers.onStatus('connecting');
    try {
      this.playCtx = new AudioContext({ sampleRate: 24000 });
      await this.playCtx.audioWorklet.addModule('/worklets/playback.js');
      this.player = new AudioWorkletNode(this.playCtx, 'playback-processor');
      this.player.port.onmessage = (e) => this.handlers.onSpeaking(Boolean(e.data.speaking));
      this.player.connect(this.playCtx.destination);
    } catch (err) {
      this.handlers.onStatus('error', err instanceof Error ? err.message : String(err));
      await this.stop();
      return;
    }

    // En paralelo: si el permiso queda pendiente o se niega, la clase sigue en modo texto.
    this.startMic().catch(() => {
      this.micMissing = true;
      this.handlers.onNotice?.('Sin micrófono: escríbele al profe abajo y te responderá en voz alta.');
    });

    const id = crypto.randomUUID().slice(0, 8);
    const ws = new WebSocket(`${BACKEND}/ws/${id}?student=${encodeURIComponent(studentId())}`);
    ws.binaryType = 'arraybuffer';
    ws.onopen = () => this.handlers.onStatus('live');
    ws.onclose = () => this.handlers.onStatus('closed');
    ws.onerror = () => this.handlers.onStatus('error', 'No se pudo conectar con el servidor del profe.');
    ws.onmessage = (msg) => {
      if (msg.data instanceof ArrayBuffer) {
        this.player?.port.postMessage(msg.data, [msg.data]);
        return;
      }
      const event = JSON.parse(msg.data as string) as ServerEvent;
      if (event.type === 'interrupted') this.player?.port.postMessage('flush');
      this.handlers.onEvent(event);
    };
    this.ws = ws;
  }

  /** true si no hubo permiso o dispositivo de micrófono: modo solo texto. */
  micMissing = false;

  private async startMic() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.micCtx = new AudioContext({ sampleRate: 16000 });
    await this.micCtx.audioWorklet.addModule('/worklets/capture.js');
    const source = this.micCtx.createMediaStreamSource(this.stream);
    const capture = new AudioWorkletNode(this.micCtx, 'capture-processor');
    capture.port.onmessage = (e) => {
      this.handlers.onMicLevel(e.data.peak as number);
      if (!this.muted && this.ws?.readyState === WebSocket.OPEN) this.ws.send(e.data.pcm as ArrayBuffer);
    };
    source.connect(capture);
  }

  setMuted(muted: boolean) {
    this.muted = muted;
  }

  send(payload: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(payload));
  }

  async stop(): Promise<void> {
    this.ws?.close();
    this.stream?.getTracks().forEach((t) => t.stop());
    await this.micCtx?.close().catch(() => {});
    await this.playCtx?.close().catch(() => {});
    this.ws = undefined;
    this.micCtx = this.playCtx = undefined;
    this.player = undefined;
  }
}
