import type { ReactNode } from 'react';

export default function MicroLabel({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`font-label text-[10px] uppercase tracking-widest text-outline ${className}`}
    >
      {children}
    </span>
  );
}
