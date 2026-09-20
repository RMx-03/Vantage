import type { ReactNode } from 'react';

export default function Panel({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`bg-surface-container-low border border-outline-variant p-8 ${className}`}
    >
      {children}
    </section>
  );
}
