// @ts-nocheck
// Iter 232M.1 — Live trade proposal modal + counter mode.
//
// This modal used to render hardcoded rosters and had no submit handler.
// It now:
//   • Loads the real "my roster" from GET /roster/{myTeamId}/detail
//   • Loads the real "my draft picks" from GET /teams/{myTeamId}/draft-picks
//   • Falls back to props (`targetPlayers`) for the target roster when
//     provided; otherwise fetches GET /roster/{targetTeamId}/detail
//   • Submits the proposal by POSTing:
//       - action=counter to /trades/{counterFromTradeId}/respond
//         when `counterFromTradeId` is set (from TradeBlock's
//         `?counter_from={id}&with={teamId}` deep-link on the
//         Trade Detail page's Counter button).
//       - POST /trades otherwise (regular proposal).
//   • Renders a sky-500 "Countering trade #XXX" banner in counter mode.
import { useEffect, useMemo, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { ArrowRightLeft, ChevronLeft, ChevronRight, Send, Reply, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

export const TradeProposalModal = ({
  open, onOpenChange,
  targetTeam, targetPlayers,
  prefilledTheirPlayerIds,
  // Iter 232M.1 — Live-data props.
  leagueId, targetTeamId, myTeamId,
  counterFromTradeId,
}) => {
  const isCounter = Boolean(counterFromTradeId);
  const [step, setStep] = useState("their-roster");
  // Selection uses stable string ObjectIds so we can pass them straight
  // into the /trades payload.
  const [selectedTheirIds, setSelectedTheirIds] = useState([]);
  const [selectedMyPlayerIds, setSelectedMyPlayerIds] = useState([]);
  const [selectedMyPickIds, setSelectedMyPickIds] = useState([]);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // ── Data: my roster + my picks + (fallback) target roster ─────
  const [myRoster, setMyRoster] = useState([]);
  const [myPicks, setMyPicks] = useState([]);
  const [theirRoster, setTheirRoster] = useState(null);

  // Reset selection whenever the modal opens.
  useEffect(() => {
    if (!open) return;
    setStep("their-roster");
    setSelectedTheirIds([]);
    setSelectedMyPlayerIds([]);
    setSelectedMyPickIds([]);
    setMessage("");
  }, [open]);

  useEffect(() => {
    if (!open || !myTeamId) return;
    let cancelled = false;
    api.get(`/roster/${myTeamId}/detail`)
      .then(({ data }) => {
        if (!cancelled) setMyRoster(data?.players || []);
      })
      .catch(() => { if (!cancelled) setMyRoster([]); });
    api.get(`/teams/${myTeamId}/draft-picks`)
      .then(({ data }) => {
        // Endpoint returns { picks: [...] } or a bare array — accept either.
        const raw = Array.isArray(data) ? data : (data?.picks || data?.items || []);
        if (!cancelled) setMyPicks(raw);
      })
      .catch(() => { if (!cancelled) setMyPicks([]); });
    return () => { cancelled = true; };
  }, [open, myTeamId]);

  useEffect(() => {
    if (!open || !targetTeamId) return;
    // In counter mode, always fetch fresh so the manager can pick from
    // the FULL target roster (not just what's on the trade block). Same
    // for the normal path when the caller didn't hand us a roster.
    if (!counterFromTradeId && targetPlayers && targetPlayers.length > 0) {
      setTheirRoster(null);
      return;
    }
    let cancelled = false;
    api.get(`/roster/${targetTeamId}/detail`)
      .then(({ data }) => {
        if (!cancelled) setTheirRoster(data?.players || []);
      })
      .catch(() => { if (!cancelled) setTheirRoster([]); });
    return () => { cancelled = true; };
  }, [open, targetTeamId, targetPlayers, counterFromTradeId]);

  // ── Normalised lists that both live-fetched and prop-passed data
  //     use the same shape: { id, name, position, team }. `id` is
  //     always a string ObjectId for POST payload compatibility.
  const theirList = useMemo(() => {
    const source = (theirRoster && theirRoster.length > 0)
      ? theirRoster
      : (targetPlayers || []);
    return source.map((p) => ({
      id: String(p.player_id || p.id || p._id || ""),
      name: p.name,
      position: p.position || "—",
      team: p.team || p.nhl_team || "",
    })).filter((p) => p.id);
  }, [theirRoster, targetPlayers]);

  const myList = useMemo(() => {
    return (myRoster || []).map((p) => ({
      id: String(p.player_id || p._id || p.id || ""),
      name: p.name,
      position: p.position || "—",
      team: p.team || p.nhl_team || "",
    })).filter((p) => p.id);
  }, [myRoster]);

  const myPickList = useMemo(() => {
    return (myPicks || []).map((p) => ({
      id: String(p._id || p.pick_id || p.id || ""),
      year: p.year || p.pick_year,
      round: p.round || p.pick_round,
      original_team_name: p.original_team_name || p.from_team_name || null,
    })).filter((p) => p.id);
  }, [myPicks]);

  // Seed the requested side from prefilledTheirPlayerIds.
  useEffect(() => {
    if (!open) return;
    if (prefilledTheirPlayerIds && prefilledTheirPlayerIds.length > 0) {
      // Convert legacy numeric ids to strings & filter to those that exist
      // in `theirList` so we don't seed ghosts.
      const target = prefilledTheirPlayerIds.map(String);
      const valid = theirList.filter((p) => target.includes(p.id)).map((p) => p.id);
      if (valid.length > 0) {
        setSelectedTheirIds(valid);
        setStep("my-roster");
      }
    }
  }, [open, prefilledTheirPlayerIds, theirList]);

  const handleClose = () => {
    setStep("their-roster");
    setSelectedTheirIds([]);
    setSelectedMyPlayerIds([]);
    setSelectedMyPickIds([]);
    setMessage("");
    onOpenChange(false);
  };

  const toggle = (setter, list) => (id) =>
    setter((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const stepTitle = {
    "their-roster": `${targetTeam || "Their"}'s Roster`,
    "my-roster": "Your Roster",
    review: isCounter ? "Review Your Counter Offer" : "Review Trade Proposal",
  }[step];

  // ── Submit ──────────────────────────────────────────────────
  const buildAssets = () => {
    const assets_requested = selectedTheirIds.map((pid) => ({
      asset_type: "player",
      player_id: pid,
    }));
    const assets_offered = [
      ...selectedMyPlayerIds.map((pid) => ({ asset_type: "player", player_id: pid })),
      ...selectedMyPickIds.map((pid) => ({ asset_type: "pick", pick_id: pid })),
    ];
    return { assets_offered, assets_requested };
  };

  const handleSubmit = async () => {
    if (submitting) return;
    if (!leagueId || !targetTeamId) {
      toast.error("League or target team missing — reopen this dialog from a specific team.");
      return;
    }
    const { assets_offered, assets_requested } = buildAssets();
    if (assets_offered.length === 0 && assets_requested.length === 0) {
      toast.error("Add at least one player or pick to either side.");
      return;
    }
    setSubmitting(true);
    try {
      if (isCounter) {
        await api.post(`/trades/${counterFromTradeId}/respond`, {
          action: "counter",
          assets_offered,
          assets_requested,
          message: message.trim() || undefined,
        });
        toast.success("Counter offer sent", {
          description: `${targetTeam} will see it in their inbox.`,
        });
      } else {
        await api.post(`/trades`, {
          league_id: leagueId,
          target_team_id: targetTeamId,
          assets_offered,
          assets_requested,
          message: message.trim() || undefined,
        });
        toast.success("Trade proposal sent", {
          description: `${targetTeam} will decide whether to accept, counter, or reject.`,
        });
      }
      handleClose();
    } catch (e) {
      toast.error(
        isCounter ? "Couldn't send counter" : "Couldn't send proposal",
        { description: e?.response?.data?.detail || e?.message },
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl bg-card border-border" data-testid="trade-proposal-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {isCounter ? <Reply className="h-5 w-5 text-sky-400" /> : <ArrowRightLeft className="h-5 w-5 text-primary" />}
            {stepTitle}
          </DialogTitle>
        </DialogHeader>

        {isCounter && (
          <div
            className="rounded-md border border-sky-500/40 bg-sky-500/10 p-3 text-sm text-sky-200 flex items-start gap-2"
            data-testid="trade-proposal-counter-banner"
          >
            <Reply className="h-4 w-4 mt-0.5 shrink-0" />
            <div className="space-y-0.5">
              <p className="font-medium">
                Countering trade #{counterFromTradeId?.slice(-6)}
              </p>
              <p className="text-xs text-sky-300/80">
                Submitting will decline the original proposal and send this counter back to {targetTeam}. They can accept, counter again, or reject.
              </p>
            </div>
          </div>
        )}

        <div className="flex gap-2 mb-2">
          {["their-roster", "my-roster", "review"].map((s, idx) => (
            <div
              key={s}
              className={`flex-1 h-1 rounded-full ${
                idx <= ["their-roster", "my-roster", "review"].indexOf(step)
                  ? "bg-primary"
                  : "bg-secondary"
              }`}
            />
          ))}
        </div>

        {step === "their-roster" && (
          <div className="space-y-3 max-h-80 overflow-y-auto" data-testid="trade-proposal-their-roster">
            <p className="text-sm text-muted-foreground">
              Select players you want from {targetTeam || "them"}
            </p>
            {theirList.length === 0 ? (
              <p className="text-sm italic text-muted-foreground py-4 text-center">
                No players available on this roster.
              </p>
            ) : theirList.map((player) => (
              <div
                key={player.id}
                className={`flex items-center gap-3 p-3 rounded-lg border transition-colors cursor-pointer ${
                  selectedTheirIds.includes(player.id)
                    ? "border-primary bg-primary/10"
                    : "border-border hover:border-primary/50"
                }`}
                onClick={() => toggle(setSelectedTheirIds, theirList)(player.id)}
                data-testid={`trade-proposal-their-player-${player.id}`}
              >
                <Checkbox checked={selectedTheirIds.includes(player.id)} />
                <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold">
                  {player.team}
                </div>
                <div className="flex-1">
                  <p className="font-medium">{player.name}</p>
                  <p className="text-sm text-muted-foreground">{player.position}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {step === "my-roster" && (
          <div className="space-y-4 max-h-80 overflow-y-auto" data-testid="trade-proposal-my-roster">
            <p className="text-sm text-muted-foreground">Select players and picks to offer</p>

            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-muted-foreground uppercase">Players</h4>
              {myList.length === 0 ? (
                <p className="text-sm italic text-muted-foreground py-2">No players on your roster.</p>
              ) : myList.map((player) => (
                <div
                  key={player.id}
                  className={`flex items-center gap-3 p-3 rounded-lg border transition-colors cursor-pointer ${
                    selectedMyPlayerIds.includes(player.id)
                      ? "border-primary bg-primary/10"
                      : "border-border hover:border-primary/50"
                  }`}
                  onClick={() => toggle(setSelectedMyPlayerIds, myList)(player.id)}
                  data-testid={`trade-proposal-my-player-${player.id}`}
                >
                  <Checkbox checked={selectedMyPlayerIds.includes(player.id)} />
                  <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold">
                    {player.team}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium">{player.name}</p>
                    <p className="text-sm text-muted-foreground">{player.position}</p>
                  </div>
                </div>
              ))}
            </div>

            {myPickList.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold text-muted-foreground uppercase">Draft Picks</h4>
                {myPickList.map((pick) => (
                  <div
                    key={pick.id}
                    className={`flex items-center gap-3 p-3 rounded-lg border transition-colors cursor-pointer ${
                      selectedMyPickIds.includes(pick.id)
                        ? "border-primary bg-primary/10"
                        : "border-border hover:border-primary/50"
                    }`}
                    onClick={() => toggle(setSelectedMyPickIds, myPickList)(pick.id)}
                    data-testid={`trade-proposal-my-pick-${pick.id}`}
                  >
                    <Checkbox checked={selectedMyPickIds.includes(pick.id)} />
                    <div className="flex-1">
                      <p className="font-medium">
                        {pick.year} R{pick.round}
                      </p>
                      {pick.original_team_name && (
                        <p className="text-sm text-muted-foreground">Via {pick.original_team_name}</p>
                      )}
                    </div>
                    <Badge variant="outline" className="bg-accent/20 text-accent">Pick</Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {step === "review" && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 rounded-lg bg-secondary/30 border border-border" data-testid="trade-proposal-review-receive">
                <h4 className="text-sm font-semibold text-muted-foreground mb-3">You Receive</h4>
                <div className="space-y-1.5">
                  {theirList
                    .filter((p) => selectedTheirIds.includes(p.id))
                    .map((p) => (
                      <div key={p.id} className="text-sm">
                        <span className="font-medium">{p.name}</span>
                        <span className="text-muted-foreground ml-1">({p.position})</span>
                      </div>
                    ))}
                  {selectedTheirIds.length === 0 && (
                    <p className="text-xs italic text-muted-foreground">Nothing selected</p>
                  )}
                </div>
              </div>
              <div className="p-4 rounded-lg bg-secondary/30 border border-border" data-testid="trade-proposal-review-send">
                <h4 className="text-sm font-semibold text-muted-foreground mb-3">You Send</h4>
                <div className="space-y-1.5">
                  {myList
                    .filter((p) => selectedMyPlayerIds.includes(p.id))
                    .map((p) => (
                      <div key={p.id} className="text-sm">
                        <span className="font-medium">{p.name}</span>
                        <span className="text-muted-foreground ml-1">({p.position})</span>
                      </div>
                    ))}
                  {myPickList
                    .filter((p) => selectedMyPickIds.includes(p.id))
                    .map((p) => (
                      <div key={p.id} className="text-sm">
                        <span className="font-medium">{p.year} R{p.round}</span>
                      </div>
                    ))}
                  {selectedMyPlayerIds.length + selectedMyPickIds.length === 0 && (
                    <p className="text-xs italic text-muted-foreground">Nothing selected</p>
                  )}
                </div>
              </div>
            </div>
            <div>
              <label htmlFor="trade-proposal-message" className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">
                Optional message
              </label>
              <Textarea
                id="trade-proposal-message"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder={
                  isCounter
                    ? "e.g. Swap in the '27 first and I'm in"
                    : "e.g. Been eyeing your D-corps depth all season"
                }
                rows={2}
                data-testid="trade-proposal-message"
                className="mt-1"
              />
            </div>
          </div>
        )}

        <div className="flex justify-between mt-4">
          <Button
            variant="outline"
            onClick={() => {
              if (step === "my-roster") setStep("their-roster");
              else if (step === "review") setStep("my-roster");
              else handleClose();
            }}
            data-testid="trade-proposal-back-btn"
          >
            <ChevronLeft className="h-4 w-4 mr-1" />
            {step === "their-roster" ? "Cancel" : "Back"}
          </Button>

          {step !== "review" ? (
            <Button
              onClick={() => {
                if (step === "their-roster") setStep("my-roster");
                else setStep("review");
              }}
              disabled={step === "their-roster" && selectedTheirIds.length === 0}
              data-testid="trade-proposal-next-btn"
            >
              Next
              <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          ) : (
            <Button
              className={isCounter
                ? "bg-sky-500/25 hover:bg-sky-500/40 text-sky-100 border border-sky-500/40"
                : "bg-primary hover:bg-primary/90"}
              disabled={
                submitting ||
                selectedTheirIds.length === 0 ||
                (selectedMyPlayerIds.length === 0 && selectedMyPickIds.length === 0)
              }
              onClick={handleSubmit}
              data-testid="trade-proposal-submit-btn"
            >
              {submitting
                ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                : (isCounter
                    ? <Reply className="h-4 w-4 mr-2" />
                    : <Send className="h-4 w-4 mr-2" />)}
              {isCounter ? "Send Counter" : "Send Proposal"}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
