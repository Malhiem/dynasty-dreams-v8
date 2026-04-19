import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowRightLeft, ThumbsUp, ThumbsDown, Clock, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

const statusConfig = {
  pending: { label: "Pending Review", icon: Clock, className: "border-amber-500/50 text-amber-400" },
  accepted: { label: "Accepted", icon: CheckCircle2, className: "border-emerald-500/50 text-emerald-400" },
  rejected: { label: "Rejected", icon: XCircle, className: "border-[#FF3B30]/50 text-[#FF3B30]" },
  vetoed: { label: "Vetoed", icon: XCircle, className: "border-[#FF3B30]/50 text-[#FF3B30]" },
  withdrawn: { label: "Withdrawn", icon: XCircle, className: "border-[#A1A1AA]/50 text-[#A1A1AA]" },
  processed: { label: "Processed", icon: CheckCircle2, className: "border-[#A1A1AA]/50 text-[#A1A1AA]" },
};

function TradeCard({ trade, onVote, onAccept, onReject, onWithdraw, userId }) {
  const status = statusConfig[trade.status] || statusConfig.pending;
  const StatusIcon = status.icon;
  const isProposer = trade.proposer_id === userId;
  const isTarget = trade.target_owner_id === userId;

  return (
    <Card className="border-white/10">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ArrowRightLeft className="h-5 w-5 text-[#00D2FF]" />
            <CardTitle className="text-lg text-white">
              {trade.proposer_team_name} <span className="text-[#A1A1AA] mx-1">↔</span> {trade.target_team_name}
            </CardTitle>
          </div>
          <Badge variant="outline" className={status.className}>
            <StatusIcon className="h-3 w-3 mr-1" />{status.label}
          </Badge>
        </div>
        <div className="flex items-center gap-4 text-xs text-[#A1A1AA] mt-1">
          <span>Submitted: {new Date(trade.submitted_at).toLocaleDateString()}</span>
          {trade.votes && <span>Votes: {trade.votes.approve} approve / {trade.votes.veto} veto</span>}
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Proposer sends */}
          <div>
            <p className="text-sm font-medium text-[#A1A1AA] mb-2">{trade.proposer_team_name} sends:</p>
            <div className="space-y-2">
              {(trade.assets_offered || []).map((asset, i) => (
                <div key={i} className="flex items-center gap-3 p-2 rounded bg-[#1A1A1A]/30">
                  <Badge variant="outline" className="text-white border-white/20">{asset.position || "Pick"}</Badge>
                  <div>
                    <p className="text-sm text-white">{asset.player_name || `${asset.pick_year} ${asset.pick_round}`}</p>
                    {asset.nhl_team && <p className="text-xs text-[#A1A1AA]">{asset.nhl_team} · {asset.points || 0} pts</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
          {/* Target sends */}
          <div>
            <p className="text-sm font-medium text-[#A1A1AA] mb-2">{trade.target_team_name} sends:</p>
            <div className="space-y-2">
              {(trade.assets_requested || []).map((asset, i) => (
                <div key={i} className="flex items-center gap-3 p-2 rounded bg-[#1A1A1A]/30">
                  <Badge variant="outline" className="text-white border-white/20">{asset.position || "Pick"}</Badge>
                  <div>
                    <p className="text-sm text-white">{asset.player_name || `${asset.pick_year} ${asset.pick_round}`}</p>
                    {asset.nhl_team && <p className="text-xs text-[#A1A1AA]">{asset.nhl_team} · {asset.points || 0} pts</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {trade.message && (
          <p className="text-sm text-[#A1A1AA] mt-3 italic">"{trade.message}"</p>
        )}

        {trade.status === "pending" && (
          <div className="flex gap-2 mt-4 justify-end">
            {isTarget && (
              <>
                <Button size="sm" className="bg-[#34C759] text-black hover:bg-[#34C759]/80" onClick={() => onAccept(trade._id)} data-testid={`accept-${trade._id}`}>
                  <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Accept
                </Button>
                <Button variant="outline" size="sm" className="text-[#FF3B30] border-[#FF3B30]/30" onClick={() => onReject(trade._id)} data-testid={`reject-${trade._id}`}>
                  <XCircle className="h-3.5 w-3.5 mr-1" /> Reject
                </Button>
              </>
            )}
            {isProposer && (
              <Button variant="outline" size="sm" className="text-[#A1A1AA] border-white/10" onClick={() => onWithdraw(trade._id)} data-testid={`withdraw-${trade._id}`}>
                Withdraw
              </Button>
            )}
            {!isTarget && !isProposer && (
              <>
                <Button variant="outline" size="sm" className="text-[#34C759] border-[#34C759]/30 hover:bg-[#34C759]/10" onClick={() => onVote(trade._id, "approve")}>
                  <ThumbsUp className="h-3.5 w-3.5 mr-1" /> Approve
                </Button>
                <Button variant="outline" size="sm" className="text-[#FF3B30] border-[#FF3B30]/30 hover:bg-[#FF3B30]/10" onClick={() => onVote(trade._id, "veto")}>
                  <ThumbsDown className="h-3.5 w-3.5 mr-1" /> Veto
                </Button>
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function TransactionsPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState("pending");
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchTrades = async () => {
    try {
      const { data } = await api.get("/trades");
      setTrades(data);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { fetchTrades(); }, []);

  const handleVote = async (tradeId, vote) => {
    try {
      await api.post(`/trades/${tradeId}/vote`, { vote });
      await fetchTrades();
    } catch (e) { console.error(e); }
  };

  const handleAccept = async (tradeId) => {
    try {
      await api.post(`/trades/${tradeId}/accept`);
      await fetchTrades();
    } catch (e) { console.error(e); }
  };

  const handleReject = async (tradeId) => {
    try {
      await api.post(`/trades/${tradeId}/reject`);
      await fetchTrades();
    } catch (e) { console.error(e); }
  };

  const handleWithdraw = async (tradeId) => {
    try {
      await api.post(`/trades/${tradeId}/withdraw`);
      await fetchTrades();
    } catch (e) { console.error(e); }
  };

  const pending = trades.filter(t => t.status === "pending");
  const accepted = trades.filter(t => t.status === "accepted");

  return (
    <AppLayout>
      <div className="space-y-6" data-testid="transactions-page">
        <div>
          <h1 className="text-2xl font-bold text-white">Transactions</h1>
          <p className="text-[#A1A1AA]">Review pending and accepted trades. Cast your vote to approve or veto.</p>
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="pending">Pending {pending.length > 0 && <Badge variant="secondary" className="ml-2 text-xs">{pending.length}</Badge>}</TabsTrigger>
            <TabsTrigger value="accepted">Accepted {accepted.length > 0 && <Badge variant="secondary" className="ml-2 text-xs">{accepted.length}</Badge>}</TabsTrigger>
            <TabsTrigger value="all">All</TabsTrigger>
          </TabsList>

          <TabsContent value="pending" className="space-y-4 mt-4">
            {pending.length === 0 ? (
              <Card className="border-white/10"><CardContent className="py-8 text-center text-[#A1A1AA]">No pending trades.</CardContent></Card>
            ) : pending.map(t => <TradeCard key={t._id} trade={t} userId={user?.id} onVote={handleVote} onAccept={handleAccept} onReject={handleReject} onWithdraw={handleWithdraw} />)}
          </TabsContent>

          <TabsContent value="accepted" className="space-y-4 mt-4">
            {accepted.length === 0 ? (
              <Card className="border-white/10"><CardContent className="py-8 text-center text-[#A1A1AA]">No accepted trades.</CardContent></Card>
            ) : accepted.map(t => <TradeCard key={t._id} trade={t} userId={user?.id} onVote={handleVote} onAccept={handleAccept} onReject={handleReject} onWithdraw={handleWithdraw} />)}
          </TabsContent>

          <TabsContent value="all" className="space-y-4 mt-4">
            {trades.length === 0 ? (
              <Card className="border-white/10"><CardContent className="py-8 text-center text-[#A1A1AA]">No trades yet.</CardContent></Card>
            ) : trades.map(t => <TradeCard key={t._id} trade={t} userId={user?.id} onVote={handleVote} onAccept={handleAccept} onReject={handleReject} onWithdraw={handleWithdraw} />)}
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
}
