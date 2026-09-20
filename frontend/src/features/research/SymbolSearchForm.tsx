import type { FormEvent } from 'react';
import { MicroLabel } from '../../components/ui';

interface SymbolSearchFormProps {
  value: string;
  onChange: (val: string) => void;
  onSubmit: (e?: FormEvent) => void;
  recent: string[];
  onPickRecent: (sym: string) => void;
  submitting: boolean;
  valid: boolean;
}

export default function SymbolSearchForm({
  value,
  onChange,
  onSubmit,
  recent,
  onPickRecent,
  submitting,
  valid,
}: SymbolSearchFormProps) {
  return (
    <>
      <form onSubmit={onSubmit} className="flex flex-col gap-2">
        <label
          htmlFor="symbol-input"
          className="text-xs font-label text-outline uppercase tracking-widest"
        >
          US equity symbol
        </label>
        <div className="flex flex-col md:flex-row gap-0">
          <div className="flex-1 bg-surface-container-low border border-outline-variant focus-within:border-primary transition-colors">
            <input
              id="symbol-input"
              type="text"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              placeholder="e.g. AAPL, MSFT, NVDA"
              className="w-full bg-transparent border-none focus:outline-none focus:ring-0 text-on-surface font-label p-4 placeholder:text-outline-variant"
            />
          </div>
          <button
            type="submit"
            disabled={!valid || submitting}
            className="bg-primary text-on-primary font-bold px-8 py-4 hover:opacity-90 transition-opacity uppercase tracking-widest text-xs disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Run research
          </button>
        </div>
      </form>

      {recent.length > 0 && (
        <div className="flex gap-4 overflow-x-auto">
          <MicroLabel>Recent:</MicroLabel>
          {recent.map((sym) => (
            <button
              key={sym}
              type="button"
              onClick={() => onPickRecent(sym)}
              className="font-label text-[10px] text-primary uppercase tracking-tighter hover:text-on-surface transition-colors"
            >
              ${sym}
            </button>
          ))}
        </div>
      )}
    </>
  );
}
