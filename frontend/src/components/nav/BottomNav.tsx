import { NavLink } from 'react-router-dom';
import { NAV_ITEMS } from './navItems';

const BASE = 'flex flex-col items-center justify-center p-2 flex-1 h-full transition-colors';
const LABEL = 'font-label text-[10px] uppercase tracking-widest mt-1';

export default function BottomNav() {
  return (
    <nav className="lg:hidden w-full z-50 flex justify-around items-center h-16 bg-[#0e0e0e] border-t border-[#191a1a] shrink-0">
      {NAV_ITEMS.map((item) =>
        item.to ? (
          <NavLink
            key={item.label}
            to={item.to}
            className={({ isActive }) =>
              `${BASE} ${
                isActive ? 'text-[#c6c6c7] bg-[#191a1a]' : 'text-[#484848] hover:bg-[#131313]'
              }`
            }
          >
            <span aria-hidden="true" className="material-symbols-outlined">
              {item.icon}
            </span>
            <span className={LABEL}>{item.label}</span>
          </NavLink>
        ) : (
          <button
            key={item.label}
            type="button"
            disabled
            aria-disabled="true"
            className={`${BASE} text-outline-variant cursor-not-allowed`}
          >
            <span aria-hidden="true" className="material-symbols-outlined">
              {item.icon}
            </span>
            <span className={LABEL}>{item.label}</span>
          </button>
        )
      )}
    </nav>
  );
}
