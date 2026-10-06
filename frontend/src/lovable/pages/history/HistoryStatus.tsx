export function HistoryStatus({loading, error, retry}: {loading?: boolean; error?: string | null; retry: () => void}) {
  if (loading) return <p role="status" className="text-center py-8">Loading history…</p>;
  if (!error) return null;
  return <div role="alert" className="text-center py-8"><p>{error}</p><button type="button" onClick={retry} className="underline mt-2">Retry</button></div>;
}

export function FilteredAwardsEmpty({active, reset, fallback}: {active: boolean; reset: () => void; fallback: string}) {
  return <div className="text-amber-200/60 text-center text-xs px-3 py-2"><p>{active ? "No awards match these filters." : fallback}</p>{active && <button type="button" onClick={reset} className="underline mt-2">Reset filters</button>}</div>;
}
