// @ts-nocheck
import { useEffect } from "react";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "./AppSidebar";
import { Search, Settings } from "lucide-react";
import { NotificationDropdown } from "./NotificationDropdown";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
// Iter 202 — UserLeagueMenu retained as export but no longer mounted in
// the top header; the sidebar's user card is the canonical entry point.
import CurrentLeagueDropdown from "./CurrentLeagueDropdown";
import { useUiScale } from "@/hooks/use-ui-scale";
import TradeDeadlineRibbon from "@/lovable/components/TradeDeadlineRibbon";

interface AppLayoutProps {
  children: React.ReactNode;
  onSettingsClick?: () => void;
}

export function AppLayout({ children, onSettingsClick }: AppLayoutProps) {
  const { scale } = useUiScale();

  // Apply scale to html root so rem-based sizes (Tailwind) scale proportionally
  useEffect(() => {
    document.documentElement.style.fontSize = `${scale}%`;
    return () => {
      document.documentElement.style.fontSize = '';
    };
  }, [scale]);

  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full bg-background">
        <AppSidebar />
        <div className="flex-1 flex flex-col">
          <header className="h-14 border-b border-border flex items-center justify-between px-4 bg-card/50 backdrop-blur-sm sticky top-0 z-10">
            <div className="flex items-center gap-4">
              <SidebarTrigger className="text-muted-foreground hover:text-foreground" />
              <div className="relative hidden md:block">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input 
                  placeholder="Search players, teams..." 
                  className="pl-9 w-64 bg-secondary border-border focus:border-primary"
                />
              </div>
            </div>
            <div className="flex items-center gap-3">
              {onSettingsClick && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="ghost" size="icon" onClick={onSettingsClick}>
                        <Settings className="h-5 w-5" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Customize Dashboard</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
              <NotificationDropdown />
              {/* Iter 202 — User profile menu removed from the top right
                  per user request; user controls now live in the sidebar
                  bottom user card to avoid duplicated entry points. */}
            </div>
          </header>
          {/* Iter 129 — Trade Deadline Countdown Ribbon (auto-hides when unset) */}
          <TradeDeadlineRibbon />
          <main className="flex-1 overflow-auto">
            {children}
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
