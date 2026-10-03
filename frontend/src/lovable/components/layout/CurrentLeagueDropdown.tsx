// @ts-nocheck
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowDown,
  ArrowUp,
  Check,
  ChevronDown,
  EyeOff,
  LayoutGrid,
  Pencil,
  Trophy,
} from "lucide-react";
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
import { toast } from "sonner";

/**
 * Global "Current League" switcher.
 *
 * Iter 230al additions:
 *   • Scrolls when the user has more than a handful of leagues
 *     (`max-h-[60vh] overflow-y-auto`).
 *   • In-place reordering (up/down arrows) — the order is persisted to
 *     localStorage via `useActiveLeague.reorderLeagues` and is honoured
 *     by every consumer of `myLeagues` (sidebar, Dashboard, etc.).
 *   • In-place hide-from-dashboard (eye-off icon) — calls the existing
 *     `/notifications/preferences/league-hide` endpoint so the league
 *     disappears from this user's day-to-day surfaces without affecting
 *     anyone else.
 */
export default function CurrentLeagueDropdown() {
  const {
    myLeagues,
    myTeamsByLeague,
    leagueId,
    league,
    myTeam,
    switchLeague,
    reloadMyLeagues,
    reorderLeagues,
    hideLeague,
  } = useActiveLeague();
  const [editMode, setEditMode] = useState(false);

  if (!league) return null;

  const triggerTeam = myTeam;
  const leagues = myLeagues || [];

  const handleHide = async (e: any, l: any) => {
    e.stopPropagation();
    e.preventDefault();
    try {
      await hideLeague(l.id);
      toast.success(`${l.name} hidden`, {
        description: "Restore any time from Notification Settings.",
      });
    } catch {
      toast.error("Couldn't hide that league");
    }
  };

  const handleMove = (e: any, from: number, to: number) => {
    e.stopPropagation();
    e.preventDefault();
    reorderLeagues(from, to);
  };

  return (
    <DropdownMenu
      onOpenChange={(open) => {
        if (open && typeof reloadMyLeagues === "function") reloadMyLeagues();
        if (!open) setEditMode(false);
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
        <div className="flex items-center justify-between px-4 pt-3 pb-1">
          <DropdownMenuLabel className="p-0 text-xs uppercase tracking-wider text-muted-foreground font-medium">
            Switch League
          </DropdownMenuLabel>
          <button
            type="button"
            data-testid="current-league-edit-toggle"
            onClick={(e) => {
              e.stopPropagation();
              setEditMode((m) => !m);
            }}
            className={`text-[10px] uppercase tracking-wider font-medium px-1.5 py-0.5 rounded transition-colors ${
              editMode
                ? "bg-primary/15 text-primary"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary"
            }`}
          >
            <Pencil className="h-3 w-3 inline-block mr-1" />
            {editMode ? "Done" : "Edit"}
          </button>
        </div>

        <div
          className="max-h-[60vh] overflow-y-auto overscroll-contain"
          data-testid="current-league-list-scroll"
        >
          {leagues.map((l: any, idx: number) => {
            const team = myTeamsByLeague?.[l.id];
            const isActive = l.id === leagueId;
            const isFirst = idx === 0;
            const isLast = idx === leagues.length - 1;
            return (
              <DropdownMenuItem
                key={l.id}
                className={`px-4 py-3 cursor-pointer focus:bg-secondary ${
                  isActive ? "bg-primary/5" : ""
                }`}
                onClick={() => !editMode && switchLeague(l.id)}
                onSelect={(e) => {
                  if (editMode) e.preventDefault();
                }}
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
                      {isActive && !editMode && (
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
                  {editMode && (
                    <div className="flex items-center gap-0.5 shrink-0">
                      <button
                        type="button"
                        disabled={isFirst}
                        onClick={(e) => handleMove(e, idx, idx - 1)}
                        data-testid={`current-league-move-up-${l.id}`}
                        aria-label="Move up"
                        className="h-7 w-7 rounded hover:bg-secondary text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center"
                      >
                        <ArrowUp className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        disabled={isLast}
                        onClick={(e) => handleMove(e, idx, idx + 1)}
                        data-testid={`current-league-move-down-${l.id}`}
                        aria-label="Move down"
                        className="h-7 w-7 rounded hover:bg-secondary text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center"
                      >
                        <ArrowDown className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={(e) => handleHide(e, l)}
                        data-testid={`current-league-hide-${l.id}`}
                        aria-label="Hide league"
                        className="h-7 w-7 rounded hover:bg-rose-500/10 text-muted-foreground hover:text-rose-300 flex items-center justify-center"
                      >
                        <EyeOff className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              </DropdownMenuItem>
            );
          })}
        </div>

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
