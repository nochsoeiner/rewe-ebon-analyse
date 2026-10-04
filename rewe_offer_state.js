// REWE's validTo denotes the displayed German calendar date, including that day.
function marketOfferState(row, checkedAt, now = new Date()) {
  if (row.status !== 'offer') return row;
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Berlin', year: 'numeric', month: '2-digit', day: '2-digit'
  }).formatToParts(now);
  const part = type => parts.find(p => p.type === type).value;
  const today = `${part('year')}-${part('month')}-${part('day')}`;
  const match = typeof row.validUntil === 'string'
    ? row.validUntil.match(/^(\d{4}-\d{2}-\d{2})(?:T.*)?$/) : null;
  const parsed = match ? new Date(match[1] + 'T00:00:00Z') : null;
  if (parsed && Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === match[1]) {
    return match[1] < today ? {...row, status: 'expired'} : row;
  }
  const age = now.getTime() - new Date(checkedAt).getTime();
  return Number.isFinite(age) && age >= 0 && age <= 30 * 3600 * 1000
    ? row : {...row, status: 'unconfirmed'};
}
