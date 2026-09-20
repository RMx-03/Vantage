export interface NavItem {
  label: string;
  icon: string;
  to: string | null;
}

export const NAV_ITEMS: NavItem[] = [
  { label: 'Terminal', icon: 'terminal', to: '/app/research' },
  { label: 'Portfolio', icon: 'account_balance_wallet', to: null },
  { label: 'Risk', icon: 'query_stats', to: null },
  { label: 'Settings', icon: 'settings', to: '/app/settings' },
];
