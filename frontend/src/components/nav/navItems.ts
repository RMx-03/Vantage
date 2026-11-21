import { workbenchEnabled } from '../../lib/flags';

export interface NavItem {
  label: string;
  icon: string;
  to: string | null;
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Terminal', icon: 'terminal', to: '/app/research' },
  { label: 'Portfolio', icon: 'account_balance_wallet', to: null },
  { label: 'Risk', icon: 'query_stats', to: null },
  { label: 'Settings', icon: 'settings', to: '/app/settings' },
];

const WORKBENCH: NavItem = { label: 'Workbench', icon: 'science', to: '/app/workbench' };

export function navItems(): NavItem[] {
  if (!workbenchEnabled()) return NAV_ITEMS;
  return [NAV_ITEMS[0], WORKBENCH, ...NAV_ITEMS.slice(1)];
}
