import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "./AppSidebar";
import { Search } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Input } from "@/components/ui/input";
import { NotificationsPanel } from "@/components/NotificationsPanel";
import { useGlobalSocketEvent } from "@/hooks/use-global-socket";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import GlobalTradeBuilder from "@/lovable/components/trade/GlobalTradeBuilder";
import AppPreferencesMenu from "./AppPreferencesMenu";
import TradeDeadlineRibbon from "@/lovable/components/TradeDeadlineRibbon";
import ProtectionListRibbon from "@/lovable/components/ProtectionListRibbon";
// Iter 207 — surface a sticky banner when user.status is banned/suspended.
import BannedUserBanner from "@/components/BannedUserBanner";

export function AppLayout({ children, onSettingsClick }) {
  const { user } = useAuth();
  const navigate = useNavigate();

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

  // Iter 231k — Real-time toast when a pending trade auto-processes.
  // Surfaces league-wide for every connected manager so users watching
  // the review window see the resolution the moment it lands.
  useGlobalSocketEvent("trade_processed", (payload) => {
    const desc = payload?.is_multi_party
      ? payload?.all_team_names || "Multi-team trade"
      : `${payload?.proposer_team_name || "Team A"} ↔ ${payload?.target_team_name || "Team B"}`;
    toast.success("Trade just executed", {
      description: desc,
      duration: 7000,
      action: payload?.trade_id
        ? {
            label: "View",
            onClick: () => navigate(`/transactions/trade/${payload.trade_id}`),
          }
        : undefined,
    });
  });

  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full bg-[#0A0A0A]">
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <header className="h-14 border-b border-white/10 flex items-center justify-between px-4 bg-[#141414]/80 backdrop-blur-sm sticky top-0 z-10">
            <div className="flex items-center gap-4">
              {/* Iter 231am — Sidebar trigger upsized on mobile (40×40
                  tap target with cyan tint + visible 1px border) so
                  users can find the menu affordance on a touch device
                  without hunting. Desktop keeps the compact 28×28
                  ghost button to stay out of the way of header
                  search + breadcrumbs. */}
              <SidebarTrigger
                className="h-10 w-10 md:h-7 md:w-7 border border-white/15 md:border-transparent bg-[#00D2FF]/10 md:bg-transparent text-[#00D2FF] md:text-[#A1A1AA] hover:text-white hover:bg-[#00D2FF]/20 md:hover:bg-transparent [&_svg]:size-5 md:[&_svg]:size-4"
                data-testid="sidebar-trigger"
                aria-label="Toggle navigation menu"
              />
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
              <NotificationsPanel />
              {/* Single unified cog — appearance toggle always available,
                  plus Team Settings + Customize this page when applicable. */}
              <AppPreferencesMenu onPageSettingsClick={onSettingsClick} />
              {user && (
                <div className="flex items-center gap-3 pl-3 border-l border-white/10">
                  {/* Username + role text removed from header per user request —
                      the avatar still surfaces account context, and the
                      sidebar footer continues to show full identity. */}
                  <div
                    className="h-9 w-9 rounded-full bg-[#00D2FF]/20 flex items-center justify-center text-sm font-bold text-[#00D2FF]"
                    title={user.name || ""}
                    data-testid="header-user-avatar"
                  >
                    {user.name?.[0]?.toUpperCase() || "U"}
                  </div>
                </div>
              )}
            </div>
          </header>
          {/* Iter 207 — Banned/suspended account banner with appeal form */}
          <BannedUserBanner />
          {/* Iter 129 — Trade Deadline Countdown Ribbon (auto-hides when unset) */}
          <TradeDeadlineRibbon />
          <ProtectionListRibbon />
          <main className="flex-1 overflow-auto p-6">
            {children}
          </main>
        </div>
      </div>
      {/* Persistent floating Trade Builder — survives route changes */}
      <GlobalTradeBuilder />
    </SidebarProvider>
  );
}
