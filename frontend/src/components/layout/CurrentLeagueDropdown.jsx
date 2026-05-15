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
 * Sidebar-mounted "Current League" switcher.
 *
 * Replaces the legacy static `sidebar-active-league-name` badge that used to
 * sit at the top of the sidebar. This is now the ONLY way to jump between
 * leagues besides the "User Dashboard" sidebar link.
 *
 * Expanded sidebar: full-width cyan card showing team logo + team name +
 * league name + chevron — visually echoing the previous "Active league"
 * tile so the UI affordance is unchanged for muscle memory.
 *
 * Collapsed sidebar (icon mode): just the team logo, centered. Click still
 * opens the same dropdown menu.
 */
export default function CurrentLeagueDropdown({ collapsed = false }) {
  const { myLeagues, myTeamsByLeague, leagueId, league, myTeam, switchLeague } =
    useActiveLeague();

  if (!league) return null;

  const triggerTeam = myTeam;

  return (
    <DropdownMenu>
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
        <DropdownMenuLabel className="px-4 pt-3 pb-1 text-xs uppercase tracking-wider text-[#71717A] font-medium">
          Switch League
        </DropdownMenuLabel>

        {(myLeagues || []).map((l) => {
          const team = myTeamsByLeague?.[l.id];
          const isActive = l.id === leagueId;
          return (
            <DropdownMenuItem
              key={l.id}
              className={`px-4 py-3 cursor-pointer focus:bg-white/5 ${
                isActive ? "bg-[#00D2FF]/5" : ""
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
                    <span className="font-semibold text-sm text-white truncate">
                      {team?.name || (
                        <span className="italic text-[#71717A]">
                          No team yet
                        </span>
                      )}
                    </span>
                    {isActive && (
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
              </div>
            </DropdownMenuItem>
          );
        })}

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
