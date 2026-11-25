// Salary-cap rules shared by mobile screens. They mirror the web app:
// "No cap, no salaries" — salary, cap and retention figures are shown only when
// the league has a salary cap enabled. The player card is the one place salary
// stays visible regardless.

export const RETENTION_OPTIONS = [
  { value: 'willing_to_retain', short: 'A', label: 'A · Willing to retain', color: '#34D399' },
  { value: 'no_preference', short: 'B', label: 'B · No preference', color: '#A1A1AA' },
  { value: 'seeking_retention', short: 'C', label: 'C · Seeking retention', color: '#FBBF24' },
];

export function retentionOption(value) {
  return RETENTION_OPTIONS.find((o) => o.value === value) || RETENTION_OPTIONS[1];
}

export const leagueCapEnabled = (league) => Boolean(league?.salary_cap_enabled);

// $12.3M style, as on the web.
export function formatMillions(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  return `$${(n / 1_000_000).toFixed(1)}M`;
}

// Normalise /teams/{id}/compliance into what the cap card renders. Returns null
// when the league has no cap, so callers render nothing.
export function capSummary(c) {
  if (!c || !c.salary_cap_enabled) return null;
  const limit = Number(c.salary_cap || 0);
  const used = Number(c.salary_used || 0);
  const remaining = limit - used;
  const slotsTotal = Number(c.salary_retention_slots_total ?? 3);
  const slotsUsed = Number(c.salary_retention_slots_used ?? 0);
  return {
    limit,
    used,
    remaining,
    over: remaining < 0,
    pct: limit > 0 ? Math.min((used / limit) * 100, 100) : 0,
    slotsTotal,
    slotsRemaining: Number(c.salary_retention_slots_remaining ?? Math.max(0, slotsTotal - slotsUsed)),
    retained: Number(c.retained_salary_total ?? 0),
    overDetail: (c.reasons || []).find((r) => r.code === 'over_salary_cap')?.detail || null,
  };
}

// Map player_id -> salary from /roster/{id}/detail, or {} for cap-less leagues.
export function salaryByPlayer(detail, capEnabled) {
  if (!capEnabled) return {};
  const out = {};
  (detail?.players || []).forEach((p) => {
    const id = p.id || p.player_id || p._id;
    const sal = p.contract?.salary;
    if (id != null && sal != null) out[String(id)] = Number(sal);
  });
  return out;
}
