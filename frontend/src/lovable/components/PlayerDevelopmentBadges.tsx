import { ArrowDownCircle } from 'lucide-react';
import { MinorEligibleBadge } from './MinorEligibleBadge';

export function PlayerDevelopmentBadges({ player }: { player: any }) {
  const inMinors = player.planning_minor || player.status_flags?.in_minors || ['minors', 'goalies_minors'].includes(player.rosterSection);
  const eligible = player.minor_eligible ?? (player.player_type === 'prospect');
  return <span className="inline-flex shrink-0 items-center gap-1">
    {inMinors && <span title="Currently in minors" aria-label="Currently in minors" data-testid="in-minors-badge"
      className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-sky-500/40 bg-sky-500/15 text-sky-300">
      <ArrowDownCircle className="h-3 w-3" aria-hidden="true" />
    </span>}
    <MinorEligibleBadge eligible={eligible} />
  </span>;
}
