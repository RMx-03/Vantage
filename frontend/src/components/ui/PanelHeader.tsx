import type { ReactNode } from 'react';

export default function PanelHeader({
  children,
  icon,
}: {
  children: ReactNode;
  icon?: string;
}) {
  return (
    <h2 className="font-headline text-xs font-bold uppercase tracking-widest text-primary flex items-center gap-2">
      {icon && (
        <span aria-hidden="true" className="material-symbols-outlined text-sm">
          {icon}
        </span>
      )}
      {children}
    </h2>
  );
}
