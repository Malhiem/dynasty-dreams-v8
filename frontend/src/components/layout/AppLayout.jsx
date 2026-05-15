import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "./AppSidebar";
import { Search, Settings, Users as UsersIcon } from "lucide-react";
import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NotificationsPanel } from "@/components/NotificationsPanel";
import { useGlobalSocketEvent } from "@/hooks/use-global-socket";
import { toast } from "sonner";
import GlobalTradeBuilder from "@/lovable/components/trade/GlobalTradeBuilder";
import TeamSettingsModal from "@/lovable/components/TeamSettingsModal";
import CurrentLeagueDropdown from "./CurrentLeagueDropdown";

export function AppLayout({ children, onSettingsClick }) {
  const { user } = useAuth();
  const [teamSettingsOpen, setTeamSettingsOpen] = useState(false);

  // Real-time championship / consolation toasts (app-wide)
  useGlobalSocketEvent("championship_crowned", (payload) => {
    toast.success(`🏆 ${payload?.team_name || "A team"} won the championship!`, {
      description: payload?.unlocked_trades
        ? `${payload.unlocked_trades} conditional trade(s) unlocked`
        : `Final score ${payload?.score || ""}`.trim(),
      duration: 8000,
    });
  });
  useGlobalSocketEvent("consolation_crowned", (payload) => {
    toast(`🎖 ${payload?.team_name || "A team"} won the consolation bracket`, {
      description: payload?.applied_steps?.[0] || "Prize recorded",
      duration: 7000,
    });
  });

  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full bg-[#0A0A0A]">
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <header className="h-14 border-b border-white/10 flex items-center justify-between px-4 bg-[#141414]/80 backdrop-blur-sm sticky top-0 z-10">
            <div className="flex items-center gap-4">
              <SidebarTrigger className="text-[#A1A1AA] hover:text-white" data-testid="sidebar-trigger" />
              <div className="relative hidden md:block">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#A1A1AA]" />
                <Input
                  placeholder="Search players, teams..."
                  className="pl-9 w-64 bg-[#1A1A1A] border-white/10 text-white placeholder:text-[#52525B] focus:border-[#00D2FF]"
                  data-testid="header-search"
                />
              </div>
            </div>
            <div className="flex items-center gap-3">
              <CurrentLeagueDropdown />
              <NotificationsPanel />
              {/* Team Settings cog — always visible to logged-in users with a team.
                  Opens a modal letting users edit team name, abbreviation
                  (max 3 chars), and logo (URL or file upload). */}
              {user && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setTeamSettingsOpen(true)}
                  data-testid="team-settings-cog"
                  title="Team settings"
                  className="text-[#A1A1AA] hover:text-white hover:bg-white/5 h-9 w-9"
                >
                  <UsersIcon className="h-5 w-5" />
                </Button>
              )}
              {/* Page-level "Customize" cog — rendered only when the
                  hosting page wires up an onSettingsClick handler (e.g.
                  League Home → DashboardSettingsModal). Placed next to
                  the notifications bell per UX spec. */}
              {onSettingsClick && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onSettingsClick}
                  data-testid="page-settings-cog"
                  title="Customize this page"
                  className="text-[#A1A1AA] hover:text-white hover:bg-white/5 h-9 w-9"
                >
                  <Settings className="h-5 w-5" />
                </Button>
              )}
              {user && (
                <div className="flex items-center gap-3 pl-3 border-l border-white/10">
                  <div className="text-right hidden sm:block">
                    <p className="text-sm font-medium text-white">{user.name}</p>
                    <p className="text-xs text-[#A1A1AA]">{user.role}</p>
                  </div>
                  <div className="h-9 w-9 rounded-full bg-[#00D2FF]/20 flex items-center justify-center text-sm font-bold text-[#00D2FF]">
                    {user.name?.[0]?.toUpperCase() || "U"}
                  </div>
                </div>
              )}
            </div>
          </header>
          <main className="flex-1 overflow-auto p-6">
            {children}
          </main>
        </div>
      </div>
      {/* Persistent floating Trade Builder — survives route changes */}
      <GlobalTradeBuilder />
      {/* Team Settings modal */}
      <TeamSettingsModal open={teamSettingsOpen} onOpenChange={setTeamSettingsOpen} />
    </SidebarProvider>
  );
}
