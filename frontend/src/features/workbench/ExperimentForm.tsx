import type { FormEvent, ReactNode } from 'react';
import { MicroLabel, Panel } from '../../components/ui';
import type { Template } from '../../types/experiments';
import type { ExperimentForm as Form, FormErrors, FormField } from './specBuilder';

const INPUT =
  'w-full bg-surface-container-lowest border border-outline-variant focus:border-primary focus:outline-none text-on-surface font-label p-3 placeholder:text-outline-variant aria-[invalid=true]:border-error';
const BUTTON =
  'px-6 py-3 text-xs font-bold font-label uppercase tracking-widest transition-opacity disabled:opacity-50 disabled:cursor-not-allowed';

const TEMPLATES: { value: Template; label: string }[] = [
  { value: 'buy_and_hold', label: 'Equal-weight hold' },
  { value: 'sma_crossover', label: 'Moving-average crossover' },
  { value: 'momentum_top_k', label: 'Momentum, top k monthly' },
];

interface Props {
  value: Form;
  errors: FormErrors;
  onChange: (field: FormField, value: string) => void;
  onPreview: () => void;
  onSubmit: () => void;
  previewing: boolean;
  submitting: boolean;
}

export default function ExperimentForm({
  value,
  errors,
  onChange,
  onPreview,
  onSubmit,
  previewing,
  submitting,
}: Props) {
  const field = (name: FormField, label: string, hint?: string) => ({
    name,
    label,
    hint,
    error: errors[name],
    value: value[name],
    onChange: (next: string) => onChange(name, next),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit();
  };

  return (
    <Panel className="flex flex-col gap-6">
      <form onSubmit={submit} noValidate className="flex flex-col gap-6">
        <Field {...field('question', 'Question', 'What do you want to learn?')} multiline />
        <Field {...field('hypothesis', 'Hypothesis', 'Optional')} multiline />
        <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
          <Field {...field('symbols', 'Symbols', 'Up to 50, separated by spaces or commas')} />
          <Field {...field('benchmark', 'Benchmark')} />
        </div>
        <div className="grid gap-6 md:grid-cols-3">
          <Field {...field('start', 'Start date')} type="date" />
          <Field {...field('end', 'End date', 'Optional; latest session if empty')} type="date" />
          <Field {...field('cost_bps', 'Cost per side', 'Basis points')} type="number" />
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="exp-template" className="text-xs font-label text-outline uppercase tracking-widest">
            Template
          </label>
          <select
            id="exp-template"
            value={value.template}
            onChange={(e) => onChange('template', e.target.value)}
            className={INPUT}
          >
            {TEMPLATES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        {value.template === 'sma_crossover' && (
          <div className="grid gap-6 md:grid-cols-2">
            <Field {...field('fast', 'Fast average', 'Sessions, 5 to 100')} type="number" />
            <Field {...field('slow', 'Slow average', 'Sessions, 20 to 250')} type="number" />
          </div>
        )}
        {value.template === 'momentum_top_k' && (
          <div className="grid gap-6 md:grid-cols-2">
            <div className="flex flex-col gap-2">
              <label htmlFor="exp-lookback" className="text-xs font-label text-outline uppercase tracking-widest">
                Lookback
              </label>
              <select
                id="exp-lookback"
                value={value.lookback}
                onChange={(e) => onChange('lookback', e.target.value)}
                className={INPUT}
              >
                <option value="126">126 sessions</option>
                <option value="252">252 sessions</option>
              </select>
            </div>
            <Field {...field('k', 'Top k', 'Names held, 1 to 10')} type="number" />
          </div>
        )}
        {value.template !== 'buy_and_hold' && (
          <Field
            {...field(
              'candidates',
              'Candidates',
              `Optional walk-forward grid, one per line: ${
                value.template === 'sma_crossover' ? 'fast,slow' : 'lookback,k'
              }`
            )}
            multiline
          />
        )}
        <Field {...field('notes', 'Notes', 'Optional, private')} multiline />

        <div className="flex flex-col gap-3 md:flex-row">
          <button
            type="button"
            onClick={onPreview}
            disabled={previewing}
            className={`${BUTTON} border border-outline-variant bg-surface-container text-on-surface hover:bg-surface-container-highest`}
          >
            {previewing ? 'Previewing…' : 'Preview plan'}
          </button>
          <button
            type="submit"
            disabled={submitting}
            className={`${BUTTON} bg-primary text-on-primary hover:opacity-90`}
          >
            {submitting ? 'Starting…' : 'Run simulation'}
          </button>
        </div>
      </form>
    </Panel>
  );
}

function Field({
  name,
  label,
  hint,
  error,
  value,
  onChange,
  type = 'text',
  multiline = false,
}: {
  name: FormField;
  label: string;
  hint?: string;
  error?: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  multiline?: boolean;
}) {
  const id = `exp-${name}`;
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ');
  const shared = {
    id,
    value,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': describedBy || undefined,
    className: INPUT,
  };
  let control: ReactNode;
  if (multiline) {
    control = <textarea {...shared} rows={2} onChange={(e) => onChange(e.target.value)} />;
  } else {
    control = <input {...shared} type={type} onChange={(e) => onChange(e.target.value)} />;
  }
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-xs font-label text-outline uppercase tracking-widest">
        {label}
      </label>
      {control}
      {hint && <MicroLabel className="normal-case tracking-normal">
        <span id={`${id}-hint`}>{hint}</span>
      </MicroLabel>}
      {error && (
        <p id={`${id}-error`} className="text-sm text-error font-body">
          {error}
        </p>
      )}
    </div>
  );
}
