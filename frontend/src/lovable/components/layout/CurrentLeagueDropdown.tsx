// @ts-nocheck
import { Link } from "react-router-dom";
import { ChevronDown, Check, Trophy, LayoutGrid } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import TeamLogo from "@/lovable/components/TeamLogo";
import { useActiveLeague } from "@/hooks/use-active-league";

/**
 * Global "Current League" switcher.
 *
 * Sits in the AppLayout header. Replaces the per-page league transfer dropdowns
 * that used to live on Transactions, Standings, and the LeagueContextBanner.
 *
 * Trigger: team logo + team name + league name underneath.
 * Menu:    one entry per league showing the same team-logo / team / league
 *          stack, with a checkmark on the active league + a quick "User
 *          Dashboard" link as the only other way to navigate across leagues.
 */
export default function CurrentLeagueDropdown() {
  const { myLeagues, myTeamsByLeague, leagueId, league, myTeam, switchLeague, reloadMyLeagues } =
    useActiveLeague();

  // Render nothing until we have at least one league. Avoids flashing an empty
  // "Current League" shell on first paint.
  if (!league) return null;

  const triggerTeam = myTeam;

  return (
    <DropdownMenu
      onOpenChange={(open) => {
        // Iter 194 — Force-refresh the league list every time the
        // switcher opens so newly-joined / newly-created leagues show
        // up immediately instead of waiting for the GET-cache TTL.
        if (open && typeof reloadMyLeagues === "function") reloadMyLeagues();
      }}
    >
      <DropdownMenuTrigger asChild>
        <button
          data-testid="current-league-dropdown-trigger"
          className="flex items-center gap-2.5 pl-1.5 pr-2 py-1 rounded-lg border border-border bg-secondary/40 hover:bg-secondary transition-colors focus:outline-none focus:ring-2 focus:ring-primary/40 max-w-[260px]"
        >
          <TeamLogo
            logo={triggerTeam?.logo_url}
            name={triggerTeam?.name || league.name}
            abbr={triggerTeam?.logo_abbr}
            size="sm"
            className="rounded-md"
          />
          <div className="flex flex-col items-start min-w-0 leading-tight">
            <span
              className="text-[10px] uppercase tracking-wider text-muted-foreground"
              data-testid="current-league-label"
            >
              Current League
            </span>
            <span
              className="text-sm font-semibold text-foreground truncate max-w-[160px]"
              data-testid="current-league-team-name"
            >
              {triggerTeam?.name || "No team"}
            </span>
            <span
              className="text-[11px] text-muted-foreground truncate max-w-[160px]"
              data-testid="current-league-league-name"
            >
              {league.name}
            </span>
          </div>
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent
        align="end"
        className="w-80 p-0 bg-popover border-border"
        data-testid="current-league-dropdown-menu"
      >
        <DropdownMenuLabel className="px-4 pt-3 pb-1 text-xs uppercase tracking-wider text-muted-foreground font-medium">
          Switch League
        </DropdownMenuLabel>

        {(myLeagues || []).map((l: any) => {
          const team = myTeamsByLeague?.[l.id];
          const isActive = l.id === leagueId;
          return (
            <DropdownMenuItem
              key={l.id}
              className={`px-4 py-3 cursor-pointer focus:bg-secondary ${
                isActive ? "bg-primary/5" : ""
              }`}
              onClick={() => switchLeague(l.id)}
              data-testid={`current-league-option-${l.id}`}
            >
              <div className="flex items-start gap-3 w-full">
                <TeamLogo
                  logo={team?.logo_url}
                  name={team?.name || l.name}
                  abbr={team?.logo_abbr}
                  size="sm"
                  className="rounded-md mt-0.5"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-sm text-foreground truncate">
                      {team?.name || (
                        <span className="italic text-muted-foreground">
                          No team yet
                        </span>
                      )}
                    </span>
                    {isActive && (
                      <Check
                        className="h-4 w-4 text-primary shrink-0"
                        data-testid={`current-league-active-${l.id}`}
                      />
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground truncate mt-0.5 flex items-center gap-1">
                    <Trophy className="h-3 w-3 shrink-0" />
                    <span className="truncate">{l.name}</span>
                  </p>
                </div>
              </div>
            </DropdownMenuItem>
          );
        })}

        <DropdownMenuSeparator className="bg-border" />

        <DropdownMenuItem
          asChild
          className="px-4 py-2.5 cursor-pointer focus:bg-secondary"
          data-testid="current-league-go-to-dashboard"
        >
          <Link to="/leagues" className="flex items-center gap-2.5 w-full">
            <LayoutGrid className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-foreground">
              User Dashboard (all leagues)
            </span>
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
