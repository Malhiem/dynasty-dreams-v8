// @ts-nocheck
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { ChevronUp, ChevronDown, RotateCcw, LayoutDashboard, ArrowRight, ZoomIn } from "lucide-react";
import { DashboardWidget, useDashboardConfig } from "@/hooks/use-dashboard-config";
import { useUiScale } from "@/hooks/use-ui-scale";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface DashboardSettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: ReturnType<typeof useDashboardConfig>;
}

const AREA_LABELS: Record<DashboardWidget["area"], string> = {
  stats: "Stat Cards",
  main: "Main Content",
  sidebar: "Sidebar Widgets",
};

const AREA_ORDER: DashboardWidget["area"][] = ["stats", "main", "sidebar"];

const DashboardSettingsModal = ({ open, onOpenChange, config }: DashboardSettingsModalProps) => {
  const { toggleVisibility, moveUp, moveDown, resetToDefaults, getWidgetsByArea, changeArea } = config;
  const uiScale = useUiScale();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto bg-card border-border">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <LayoutDashboard className="h-5 w-5 text-primary" />
            Customize Dashboard
          </DialogTitle>
          <DialogDescription>
            Show, hide, reorder, and move widgets between sections. Changes are saved automatically.
          </DialogDescription>
        </DialogHeader>

        {/* UI Scale Control */}
        <div className="p-4 rounded-lg border border-border bg-secondary/20">
          <div className="flex items-center gap-2 mb-3">
            <ZoomIn className="h-4 w-4 text-primary" />
            <h4 className="text-sm font-semibold text-foreground">Display Scale</h4>
            <span className="ml-auto text-xs font-mono text-muted-foreground">{uiScale.scale}%</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground w-8">{uiScale.MIN_SCALE}%</span>
            <Slider
              value={[uiScale.scale]}
              onValueChange={([v]) => uiScale.setScale(v)}
              min={uiScale.MIN_SCALE}
              max={uiScale.MAX_SCALE}
              step={uiScale.STEP}
              className="flex-1"
            />
            <span className="text-xs text-muted-foreground w-8">{uiScale.MAX_SCALE}%</span>
          </div>
          {uiScale.scale !== 100 && (
            <Button variant="ghost" size="sm" onClick={uiScale.resetScale} className="mt-2 text-xs text-muted-foreground h-6 px-2">
              Reset to 100%
            </Button>
          )}
        </div>

        <div className="space-y-6 mt-2">
          {AREA_ORDER.map((area) => {
            const areaWidgets = getWidgetsByArea(area);
            return (
              <div key={area}>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                  {AREA_LABELS[area]}
                </h4>
                <div className="space-y-1">
                  {areaWidgets.map((widget, index) => {
                    const otherAreas = AREA_ORDER.filter((a) => a !== area);
                    return (
                      <div
                        key={widget.id}
                        className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
                          widget.visible
                            ? "bg-secondary/30 border-border"
                            : "bg-secondary/10 border-border/50 opacity-60"
                        }`}
                      >
                        <div className="flex flex-col gap-0.5">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-5 w-5"
                            disabled={index === 0}
                            onClick={() => moveUp(area, index)}
                          >
                            <ChevronUp className="h-3 w-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-5 w-5"
                            disabled={index === areaWidgets.length - 1}
                            onClick={() => moveDown(area, index)}
                          >
                            <ChevronDown className="h-3 w-3" />
                          </Button>
                        </div>

                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-foreground">{widget.label}</p>
                          <p className="text-xs text-muted-foreground">{widget.description}</p>
                        </div>

                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0">
                              <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="min-w-[160px]">
                            {otherAreas.map((target) => (
                              <DropdownMenuItem
                                key={target}
                                onClick={() => changeArea(widget.id, target)}
                              >
                                Move to {AREA_LABELS[target]}
                              </DropdownMenuItem>
                            ))}
                          </DropdownMenuContent>
                        </DropdownMenu>

                        <Switch
                          checked={widget.visible}
                          onCheckedChange={() => toggleVisibility(widget.id)}
                        />
                      </div>
                    );
                  })}
                  {areaWidgets.length === 0 && (
                    <p className="text-xs text-muted-foreground italic py-3 text-center">
                      No widgets — move one here from another section
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex justify-between items-center pt-4 border-t border-border mt-4">
          <Button variant="ghost" size="sm" onClick={resetToDefaults} className="text-muted-foreground">
            <RotateCcw className="h-4 w-4 mr-2" />
            Reset to Defaults
          </Button>
          <Button onClick={() => onOpenChange(false)} size="sm">
            Done
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default DashboardSettingsModal;
