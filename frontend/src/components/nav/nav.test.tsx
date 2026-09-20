import { screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { renderWithRouter } from '../../test/renderWithRouter';
import SideNav from './SideNav';
import { NAV_ITEMS } from './navItems';

describe('SideNav', () => {
  it('renders every configured destination', () => {
    renderWithRouter(<SideNav />, { route: '/app/research' });
    for (const item of NAV_ITEMS) {
      expect(screen.getByText(item.label)).toBeVisible();
    }
  });

  it('marks the active destination with aria-current', () => {
    renderWithRouter(<SideNav />, { route: '/app/settings/profile' });
    expect(screen.getByRole('link', { name: /Settings/i })).toHaveAttribute(
      'aria-current',
      'page'
    );
  });

  it('renders phase-2 destinations as disabled, not links', () => {
    renderWithRouter(<SideNav />, { route: '/app/research' });
    expect(screen.queryByRole('link', { name: /Portfolio/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Portfolio/i })).toBeDisabled();
  });
});
