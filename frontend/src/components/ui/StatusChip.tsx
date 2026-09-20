import type { ResearchStatus } from '../../types/research';

const VARIANTS: Record<string, { label: string; className: string }> = {
  informational: {
    label: 'informational',
    className: 'border-outline-variant bg-surface-container-highest text-on-surface-variant',
  },
  review: {
    label: 'review',
    className: 'border-outline bg-surface-container-highest text-on-surface font-bold',
  },
  insufficient_data: {
    label: 'insufficient data',
    className: 'border-error-container bg-error-container/30 text-error',
  },
  failed: {
    label: 'failed',
    className: 'border-error-container bg-error-container/40 text-error',
  },
  unknown: {
    label: 'unknown',
    className: 'border-outline-variant bg-surface-container text-outline',
  },
};

export default function StatusChip({
  status,
  label,
}: {
  status: ResearchStatus | 'unknown' | null;
  label?: string;
}) {
  const variant = VARIANTS[status ?? 'unknown'] ?? VARIANTS.unknown;
  return (
    <span
      className={`inline-flex items-center border px-3 py-1 font-label text-[10px] uppercase tracking-widest ${variant.className}`}
    >
      {label ?? variant.label}
    </span>
  );
}
