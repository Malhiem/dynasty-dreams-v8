// @ts-nocheck
import { useState } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowRightLeft, ThumbsUp, ThumbsDown, Clock, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import TeamLink from "@/lovable/components/TeamLink";

interface TradeAsset {
  name: string;
  position: string;
  age: number;
  capHit: string;
  goals: number;
  assists: number;
  points: number;
  fantasyPts: number;
  type: "player" | "pick";
}

interface PendingTrade {
  id: string;
  teamA: string;
  teamB: string;
  assetsFromA: TradeAsset[];
  assetsFromB: TradeAsset[];
  status: "pending" | "accepted" | "vetoed" | "processed";
  submittedAt: string;
  processesAt: string;
  votes: { approve: number; veto: number; total: number };
  salaryRetained?: { team: string; amount: string; duration: string };
}

const MOCK_TRADES: PendingTrade[] = [
  {
    id: "T-001",
    teamA: "Frost Giants",
    teamB: "Ice Wolves",
    assetsFromA: [
      { name: "Connor McDavid", position: "C", age: 29, capHit: "$12.5M", goals: 38, assists: 62, points: 100, fantasyPts: 412, type: "player" },
    ],
    assetsFromB: [
      { name: "Auston Matthews", position: "C", age: 28, capHit: "$13.25M", goals: 42, assists: 38, points: 80, fantasyPts: 368, type: "player" },
      { name: "2026 1st Round Pick", position: "—", age: 0, capHit: "—", goals: 0, assists: 0, points: 0, fantasyPts: 0, type: "pick" },
    ],
    status: "pending",
    submittedAt: "2026-02-20 14:30",
    processesAt: "2026-02-23 14:30",
    votes: { approve: 5, veto: 2, total: 12 },
  },
  {
    id: "T-002",
    teamA: "Northern Lights",
    teamB: "Blizzard",
    assetsFromA: [
      { name: "Cale Makar", position: "D", age: 27, capHit: "$9.0M", goals: 18, assists: 52, points: 70, fantasyPts: 310, type: "player" },
    ],
    assetsFromB: [
      { name: "Quinn Hughes", position: "D", age: 26, capHit: "$7.85M", goals: 12, assists: 58, points: 70, fantasyPts: 295, type: "player" },
      { name: "2027 2nd Round Pick", position: "—", age: 0, capHit: "—", goals: 0, assists: 0, points: 0, fantasyPts: 0, type: "pick" },
    ],
    status: "pending",
    submittedAt: "2026-02-21 09:15",
    processesAt: "2026-02-24 09:15",
    votes: { approve: 3, veto: 1, total: 12 },
    salaryRetained: { team: "Northern Lights", amount: "$1.5M", duration: "2 years" },
  },
  {
    id: "T-003",
    teamA: "Avalanche",
    teamB: "Storm Surge",
    assetsFromA: [
      { name: "Mikko Rantanen", position: "RW", age: 29, capHit: "$9.25M", goals: 30, assists: 35, points: 65, fantasyPts: 290, type: "player" },
    ],
    assetsFromB: [
      { name: "Tim Stützle", position: "C", age: 24, capHit: "$8.35M", goals: 28, assists: 42, points: 70, fantasyPts: 305, type: "player" },
    ],
    status: "accepted",
    submittedAt: "2026-02-18 11:00",
    processesAt: "2026-02-21 11:00",
    votes: { approve: 8, veto: 1, total: 12 },
  },
];

const statusConfig = {
  pending: { label: "Pending Review", icon: Clock, variant: "outline" as const, className: "border-amber-500/50 text-amber-400" },
  accepted: { label: "Accepted", icon: CheckCircle2, variant: "outline" as const, className: "border-emerald-500/50 text-emerald-400" },
  vetoed: { label: "Vetoed", icon: XCircle, variant: "destructive" as const, className: "" },
  processed: { label: "Processed", icon: CheckCircle2, variant: "outline" as const, className: "border-muted-foreground/50 text-muted-foreground" },
};

