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

// Several receipt names can map to the same shop product. Keep the receipt
// rows intact and combine only cards with the same product and offer terms.
function groupMarketProducts(rows) {
  const groups = new Map();
  for (const row of rows) {
    const key = row.productId ? JSON.stringify([
      String(row.productId), row.status, row.price, row.regular, row.validUntil
    ]) : Symbol();
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  return Array.from(groups.values(), members => {
    const dated = members.every(row => /^\d{4}-\d{2}-\d{2}$/.test(row.lastPurchaseDate || '')
      && Number.isInteger(row.lastPurchaseId));
    const latest = dated ? members.reduce((a, b) =>
      b.lastPurchaseDate > a.lastPurchaseDate ||
      (b.lastPurchaseDate === a.lastPurchaseDate && b.lastPurchaseId > a.lastPurchaseId) ? b : a) : null;
    const prices = [...new Set(members.map(row => row.lastPrice).filter(Number.isFinite))];
    const minimums = members.map(row => row.minPrice).filter(Number.isFinite);
    return {
      ...(latest || members[0]),
      purchases: members.reduce((sum, row) => sum + (row.purchases || 0), 0),
      lastPrice: latest ? latest.lastPrice : prices.length === 1 ? prices[0] : null,
      lastPriceRange: !latest && prices.length > 1 ? [Math.min(...prices), Math.max(...prices)] : null,
      minPrice: minimums.length ? Math.min(...minimums) : null,
    };
  });
}
