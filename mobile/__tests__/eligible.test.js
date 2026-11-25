const fs = require('fs');
const path = require('path');
jest.mock('react-native', () => ({
  Alert: { alert: jest.fn() }, View: 'View', Text: 'Text', TouchableOpacity: 'TouchableOpacity',
  ActivityIndicator: 'ActivityIndicator', StyleSheet: { create: (s) => s },
}));
const { eligibleUrl, mergePlayers, remainingCount, fetchEligible, PAGE_SIZE } = require('../src/lib/eligible');
const EligiblePlayerList = require('../src/components/EligiblePlayerList').default;

const mk = (from, n) => Array.from({ length: n }, (_, i) => ({ id: `p${from + i}`, name: `P${from + i}` }));
// A fake API serving `total` players in pages of `limit`.
const fakeApi = (total) => ({
  calls: [],
  async get(url) {
    this.calls.push(url);
    const q = new URL(`http://x${url}`).searchParams;
    const page = Number(q.get('page')); const limit = Number(q.get('limit'));
    const start = (page - 1) * limit;
    return { data: { players: mk(start, Math.max(0, Math.min(limit, total - start))), total, page, pages: Math.ceil(total / limit) } };
  },
});

describe('eligibleUrl', () => {
  test('pages and limits', () => {
    expect(eligibleUrl('d1', { page: 3 })).toBe(`/drafts/d1/eligible-players?page=3&limit=${PAGE_SIZE}`);
  });
  test('URL-encodes the search text', () => {
    expect(eligibleUrl('d1', { search: 'O\'Reilly & co' })).toContain('search=O%27Reilly+%26+co');
  });
  test('ignores a blank search', () => {
    expect(eligibleUrl('d1', { search: '   ' })).not.toContain('search');
  });
});

describe('mergePlayers / remainingCount', () => {
  test('appends only unseen players, in order', () => {
    expect(mergePlayers([{ id: 'a' }, { id: 'b' }], [{ id: 'b' }, { id: 'c' }]).map((p) => p.id)).toEqual(['a', 'b', 'c']);
  });
  test('remaining never goes negative', () => {
    expect(remainingCount(100, 25)).toBe(75);
    expect(remainingCount(10, 25)).toBe(0);
    expect(remainingCount(undefined, 0)).toBe(0);
  });
});

describe('fetchEligible', () => {
  test('first page reports totals so the UI can offer "load more"', async () => {
    const api = fakeApi(60);
    const r = await fetchEligible(api, 'd1', {});
    expect(r.players).toHaveLength(25);
    expect(r).toMatchObject({ total: 60, pages: 3, page: 1 });
  });
  test('loading the next page continues where the list left off', async () => {
    const api = fakeApi(60);
    const r = await fetchEligible(api, 'd1', { fromPage: 3 });
    expect(r.players.map((p) => p.id)[0]).toBe('p50');
    expect(r.players).toHaveLength(10);
    expect(r.page).toBe(3);
  });
  test('refresh re-fetches pages 1..N and stops at the last page', async () => {
    const api = fakeApi(60);
    const r = await fetchEligible(api, 'd1', { fromPage: 1, toPage: 5 });
    expect(api.calls).toHaveLength(3);
    expect(r.players).toHaveLength(60);
  });
  test('an empty result is fine', async () => {
    const r = await fetchEligible(fakeApi(0), 'd1', { search: 'zzz' });
    expect(r.players).toEqual([]);
    expect(r.total).toBe(0);
  });
});

describe('EligiblePlayerList', () => {
  const base = { players: mk(0, 2), total: 60, hasMore: true, loading: false, loadingMore: false, error: null, loadMore: jest.fn(), reload: jest.fn() };
  const text = (n) => JSON.stringify(n, (k, v) => (typeof v === 'function' ? '[fn]' : v));
  test('offers Load more with the remaining count', () => {
    const t = text(EligiblePlayerList({ list: base, renderRow: (p) => ({ type: 'Row', key: p.id }) }));
    expect(t).toContain('eligible-load-more');
    expect(t).toContain('58');
    expect(t).toContain('60 available');
  });
  test('no Load more on the last page', () => {
    expect(text(EligiblePlayerList({ list: { ...base, hasMore: false }, renderRow: () => null }))).not.toContain('eligible-load-more');
  });
  test('says when nothing matches, and shows an error instead of "no matches"', () => {
    expect(text(EligiblePlayerList({ list: { ...base, players: [], total: 0, hasMore: false }, renderRow: () => null }))).toContain('No players match');
    const err = text(EligiblePlayerList({ list: { ...base, players: [], error: 'Cannot reach the server.', hasMore: false }, renderRow: () => null }));
    expect(err).toContain('Cannot reach the server.');
    expect(err).not.toContain('No players match');
  });
});

describe('draft screens', () => {
  const read = (f) => fs.readFileSync(path.join(__dirname, '..', 'src', 'screens', f), 'utf8');
  test.each(['DraftRoomScreen.js', 'AuctionDraftScreen.js'])('%s pages the player list instead of slicing it', (f) => {
    const src = read(f);
    expect(src).toMatch(/useEligiblePlayers\(draftId, search\)/);
    expect(src).toMatch(/<EligiblePlayerList list=\{eligible\}/);
    expect(src).not.toMatch(/players\.slice\(0, \d+\)/);
  });
  test('the auction no longer polls (and resets) the player list every 3s or concatenates the search', () => {
    const src = read('AuctionDraftScreen.js');
    expect(src).not.toMatch(/eligible-players\?limit=20/);
    expect(src).not.toMatch(/&search=\$\{search\}/);
  });
});
