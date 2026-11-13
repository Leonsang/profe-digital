import DOMPurify from 'dompurify';
import katex from 'katex';
import { compile } from 'mathjs';
import { useMemo } from 'react';
import { BaseBoxShapeUtil, HTMLContainer, T, type RecordProps, type TLShape } from 'tldraw';
import type { BoardEvent } from '../lib/live';
import { Simulation } from './Simulation';

/** Lo que dibuja el profe: una tarjeta con contenido rico dentro de la pizarra. */
export const CARD = 'profe-card';

declare module 'tldraw' {
  export interface TLGlobalShapePropsMap {
    [CARD]: { w: number; h: number; payload: string };
  }
}

export type CardShape = TLShape<typeof CARD>;
type CardPayload = Extract<BoardEvent, { type: 'board' }>;

export class CardShapeUtil extends BaseBoxShapeUtil<CardShape> {
  static override type = CARD;
  static override props: RecordProps<CardShape> = { w: T.number, h: T.number, payload: T.string };

  override canEdit() {
    return false;
  }

  override getDefaultProps(): CardShape['props'] {
    return { w: 480, h: 120, payload: '{"kind":"text","text":""}' };
  }

  override component(shape: CardShape) {
    return (
      <HTMLContainer className="card" style={{ width: shape.props.w, height: shape.props.h }}>
        <CardBody payload={shape.props.payload} />
      </HTMLContainer>
    );
  }

  override getIndicatorPath(shape: CardShape) {
    const path = new Path2D();
    path.roundRect(0, 0, shape.props.w, shape.props.h, 14);
    return path;
  }
}

/** Tamaño inicial de cada tipo de tarjeta en la pizarra. */
export function cardSize(event: CardPayload): { w: number; h: number } {
  switch (event.kind) {
    case 'text':
      return { w: 480, h: Math.max(64, 30 * Math.ceil(event.text.length / 34) + 30) };
    case 'formula':
      return { w: 480, h: event.caption ? 150 : 110 };
    case 'plot':
      return { w: 480, h: 360 };
    case 'svg':
      return { w: 480, h: 400 };
    case 'sim':
      return { w: 480, h: 380 };
    case 'image':
      return { w: 480, h: 400 };
    case 'pending':
      return { w: 480, h: 64 };
  }
}

function CardBody({ payload }: { payload: string }) {
  const data = useMemo(() => JSON.parse(payload) as CardPayload, [payload]);
  switch (data.kind) {
    case 'text':
      return <p className="card-text">{data.text}</p>;
    case 'formula':
      return (
        <div className="card-formula">
          <Formula latex={data.latex} />
          {data.caption && <p className="card-caption">{data.caption}</p>}
        </div>
      );
    case 'plot':
      return <Plot expressions={data.expressions} xMin={data.x_min} xMax={data.x_max} title={data.title} />;
    case 'svg':
      return (
        <figure className="card-figure">
          <div className="card-svg" dangerouslySetInnerHTML={{ __html: cleanSvg(data.svg) }} />
          {data.caption && <figcaption className="card-caption">{data.caption}</figcaption>}
        </figure>
      );
    case 'sim':
      return <Simulation kind={data.sim} a={data.a} b={data.b} caption={data.caption} />;
    case 'image':
      return (
        <figure className="card-figure">
          <img className="card-image" src={data.url} alt={data.caption ?? ''} draggable={false} />
          <figcaption className="card-caption">
            {data.caption}
            {data.source && <span className="card-source"> · {data.source}</span>}
          </figcaption>
        </figure>
      );
    case 'pending':
      return <p className="card-text card-pending">{data.text}</p>;
  }
}

function Formula({ latex }: { latex: string }) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(latex, { displayMode: true, throwOnError: false });
    } catch {
      return latex;
    }
  }, [latex]);
  return <div className="katex-wrap" dangerouslySetInnerHTML={{ __html: html }} />;
}

function cleanSvg(svg: string): string {
  return DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true } });
}

const PLOT_COLORS = ['#2f6fed', '#e2552b', '#1f9d63', '#9b4ddb'];

function Plot({ expressions, xMin, xMax, title }: { expressions: string[]; xMin: number; xMax: number; title?: string }) {
  const W = 460;
  const H = title ? 300 : 330;
  const plot = useMemo(() => {
    const lo = Number.isFinite(xMin) ? xMin : -10;
    const hi = Number.isFinite(xMax) && xMax > lo ? xMax : lo + 20;
    const series = expressions.map((expr) => {
      try {
        const fn = compile(expr);
        return Array.from({ length: 301 }, (_, i) => {
          const x = lo + ((hi - lo) * i) / 300;
          const y = Number(fn.evaluate({ x }));
          return { x, y: Number.isFinite(y) ? y : NaN };
        });
      } catch {
        return [];
      }
    });
    const ys = series.flat().map((p) => p.y).filter((y) => Number.isFinite(y)).sort((a, b) => a - b);
    // recorta extremos (asíntotas) con percentiles
    let yLo = ys.length ? ys[Math.floor(ys.length * 0.02)] : -10;
    let yHi = ys.length ? ys[Math.ceil(ys.length * 0.98) - 1] : 10;
    if (yHi - yLo < 1e-6) {
      yLo -= 1;
      yHi += 1;
    }
    const pad = (yHi - yLo) * 0.1;
    yLo -= pad;
    yHi += pad;
    const sx = (x: number) => ((x - lo) / (hi - lo)) * W;
    const sy = (y: number) => H - ((y - yLo) / (yHi - yLo)) * H;
    const paths = series.map((pts) => {
      let d = '';
      let pen = false;
      for (const p of pts) {
        if (!Number.isFinite(p.y) || p.y < yLo - (yHi - yLo) || p.y > yHi + (yHi - yLo)) {
          pen = false;
          continue;
        }
        d += `${pen ? 'L' : 'M'}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`;
        pen = true;
      }
      return d;
    });
    return { paths, x0: sx(0), y0: sy(0), lo, hi, yLo, yHi, valid: series.map((s) => s.length > 0) };
  }, [expressions, xMin, xMax, H]);

  return (
    <figure className="card-figure">
      {title && <figcaption className="card-title">{title}</figcaption>}
      <svg viewBox={`0 0 ${W} ${H}`} className="plot">
        <rect width={W} height={H} fill="#fbfaf6" />
        {plot.x0 >= 0 && plot.x0 <= W && <line x1={plot.x0} x2={plot.x0} y1={0} y2={H} className="axis" />}
        {plot.y0 >= 0 && plot.y0 <= H && <line x1={0} x2={W} y1={plot.y0} y2={plot.y0} className="axis" />}
        {plot.paths.map((d, i) => (
          <path key={i} d={d} fill="none" stroke={PLOT_COLORS[i % PLOT_COLORS.length]} strokeWidth={2.6} />
        ))}
        <text x={4} y={H - 4} className="tick">{plot.lo}</text>
        <text x={W - 4} y={H - 4} className="tick" textAnchor="end">{plot.hi}</text>
        <text x={4} y={12} className="tick">{plot.yHi.toPrecision(3)}</text>
      </svg>
      <figcaption className="plot-legend">
        {expressions.map((e, i) => (
          <span key={i} style={{ color: PLOT_COLORS[i % PLOT_COLORS.length] }}>
            {plot.valid[i] ? `y = ${e}` : `✗ ${e}`}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
