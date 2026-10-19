import { PlayerStatusBadges } from '@/components/player/PlayerStatusBadges';
import { PlayerDevelopmentBadges } from './PlayerDevelopmentBadges';
import { TooltipProvider } from '@/components/ui/tooltip';

export function PlanningPlayerBadges({ player }: { player: any }) {
  const flags = { ...player.status_flags, in_minors: false,
    injured: player.status_flags?.injured || player.rosterSection === 'ir' };
  return <TooltipProvider><span className="inline-flex shrink-0 items-center gap-1">
    <PlayerDevelopmentBadges player={player} />
    <PlayerStatusBadges flags={flags} />
  </span></TooltipProvider>;
}
