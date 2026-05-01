// @ts-nocheck
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { LEAGUE_HOME_WIDGETS } from "@/hooks/use-league-home-config";

/**
 * Customize modal for the League Home page.
 *
 * Reads `visibility` (map of widget id → bool) from the parent-supplied hook,
 * calls `onToggle(id)` to flip one and `onReset()` to return all widgets to
 * visible defaults. The modal intentionally skips reorder controls here —
 * LeagueDetailPage is a fixed monolithic layout so only show/hide is
 * meaningful without a larger refactor.
 */
export default function LeagueHomeSettingsModal({ open, onOpenChange, visibility, onToggle, onReset }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#141414] border-white/10 max-w-lg" data-testid="league-home-settings-modal">
        <DialogHeader>
          <DialogTitle className="text-white">Customize League Home</DialogTitle>
          <DialogDescription className="text-[#A1A1AA]">
            Toggle widgets on or off. Changes save automatically and are kept per-league.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {LEAGUE_HOME_WIDGETS.map((w) => (
            <div
              key={w.id}
              className="flex items-start justify-between gap-4 p-3 rounded-lg bg-white/[0.03] border border-white/5"
              data-testid={`league-home-widget-row-${w.id}`}
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-white">{w.label}</p>
                <p className="text-xs text-[#A1A1AA] mt-0.5">{w.description}</p>
              </div>
              <Switch
                checked={!!visibility[w.id]}
                onCheckedChange={() => onToggle(w.id)}
                data-testid={`league-home-widget-toggle-${w.id}`}
              />
            </div>
          ))}
        </div>

        <DialogFooter className="flex items-center justify-between gap-2 pt-2">
          <Button
            variant="ghost"
            onClick={onReset}
            data-testid="league-home-settings-reset"
            className="text-[#A1A1AA] hover:text-white"
          >
            Reset to defaults
          </Button>
          <Button
            onClick={() => onOpenChange(false)}
            data-testid="league-home-settings-done"
            className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]"
          >
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
