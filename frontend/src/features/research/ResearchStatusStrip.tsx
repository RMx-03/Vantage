import type { ResearchRun } from '../../types/research';
import { buildStatusStrip } from './runChrome';

export default function ResearchStatusStrip({ run }: { run: ResearchRun | null }) {
  const strip = buildStatusStrip(run);
  if (!strip) return null;

  return (
    <footer className="mt-20 py-8 border-t border-outline-variant/20 flex flex-col gap-4 items-center">
      <div className="bg-primary/5 px-6 py-2 border border-primary/20">
        <span className="font-label text-[10px] text-primary uppercase tracking-[0.3em]">
          {strip}
        </span>
      </div>
      <p className="font-label text-[10px] text-outline-variant">© 2026 VANTAGE QUANT SYSTEMS</p>
    </footer>
  );
}
