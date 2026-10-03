import { useState, useEffect } from "react";
import {
  Settings, Sun, Moon, Monitor, Users as UsersIcon, LayoutGrid, Trophy,
  Vibrate, Volume2, VolumeX, Play,
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
import { Slider } from "@/components/ui/slider";
import { useTheme } from "@/hooks/use-theme";
import { useActiveLeague } from "@/hooks/use-active-league";
import { useHapticPreference } from "@/hooks/use-haptic-preference";
import {
  areDraftSoundsEnabled, setDraftSoundsEnabled,
  getDraftSoundsVolume, setDraftSoundsVolume,
  playDing,
} from "@/lib/draft-sounds";
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
  // Iter 232e — Haptic buzz preference (used for the "someone came
  // online" pulse in the mobile bottom nav, and reusable for any
  // future haptic events like trade proposals, on-clock alerts).
  const { supported: hapticsSupported, enabled: hapticsEnabled, setEnabled: setHapticsEnabled } = useHapticPreference();
  // Iter 232g — Draft-sounds preference. Local state mirrors
  // localStorage so the slider + toggle stay in sync across menu
  // opens without pulling a full pref-context on every render.
  const [soundsEnabled, setSoundsEnabledState] = useState(() => areDraftSoundsEnabled());
  const [soundsVolume, setSoundsVolumeState] = useState(() => getDraftSoundsVolume());
  // Re-read from localStorage every time the menu opens so a
  // second-tab flip is reflected without a page reload.
  useEffect(() => {
    setSoundsEnabledState(areDraftSoundsEnabled());
    setSoundsVolumeState(getDraftSoundsVolume());
  }, [teamSettingsOpen]);
  const handleToggleSounds = () => {
    const next = !soundsEnabled;
    setDraftSoundsEnabled(next);
    setSoundsEnabledState(next);
    // Preview chime the moment the user turns it on so they can
    // gauge volume against their environment immediately.
    if (next) playDing();
  };
  const handleVolumeChange = (v) => {
    const next = Array.isArray(v) ? v[0] : v;
    setDraftSoundsVolume(next);
    setSoundsVolumeState(next);
  };
  const handlePreviewSound = (e) => {
    // Prevent the dropdown from closing when the user hits the
    // preview button (which lives inside a DropdownMenuItem).
    e?.stopPropagation?.();
    playDing();
  };

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
          {/* Iter 232e — Haptic buzz toggle. Only surfaces when the
              device actually supports `navigator.vibrate` — otherwise
              hiding the row prevents users from tweaking a knob that
              can't do anything on their hardware. */}
          {/* Iter 232e/g — Alerts group. Always shown (audio works
              on every browser; haptics-only row is inside gated by
              `hapticsSupported`). */}
          <>
            <DropdownMenuLabel className="text-xs uppercase tracking-wider text-muted-foreground">
                Alerts
              </DropdownMenuLabel>
              {hapticsSupported && (
                <DropdownMenuItem
                  onClick={() => setHapticsEnabled(!hapticsEnabled)}
                  data-testid="prefs-haptics-toggle"
                  data-enabled={hapticsEnabled ? "true" : "false"}
                  className={hapticsEnabled ? "bg-secondary" : ""}
                >
                  <Vibrate className="h-4 w-4 mr-2" />
                  <div className="flex flex-col leading-tight">
                    <span>Haptic buzz on live events</span>
                    <span className="text-[10px] text-muted-foreground">
                      A tiny wrist tap when a manager comes online
                    </span>
                  </div>
                  {hapticsEnabled && (
                    <span
                      className="ml-auto text-[10px] text-primary"
                      data-testid="prefs-haptics-active"
                    >
                      ON
                    </span>
                  )}
                </DropdownMenuItem>
              )}
              {/* Iter 232g — Draft-sounds toggle + volume slider.
                  Cross-modal chirp paired with the iter 232f draft
                  haptics (soft "ding" at pick start, urgent buzz in
                  the final 10s). */}
              <DropdownMenuItem
                onSelect={(e) => { e.preventDefault(); handleToggleSounds(); }}
                data-testid="prefs-sounds-toggle"
                data-enabled={soundsEnabled ? "true" : "false"}
                className={soundsEnabled ? "bg-secondary" : ""}
              >
                {soundsEnabled ? <Volume2 className="h-4 w-4 mr-2" /> : <VolumeX className="h-4 w-4 mr-2" />}
                <div className="flex flex-col leading-tight">
                  <span>Draft sounds</span>
                  <span className="text-[10px] text-muted-foreground">
                    Soft ding at pick start, urgent buzz in final 10s
                  </span>
                </div>
                {soundsEnabled && (
                  <span
                    className="ml-auto text-[10px] text-primary"
                    data-testid="prefs-sounds-active"
                  >
                    ON
                  </span>
                )}
              </DropdownMenuItem>
              {soundsEnabled && (
                <div
                  className="px-2 pb-2 pt-1 flex items-center gap-2"
                  onClick={(e) => e.stopPropagation()}
                  data-testid="prefs-sounds-volume-row"
                >
                  <VolumeX className="h-3 w-3 text-muted-foreground shrink-0" />
                  <Slider
                    value={[soundsVolume]}
                    onValueChange={handleVolumeChange}
                    min={0}
                    max={100}
                    step={5}
                    className="flex-1"
                    data-testid="prefs-sounds-volume-slider"
                    aria-label="Draft sounds volume"
                  />
                  <Volume2 className="h-3 w-3 text-muted-foreground shrink-0" />
                  <button
                    type="button"
                    onClick={handlePreviewSound}
                    className="ml-1 rounded px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground hover:text-foreground hover:bg-secondary flex items-center gap-1"
                    data-testid="prefs-sounds-preview"
                    aria-label="Preview draft sound"
                  >
                    <Play className="h-3 w-3" />
                    Test
                  </button>
                </div>
              )}
              <DropdownMenuSeparator />
            </>
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
