import { useState } from "react";
import {
  Settings, Sun, Moon, Monitor, Users as UsersIcon, LayoutGrid, Trophy,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/hooks/use-theme";
import { useActiveLeague } from "@/hooks/use-active-league";
import TeamSettingsModal from "@/lovable/components/TeamSettingsModal";

/**
 * Unified app preferences cog. Renders in the global header on every screen.
 *
 * Contents:
 *   - Appearance: Light / Dark toggle (always available)
 *   - Team:       Team Settings, Customize this page (only when the user is
 *                 actively viewing a league + owns a team in it; the
 *                 "customize this page" entry is gated on the host page
 *                 passing `onPageSettingsClick`)
 *
 * When no league/team is in context (e.g. login screen edge cases or
 * user-dashboard), only the Appearance group is shown — per UX spec.
 */
export default function AppPreferencesMenu({ onPageSettingsClick }) {
  const { theme, setTheme } = useTheme();
  const { myTeam, league } = useActiveLeague();
  const [teamSettingsOpen, setTeamSettingsOpen] = useState(false);

  // Team-scoped options are only available when the user actually has a team
  // in the active league. Empty/no-team leagues fall back to appearance-only.
  const hasTeamContext = Boolean(league && myTeam);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            data-testid="app-preferences-cog"
            title="App preferences"
            className="text-muted-foreground hover:text-foreground hover:bg-white/5 dark:hover:bg-white/5 h-9 w-9"
          >
            <Settings className="h-5 w-5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end"
          className="w-60"
          data-testid="app-preferences-menu"
        >
          {hasTeamContext && (
            <>
              <DropdownMenuLabel className="text-xs uppercase tracking-wider text-muted-foreground">
                Team — {myTeam.name}
              </DropdownMenuLabel>
              <DropdownMenuItem
                onClick={() => setTeamSettingsOpen(true)}
                data-testid="prefs-team-settings"
              >
                <UsersIcon className="h-4 w-4 mr-2" />
                <span>Team Settings</span>
              </DropdownMenuItem>
              {onPageSettingsClick && (
                <DropdownMenuItem
                  onClick={onPageSettingsClick}
                  data-testid="prefs-page-settings"
                >
                  <LayoutGrid className="h-4 w-4 mr-2" />
                  <span>Customize this page</span>
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
            </>
          )}

          <DropdownMenuLabel className="text-xs uppercase tracking-wider text-muted-foreground">
            Appearance
          </DropdownMenuLabel>
          <DropdownMenuItem
            onClick={() => setTheme("dark")}
            data-testid="theme-option-dark"
            className={theme === "dark" ? "bg-secondary" : ""}
          >
            <Moon className="h-4 w-4 mr-2" />
            <span>Dark</span>
            {theme === "dark" && (
              <span
                className="ml-auto text-[10px] text-primary"
                data-testid="theme-active-dark"
              >
                ACTIVE
              </span>
            )}
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => setTheme("light")}
            data-testid="theme-option-light"
            className={theme === "light" ? "bg-secondary" : ""}
          >
            <Sun className="h-4 w-4 mr-2" />
            <span>Light</span>
            {theme === "light" && (
              <span
                className="ml-auto text-[10px] text-primary"
                data-testid="theme-active-light"
              >
                ACTIVE
              </span>
            )}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem disabled>
            <Monitor className="h-4 w-4 mr-2" />
            <span className="text-xs text-muted-foreground">
              More preferences soon
            </span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* TeamSettingsModal is mounted here so the cog owns its full
          lifecycle — opening it from any screen "just works". */}
      <TeamSettingsModal open={teamSettingsOpen} onOpenChange={setTeamSettingsOpen} />
    </>
  );
}
