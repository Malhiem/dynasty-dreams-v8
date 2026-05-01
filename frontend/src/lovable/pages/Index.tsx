// @ts-nocheck
import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import StatCard from "@/lovable/components/dashboard/StatCard";
import PlayerRoster from "@/lovable/components/dashboard/PlayerRoster";
import Standings from "@/lovable/components/dashboard/Standings";
import RecentActivity from "@/lovable/components/dashboard/RecentActivity";
import DraftPicks from "@/lovable/components/dashboard/DraftPicks";
import PlayerNotifications from "@/lovable/components/dashboard/PlayerNotifications";
import WeeklyTopScorers from "@/lovable/components/dashboard/WeeklyTopScorers";
import PendingTrades from "@/lovable/components/dashboard/PendingTrades";
import ChatWidget from "@/lovable/components/dashboard/ChatWidget";
import TradeBlockWidget from "@/lovable/components/dashboard/TradeBlockWidget";
import LeagueScheduleWidget from "@/lovable/components/dashboard/LeagueScheduleWidget";
import DashboardSettingsModal from "@/lovable/components/dashboard/DashboardSettingsModal";
import { useDashboardConfig } from "@/hooks/use-dashboard-config";
import OutstandingFeesBanner from "@/lovable/components/dashboard/OutstandingFeesBanner";
import { Trophy, TrendingUp, Users, Target, Calendar, Flag, CalendarCheck, Clock } from "lucide-react";
import { Separator } from "@/components/ui/separator";

const STAT_WIDGETS: Record<string, { title: string; value: string; subtitle: string; icon: any; trend?: { value: number; positive: boolean }; highlight?: boolean }> = {
  "stat-rank": { title: "League Rank", value: "#2", subtitle: "of 12 teams", icon: Trophy, trend: { value: 8, positive: true }, highlight: true },
  "stat-points": { title: "Total Points", value: "812", subtitle: "Season total", icon: TrendingUp, trend: { value: 5.2, positive: true } },
  
  "stat-roster": { title: "Roster Size", value: "24", subtitle: "6 spots available", icon: Users },
};

const WIDGET_COMPONENTS: Record<string, React.FC> = {
  "standings": Standings,
  "trade-block": TradeBlockWidget,
  "league-schedule": LeagueScheduleWidget,
  "player-roster": PlayerRoster,
  "notifications": PlayerNotifications,
  "weekly-top-scorers": WeeklyTopScorers,
  "draft-picks": DraftPicks,
  "recent-activity": RecentActivity,
  "pending-trades": PendingTrades,
  "chat-widget": ChatWidget,
};

const TRADE_DEADLINE = new Date("2026-03-21T15:00:00-05:00");

const TradeDeadlineCountdown = () => {
  const [timeLeft, setTimeLeft] = useState(() => getTimeLeft());

  function getTimeLeft() {
    const diff = Math.max(0, TRADE_DEADLINE.getTime() - Date.now());
    return {
      days: Math.floor(diff / (1000 * 60 * 60 * 24)),
      hours: Math.floor((diff / (1000 * 60 * 60)) % 24),
      minutes: Math.floor((diff / (1000 * 60)) % 60),
      expired: diff <= 0,
    };
  }

  useEffect(() => {
    const interval = setInterval(() => setTimeLeft(getTimeLeft()), 60_000);
    return () => clearInterval(interval);
  }, []);

  if (timeLeft.expired) {
    return (
      <>
        <Separator orientation="vertical" className="h-4" />
        <div className="flex items-center gap-1.5">
          <Clock className="h-4 w-4 text-muted-foreground" />
          <span className="font-semibold text-muted-foreground">Trade deadline passed</span>
        </div>
        <Separator orientation="vertical" className="h-4" />
      </>
    );
  }

  if (timeLeft.days >= 30) return null;

  return (
    <>
      <Separator orientation="vertical" className="h-4" />
      <div className="flex items-center gap-1.5">
        <Clock className="h-4 w-4 text-destructive animate-pulse" />
        <span className="font-semibold text-destructive tabular-nums">
          {timeLeft.days}d {timeLeft.hours}h {timeLeft.minutes}m remaining
        </span>
      </div>
      <Separator orientation="vertical" className="h-4" />
    </>
  );
};

