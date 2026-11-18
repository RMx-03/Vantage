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

/**
 * An unparsable or empty value renders as "Unavailable" rather than throwing,
 * because a RangeError here would blank the whole result page.
 */
export function formatUtcDate(value: string): string {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return 'Unavailable';
  return MARKET_DATE_FORMATTER.format(date);
}
