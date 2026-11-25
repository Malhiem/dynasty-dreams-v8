import {test,expect} from '@playwright/test';
import {actors,dispose,league,type Actors} from '../support/access-history';
import {database,result,type League} from '../support/h2h';
import {ObjectId} from 'mongodb';

// Draft routes are members-only, and in-draft pick trades need the receiving
// team's consent. League fixture: team 0 is owned by `manager`, team 1 by
// `manager2`, the rest by `commissioner`; `outsider` is in no league.
let a: Actors, l: League, draftId: string;
test.beforeAll(async () => {
  a = await actors(); l = await league(a);
  const created = await result(await a.commissioner.api.post('/api/drafts', { data: {
    league_id: l.id, name: 'Access draft', total_rounds: 3, time_per_pick: 60,
    draft_type: 'snake', snake_draft: true, pick_trading_enabled: true, trading_window_opens: 'immediately',
  } }));
  draftId = created.id || created._id; expect(draftId).toBeTruthy();
});
test.afterAll(async () => { if (a) await dispose(a); });

const reads = [
  ['draft list for the league', (l: League) => `/api/drafts?league_id=${l.id}`],
  ['board', (_: League) => `/api/drafts/${draftId}/board`],
  ['eligible players', (_: League) => `/api/drafts/${draftId}/eligible-players`],
] as const;

for (const [name, url] of reads) {
  test(`D01 draft ${name}: members read it, outsiders and anonymous users cannot`, async () => {
    for (const who of [a.manager, a.manager2, a.commissioner]) expect((await who.api.get(url(l))).status(), `member ${name}`).toBe(200);
    expect((await a.outsider.api.get(url(l))).status(), 'outsider').toBe(403);
    expect((await a.anonymous.api.get(url(l))).status(), 'anonymous').toBe(401);
  });
}

test('D02 the unfiltered draft list only shows drafts from the caller\'s leagues', async () => {
  const ids = async (who: any) => ((await result(await who.api.get('/api/drafts'))) as any[]).map(d => String(d._id || d.id));
  expect(await ids(a.manager)).toContain(draftId);
  expect(await ids(a.outsider)).not.toContain(draftId);
  expect((await a.anonymous.api.get('/api/drafts')).status()).toBe(401);
});

const propose = (who: any, body: any) => who.api.post(`/api/drafts/${l.id}/propose-pick-trade`, { data: body });
const offer = (over: any = {}) => ({
  proposer_team_id: l.teams[0].id, receiver_team_id: l.teams[1].id,
  proposer_assets: [{ type: 'pick', year: 2030, round: 1 }], receiver_assets: [], ...over,
});
const act = (who: any, id: string, action: string, data?: any) =>
  who.api.post(`/api/drafts/${l.id}/pick-trade/${id}/${action}`, data ? { data } : undefined);
const status = async (id: string) => database(async db => (await db.collection('trades').findOne({ _id: new ObjectId(id) }))!.status);

test('D03 only the owner of the proposing team can propose a pick trade', async () => {
  expect((await propose(a.outsider, offer())).status(), 'outsider').toBe(403);
  expect((await propose(a.anonymous, offer())).status(), 'anonymous').toBe(401);
  expect((await propose(a.manager2, offer())).status(), "someone else's team").toBe(403);
  expect((await propose(a.manager, offer({ proposer_assets: [] }))).status(), 'no pick offered').toBe(400);
  expect((await propose(a.manager, offer({ receiver_team_id: l.teams[0].id }))).status(), 'trade with yourself').toBe(400);
});

test('D04 a new pick trade waits on the receiver, who accepts to open league review', async () => {
  const p = await result(await propose(a.manager, offer()));
  expect(p.status).toBe('pending_acceptance');
  expect(p.awaiting_team_id).toBe(l.teams[1].id);
  const id = p.trade_id;
  // nobody can vote before the receiver agrees
  expect((await act(a.commissioner, id, 'vote', { choice: 'approve' })).status()).toBe(400);
  // the sender (implied accept), the commissioner and outsiders cannot answer for the receiver
  for (const who of [a.manager, a.commissioner]) expect((await act(who, id, 'accept')).status()).toBe(403);
  expect((await act(a.outsider, id, 'accept')).status()).toBe(403);
  // the commissioner cannot force the trade through without consent
  expect((await act(a.commissioner, id, 'resolve', { decision: 'execute' })).status()).toBe(400);
  expect(await status(id)).toBe('pending_acceptance');
  // the receiver sees it as theirs to answer
  const seen = await result(await a.manager2.api.get(`/api/drafts/${l.id}/pick-trade/${id}`));
  expect(seen.can_respond).toBe(true);
  expect((await result(await a.manager.api.get(`/api/drafts/${l.id}/pick-trade/${id}`))).can_respond).toBe(false);

  const accepted = await result(await act(a.manager2, id, 'accept'));
  expect(accepted.status).toBe('pending_draft_review'); expect(accepted.review_expires_at).toBeTruthy();
  expect((await act(a.manager2, id, 'accept')).status(), 'not accepted twice').toBe(400);
  expect((await act(a.commissioner, id, 'vote', { choice: 'approve' })).status()).toBe(200);
  expect((await act(a.outsider, id, 'vote', { choice: 'veto' })).status()).toBe(403);
});

test('D05 the receiver can decline, ending the trade', async () => {
  const { trade_id: id } = await result(await propose(a.manager, offer()));
  expect((await act(a.manager, id, 'decline')).status(), 'sender cannot decline their own offer').toBe(403);
  expect((await act(a.manager2, id, 'decline')).status()).toBe(200);
  expect(await status(id)).toBe('declined');
  expect((await act(a.manager2, id, 'accept')).status(), 'cannot accept a declined trade').toBe(400);
});

test('D06 an edit by the receiver returns the trade to the sender to accept', async () => {
  const { trade_id: id } = await result(await propose(a.manager, offer()));
  const counter = { proposer_assets: [{ type: 'pick', year: 2030, round: 1 }], receiver_assets: [{ type: 'pick', year: 2031, round: 2 }] };
  expect((await act(a.manager, id, 'edit', counter)).status(), 'sender cannot edit while waiting').toBe(403);
  expect((await act(a.manager2, id, 'edit', { proposer_assets: [], receiver_assets: [] })).status(), 'must keep a pick').toBe(400);
  const edited = await result(await act(a.manager2, id, 'edit', counter));
  expect(edited.awaiting_team_id).toBe(l.teams[0].id);
  expect(await status(id)).toBe('pending_acceptance');
  expect((await act(a.manager2, id, 'accept')).status(), 'the editor cannot accept their own edit').toBe(403);
  const back = await result(await a.manager.api.get(`/api/drafts/${l.id}/pick-trade/${id}`));
  expect(back.can_respond).toBe(true); expect(back.receiver_assets).toEqual(counter.receiver_assets);
  expect((await act(a.manager, id, 'accept')).status()).toBe(200);
  expect(await status(id)).toBe('pending_draft_review');
  expect((await act(a.manager, id, 'edit', counter)).status(), 'no edits once in review').toBe(400);
});

test('D07 pending list shows trades awaiting acceptance to members only', async () => {
  const { trade_id: id } = await result(await propose(a.manager, offer()));
  const rows = (await result(await a.manager2.api.get(`/api/drafts/${l.id}/pick-trades/pending`))).pending as any[];
  const row = rows.find(r => r.trade_id === id)!;
  expect(row.status).toBe('pending_acceptance'); expect(row.can_respond).toBe(true);
  expect((await a.outsider.api.get(`/api/drafts/${l.id}/pick-trades/pending`)).status()).toBe(403);
});
