import { useEffect, useState } from 'react';

export default function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const id = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(id);
  }, [copied]);

  const copy = async () => {
    try {
      // Absent in insecure contexts and older browsers; never let it throw.
      await navigator?.clipboard?.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={copy}
        aria-label={label}
        className="text-outline hover:text-primary transition-colors align-middle"
      >
        <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
          content_copy
        </span>
      </button>
      <span aria-live="polite" className="font-label text-[10px] uppercase tracking-widest text-primary">
        {copied ? 'Copied' : ''}
      </span>
    </span>
  );
}
