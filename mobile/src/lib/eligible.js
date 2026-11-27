// Paging for GET /drafts/{id}/eligible-players (shared by both draft screens).

export const PAGE_SIZE = 25;
export const MAX_REFRESH_PAGES = 8;

export function eligibleUrl(draftId, { search, page = 1, limit = PAGE_SIZE } = {}) {
  const params = new URLSearchParams({ page: String(page), limit: String(limit) });
  if (search && search.trim()) params.append('search', search.trim()); // encoded, unlike string concatenation
  return `/drafts/${draftId}/eligible-players?${params}`;
}

// Append a page, ignoring players we already have (a pick can shift pages).
export function mergePlayers(existing, incoming) {
  const seen = new Set(existing.map((p) => p.id));
  return existing.concat((incoming || []).filter((p) => !seen.has(p.id)));
}

export const remainingCount = (total, loaded) => Math.max(0, Number(total || 0) - loaded);

// Fetch pages fromPage..toPage (inclusive, stopping at the last page).
export async function fetchEligible(api, draftId, { search, fromPage = 1, toPage = fromPage, limit = PAGE_SIZE } = {}) {
  let players = [];
  let total = 0;
  let pages = 1;
  let page = fromPage - 1;
  for (let p = fromPage; p <= Math.min(toPage, MAX_REFRESH_PAGES + fromPage); p += 1) {
    const { data } = await api.get(eligibleUrl(draftId, { search, page: p, limit }));
    const rows = data?.players || [];
    total = Number(data?.total ?? 0);
    pages = Number(data?.pages ?? 1);
    players = mergePlayers(players, rows);
    page = p;
    if (p >= pages || rows.length === 0) break;
  }
  return { players, total, pages, page };
}
