// @ts-nocheck
/**
 * Iter 228y — Public landing page for a slot-locked team invite token.
 *
 * Flow:
 *   1. URL: /team-invites/:token
 *   2. We hit GET /api/team-invites/:token/preview (no auth) to render
 *      league/team metadata.
 *   3. If the visitor isn't signed in, we send them through /login and
 *      bounce them back here.
 *   4. Signed-in users hit POST /api/team-invites/:token/accept and on
 *      success are redirected into their newly claimed team.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api, { invalidateApiCache } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { ShieldCheck, AlertTriangle, Mail, Users, Sparkles } from "lucide-react";

const STATUS_BADGE = {
  pending: { label: "Pending — claim it", className: "border-emerald-500/50 text-emerald-300 bg-emerald-500/10" },
  accepted: { label: "Already claimed", className: "border-muted text-muted-foreground bg-secondary/40" },
  revoked: { label: "Invite revoked", className: "border-destructive/40 text-destructive bg-destructive/10" },
  expired: { label: "Invite expired", className: "border-amber-500/40 text-amber-300 bg-amber-500/10" },
};

export default function ClaimTeamInvite() {
  const { token } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState(null);
  // Iter 229f — "Name your team" modal that appears immediately after
  // an owner-role accept. Co-owners don't get this modal since they're
  // joining a team the primary owner already named.
  const [nameModalOpen, setNameModalOpen] = useState(false);
  const [claimedTeamId, setClaimedTeamId] = useState(null);
  const [claimedLeagueId, setClaimedLeagueId] = useState(null);
  const [newTeamName, setNewTeamName] = useState("");
  const [newTeamAbbr, setNewTeamAbbr] = useState("");
  const [savingName, setSavingName] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get(`/team-invites/${token}/preview`)
      .then(({ data }) => { if (!cancelled) setPreview(data); })
      .catch((e) => {
        if (!cancelled) setError(e?.response?.data?.detail || "Invite not found");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [token]);

  const statusBadge = useMemo(
    () => STATUS_BADGE[preview?.status] || STATUS_BADGE.pending,
    [preview?.status],
  );

  const emailMismatch = useMemo(() => {
    if (!preview?.email_lock || !user?.email) return false;
    return preview.email_lock.toLowerCase() !== user.email.toLowerCase();
  }, [preview, user]);

  const canAccept = preview?.status === "pending" && user && !emailMismatch;

  const onAccept = async () => {
    if (!canAccept) return;
    setAccepting(true);
    try {
      const { data } = await api.post(`/team-invites/${token}/accept`);
      const isCo = data.role === "co_owner";
      // Iter 229c — Switch the active league context to the team's
      // league so the user lands in the right place. Without this the
      // dashboard / /team page falls back to the user's prior default
      // league and feels like the invite "did nothing".
      try { localStorage.setItem("dd_active_league_id", data.league_id); } catch { /* noop */ }
      // Iter 229e — Bust the cached `/api/leagues?my_leagues=true`
      // response + broadcast a custom event so the sidebar dropdown
      // shows the newly joined league immediately.
      try { invalidateApiCache(/leagues\?my_leagues=true/); } catch { /* noop */ }
      try { window.dispatchEvent(new CustomEvent("dd:leagues-changed")); } catch { /* noop */ }
      const teamLabel = data.team_name || "your new team";
      toast.success(isCo
        ? `You've joined ${teamLabel} as a co-owner!`
        : `You've claimed ${teamLabel}!`);
      // Iter 229f — Owner-role: pop the "Name your team" modal so the
      // new owner can replace the "Open Slot N" placeholder in one
      // step. Co-owners skip — they're joining a team the primary
      // owner already named.
      if (!isCo) {
        setClaimedTeamId(data.team_id);
        setClaimedLeagueId(data.league_id);
        // Pre-seed with the user's first name to give them a nudge.
        const guess = (user?.name || user?.email || "").split(/\s|@/)[0];
        setNewTeamName(guess ? `${guess.charAt(0).toUpperCase()}${guess.slice(1)}'s Team` : "");
        setNewTeamAbbr("");
        setNameModalOpen(true);
      } else {
        navigate(`/leagues/${data.league_id}`);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't accept invite");
    } finally {
      setAccepting(false);
    }
  };

  // Iter 229f — Save the chosen team name + abbreviation via the
  // existing `PUT /api/teams/{team_id}` whitelist endpoint.
  const onSaveName = async () => {
    if (!claimedTeamId) return;
    const name = newTeamName.trim();
    const abbr = newTeamAbbr.trim().toUpperCase();
    if (!name) { toast.error("Pick a team name to continue"); return; }
    setSavingName(true);
    try {
      await api.put(`/teams/${claimedTeamId}`, {
        name,
        logo_abbr: abbr || undefined,
      });
      toast.success(`Welcome, ${name}!`);
      setNameModalOpen(false);
      navigate(`/leagues/${claimedLeagueId}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't save team name");
    } finally {
      setSavingName(false);
    }
  };

  const onSkipName = () => {
    setNameModalOpen(false);
    if (claimedLeagueId) navigate(`/leagues/${claimedLeagueId}`);
  };

  if (loading || authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-6">
        <p className="text-sm text-muted-foreground">Loading invite…</p>
      </div>
    );
  }

  if (error || !preview) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-6">
        <Card className="max-w-md w-full" data-testid="claim-team-invite-error">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-4 w-4" />
              Invite unavailable
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>{error || "This invite doesn't exist."}</p>
            <Button asChild variant="outline">
              <Link to="/dashboard">Go to Dashboard</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-6">
      <Card className="max-w-lg w-full" data-testid="claim-team-invite">
        <CardHeader className="space-y-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-300" />
            <CardTitle className="text-xl">Team Invite</CardTitle>
          </div>
          <p className="text-sm text-muted-foreground">
            You&apos;ve been invited to {preview.role === "co_owner" ? "co-manage" : "claim"}{" "}
            <span className="text-foreground font-semibold" data-testid="claim-team-name">
              {preview.team_name || "a team"}
            </span>{" "}
            in{" "}
            <span className="text-foreground font-semibold" data-testid="claim-league-name">
              {preview.league_name || "this league"}
            </span>.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className={statusBadge.className} data-testid="claim-status-badge">
              {statusBadge.label}
            </Badge>
            <Badge variant="outline" className="border-border text-muted-foreground bg-secondary/40">
              {preview.role === "co_owner" ? (
                <><Users className="h-3 w-3 mr-1 inline" /> Co-owner</>
              ) : (
                "Primary owner"
              )}
            </Badge>
            {preview.email_lock && (
              <Badge variant="outline" className="border-border text-muted-foreground bg-secondary/40">
                <Mail className="h-3 w-3 mr-1 inline" /> {preview.email_lock}
              </Badge>
            )}
          </div>

          {!user && (
            <div className="rounded-md border border-border bg-secondary/40 p-3 text-xs text-muted-foreground" data-testid="claim-need-login">
              <p className="mb-2">You need to sign in to accept this invite.</p>
              <div className="flex gap-2">
                <Button asChild size="sm">
                  <Link to={`/login?next=/team-invites/${token}`}>Sign in</Link>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <Link to={`/register?next=/team-invites/${token}`}>Create account</Link>
                </Button>
              </div>
            </div>
          )}

          {user && emailMismatch && (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200" data-testid="claim-email-mismatch">
              This invite is locked to <strong>{preview.email_lock}</strong>. You&apos;re signed in as <strong>{user.email}</strong>.
              Sign out and sign back in with the matching email to accept.
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button asChild variant="ghost" size="sm">
              <Link to="/dashboard">Cancel</Link>
            </Button>
            <Button
              onClick={onAccept}
              disabled={!canAccept || accepting}
              data-testid="claim-accept-btn"
            >
              {accepting
                ? "Accepting…"
                : preview.role === "co_owner"
                  ? "Join as Co-owner"
                  : "Claim Team"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Iter 229f — "Name your team" modal that appears right after
          a successful owner-role accept. The new owner can set both
          the team name + 3-char abbreviation in a single step instead
          of hunting through League Admin > Teams & Owners afterward. */}
      <Dialog open={nameModalOpen} onOpenChange={(open) => !open && onSkipName()}>
        <DialogContent className="max-w-md" data-testid="name-your-team-modal">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-amber-300" />
              Name your team
            </DialogTitle>
            <DialogDescription>
              You&apos;ve claimed the seat. Give your franchise an identity — you can always rename it later from League Admin.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label htmlFor="claim-team-name-input">Team name</Label>
              <Input
                id="claim-team-name-input"
                value={newTeamName}
                onChange={(e) => setNewTeamName(e.target.value)}
                placeholder="e.g. Frostbite Phantoms"
                maxLength={40}
                autoFocus
                data-testid="name-your-team-name-input"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="claim-team-abbr-input">Abbreviation <span className="text-muted-foreground text-xs">(optional, max 3 letters)</span></Label>
              <Input
                id="claim-team-abbr-input"
                value={newTeamAbbr}
                onChange={(e) => setNewTeamAbbr(e.target.value.toUpperCase().slice(0, 3))}
                placeholder="FRO"
                maxLength={3}
                className="w-24"
                data-testid="name-your-team-abbr-input"
              />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-2">
            <Button
              variant="ghost"
              onClick={onSkipName}
              disabled={savingName}
              data-testid="name-your-team-skip"
            >
              Skip for now
            </Button>
            <Button
              onClick={onSaveName}
              disabled={savingName || !newTeamName.trim()}
              data-testid="name-your-team-save"
            >
              {savingName ? "Saving…" : "Save & continue"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
