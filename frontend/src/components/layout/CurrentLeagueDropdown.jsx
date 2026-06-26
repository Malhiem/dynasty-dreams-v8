import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
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
 * Sidebar-mounted "Current League" switcher.
 *
 * Iter 230al — Adds:
 *   • Scrollable league list (`max-h-[60vh] overflow-y-auto`).
 *   • Edit mode toggle revealing up/down reorder + hide buttons per
 *     league. Order is persisted to localStorage via
 *     `useActiveLeague.reorderLeagues`. Hides hit
 *     `/notifications/preferences/league-hide`.
 */
export default function CurrentLeagueDropdown({ collapsed = false }) {
  const navigate = useNavigate();
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

  const handlePick = (id) => {
    if (id !== leagueId) switchLeague(id);
    navigate(`/leagues/${id}`);
  };

  const handleOpenChange = (open) => {
    if (open && typeof reloadMyLeagues === "function") reloadMyLeagues();
    if (!open) setEditMode(false);
  };

  const handleHide = async (e, l) => {
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

  const handleMove = (e, from, to) => {
    e.stopPropagation();
    e.preventDefault();
    reorderLeagues(from, to);
  };

  return (
    <DropdownMenu onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger asChild>
        {collapsed ? (
          <button
            data-testid="current-league-dropdown-trigger"
            title={`Current League: ${triggerTeam?.name ? `${triggerTeam.name} · ` : ""}${league.name}`}
            className="mx-auto my-2 flex h-9 w-9 items-center justify-center rounded-lg border border-[#00D2FF]/25 bg-[#00D2FF]/5 hover:bg-[#00D2FF]/10 transition-colors focus:outline-none focus:ring-2 focus:ring-[#00D2FF]/40"
          >
            <TeamLogo
              logo={triggerTeam?.logo_url}
              name={triggerTeam?.name || league.name}
              abbr={triggerTeam?.logo_abbr}
              size="xs"
              className="rounded-md"
            />
          </button>
        ) : (
          <button
            data-testid="current-league-dropdown-trigger"
            className="mx-2 mt-2 mb-1 flex w-[calc(100%-1rem)] items-center gap-2.5 px-3 py-2 rounded-md border border-[#00D2FF]/25 bg-[#00D2FF]/5 hover:bg-[#00D2FF]/10 transition-colors focus:outline-none focus:ring-2 focus:ring-[#00D2FF]/40 text-left"
          >
            <TeamLogo
              logo={triggerTeam?.logo_url}
              name={triggerTeam?.name || league.name}
              abbr={triggerTeam?.logo_abbr}
              size="sm"
              className="rounded-md shrink-0"
            />
            <div className="flex flex-col items-start min-w-0 leading-tight flex-1">
              <span
                className="text-[9px] uppercase tracking-widest text-[#71717A]"
                data-testid="current-league-label"
              >
                Current League
              </span>
              <span
                className="text-sm font-bold text-white truncate w-full"
                data-testid="current-league-team-name"
              >
                {triggerTeam?.name || "No team"}
              </span>
              <span
                className="text-[11px] text-[#A1A1AA] truncate w-full"
                data-testid="current-league-league-name"
              >
                {league.name}
              </span>
            </div>
            <ChevronDown className="h-3.5 w-3.5 text-[#A1A1AA] shrink-0" />
          </button>
        )}
      </DropdownMenuTrigger>

      <DropdownMenuContent
        align="start"
        side="right"
        className="w-80 p-0 bg-[#141414] border-white/10"
        data-testid="current-league-dropdown-menu"
      >
        <div className="flex items-center justify-between px-4 pt-3 pb-1">
          <DropdownMenuLabel className="p-0 text-xs uppercase tracking-wider text-[#71717A] font-medium">
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
                ? "bg-[#00D2FF]/15 text-[#00D2FF]"
                : "text-[#71717A] hover:text-white hover:bg-white/5"
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
          {leagues.map((l, idx) => {
            const team = myTeamsByLeague?.[l.id];
            const isActive = l.id === leagueId;
            const isFirst = idx === 0;
            const isLast = idx === leagues.length - 1;
            return (
              <DropdownMenuItem
                key={l.id}
                className={`px-4 py-3 cursor-pointer focus:bg-white/5 ${
                  isActive ? "bg-[#00D2FF]/5" : ""
                }`}
                onClick={() => !editMode && handlePick(l.id)}
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
                      <span className="font-semibold text-sm text-white truncate">
                        {team?.name || (
                          <span className="italic text-[#71717A]">
                            No team yet
                          </span>
                        )}
                      </span>
                      {isActive && !editMode && (
                        <Check
                          className="h-4 w-4 text-[#00D2FF] shrink-0"
                          data-testid={`current-league-active-${l.id}`}
                        />
                      )}
                    </div>
                    <p className="text-xs text-[#A1A1AA] truncate mt-0.5 flex items-center gap-1">
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
                        className="h-7 w-7 rounded hover:bg-white/5 text-[#A1A1AA] hover:text-white disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center"
                      >
                        <ArrowUp className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        disabled={isLast}
                        onClick={(e) => handleMove(e, idx, idx + 1)}
                        data-testid={`current-league-move-down-${l.id}`}
                        aria-label="Move down"
                        className="h-7 w-7 rounded hover:bg-white/5 text-[#A1A1AA] hover:text-white disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center"
                      >
                        <ArrowDown className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={(e) => handleHide(e, l)}
                        data-testid={`current-league-hide-${l.id}`}
                        aria-label="Hide league"
                        className="h-7 w-7 rounded hover:bg-rose-500/10 text-[#A1A1AA] hover:text-rose-300 flex items-center justify-center"
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

        <DropdownMenuSeparator className="bg-white/10" />

        <DropdownMenuItem
          asChild
          className="px-4 py-2.5 cursor-pointer focus:bg-white/5"
          data-testid="current-league-go-to-dashboard"
        >
          <Link to="/dashboard" className="flex items-center gap-2.5 w-full">
            <LayoutGrid className="h-4 w-4 text-[#A1A1AA]" />
            <span className="text-sm text-white">
              User Dashboard (all leagues)
            </span>
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
