// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Calendar, Users, Shield, Trophy, Clock, DollarSign, ArrowRightLeft, Star } from "lucide-react";

interface ScoringCategory {
  name: string;
  abbr: string;
  points: number;
  description: string;
}

interface Transaction {
  id: number;
  type: "trade" | "waiver" | "drop" | "add";
  description: string;
  timestamp: string;
  team: string;
}

const skaterCategories: ScoringCategory[] = [
  { name: "Goals", abbr: "G", points: 3, description: "Goal scored" },
  { name: "Assists", abbr: "A", points: 2, description: "Primary or secondary assist" },
  { name: "Plus/Minus", abbr: "+/-", points: 0.5, description: "Per plus or minus" },
  { name: "Powerplay Points", abbr: "PPP", points: 1, description: "Bonus for PP goals/assists" },
  { name: "Shorthanded Points", abbr: "SHP", points: 2, description: "Bonus for SH goals/assists" },
  { name: "Game Winning Goals", abbr: "GWG", points: 2, description: "Bonus for game winners" },
  { name: "Shots on Goal", abbr: "SOG", points: 0.3, description: "Per shot on goal" },
  { name: "Hits", abbr: "HIT", points: 0.2, description: "Per hit" },
  { name: "Blocked Shots", abbr: "BLK", points: 0.3, description: "Per blocked shot" },
];

const goalieCategories: ScoringCategory[] = [
  { name: "Wins", abbr: "W", points: 5, description: "Goalie win" },
  { name: "Saves", abbr: "SV", points: 0.2, description: "Per save" },
  { name: "Goals Against", abbr: "GA", points: -1, description: "Per goal allowed" },
  { name: "Shutouts", abbr: "SO", points: 5, description: "Bonus for shutout" },
  { name: "Overtime Losses", abbr: "OTL", points: 1, description: "Point for OT loss" },
];

const recentTransactions: Transaction[] = [
  { id: 1, type: "trade", description: "Ice Crushers traded Alex Ovechkin to Puck Masters for 2025 1st + 2026 2nd", timestamp: "2 hours ago", team: "Multiple" },
  { id: 2, type: "waiver", description: "Glacier Kings claimed Marco Rossi ($12 FAAB)", timestamp: "5 hours ago", team: "Glacier Kings" },
  { id: 3, type: "add", description: "Frozen Thunder added Shane Wright from FA", timestamp: "8 hours ago", team: "Frozen Thunder" },
  { id: 4, type: "drop", description: "Team Frostbite dropped Jake Oettinger", timestamp: "1 day ago", team: "Team Frostbite" },
  { id: 5, type: "trade", description: "Blizzard Brigade traded 2025 2nd to Ice Crushers for Ryan Nugent-Hopkins", timestamp: "1 day ago", team: "Multiple" },
];

interface LeagueInfoItem {
  label: string;
  value: string;
}

const seasonInfo: LeagueInfoItem[] = [
  { label: "Season Length", value: "October – April (26 weeks)" },
  { label: "Number of Matchups", value: "22 regular season + 4 playoff weeks" },
  { label: "Matchup Period", value: "Monday – Sunday" },
  { label: "Playoff Teams", value: "8 of 12 teams" },
  { label: "Playoff Format", value: "Head-to-Head, Single Elimination" },
  { label: "Scoring Type", value: "Points League" },
  { label: "Waiver Type", value: "FAAB ($100 budget)" },
  { label: "Trade Deadline", value: "Week 18 (Mid-February)" },
];

interface RosterSlot {
  position: string;
  skaterSlots: number;
  goalieSlots: number;
}

const rosterConfig: RosterSlot[] = [
  { position: "Starting Roster", skaterSlots: 12, goalieSlots: 2 },
  { position: "Bench", skaterSlots: 4, goalieSlots: 1 },
  { position: "Injury Reserve (IR)", skaterSlots: 3, goalieSlots: 1 },
  { position: "Minors", skaterSlots: 6, goalieSlots: 1 },
];

const positionBreakdown = [
  { position: "Centers (C)", slots: 3 },
  { position: "Left Wing (LW)", slots: 3 },
  { position: "Right Wing (RW)", slots: 3 },
  { position: "Defensemen (D)", slots: 4 },
  { position: "Utility (F/D)", slots: 1 },
  { position: "Goalies (G)", slots: 2 },
];

const salaryCapInfo: LeagueInfoItem[] = [
  { label: "Salary Cap Limit", value: "$82,500,000" },
  { label: "Cap Floor", value: "$61,000,000" },
  { label: "Max Retention Slots", value: "3 per season" },
  { label: "Max Retained Salary", value: "50% of player's AAV" },
  { label: "LTIR Eligible", value: "Yes (24+ games missed)" },
  { label: "Entry-Level Contract Max", value: "3 years" },
];