function TradeCard({ trade }: { trade: PendingTrade }) {
  const status = statusConfig[trade.status];
  const StatusIcon = status.icon;

  return (
    <Card className="border-border/50">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ArrowRightLeft className="h-5 w-5 text-primary" />
            <CardTitle className="text-lg">
              <TeamLink name={trade.teamA} /> <span className="text-muted-foreground mx-1">↔</span> <TeamLink name={trade.teamB} />
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={status.variant} className={status.className}>
              <StatusIcon className="h-3 w-3 mr-1" />
              {status.label}
            </Badge>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground mt-1">
          <span>Submitted: {trade.submittedAt}</span>
          <span>Processes: {trade.processesAt}</span>
          <span>Votes: {trade.votes.approve} approve / {trade.votes.veto} veto of {trade.votes.total}</span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Team A sends */}
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2"><TeamLink name={trade.teamA} /> sends:</p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Player</TableHead>
                  <TableHead className="text-xs">Pos</TableHead>
                  <TableHead className="text-xs">Age</TableHead>
                  <TableHead className="text-xs">Cap Hit</TableHead>
                  <TableHead className="text-xs">G</TableHead>
                  <TableHead className="text-xs">A</TableHead>
                  <TableHead className="text-xs">P</TableHead>
                  <TableHead className="text-xs">FPts</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trade.assetsFromA.map((asset) => (
                  <TableRow key={asset.name}>
                    <TableCell className="font-medium text-sm">
                      {asset.name}
                      {asset.type === "pick" && <Badge variant="secondary" className="ml-1 text-[10px]">Pick</Badge>}
                    </TableCell>
                    <TableCell className="text-sm">{asset.position}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.age : "—"}</TableCell>
                    <TableCell className="text-sm">{asset.capHit}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.goals : "—"}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.assists : "—"}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.points : "—"}</TableCell>
                    <TableCell className="text-sm font-semibold text-primary">{asset.type === "player" ? asset.fantasyPts : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Team B sends */}
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2"><TeamLink name={trade.teamB} /> sends:</p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Player</TableHead>
                  <TableHead className="text-xs">Pos</TableHead>
                  <TableHead className="text-xs">Age</TableHead>
                  <TableHead className="text-xs">Cap Hit</TableHead>
                  <TableHead className="text-xs">G</TableHead>
                  <TableHead className="text-xs">A</TableHead>
                  <TableHead className="text-xs">P</TableHead>
                  <TableHead className="text-xs">FPts</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trade.assetsFromB.map((asset) => (
                  <TableRow key={asset.name}>
                    <TableCell className="font-medium text-sm">
                      {asset.name}
                      {asset.type === "pick" && <Badge variant="secondary" className="ml-1 text-[10px]">Pick</Badge>}
                    </TableCell>
                    <TableCell className="text-sm">{asset.position}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.age : "—"}</TableCell>
                    <TableCell className="text-sm">{asset.capHit}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.goals : "—"}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.assists : "—"}</TableCell>
                    <TableCell className="text-sm">{asset.type === "player" ? asset.points : "—"}</TableCell>
                    <TableCell className="text-sm font-semibold text-primary">{asset.type === "player" ? asset.fantasyPts : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>

        {trade.salaryRetained && (
          <div className="mt-3 flex items-center gap-2 text-xs">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
            <span className="text-muted-foreground">
              Salary retained: <span className="text-foreground font-medium">{trade.salaryRetained.team}</span> retains{" "}
              <span className="text-foreground font-medium">{trade.salaryRetained.amount}</span> for{" "}
              <span className="text-foreground font-medium">{trade.salaryRetained.duration}</span>
            </span>
          </div>
        )}

        {trade.status === "pending" && (
          <div className="flex gap-2 mt-4 justify-end">
            <Button variant="outline" size="sm" className="text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10">
              <ThumbsUp className="h-3.5 w-3.5 mr-1" /> Approve
            </Button>
            <Button variant="outline" size="sm" className="text-destructive border-destructive/30 hover:bg-destructive/10">
              <ThumbsDown className="h-3.5 w-3.5 mr-1" /> Veto
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const Transactions = () => {
  const { league, leagueTeams } = useActiveLeague();
  const leagueTeamsCount = leagueTeams?.length || 0;
  const totalFpts = Math.round((leagueTeams || []).reduce((a, t) => a + ((t.points_for || 0) + (t.live_points || 0)), 0));
  const pendingTradesCount = 0; // wired in follow-up
  const pendingClaimsCount = 0;

  const [tab, setTab] = useState("pending");

  const pending = MOCK_TRADES.filter((t) => t.status === "pending");
  const accepted = MOCK_TRADES.filter((t) => t.status === "accepted");
  const all = MOCK_TRADES;

  return (
    <AppLayout>
        <div className="container py-8">
          <LeagueContextBanner title="Transactions" kpiLabel="Active trades" kpiValue={pendingTradesCount} primaryHref="/trade-block" primaryLabel="Open Trade Block" />
        <div className="mb-6 animate-fade-in">
          <h1 className="text-3xl font-bold mb-2">Transactions</h1>
          <p className="text-muted-foreground">Review pending and accepted trades. Cast your vote to approve or veto.</p>
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="mb-6">
            <TabsTrigger value="pending">
              Pending
              {pending.length > 0 && (
                <Badge variant="secondary" className="ml-2 text-xs">{pending.length}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="accepted">
              Accepted
              {accepted.length > 0 && (
                <Badge variant="secondary" className="ml-2 text-xs">{accepted.length}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="all">All</TabsTrigger>
          </TabsList>

          <TabsContent value="pending" className="space-y-4">
            {pending.length === 0 ? (
              <Card><CardContent className="py-8 text-center text-muted-foreground">No pending trades.</CardContent></Card>
            ) : pending.map((t) => <TradeCard key={t.id} trade={t} />)}
          </TabsContent>

          <TabsContent value="accepted" className="space-y-4">
            {accepted.length === 0 ? (
              <Card><CardContent className="py-8 text-center text-muted-foreground">No accepted trades awaiting processing.</CardContent></Card>
            ) : accepted.map((t) => <TradeCard key={t.id} trade={t} />)}
          </TabsContent>

          <TabsContent value="all" className="space-y-4">
            {all.map((t) => <TradeCard key={t.id} trade={t} />)}
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
};

export default Transactions;
