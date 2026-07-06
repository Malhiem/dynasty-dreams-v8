// Iter 232N.37 — Compact "team cell" that renders the amateur/minor
// league (WHL, OHL, USNTP, NCAA, KHL, SHL, etc.) with a tooltip
// revealing the actual junior/minor team the prospect plays for.
// Falls back to plain NHL abbreviation when the player is a veteran.
//
// Consumers: RosterPage, Waivers/FreeAgents table, DraftRoom eligible
// players list, Draft Board (any surface with a "Team" column).
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";

/**
 * @param {object} props
 * @param {string} [props.team]           — NHL abbr (e.g. "EDM") OR junior team name (e.g. "Medicine Hat")
 * @param {string} [props.amateurLeague]  — WHL / OHL / USNTP / NCAA / KHL / SHL / QMJHL / etc. Only set for prospects.
 * @param {string} [props.className]      — extra classes for the outer span
 * @param {string} [props.testIdPrefix]   — override for the data-testid stem
 */
export default function PlayerTeamCell({ team, amateurLeague, className = "", testIdPrefix = "player-team" }) {
  const hasLeague = !!(amateurLeague && String(amateurLeague).trim());
  if (!hasLeague) {
    // NHL veteran — plain abbreviation, no tooltip needed.
    return (
      <span className={className} data-testid={`${testIdPrefix}-nhl`}>
        {team || "—"}
      </span>
    );
  }
  const league = String(amateurLeague).trim();
  const teamLabel = team || "Unknown team";
  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={`cursor-help underline decoration-dotted decoration-white/30 underline-offset-2 ${className}`}
            data-testid={`${testIdPrefix}-amateur`}
            data-amateur-league={league}
          >
            {league}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="text-xs">
          {teamLabel}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
