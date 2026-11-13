import { useState } from 'react';
import type { Quest, Question } from '../lib/live';

interface Props {
  question: Question | null;
  quests: Quest[];
  onAnswer: (q: Question, choice: number) => void;
  onQuestProgress: (quest: Quest, done: number) => void;
}

export function QuestPanel({ question, quests, onAnswer, onQuestProgress }: Props) {
  return (
    <section className="quests" aria-label="Retos y preguntas">
      {question && <QuestionCard key={question.id} q={question} onAnswer={onAnswer} />}
      {quests.map((quest) => (
        <QuestCard key={quest.id} quest={quest} onProgress={onQuestProgress} />
      ))}
      {!question && quests.length === 0 && (
        <p className="quests-empty">Aquí aparecerán las preguntas y los retos que te proponga el profe.</p>
      )}
    </section>
  );
}

function QuestionCard({ q, onAnswer }: { q: Question; onAnswer: Props['onAnswer'] }) {
  const [picked, setPicked] = useState<number | null>(null);
  const answered = picked !== null;
  return (
    <article className="qcard">
      <header className="qcard-head">Pregunta</header>
      <p className="qcard-question">{q.question}</p>
      <div className="qcard-options">
        {q.options.map((option, i) => {
          const state = !answered ? '' : i === q.correct ? 'is-correct' : i === picked ? 'is-wrong' : 'is-dim';
          return (
            <button
              key={i}
              className={`qopt ${state}`}
              disabled={answered}
              onClick={() => {
                setPicked(i);
                onAnswer(q, i);
              }}
            >
              <span className="qopt-letter">{'ABCD'[i]}</span>
              {option}
            </button>
          );
        })}
      </div>
      {answered && picked !== q.correct && q.hint && <p className="qcard-hint">Pista: {q.hint}</p>}
    </article>
  );
}

function QuestCard({ quest, onProgress }: { quest: Quest; onProgress: Props['onQuestProgress'] }) {
  const [done, setDone] = useState<boolean[]>(() => quest.steps.map(() => false));
  const count = done.filter(Boolean).length;
  const complete = count === quest.steps.length;
  return (
    <article className={`qcard quest ${complete ? 'is-complete' : ''}`}>
      <header className="qcard-head">
        Reto <span className="quest-count">{count}/{quest.steps.length}</span>
      </header>
      <p className="qcard-question">{quest.title}</p>
      <div className="quest-bar">
        <span style={{ width: `${(count / quest.steps.length) * 100}%` }} />
      </div>
      <ol className="quest-steps">
        {quest.steps.map((step, i) => (
          <li key={i}>
            <label>
              <input
                type="checkbox"
                checked={done[i]}
                onChange={() => {
                  const next = done.map((d, j) => (j === i ? !d : d));
                  setDone(next);
                  onProgress(quest, next.filter(Boolean).length);
                }}
              />
              <span>{step}</span>
            </label>
          </li>
        ))}
      </ol>
      {complete && quest.reward && <p className="quest-reward">★ {quest.reward}</p>}
    </article>
  );
}