const Index = () => {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const config = useDashboardConfig();
  const { getVisibleWidgets } = config;

  const visibleStats = getVisibleWidgets("stats");
  const visibleMain = getVisibleWidgets("main");
  const visibleSidebar = getVisibleWidgets("sidebar");

  return (
    <AppLayout onSettingsClick={() => setSettingsOpen(true)}>
      <div className="container py-8">
        {/* Welcome Section */}
        <div className="mb-8 animate-fade-in">
          <h1 className="text-3xl font-bold mb-2">
            Welcome to the <span className="text-gradient-ice">Dynasty Pro League</span>
          </h1>
          <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <Calendar className="h-4 w-4 text-destructive" />
              <span>Trade Deadline: <span className="font-semibold text-foreground">Mar 21, 2026 — 3:00 PM EST</span></span>
            </div>
            <TradeDeadlineCountdown />
            <div className="flex items-center gap-1.5">
              <Flag className="h-4 w-4 text-primary" />
              <span>Playoffs Begin: <span className="font-semibold text-foreground">Apr 6, 2026</span></span>
            </div>
            <Separator orientation="vertical" className="h-4" />
            <div className="flex items-center gap-1.5">
              <CalendarCheck className="h-4 w-4 text-accent" />
              <span>Season Ends: <span className="font-semibold text-foreground">Apr 27, 2026</span></span>
            </div>
          </div>
        </div>

        <OutstandingFeesBanner />

        {/* Stats Grid */}
        {visibleStats.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            {visibleStats.map((widget) => {
              const statProps = STAT_WIDGETS[widget.id];
              if (statProps) return <StatCard key={widget.id} {...statProps} />;
              const Component = WIDGET_COMPONENTS[widget.id];
              return Component ? (
                <div key={widget.id} className="max-h-48 overflow-y-auto rounded-xl border border-border">
                  <Component />
                </div>
              ) : null;
            })}
          </div>
        )}

        {/* Main Content Grid */}
        {(visibleMain.length > 0 || visibleSidebar.length > 0) ? (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {visibleMain.length > 0 && (
              <div className="lg:col-span-2 space-y-6">
                {visibleMain.map((widget) => {
                  const statProps = STAT_WIDGETS[widget.id];
                  if (statProps) return <StatCard key={widget.id} {...statProps} />;
                  const Component = WIDGET_COMPONENTS[widget.id];
                  return Component ? <Component key={widget.id} /> : null;
                })}
              </div>
            )}

            {visibleSidebar.length > 0 && (
              <div className="space-y-6">
                {visibleSidebar.map((widget) => {
                  const statProps = STAT_WIDGETS[widget.id];
                  if (statProps) return <StatCard key={widget.id} {...statProps} />;
                  const Component = WIDGET_COMPONENTS[widget.id];
                  return Component ? <Component key={widget.id} /> : null;
                })}
              </div>
            )}
          </div>
        ) : visibleStats.length === 0 ? (
          <div
            className="rounded-xl border border-dashed border-border p-10 text-center"
            data-testid="dashboard-empty-state"
          >
            <p className="text-sm text-muted-foreground mb-3">
              You've hidden every widget on this page.
            </p>
            <button
              className="text-sm font-semibold text-[#00D2FF] hover:underline"
              onClick={() => setSettingsOpen(true)}
              data-testid="dashboard-empty-state-open-settings"
            >
              Open Customize Dashboard →
            </button>
          </div>
        ) : null}
      </div>

      <DashboardSettingsModal
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        config={config}
      />
    </AppLayout>
  );
};

export default Index;
