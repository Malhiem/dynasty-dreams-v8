// @ts-nocheck
/**
 * Iter 148 — Draft Room chat panel split into All / Chat / Trades tabs.
 *
 * • "All" merges chat messages + trade activity (newest first per source,
 *   then interleaved by timestamp).
 * • "Chat" shows only chat messages (existing behavior).
 * • "Trades" shows in-flight + completed trades posted in this league.
 *   - Pending trades expose ✓ approve and ✗ veto buttons (only owners of
 *     teams NOT involved in the trade can vote; commissioner sees an
 *     override switch in `commish` mode for force-approve / force-veto).
 *   - Veto threshold is read from the league config and surfaced inline
 *     ("3 / 6 vetoes — auto-veto at 6").
 *   - Status stamps render for terminal states: PROCESSED (emerald),
 *     VETOED (rose), CANCELLED (slate), REJECTED (slate).
 */
import { useEffect, useMemo, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import {
  MessageSquare,
  Send,
  Check,
  X,
  Repeat,
  ShieldCheck,
  ShieldX,
  Clock,
  Sparkles,
  Trophy,
} from "lucide-react";
import { cn } from "@/lib/utils";
import api from "@/lib/api";
import { toast } from "sonner";

const POLL_MS = 10_000;

function fmtTs(t) {
  try {
    const d = t instanceof Date ? t : new Date(t);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function statusStamp(status) {
  const map = {
    processed: { label: "PROCESSED", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40" },
    executed:  { label: "PROCESSED", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40" },
    vetoed:    { label: "VETOED", cls: "bg-rose-500/15 text-rose-300 border-rose-500/40" },
    cancelled: { label: "CANCELLED", cls: "bg-slate-500/15 text-slate-300 border-slate-500/40" },
    withdrawn: { label: "CANCELLED", cls: "bg-slate-500/15 text-slate-300 border-slate-500/40" },
    rejected:  { label: "REJECTED", cls: "bg-slate-500/15 text-slate-300 border-slate-500/40" },
  };
  return map[status] || null;
}

function summarizeAssets(items) {
  if (!Array.isArray(items) || items.length === 0) return "—";
  return items
    .map((a) => {
      if (typeof a === "string") return a;
      if (a?.player_name) return a.position ? `${a.player_name} (${a.position})` : a.player_name;
      if (a?.pick_label) return a.pick_label;
      if (a?.round) return `${a.year || ""} R${a.round}`.trim();
      if (a?.faab) return `$${a.faab} FAAB`;
      return JSON.stringify(a);
    })
    .join(", ");
}

function tradeIsPending(t) {
  return t && ["pending", "accepted", "voting", "conditional"].includes(t.status);
}

function TradeRow({ trade, myUserId, isCommissioner, vetoThreshold, onVote, onForce }) {
  const stamp = statusStamp(trade.status);
  const isInvolved =
    trade.proposer_id === myUserId || trade.target_owner_id === myUserId;
  const counts = trade.votes || { approve: 0, veto: 0, choices: {} };
  const myVote = (counts.choices || {})[myUserId] || null;
  const showVoteButtons = tradeIsPending(trade) && !isInvolved && myUserId;
  const submittedAt = trade.submitted_at || trade.created_at;
  const tradeId = trade._id || trade.id;
  return (
    <div
      data-testid={`draft-chat-trade-row-${tradeId}`}
      className="rounded-md border border-cyan-500/30 bg-cyan-500/5 p-2 space-y-2"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-cyan-300">
          <Repeat className="h-3.5 w-3.5" />
          <span data-testid={`draft-chat-trade-from-${tradeId}`}>{trade.proposer_team_name || "—"}</span>
          <span className="text-muted-foreground">→</span>
          <span data-testid={`draft-chat-trade-to-${tradeId}`}>{trade.target_team_name || "—"}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {stamp && (
            <Badge
              variant="outline"
              className={cn("text-[9px] tracking-wider", stamp.cls)}
              data-testid={`draft-chat-trade-stamp-${tradeId}`}
            >
              {stamp.label}
            </Badge>
          )}
          {tradeIsPending(trade) && (
            <Badge
              variant="outline"
              className="text-[9px] tracking-wider bg-amber-500/15 text-amber-300 border-amber-500/40"
              data-testid={`draft-chat-trade-pending-${tradeId}`}
            >
              PENDING
            </Badge>
          )}
          <span className="text-[9px] text-muted-foreground tabular-nums">
            {fmtTs(submittedAt)}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <div>
          <div className="text-muted-foreground uppercase tracking-wide">Sending</div>
          <div className="text-foreground">
            {summarizeAssets(
              /* Iter 232N.49 — Trade docs saved by the trade builder
                 use `assets_offered` / `assets_requested`; older /
                 alternate shapes (proposer_assets, from_assets, etc.)
                 remain supported so historical draft chat cards still
                 render. Without the two `assets_*` fallbacks, every
                 real trade rendered "Sending —, Receiving —". */
              trade.proposer_assets || trade.from_assets || trade.assets_offered,
            )}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground uppercase tracking-wide">Receiving</div>
          <div className="text-foreground">
            {summarizeAssets(
              trade.target_assets || trade.to_assets || trade.assets_requested,
            )}
          </div>
        </div>
      </div>

      {tradeIsPending(trade) && vetoThreshold?.enabled && (
        <div className="flex items-center gap-1 text-[10px] text-muted-foreground" data-testid={`draft-chat-trade-veto-meter-${tradeId}`}>
          <ShieldX className="h-3 w-3 text-rose-400" />
          <span className="tabular-nums">
            {counts.veto || 0}/{vetoThreshold.teams_required} vetoes
          </span>
          <span>· auto-veto at {vetoThreshold.teams_required}</span>
        </div>
      )}

      {showVoteButtons && (
        <div className="flex items-center gap-1.5">
          <Button
            size="sm"
            variant={myVote === "approve" ? "default" : "outline"}
            className={cn(
              "h-7 px-2 gap-1 text-[11px]",
              myVote === "approve" ? "bg-emerald-500 hover:bg-emerald-600 text-white" : "text-emerald-300 hover:text-emerald-200",
            )}
            data-testid={`draft-chat-trade-approve-${tradeId}`}
            onClick={() => onVote(trade, "approve")}
          >
            <Check className="h-3 w-3" />
            Approve
          </Button>
          <Button
            size="sm"
            variant={myVote === "veto" ? "default" : "outline"}
            className={cn(
              "h-7 px-2 gap-1 text-[11px]",
              myVote === "veto" ? "bg-rose-500 hover:bg-rose-600 text-white" : "text-rose-300 hover:text-rose-200",
            )}
            data-testid={`draft-chat-trade-veto-${tradeId}`}
            onClick={() => onVote(trade, "veto")}
          >
            <X className="h-3 w-3" />
            Veto
          </Button>
          {myVote && (
            <span className="text-[9px] text-muted-foreground italic">
              You voted: {myVote}
            </span>
          )}
        </div>
      )}

      {isCommissioner && tradeIsPending(trade) && (
        <div className="flex items-center gap-1.5 pt-1 border-t border-cyan-500/20">
          <span className="text-[9px] uppercase tracking-wider text-cyan-300/80">Commish override</span>
          <Button
            size="sm"
            variant="outline"
            className="h-6 px-2 text-[10px] gap-1 text-emerald-300 hover:text-emerald-200"
            data-testid={`draft-chat-trade-force-approve-${tradeId}`}
            onClick={() => onForce(trade, "approve")}
          >
            <ShieldCheck className="h-3 w-3" />
            Force approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-6 px-2 text-[10px] gap-1 text-rose-300 hover:text-rose-200"
            data-testid={`draft-chat-trade-force-veto-${tradeId}`}
            onClick={() => onForce(trade, "veto")}
          >
            <ShieldX className="h-3 w-3" />
            Force veto
          </Button>
        </div>
      )}

      {isInvolved && tradeIsPending(trade) && (
        <div className="text-[9px] text-muted-foreground italic" data-testid={`draft-chat-trade-involved-${tradeId}`}>
          You're a party to this trade — voting is restricted to neutral teams.
        </div>
      )}
    </div>
  );
}

function ChatBubble({ msg, mySender }) {
  // Iter 170l — pick rows surfaced by an `auto-pick` system message
  // get a small clock badge next to the sender label so the Picks
  // list mirrors the Draft Board tile's auto-pick affordance. We
  // detect via the explicit `auto_picked` meta when present, falling
  // back to a tolerant "Auto-pick" sniff for older messages.
  const isAutoPick = msg.type === "pick" && (msg.auto_picked || /auto.pick/i.test(msg.text || ""));
  return (
    <div
      key={msg.id}
      data-testid={isAutoPick ? `draft-chat-auto-pick-${msg.id}` : undefined}
      className={cn(
        "text-xs rounded-md p-2",
        msg.type === "pick"
          ? "bg-primary/10 border border-primary/20"
          : msg.sender === mySender
          ? "bg-accent/10 border border-accent/20"
          : "bg-secondary/40",
      )}
    >
      <div className="flex items-center justify-between mb-0.5">
        <span
          className={cn(
            "font-semibold text-[11px] inline-flex items-center gap-1",
            msg.type === "pick" ? "text-primary" : "text-foreground",
          )}
        >
          {msg.sender}
          {isAutoPick && (
            <span
              className="inline-flex items-center justify-center h-3.5 w-3.5 rounded-sm bg-sky-500/25 text-sky-300"
              title="Auto-picked on timeout"
            >
              <Clock className="h-2 w-2" />
            </span>
          )}
        </span>
        <span className="text-[9px] text-muted-foreground">{fmtTs(msg.timestamp)}</span>
      </div>
      <p className="text-muted-foreground">{msg.text}</p>
    </div>
  );
}

export default function DraftChatPanel({
  chatMessages,
  chatInput,
  setChatInput,
  onSendChat,
  mySender,
  leagueId,
  myUserId,
  isCommissioner,
  league,
}) {
  const [tab, setTab] = useState("all");
  const [trades, setTrades] = useState([]);
  const [vetoThreshold, setVetoThreshold] = useState({ enabled: false, teams_required: 0 });

  const loadTrades = useCallback(async () => {
    if (!leagueId) return;
    try {
      const { data } = await api.get(`/trades?league_id=${leagueId}`);
      setTrades(Array.isArray(data) ? data : []);
    } catch (e) {
      /* silent — chat tab still works */
    }
  }, [leagueId]);

  useEffect(() => {
    loadTrades();
    if (!leagueId) return;
    const id = setInterval(loadTrades, POLL_MS);
    return () => clearInterval(id);
  }, [leagueId, loadTrades]);

  // Derive veto threshold from league config (already shipped by /leagues/{id}/veto-threshold-preview backend)
  useEffect(() => {
    if (!leagueId) return;
    const pct = league?.trade_veto_threshold_pct;
    if (pct == null) {
      setVetoThreshold({ enabled: false, teams_required: 0 });
      return;
    }
    api
      .get(`/leagues/${leagueId}/veto-threshold-preview`, { params: { pct } })
      .then(({ data }) => setVetoThreshold(data || { enabled: false, teams_required: 0 }))
      .catch(() => {});
  }, [leagueId, league?.trade_veto_threshold_pct]);

  const handleVote = useCallback(
    async (trade, choice) => {
      const tradeId = trade._id || trade.id;
      try {
        const { data } = await api.post(`/trades/${tradeId}/vote`, { vote: choice });
        toast.success(data?.message || `Vote ${choice} recorded`);
        await loadTrades();
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Vote failed");
      }
    },
    [loadTrades],
  );

  const handleForce = useCallback(
    async (trade, choice) => {
      const tradeId = trade._id || trade.id;
      try {
        if (choice === "approve") {
          await api.post(`/trades/${tradeId}/execute`);
          toast.success("Trade force-processed");
        } else {
          // Force-veto via vote (commissioner cast counts toward threshold; backend trips veto immediately if league is small)
          await api.post(`/trades/${tradeId}/vote`, { vote: "veto" });
          toast.success("Veto cast");
        }
        await loadTrades();
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Override failed");
      }
    },
    [loadTrades],
  );

  // Merge for "All": chat msgs + trades (as feed cards) by timestamp desc
  const mergedFeed = useMemo(() => {
    const items = [];
    for (const m of chatMessages || []) {
      items.push({ kind: "chat", ts: m.timestamp instanceof Date ? m.timestamp.getTime() : new Date(m.timestamp).getTime(), data: m });
    }
    for (const t of trades || []) {
      const ts = t.processed_at || t.responded_at || t.submitted_at || t.created_at;
      items.push({ kind: "trade", ts: ts ? new Date(ts).getTime() : 0, data: t });
    }
    items.sort((a, b) => a.ts - b.ts); // chronological so latest appears at the bottom (matches chat UX)
    return items;
  }, [chatMessages, trades]);

  const tradesOnly = useMemo(() => {
    return [...(trades || [])].sort(
      (a, b) =>
        new Date(a.submitted_at || a.created_at || 0).getTime() -
        new Date(b.submitted_at || b.created_at || 0).getTime(),
    );
  }, [trades]);

  // Iter 152 — Selections feed: filter chat events where type === "pick"
  const selectionsOnly = useMemo(() => {
    const items = (chatMessages || []).filter((m) => m.type === "pick");
    return items.sort(
      (a, b) =>
        (a.timestamp instanceof Date ? a.timestamp.getTime() : new Date(a.timestamp).getTime()) -
        (b.timestamp instanceof Date ? b.timestamp.getTime() : new Date(b.timestamp).getTime()),
    );
  }, [chatMessages]);

  return (
    <Card className="border-border" data-testid="draft-chat-panel">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-primary" />
          Draft Chat
        </CardTitle>
      </CardHeader>
      <CardContent className="p-2 space-y-2">
        <Tabs value={tab} onValueChange={setTab} className="w-full">
          <TabsList className="grid w-full grid-cols-4 h-8" data-testid="draft-chat-tabs">
            <TabsTrigger value="all" className="text-[11px]" data-testid="draft-chat-tab-all">
              <Sparkles className="h-3 w-3 mr-1" />
              All
            </TabsTrigger>
            <TabsTrigger value="chat" className="text-[11px]" data-testid="draft-chat-tab-chat">
              <MessageSquare className="h-3 w-3 mr-1" />
              Chat
            </TabsTrigger>
            <TabsTrigger value="selections" className="text-[11px]" data-testid="draft-chat-tab-selections">
              <Trophy className="h-3 w-3 mr-1" />
              Picks
              {selectionsOnly.length > 0 && (
                <span className="ml-1 inline-flex items-center justify-center h-4 min-w-4 px-1 rounded-full bg-primary/30 text-primary text-[9px] font-bold">
                  {selectionsOnly.length}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="trades" className="text-[11px]" data-testid="draft-chat-tab-trades">
              <Repeat className="h-3 w-3 mr-1" />
              Trades
              {trades.filter(tradeIsPending).length > 0 && (
                <span className="ml-1 inline-flex items-center justify-center h-4 min-w-4 px-1 rounded-full bg-amber-500/30 text-amber-200 text-[9px] font-bold">
                  {trades.filter(tradeIsPending).length}
                </span>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="all" className="m-0">
            <ScrollArea className="h-[260px]">
              <div className="space-y-2 p-1" data-testid="draft-chat-feed-all">
                {mergedFeed.length === 0 && (
                  <p className="text-xs text-muted-foreground italic text-center py-6">
                    No activity yet
                  </p>
                )}
                {mergedFeed.map((it, idx) =>
                  it.kind === "chat" ? (
                    <ChatBubble key={`c-${it.data.id || idx}`} msg={it.data} mySender={mySender} />
                  ) : (
                    <TradeRow
                      key={`t-${it.data._id || it.data.id || idx}`}
                      trade={it.data}
                      myUserId={myUserId}
                      isCommissioner={isCommissioner}
                      vetoThreshold={vetoThreshold}
                      onVote={handleVote}
                      onForce={handleForce}
                    />
                  ),
                )}
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="chat" className="m-0">
            <ScrollArea className="h-[260px]">
              <div className="space-y-2 p-1" data-testid="draft-chat-feed-chat">
                {(chatMessages || []).map((msg) => (
                  <ChatBubble key={msg.id} msg={msg} mySender={mySender} />
                ))}
              </div>
            </ScrollArea>
          </TabsContent>

          {/* Iter 152 — Picks/Selections feed (live as each pick is made) */}
          <TabsContent value="selections" className="m-0">
            <ScrollArea className="h-[260px]">
              <div className="space-y-2 p-1" data-testid="draft-chat-feed-selections">
                {selectionsOnly.length === 0 ? (
                  <p className="text-xs text-muted-foreground italic text-center py-6 flex flex-col items-center gap-1">
                    <Trophy className="h-4 w-4" />
                    No picks made yet
                  </p>
                ) : (
                  selectionsOnly.map((m) => (
                    <ChatBubble key={m.id} msg={m} mySender={mySender} />
                  ))
                )}
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="trades" className="m-0">
            <ScrollArea className="h-[260px]">
              <div className="space-y-2 p-1" data-testid="draft-chat-feed-trades">
                {tradesOnly.length === 0 && (
                  <p className="text-xs text-muted-foreground italic text-center py-6 flex flex-col items-center gap-1">
                    <Clock className="h-4 w-4" />
                    No trades posted yet in this draft
                  </p>
                )}
                {tradesOnly.map((t) => (
                  <TradeRow
                    key={t._id || t.id}
                    trade={t}
                    myUserId={myUserId}
                    isCommissioner={isCommissioner}
                    vetoThreshold={vetoThreshold}
                    onVote={handleVote}
                    onForce={handleForce}
                  />
                ))}
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>

        {tab !== "trades" && tab !== "selections" && (
          <div className="flex gap-2">
            <Input
              placeholder="Type a message..."
              className="h-8 text-sm bg-secondary/50 flex-1"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onSendChat()}
              data-testid="draft-chat-input"
            />
            <Button
              variant="default"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={onSendChat}
              data-testid="draft-chat-send"
            >
              <Send className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
