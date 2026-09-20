/**
 * Market session dates are anchored to the US exchange calendar, so they must
 * render identically regardless of the viewer's timezone. The formatter is
 * pinned to UTC and to en-US month names; a browser locale never shifts the
 * session a run belongs to.
 */
const MARKET_DATE_FORMATTER = new Intl.DateTimeFormat('en-US', {
  timeZone: 'UTC',
  month: 'short',
  day: 'numeric',
  year: 'numeric',
});

export function formatUtcDate(value: string): string {
  return MARKET_DATE_FORMATTER.format(new Date(value));
}
