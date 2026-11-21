import { useState } from 'react';
import MicroLabel from './MicroLabel';

export interface ChartSeries {
  name: string;
  values: (number | null)[];
}

// Dash patterns keep series apart without relying on colour alone.
const STYLES = [
  { className: 'stroke-primary', dash: undefined },
  { className: 'stroke-outline', dash: '6 4' },
  { className: 'stroke-on-surface-variant', dash: '2 3' },
  { className: 'stroke-primary-dim', dash: '10 3 2 3' },
];
const WIDTH = 600;
const HEIGHT = 220;

const finite = (v: number | null | undefined): v is number =>
  typeof v === 'number' && Number.isFinite(v);

/** One SVG path per series; a missing value starts a new segment, never a bridge. */
function pathFor(values: (number | null)[], x: (i: number) => number, y: (v: number) => number) {
  let d = '';
  let drawing = false;
  values.forEach((v, i) => {
    if (!finite(v)) {
      drawing = false;
      return;
    }
    d += `${drawing ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    drawing = true;
  });
  return d;
}

export default function LineChart({
  title,
  dates,
  series,
  format,
}: {
  title: string;
  dates: string[];
  series: ChartSeries[];
  format: (n: number) => string;
}) {
  const [showTable, setShowTable] = useState(false);
  const all = series.flatMap((s) => s.values.filter(finite));
  const lo = all.length ? Math.min(...all) : 0;
  const hi = all.length ? Math.max(...all) : 1;
  const span = hi - lo || 1;
  const x = (i: number) => (dates.length > 1 ? (i / (dates.length - 1)) * WIDTH : WIDTH / 2);
  const y = (v: number) => HEIGHT - ((v - lo) / span) * HEIGHT;

  return (
    <figure className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-4">
        {series.map((s, i) => (
          <span key={s.name} className="flex items-center gap-2">
            <svg aria-hidden="true" width="24" height="8">
              <line
                x1="0"
                y1="4"
                x2="24"
                y2="4"
                strokeWidth="2"
                strokeDasharray={STYLES[i % STYLES.length].dash}
                className={STYLES[i % STYLES.length].className}
              />
            </svg>
            <MicroLabel>{s.name}</MicroLabel>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <div className="flex flex-col justify-between text-right">
          <MicroLabel>{format(hi)}</MicroLabel>
          <MicroLabel>{format(lo)}</MicroLabel>
        </div>
        <svg
          role="img"
          aria-label={title}
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          preserveAspectRatio="none"
          className="h-56 w-full border-l border-b border-outline-variant"
        >
          {series.map((s, i) => (
            <path
              key={s.name}
              data-series={s.name}
              d={pathFor(s.values, x, y)}
              fill="none"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
              strokeDasharray={STYLES[i % STYLES.length].dash}
              className={STYLES[i % STYLES.length].className}
            />
          ))}
        </svg>
      </div>
      <div className="flex justify-between pl-12">
        <MicroLabel>{dates[0]}</MicroLabel>
        <MicroLabel>{dates[dates.length - 1]}</MicroLabel>
      </div>
      <button
        type="button"
        aria-expanded={showTable}
        onClick={() => setShowTable((v) => !v)}
        className="self-start text-xs font-label uppercase tracking-widest text-on-surface-variant underline hover:text-on-surface"
      >
        {showTable ? 'Hide data table' : 'Show data table'}
      </button>
      {showTable && (
        <div className="max-h-80 overflow-auto border border-outline-variant">
          <table className="w-full text-left text-sm font-label">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr>
                <th scope="col" className="p-2">Date</th>
                {series.map((s) => (
                  <th key={s.name} scope="col" className="p-2">
                    {s.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dates.map((date, i) => (
                <tr key={date} className="border-t border-outline-variant/40">
                  <td className="p-2">{date}</td>
                  {series.map((s) => {
                    const v = s.values[i];
                    return (
                      <td key={s.name} className="p-2">
                        {finite(v) ? format(v) : '—'}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </figure>
  );
}
