const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const context = vm.createContext({Intl, Date});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../rewe_offer_state.js'), 'utf8'), context);
const state = (row, checkedAt, now) => context.marketOfferState(row, checkedAt, new Date(now));
const checkedAt = '2026-09-28T06:00:00+00:00';
const offer = {name: 'Testartikel', status: 'offer', validUntil: '2026-10-03T00:00:00CEST'};

test('a still valid offer survives multiple failed nightly refreshes', () => {
  assert.equal(state(offer, checkedAt, '2026-10-02T21:00:00Z').status, 'offer');
  assert.equal(offer.status, 'offer');
});

test('REWE end date includes the full day in Berlin, then becomes historical', () => {
  assert.equal(state(offer, checkedAt, '2026-10-03T21:59:59Z').status, 'offer');
  const expired = state(offer, checkedAt, '2026-10-03T22:00:00Z');
  assert.equal(expired.status, 'expired');
  assert.equal(expired.name, offer.name);
  assert.equal(offer.status, 'offer');
});

test('Berlin date remains correct across daylight saving changes', () => {
  const winterOffer = {...offer, validUntil: '2026-10-25T00:00:00CET'};
  assert.equal(state(winterOffer, checkedAt, '2026-10-25T22:59:59Z').status, 'offer');
  assert.equal(state(winterOffer, checkedAt, '2026-10-25T23:00:00Z').status, 'expired');
});

test('missing or invalid end date is retained but unconfirmed after 30 hours', () => {
  for (const validUntil of [null, '', 'invalid', '2026-02-30T00:00:00CET']) {
    const row = {...offer, validUntil};
    assert.equal(state(row, '2026-10-02T18:00:00Z', '2026-10-03T23:59:59Z').status, 'offer');
    assert.equal(state(row, '2026-10-02T18:00:00Z', '2026-10-04T00:00:01Z').status, 'unconfirmed');
  }
});

test('expired offer stays expired even if fetched recently', () => {
  assert.equal(state(offer, '2026-10-04T10:00:00Z', '2026-10-04T11:00:00Z').status, 'expired');
});

test('unparseable fetch time does not confirm an undated offer', () => {
  assert.equal(state({...offer, validUntil: null}, 'invalid', '2026-10-02T21:00:00Z').status, 'unconfirmed');
});

test('regular purchase rows keep their availability status', () => {
  const row = {name: 'Testartikel', status: 'pending'};
  assert.equal(state(row, checkedAt, '2026-10-04T11:00:00Z'), row);
});
