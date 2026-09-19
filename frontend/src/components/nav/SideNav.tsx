import { NavLink } from 'react-router-dom';
import { NAV_ITEMS } from './navItems';
import { MicroLabel } from '../ui';

const BASE = 'flex items-center gap-4 p-3 w-full text-sm tracking-tight font-body transition-colors duration-150';

export default function SideNav() {
  return (
    <nav className="flex flex-col gap-4">
      {NAV_ITEMS.map((item) =>
        item.to ? (
          <NavLink
            key={item.label}
            to={item.to}
            className={({ isActive }) =>
              `${BASE} ${
                isActive
                  ? 'text-[#c6c6c7] bg-[#191a1a]'
                  : 'text-[#484848] hover:bg-[#131313] hover:text-[#c6c6c7]'
              }`
            }
          >
            <span aria-hidden="true" className="material-symbols-outlined">
              {item.icon}
            </span>
            {item.label}
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
            {item.label}
            <MicroLabel className="ml-auto">Phase 2</MicroLabel>
          </button>
        )
      )}
    </nav>
  );
}
