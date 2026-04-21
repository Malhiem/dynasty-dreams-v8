// @ts-nocheck
import { useState, useEffect } from "react";
import { RefreshCw, Trophy, UserPlus, TrendingUp, Newspaper, AlertTriangle, Filter } from "lucide-react";
import TeamLink from "@/lovable/components/TeamLink";
import { Badge } from "@/components/ui/badge";

type ActivityType = "trade" | "waiver" | "achievement" | "injury" | "game_summary" | "news";

interface Activity {
  id: number;
  type: ActivityType;
  title: string;
  description: string;
  time: string;
  teams?: string[];
}

const FILTER_OPTIONS: { value: ActivityType | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "game_summary", label: "Game Summary" },
  { value: "injury", label: "Injury News" },
  { value: "trade", label: "Trades" },
  { value: "waiver", label: "Transactions" },
  { value: "achievement", label: "Achievements" },
  { value: "news", label: "League News" },
];

const STORAGE_KEY = "recent-activity-filters";

const mockActivity: Activity[] = [
  { id: 1, type: "trade", title: "Trade Completed", description: "Ice Breakers received J. Hughes for 2025 1st + S. Reinhart", time: "2h ago", teams: ["Ice Breakers"] },
  { id: 2, type: "achievement", title: "Weekly High Score", description: "You scored 127 points this week - 2nd highest in the league!", time: "1d ago" },
  { id: 3, type: "waiver", title: "Waiver Claim", description: "Frozen Assets claimed M. Tkachuk off waivers", time: "2d ago", teams: ["Frozen Assets"] },
  { id: 4, type: "injury", title: "Injury Alert", description: "C. McDavid expected to miss 2 games with lower body injury", time: "3d ago" },
  { id: 5, type: "game_summary", title: "Game Summary", description: "Your team scored 34 pts last night — McDavid 12, Makar 8, Hellebuyck 14", time: "12h ago" },
  { id: 6, type: "news", title: "League Update", description: "Trade deadline has been extended to March 25th by commissioner", time: "4d ago" },
  { id: 7, type: "injury", title: "Injury Update", description: "A. Matthews upgraded to day-to-day, could return this week", time: "1d ago" },
  { id: 8, type: "game_summary", title: "Game Summary", description: "Frozen Assets defeated Puck Dynasty 78-64 in Week 18 matchup", time: "2d ago", teams: ["Frozen Assets"] },
];

function loadFilters(): (ActivityType | "all")[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return JSON.parse(stored);
  } catch {}
  return ["all"];
}

function saveFilters(filters: (ActivityType | "all")[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
}

/** Renders description text, wrapping known team names in TeamLink */
const renderDescription = (description: string, teams?: string[]) => {
  if (!teams || teams.length === 0) return description;

  const parts: (string | React.ReactNode)[] = [];
  let remaining = description;
  let key = 0;

  for (const team of teams) {
    const idx = remaining.indexOf(team);
    if (idx === -1) continue;
    if (idx > 0) parts.push(remaining.slice(0, idx));
    parts.push(<TeamLink key={key++} name={team} className="font-medium" />);
    remaining = remaining.slice(idx + team.length);
  }
  if (remaining) parts.push(remaining);

  return <>{parts}</>;
};

const RecentActivity = () => {
  const [activeFilters, setActiveFilters] = useState<(ActivityType | "all")[]>(loadFilters);

  useEffect(() => {
    saveFilters(activeFilters);
  }, [activeFilters]);

  const toggleFilter = (value: ActivityType | "all") => {
    if (value === "all") {
      setActiveFilters(["all"]);
      return;
    }
    setActiveFilters((prev) => {
      const withoutAll = prev.filter((f) => f !== "all");
      const next = withoutAll.includes(value)
        ? withoutAll.filter((f) => f !== value)
        : [...withoutAll, value];
      return next.length === 0 ? ["all"] : next;
    });
  };

  const isActive = (value: ActivityType | "all") => activeFilters.includes(value);

  const filtered = activeFilters.includes("all")
    ? mockActivity
    : mockActivity.filter((a) => activeFilters.includes(a.type));

  return (
    <div className="stat-card p-0 overflow-hidden">
      <div className="p-6 pb-3 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold">Recent Activity</h3>
          <span className="text-xs text-primary font-medium cursor-pointer hover:underline">View All →</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {FILTER_OPTIONS.map((opt) => (
            <Badge
              key={opt.value}
              variant="outline"
              onClick={() => toggleFilter(opt.value)}
              className={`cursor-pointer text-xs px-2.5 py-0.5 transition-colors select-none ${
                isActive(opt.value)
                  ? "bg-primary/20 text-primary border-primary/40"
                  : "bg-secondary/50 text-muted-foreground border-border hover:bg-secondary hover:text-foreground"
              }`}
            >
              {opt.label}
            </Badge>
          ))}
        </div>
      </div>
      
      <div className="divide-y divide-border/50">
        {filtered.length === 0 && (
          <div className="p-8 text-center text-muted-foreground text-sm">
            <Filter className="h-5 w-5 mx-auto mb-2 opacity-50" />
            No activity matches your filters.
          </div>
        )}
        {filtered.map((activity, index) => (
          <div 
            key={activity.id} 
            className="p-4 hover:bg-secondary/20 transition-colors animate-slide-up"
            style={{ animationDelay: `${index * 50}ms` }}
          >
            <div className="flex gap-4">
              <div className={`flex-shrink-0 h-10 w-10 rounded-lg flex items-center justify-center ${getActivityIconStyle(activity.type)}`}>
                {getActivityIcon(activity.type)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <p className="font-medium text-foreground truncate">{activity.title}</p>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">{activity.time}</span>
                </div>
                <p className="text-sm text-muted-foreground line-clamp-2">
                  {renderDescription(activity.description, activity.teams)}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const getActivityIcon = (type: ActivityType) => {
  switch (type) {
    case "trade": return <RefreshCw className="h-5 w-5" />;
    case "achievement": return <Trophy className="h-5 w-5" />;
    case "waiver": return <UserPlus className="h-5 w-5" />;
    case "injury": return <AlertTriangle className="h-5 w-5" />;
    case "game_summary": return <Newspaper className="h-5 w-5" />;
    case "news": return <TrendingUp className="h-5 w-5" />;
  }
};

const getActivityIconStyle = (type: ActivityType) => {
  switch (type) {
    case "trade": return "bg-primary/20 text-primary";
    case "achievement": return "bg-accent/20 text-accent";
    case "waiver": return "bg-[hsl(var(--success))]/20 text-[hsl(var(--success))]";
    case "injury": return "bg-destructive/20 text-destructive";
    case "game_summary": return "bg-[hsl(var(--ice-subtle))]/30 text-primary";
    case "news": return "bg-orange-500/20 text-orange-400";
  }
};

export default RecentActivity;
