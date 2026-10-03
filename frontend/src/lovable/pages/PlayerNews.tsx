// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertTriangle, TrendingUp, TrendingDown, Activity, Clock } from "lucide-react";

interface NewsItem {
  id: number;
  player: string;
  team: string;
  type: "injury" | "hot" | "cold" | "news" | "lineup";
  headline: string;
  summary: string;
  impact: "high" | "medium" | "low";
  timestamp: string;
  isOnMyTeam?: boolean;
}

const newsItems: NewsItem[] = [
  {
    id: 1,
    player: "Connor McDavid",
    team: "EDM",
    type: "hot",
    headline: "McDavid on 8-game point streak",
    summary: "Captain has 5G, 12A in his last 8 games. Fantasy value continues to climb.",
    impact: "high",
    timestamp: "10 min ago",
    isOnMyTeam: true,
  },
  {
    id: 2,
    player: "Auston Matthews",
    team: "TOR",
    type: "injury",
    headline: "Matthews day-to-day with upper body injury",
    summary: "Left practice early. Expected to miss 1-2 games. Monitor closely.",
    impact: "high",
    timestamp: "25 min ago",
  },
  {
    id: 3,
    player: "Igor Shesterkin",
    team: "NYR",
    type: "lineup",
    headline: "Shesterkin confirmed starter tonight",
    summary: "Will face BOS in marquee matchup. Good streaming option.",
    impact: "medium",
    timestamp: "1 hour ago",
    isOnMyTeam: true,
  },
  {
    id: 4,
    player: "Kirill Kaprizov",
    team: "MIN",
    type: "cold",
    headline: "Kaprizov in scoring drought",
    summary: "Zero goals in last 6 games. Still producing assists but owners concerned.",
    impact: "medium",
    timestamp: "2 hours ago",
  },
  {
    id: 5,
    player: "Quinn Hughes",
    team: "VAN",
    type: "news",
    headline: "Hughes nominated for Norris Trophy",
    summary: "D-man continues elite season. Trade value at all-time high.",
    impact: "low",
    timestamp: "3 hours ago",
  },
  {
    id: 6,
    player: "Nikita Kucherov",
    team: "TBL",
    type: "hot",
    headline: "Kucherov has 4 multi-point games this week",
    summary: "League-leading scorer showing no signs of slowing down.",
    impact: "high",
    timestamp: "4 hours ago",
    isOnMyTeam: true,
  },
];

const PlayerNews = () => {
  return (
    <AppLayout>
      <div className="container py-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Player News</h1>
            <p className="text-muted-foreground">Real-time updates and injury alerts</p>
          </div>
        </div>

        <Tabs defaultValue="all" className="space-y-4">
          <TabsList className="bg-secondary">
            <TabsTrigger value="all">All News</TabsTrigger>
            <TabsTrigger value="myteam">My Team</TabsTrigger>
            <TabsTrigger value="injuries">Injuries</TabsTrigger>
            <TabsTrigger value="trending">Trending</TabsTrigger>
          </TabsList>

          <TabsContent value="all" className="space-y-4">
            <NewsGrid items={newsItems} />
          </TabsContent>

          <TabsContent value="myteam" className="space-y-4">
            <NewsGrid items={newsItems.filter(n => n.isOnMyTeam)} />
          </TabsContent>

          <TabsContent value="injuries" className="space-y-4">
            <NewsGrid items={newsItems.filter(n => n.type === "injury")} />
          </TabsContent>

          <TabsContent value="trending" className="space-y-4">
            <NewsGrid items={newsItems.filter(n => n.type === "hot" || n.type === "cold")} />
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
};

const NewsGrid = ({ items }: { items: NewsItem[] }) => {
  if (items.length === 0) {
    return (
      <Card className="bg-card border-border">
        <CardContent className="py-12 text-center text-muted-foreground">
          No news items to display
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-4">
      {items.map((item) => (
        <NewsCard key={item.id} item={item} />
      ))}
    </div>
  );
};

const NewsCard = ({ item }: { item: NewsItem }) => {
  const getTypeIcon = () => {
    switch (item.type) {
      case "injury": return <AlertTriangle className="h-4 w-4 text-destructive" />;
      case "hot": return <TrendingUp className="h-4 w-4 text-success" />;
      case "cold": return <TrendingDown className="h-4 w-4 text-ice" />;
      case "lineup": return <Activity className="h-4 w-4 text-accent" />;
      default: return <Clock className="h-4 w-4 text-muted-foreground" />;
    }
  };

  const getTypeBadge = () => {
    switch (item.type) {
      case "injury": return <Badge variant="destructive">Injury</Badge>;
      case "hot": return <Badge className="bg-success/20 text-success border-success/30">Hot Streak</Badge>;
      case "cold": return <Badge className="bg-ice/20 text-ice border-ice/30">Cold Streak</Badge>;
      case "lineup": return <Badge className="bg-accent/20 text-accent border-accent/30">Lineup</Badge>;
      default: return <Badge variant="outline">News</Badge>;
    }
  };

  return (
    <Card className={`bg-card border-border hover:border-primary/30 transition-colors ${item.isOnMyTeam ? "border-l-4 border-l-primary" : ""}`}>
      <CardContent className="p-4">
        <div className="flex items-start gap-4">
          <div className="h-12 w-12 rounded-lg bg-secondary flex items-center justify-center text-sm font-bold shrink-0">
            {item.team}
          </div>
          
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              {getTypeIcon()}
              <span className="font-semibold">{item.player}</span>
              <span className="text-muted-foreground">•</span>
              <span className="text-sm text-muted-foreground">{item.team}</span>
              {item.isOnMyTeam && (
                <Badge variant="outline" className="text-xs bg-primary/10 text-primary border-primary/30">
                  On My Team
                </Badge>
              )}
            </div>
            
            <h3 className="font-semibold text-lg mb-1">{item.headline}</h3>
            <p className="text-muted-foreground text-sm mb-3">{item.summary}</p>
            
            <div className="flex items-center gap-3">
              {getTypeBadge()}
              <Badge variant={item.impact === "high" ? "destructive" : "outline"} className={
                item.impact === "high" ? "" : 
                item.impact === "medium" ? "bg-accent/20 text-accent border-accent/30" : 
                "bg-secondary text-muted-foreground"
              }>
                {item.impact.charAt(0).toUpperCase() + item.impact.slice(1)} Impact
              </Badge>
              <span className="text-xs text-muted-foreground ml-auto">{item.timestamp}</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default PlayerNews;
