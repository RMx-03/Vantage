import { NavLink } from 'react-router-dom';
import { NAV_ITEMS } from './navItems';
import { MicroLabel } from '../ui';

const BASE =
  'group flex items-center gap-3 px-3 py-2.5 w-full text-xs tracking-wider uppercase font-label transition-colors duration-150 border-l-2';

export default function SideNav() {
  return (
    <nav className="flex flex-col gap-1.5">
      <div className="px-3 pt-1 pb-2 text-[10px] font-label font-medium uppercase tracking-[0.2em] text-outline/70 border-b border-outline-variant/20 mb-1">
        Navigation
      </div>
      {NAV_ITEMS.map((item) =>
        item.to ? (
          <NavLink
            key={item.label}
            to={item.to}
            className={({ isActive }) =>
              `${BASE} ${
                isActive
                  ? 'text-on-surface bg-surface-container-high border-primary font-bold'
                  : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container-low border-transparent'
              }`
            }
          >
            <span
              aria-hidden="true"
              className="material-symbols-outlined text-lg shrink-0 text-outline group-hover:text-primary transition-colors"
            >
              {item.icon}
            </span>
            <span>{item.label}</span>
          </NavLink>
        ) : (
          <button
            key={item.label}
            type="button"
            disabled
            aria-disabled="true"
            className={`${BASE} text-outline-variant border-transparent cursor-not-allowed`}
          >
            <span aria-hidden="true" className="material-symbols-outlined text-lg shrink-0 text-outline-variant">
              {item.icon}
            </span>
            <span>{item.label}</span>
            <MicroLabel className="ml-auto text-[9px] px-1.5 py-0.5 border border-outline-variant/30 bg-surface-container-lowest">
              Phase 2
            </MicroLabel>
          </button>
        )
      )}
    </nav>
  );
}
