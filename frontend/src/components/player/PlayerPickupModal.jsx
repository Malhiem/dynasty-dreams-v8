// @ts-nocheck
/**
 * Iter 232N.15 — Player Pickup Toast/Modal
 *
 * Opens inline on the Free Agent screen when the manager clicks the
 * `+` button on a player row. Owns the entire pickup flow so we don't
 * ship the user off to the legacy `/waivers` page anymore:
 *
 *   1. GET `/waivers/precheck` to learn the roster/cap/draft-lock state
 *   2. If the response carries `draft_lock`, render an inert explainer
 *      (no confirm button) — the pool is frozen until the draft wraps.
 *   3. If the player is on waivers, show a FAAB-bid input and POST to
 *      `/waivers/claim`.
 *   4. Otherwise POST straight to `/roster/{teamId}/add`.
 *
 * Emits `pending-waivers-updated` on submit so the sidebar badge and
 * Waivers panel refresh without a full reload.
 */
import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { AlertTriangle, CalendarClock, Loader2, PlusCircle } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { notifyPendingWaiversChanged } from "@/hooks/use-pending-waivers";

export default function PlayerPickupModal({ open, player, leagueId, onClose, onSuccess }) {
  const [loading, setLoading] = useState(false);
  const [precheck, setPrecheck] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [bid, setBid] = useState(0);

  const onWaivers = !!(player?.waiver_status && player.waiver_status.on_waivers);

  useEffect(() => {
    if (!open || !player || !leagueId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPrecheck(null);
    setBid(0);
    api.get(`/waivers/precheck`, {
      params: { league_id: leagueId, player_id: player._id, bid_amount: 0 },
    })
      .then(({ data }) => {
        if (cancelled) return;
        setPrecheck(data);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(formatApiError(e));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, player?._id, leagueId]);

  const draftLock = precheck?.draft_lock;
  const blockingIssues = (precheck?.issues || []).filter(
    (i) => i.severity === "error" && i.code !== "draft_locked",
  );
  const canSubmit = !draftLock && precheck && precheck.can_claim && !submitting;

  const handleSubmit = async () => {
    if (!precheck || !player) return;
    setSubmitting(true);
    try {
      if (onWaivers) {
        await api.post(`/waivers/claim`, {
          league_id: leagueId,
          player_id: player._id,
          bid_amount: Number(bid) || 0,
        });
        toast.success(`Waiver claim submitted for ${player.name}`);
      } else {
        await api.post(`/roster/${precheck.team.id}/add`, {
          player_id: player._id,
        });
        toast.success(`${player.name} added to your roster`);
      }
      notifyPendingWaiversChanged();
      onSuccess?.();
      onClose?.();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose?.()}>
      <DialogContent className="max-w-md" data-testid="player-pickup-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {onWaivers ? (
              <Badge className="bg-amber-500/20 text-amber-300 border-amber-500/40">Waivers</Badge>
            ) : (
              <Badge className="bg-emerald-500/20 text-emerald-300 border-emerald-500/40">Free Agent</Badge>
            )}
            <span>{player?.name}</span>
          </DialogTitle>
          <p className="text-xs text-muted-foreground">
            {player?.position} · {player?.nhl_team || player?.team || "—"}
          </p>
        </DialogHeader>

        {loading && (
          <div className="flex items-center justify-center py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 mr-2 animate-spin" /> Checking eligibility…
          </div>
        )}

        {error && !loading && (
          <div className="text-sm text-destructive" data-testid="player-pickup-error">
            {error}
          </div>
        )}

        {!loading && !error && draftLock && (
          <div
            className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 flex gap-3"
            data-testid="player-pickup-draft-lock"
          >
            <CalendarClock className="h-5 w-5 text-amber-300 shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-medium text-amber-200">Draft in progress</p>
              <p className="text-amber-100/80 mt-1">{draftLock.message}</p>
            </div>
          </div>
        )}

        {!loading && !error && !draftLock && precheck && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-md border border-border p-2">
                <div className="text-muted-foreground">Roster</div>
                <div className="font-semibold">
                  {precheck.roster.current}/{precheck.roster.max}
                </div>
              </div>
              {precheck.cap.enabled && (
                <div className="rounded-md border border-border p-2">
                  <div className="text-muted-foreground">Cap after add</div>
                  <div className={`font-semibold ${precheck.cap.fits ? "" : "text-destructive"}`}>
                    ${(precheck.cap.would_be / 1_000_000).toFixed(2)}M
                    <span className="text-muted-foreground text-[10px] ml-1">
                      / ${(precheck.cap.cap / 1_000_000).toFixed(1)}M
                    </span>
                  </div>
                </div>
              )}
            </div>

            {onWaivers && (
              <div>
                <label className="text-xs text-muted-foreground">FAAB Bid ($)</label>
                <Input
                  type="number"
                  min={0}
                  value={bid}
                  onChange={(e) => setBid(e.target.value)}
                  data-testid="player-pickup-bid"
                />
              </div>
            )}

            {blockingIssues.length > 0 && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 space-y-1">
                {blockingIssues.map((iss, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <AlertTriangle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
                    <span>{iss.message}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={onClose}
            data-testid="player-pickup-cancel"
          >
            {draftLock ? "Close" : "Cancel"}
          </Button>
          {!draftLock && (
            <Button
              onClick={handleSubmit}
              disabled={!canSubmit}
              data-testid="player-pickup-submit"
            >
              {submitting ? (
                <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Submitting…</>
              ) : (
                <><PlusCircle className="h-4 w-4 mr-2" />
                {onWaivers ? "Submit Claim" : "Add to Roster"}</>
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