const draftInfo: LeagueInfoItem[] = [
  { label: "Draft Type", value: "Snake Draft" },
  { label: "Draft Rounds", value: "16 rounds" },
  { label: "Pick Time Limit", value: "90 seconds" },
  { label: "Draft Lottery", value: "Bottom 4 non-playoff teams" },
  { label: "Tradeable Draft Picks", value: "Up to 3 years out" },
  { label: "Keeper Slots", value: "Unlimited (dynasty)" },
];

const Scoring = () => {
  return (
    <AppLayout>
      <div className="container py-8 space-y-6">
        <div>
          <h1 className="text-2xl font-bold">League Information</h1>
          <p className="text-muted-foreground">Everything you need to know about how the league works</p>
        </div>

        <Tabs defaultValue="overview" className="space-y-4">
          <TabsList className="bg-secondary flex-wrap h-auto gap-1">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="roster">Roster Rules</TabsTrigger>
            <TabsTrigger value="scoring">Scoring</TabsTrigger>
            <TabsTrigger value="salary">Salary Cap</TabsTrigger>
            <TabsTrigger value="draft">Draft</TabsTrigger>
            <TabsTrigger value="transactions">Transactions</TabsTrigger>
          </TabsList>

          {/* OVERVIEW TAB */}
          <TabsContent value="overview" className="space-y-6">
            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Calendar className="h-5 w-5 text-primary" />
                  Season & Schedule
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {seasonInfo.map((item) => (
                    <div key={item.label} className="flex justify-between items-center p-3 rounded-lg bg-secondary/30">
                      <span className="text-sm text-muted-foreground">{item.label}</span>
                      <span className="text-sm font-semibold">{item.value}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card className="bg-card border-border">
                <CardContent className="pt-6 text-center space-y-2">
                  <Users className="h-8 w-8 text-primary mx-auto" />
                  <p className="text-2xl font-bold">12</p>
                  <p className="text-sm text-muted-foreground">Teams in League</p>
                </CardContent>
              </Card>
              <Card className="bg-card border-border">
                <CardContent className="pt-6 text-center space-y-2">
                  <Trophy className="h-8 w-8 text-primary mx-auto" />
                  <p className="text-2xl font-bold">22</p>
                  <p className="text-sm text-muted-foreground">Regular Season Matchups</p>
                </CardContent>
              </Card>
              <Card className="bg-card border-border">
                <CardContent className="pt-6 text-center space-y-2">
                  <Shield className="h-8 w-8 text-primary mx-auto" />
                  <p className="text-2xl font-bold">Dynasty</p>
                  <p className="text-sm text-muted-foreground">League Format</p>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* ROSTER RULES TAB */}
          <TabsContent value="roster" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Users className="h-5 w-5 text-primary" />
                    Roster Caps by Section
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border">
                        <TableHead>Section</TableHead>
                        <TableHead className="text-center">Skaters</TableHead>
                        <TableHead className="text-center">Goalies</TableHead>
                        <TableHead className="text-center">Total</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rosterConfig.map((slot) => (
                        <TableRow key={slot.position} className="border-border">
                          <TableCell className="font-medium">{slot.position}</TableCell>
                          <TableCell className="text-center">{slot.skaterSlots}</TableCell>
                          <TableCell className="text-center">{slot.goalieSlots}</TableCell>
                          <TableCell className="text-center font-semibold text-primary">
                            {slot.skaterSlots + slot.goalieSlots}
                          </TableCell>
                        </TableRow>
                      ))}
                      <TableRow className="border-border bg-secondary/30">
                        <TableCell className="font-bold">Total Roster</TableCell>
                        <TableCell className="text-center font-bold">
                          {rosterConfig.reduce((sum, s) => sum + s.skaterSlots, 0)}
                        </TableCell>
                        <TableCell className="text-center font-bold">
                          {rosterConfig.reduce((sum, s) => sum + s.goalieSlots, 0)}
                        </TableCell>
                        <TableCell className="text-center font-bold text-primary">
                          {rosterConfig.reduce((sum, s) => sum + s.skaterSlots + s.goalieSlots, 0)}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Shield className="h-5 w-5 text-accent" />
                    Starting Lineup Positions
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border">
                        <TableHead>Position</TableHead>
                        <TableHead className="text-center">Slots</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {positionBreakdown.map((pos) => (
                        <TableRow key={pos.position} className="border-border">
                          <TableCell className="font-medium">{pos.position}</TableCell>
                          <TableCell className="text-center">
                            <Badge variant="outline" className="bg-secondary/50">{pos.slots}</Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                      <TableRow className="border-border bg-secondary/30">
                        <TableCell className="font-bold">Total Starting</TableCell>
                        <TableCell className="text-center">
                          <Badge className="bg-primary/20 text-primary border-primary/30">
                            {positionBreakdown.reduce((sum, p) => sum + p.slots, 0)}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </div>

            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Star className="h-5 w-5 text-primary" />
                  Additional Roster Rules
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {[
                    { label: "IR Eligibility", value: "Players on NHL IR or IR+" },
                    { label: "Minors Eligibility", value: "Players in AHL/Juniors/Europe" },
                    { label: "Max Adds per Week", value: "4 transactions" },
                    { label: "Min Roster Size", value: "20 players" },
                    { label: "Lineup Lock", value: "Per-game at puck drop" },
                    { label: "Taxi Squad", value: "Not enabled" },
                  ].map((item) => (
                    <div key={item.label} className="flex justify-between items-center p-3 rounded-lg bg-secondary/30">
                      <span className="text-sm text-muted-foreground">{item.label}</span>
                      <span className="text-sm font-semibold">{item.value}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* SCORING TAB */}
          <TabsContent value="scoring" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <span className="h-6 w-6 rounded bg-primary/20 flex items-center justify-center text-xs text-primary">S</span>
                    Skater Scoring
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border">
                        <TableHead>Category</TableHead>
                        <TableHead className="text-center">Abbr</TableHead>
                        <TableHead className="text-right">Points</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {skaterCategories.map((cat) => (
                        <TableRow key={cat.abbr} className="border-border">
                          <TableCell>
                            <div>
                              <p className="font-medium">{cat.name}</p>
                              <p className="text-xs text-muted-foreground">{cat.description}</p>
                            </div>
                          </TableCell>
                          <TableCell className="text-center">
                            <Badge variant="outline" className="bg-secondary/50">{cat.abbr}</Badge>
                          </TableCell>
                          <TableCell className="text-right font-semibold text-primary">
                            {cat.points > 0 ? "+" : ""}{cat.points}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <span className="h-6 w-6 rounded bg-accent/20 flex items-center justify-center text-xs text-accent">G</span>
                    Goalie Scoring
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border">
                        <TableHead>Category</TableHead>
                        <TableHead className="text-center">Abbr</TableHead>
                        <TableHead className="text-right">Points</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {goalieCategories.map((cat) => (
                        <TableRow key={cat.abbr} className="border-border">
                          <TableCell>
                            <div>
                              <p className="font-medium">{cat.name}</p>
                              <p className="text-xs text-muted-foreground">{cat.description}</p>
                            </div>
                          </TableCell>
                          <TableCell className="text-center">
                            <Badge variant="outline" className="bg-secondary/50">{cat.abbr}</Badge>
                          </TableCell>
                          <TableCell className={`text-right font-semibold ${cat.points >= 0 ? "text-primary" : "text-destructive"}`}>
                            {cat.points > 0 ? "+" : ""}{cat.points}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* SALARY CAP TAB */}
          <TabsContent value="salary" className="space-y-6">
            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <DollarSign className="h-5 w-5 text-primary" />
                  Salary Cap Rules
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {salaryCapInfo.map((item) => (
                    <div key={item.label} className="flex justify-between items-center p-3 rounded-lg bg-secondary/30">
                      <span className="text-sm text-muted-foreground">{item.label}</span>
                      <span className="text-sm font-semibold">{item.value}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* DRAFT TAB */}
          <TabsContent value="draft" className="space-y-6">
            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Star className="h-5 w-5 text-primary" />
                  Draft Settings
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {draftInfo.map((item) => (
                    <div key={item.label} className="flex justify-between items-center p-3 rounded-lg bg-secondary/30">
                      <span className="text-sm text-muted-foreground">{item.label}</span>
                      <span className="text-sm font-semibold">{item.value}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* TRANSACTIONS TAB */}
          <TabsContent value="transactions">
            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ArrowRightLeft className="h-5 w-5 text-primary" />
                  Recent Transactions
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[500px]">
                  <div className="space-y-4">
                    {recentTransactions.map((tx) => (
                      <TransactionRow key={tx.id} transaction={tx} />
                    ))}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
};

const TransactionRow = ({ transaction }: { transaction: Transaction }) => {
  const getTypeBadge = () => {
    switch (transaction.type) {
      case "trade": return <Badge className="bg-primary/20 text-primary border-primary/30">Trade</Badge>;
      case "waiver": return <Badge className="bg-accent/20 text-accent border-accent/30">Waiver</Badge>;
      case "add": return <Badge className="bg-success/20 text-success border-success/30">Add</Badge>;
      case "drop": return <Badge className="bg-destructive/20 text-destructive border-destructive/30">Drop</Badge>;
    }
  };

  return (
    <div className="flex items-start gap-4 p-4 rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-colors">
      <div className="shrink-0">{getTypeBadge()}</div>
      <div className="flex-1">
        <p className="text-sm">{transaction.description}</p>
        <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
          <span>{transaction.team}</span>
          <span>•</span>
          <span>{transaction.timestamp}</span>
        </div>
      </div>
    </div>
  );
};

export default Scoring;
