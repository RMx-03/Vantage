import { screen } from '@testing-library/react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { renderWithRouter } from '../../test/renderWithRouter';
import SideNav from './SideNav';
import { navItems } from './navItems';

describe('SideNav', () => {
  it('renders every configured destination', () => {
    renderWithRouter(<SideNav />, { route: '/app/research' });
    for (const item of navItems()) {
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

  describe('workbench flag', () => {
    afterEach(() => vi.unstubAllEnvs());

    it('hides the Workbench destination while the flag is off', () => {
      vi.stubEnv('VITE_RESEARCH_WORKBENCH_ENABLED', 'false');
      renderWithRouter(<SideNav />, { route: '/app/research' });
      expect(screen.queryByText('Workbench')).not.toBeInTheDocument();
    });

    it('links to the workbench when the flag is true', () => {
      vi.stubEnv('VITE_RESEARCH_WORKBENCH_ENABLED', 'true');
      renderWithRouter(<SideNav />, { route: '/app/research' });
      expect(screen.getByRole('link', { name: /Workbench/i })).toHaveAttribute(
        'href',
        '/app/workbench'
      );
    });
  });
});
