import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { TableCell } from '@/components/ui/table';
import { perGameFromTotal, points, totalFromPerGame } from './model';

export function FantasyPointInputs({ player, total, disabled, onChange, compact = false, testSuffix = "", seasonLabel = "" }: any) {
  const [draft, setDraft] = useState<{ field: string; text: string } | null>(null);
  const change = (field: string, text: string) => {
    // Preserve transient empty/decimal input while typing, deriving the other field
    // from one stored season total rather than maintaining competing values.
    setDraft({ field, text });
    const value = Number(text);
    if (Number.isFinite(value)) onChange(Math.max(-1e6, Math.min(1e6,
      field === 'fpg' ? totalFromPerGame(value) : points(value))));
  };
  const Cell = compact ? "div" : TableCell;
  return <>
    <Cell><Input type="number" step="0.0001" className={compact ? "w-full h-8 text-xs px-2" : "w-28"} disabled={disabled}
      aria-label={`${player.name} ${seasonLabel} FP/G`} data-testid={`depth-fpg-${player.id}${testSuffix}`}
      value={draft?.field === 'fpg' ? draft.text : perGameFromTotal(total)}
      onFocus={() => setDraft({ field: 'fpg', text: String(perGameFromTotal(total)) })}
      onChange={event => change('fpg', event.target.value)} onBlur={() => setDraft(null)} /></Cell>
    <Cell><Input type="number" step="0.01" className={compact ? "w-full h-8 text-xs px-2" : "w-24"} disabled={disabled}
      aria-label={`${player.name} ${seasonLabel} Total FP`} data-testid={`depth-pf-${player.id}${testSuffix}`}
      value={draft?.field === 'total' ? draft.text : total}
      onFocus={() => setDraft({ field: 'total', text: String(total) })}
      onChange={event => change('total', event.target.value)} onBlur={() => setDraft(null)} /></Cell>
  </>;
}
