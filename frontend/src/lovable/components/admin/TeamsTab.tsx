// @ts-nocheck
/**
 * Iter 228z — Live "Teams & Owners" panel for the League Admin.
 *
 * Replaces the previous mocked 12-team `initialTeams` array with a
 * fetch against `GET /api/leagues/{league_id}/pending-team-invites`,
 * which already returns every team in the league + its
 * owner_id/owner_name/invite_email/status. Unclaimed slots render as
 * "Open Slot N" (1-indexed by draft_position or natural order) per the
 * user's spec, so commissioners aren't misled by stub names like
 * "Polar Bears" before the slot is actually claimed.
 *
 * Per-row controls:
 *   • Edit team name + abbreviation → POST /api/teams/{team_id}/admin-update
 *     (whitelisted commissioner endpoint)
 *   • Add owner → mints a slot-locked invite via
 *     POST /api/leagues/{league_id}/teams/{team_id}/invites and copies
 *     the URL to the clipboard.
 *   • Re-invite + Remove owner (only render for accepted owners) call
 *     the existing send-invite-email + roster-management endpoints.
 *   • Each row has data-testids so the testing agent can drive flows.
 */
import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Plus, X, Pencil, Check, Mail, Users, Link2, Copy, ShieldCheck } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";

const TeamsTab = () => {
  const { league } = useActiveLeague();
  const leagueId = league?.id || league?._id;
  const [data, setData] = useState({ teams: [] });
  const [slotInvites, setSlotInvites] = useState({});
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState("");
  const [editAbbr, setEditAbbr] = useState("");
  const [addingOwnerFor, setAddingOwnerFor] = useState(null);
  const [newOwnerEmail, setNewOwnerEmail] = useState("");
  const [busy, setBusy] = useState({});
  // Iter 231p — Track which invite is pending revocation so the
  // AlertDialog can render its content + run the actual delete on
  // confirm. Replaces the unreliable native `window.confirm` (which
  // some embedded browsers / popup blockers swallow → "Yes click does
  // nothing").
  const [revokeTarget, setRevokeTarget] = useState(null);

  const setBusyFor = (teamId, val) =>
    setBusy((prev) => ({ ...prev, [teamId]: val }));

  const load = async () => {
    if (!leagueId) return;
    setLoading(true);
    try {
      const [r, sr] = await Promise.all([
        api.get(`/leagues/${leagueId}/pending-team-invites`),
        api.get(`/leagues/${leagueId}/team-invites`).catch(() => ({ data: { invites: [] } })),
      ]);
      setData(r.data || { teams: [] });
      const byTeam = {};
      (sr.data?.invites || []).forEach((inv) => {
        // Iter 231aa — Defense in depth: also drop revoked/accepted invites
        // client-side. The backend now filters them by default, but if any
        // legacy server returns them, never render an already-revoked invite
        // as if it were pending — that's what made the user click "revoke"
        // on a no-op row and complain the button didn't work.
        if (inv?.status === "revoked" || inv?.status === "accepted" || inv?.status === "expired") return;
        if (!byTeam[inv.team_id]) byTeam[inv.team_id] = [];
        byTeam[inv.team_id].push(inv);
      });
      setSlotInvites(byTeam);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load teams");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [leagueId]);

  // Normalize teams + render "Open Slot N" for unclaimed seats.
  const rows = useMemo(() => {
    const teams = data?.teams || [];
    return teams.map((t, idx) => {
      const slotNumber = t.draft_position ?? idx + 1;
      const isOpenSlot = !t.owner_id;
      const displayName = isOpenSlot ? `Open Slot ${slotNumber}` : (t.team_name || `Team ${slotNumber}`);
      return {
        ...t,
        slotNumber,
        isOpenSlot,
        displayName,
      };
    });
  }, [data]);

  const startEditing = (row) => {
    setEditingId(row.team_id);
    setEditName(row.isOpenSlot ? "" : row.team_name);
    setEditAbbr(row.abbreviation || "");
  };

  const saveEditing = async (row) => {
    if (!editingId) return;
    setBusyFor(row.team_id, true);
    try {
      await api.put(`/teams/${row.team_id}`, {
        name: editName.trim() || undefined,
        logo_abbr: editAbbr.trim().toUpperCase() || undefined,
      });
      toast.success("Team updated");
      setEditingId(null);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't update team");
    } finally {
      setBusyFor(row.team_id, false);
    }
  };

  const mintInviteForRow = async (row, role) => {
    if (!newOwnerEmail.trim() || !newOwnerEmail.includes("@")) {
      toast.error("Enter a valid email first");
      return;
    }
    setBusyFor(row.team_id, true);
    try {
      const { data: inv } = await api.post(
        `/leagues/${leagueId}/teams/${row.team_id}/invites`,
        { email: newOwnerEmail.trim(), role },
      );
      try {
        await navigator.clipboard?.writeText(inv.invite_url);
        toast.success("Invite created · link copied");
      } catch {
        toast.success("Invite created");
      }
      setAddingOwnerFor(null);
      setNewOwnerEmail("");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't create invite");
    } finally {
      setBusyFor(row.team_id, false);
    }
  };

  const copyInviteUrl = async (inv) => {
    try {
      await navigator.clipboard?.writeText(inv.invite_url);
      toast.success("Invite link copied");
    } catch {
      toast.error("Clipboard unavailable");
    }
  };

  const revokeInvite = async (inv) => {
    // Iter 231p — Guard against malformed invite docs (missing id is the
    // most-likely silent-fail path). Without this guard, axios issues a
    // DELETE to `/team-invites/undefined` which hits a 404 + a vague
    // "Couldn't revoke invite" toast that the user often misses.
    if (!inv?.id) {
      toast.error("Cannot revoke — invite id missing. Reload the page and try again.");
      return;
    }
    setBusyFor(inv.team_id, true);
    try {
      await api.delete(`/team-invites/${inv.id}`);
      toast.success("Invite revoked");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't revoke invite");
    } finally {
      setBusyFor(inv.team_id, false);
      setRevokeTarget(null);
    }
  };

  // Iter 231ae — Toggle whether a league admin manually manages this team.
  // Used for owner-removal continuity scenarios. When enabled, the Draft
  // Room timer worker stops auto-picking BPA for this team (admin will
  // pick manually) and the row badges as "Admin-managed" so other owners
  // know who's running it.
  const toggleAdminManaged = async (row, enabled) => {
    setBusyFor(row.team_id, true);
    try {
      await api.post(
        `/leagues/${leagueId}/teams/${row.team_id}/admin-managed`,
        { enabled },
      );
      toast.success(
        enabled
          ? "Admin-managed enabled — you'll run this team."
          : "Admin-managed disabled.",
      );
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't update admin management");
    } finally {
      setBusyFor(row.team_id, false);
    }
  };

  return (
    <Card className="bg-card border-border" data-testid="teams-tab-root">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="h-5 w-5 text-primary" />
          Teams & Owners
        </CardTitle>
        <CardDescription>
          {league?.name ? `${league.name} — ` : ""}Manage team names, abbreviations, and owner assignments. Unclaimed seats appear as Open Slots until an owner accepts.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading && (
          <p className="text-sm text-muted-foreground">Loading teams…</p>
        )}
        {!loading && rows.length === 0 && (
          <p className="text-sm text-muted-foreground italic">This league has no teams yet. Run the Setup Wizard to seed slots.</p>
        )}
        {!loading && rows.length > 0 && (
        <Table data-testid="teams-tab-table">
          <TableHeader>
            <TableRow className="border-border">
              <TableHead className="text-muted-foreground w-[200px]">Team Name</TableHead>
              <TableHead className="text-muted-foreground w-[100px]">Abbreviation</TableHead>
              <TableHead className="text-muted-foreground">Manager Email(s)</TableHead>
              <TableHead className="text-muted-foreground text-center w-[100px]">Joined</TableHead>
              <TableHead className="text-muted-foreground text-center w-[80px]">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => {
              const teamInvites = slotInvites[row.team_id] || [];
              const isEditing = editingId === row.team_id;
              const isBusy = !!busy[row.team_id];
              return (
              <TableRow
                key={row.team_id}
                className="border-border"
                data-testid={`teams-tab-row-${row.team_id}`}
                data-open-slot={row.isOpenSlot ? "true" : "false"}
              >
                <TableCell>
                  {isEditing ? (
                    <Input
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      placeholder={row.isOpenSlot ? row.displayName : ""}
                      className="h-8 bg-secondary border-border"
                      data-testid={`teams-tab-name-input-${row.team_id}`}
                    />
                  ) : (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className={`font-medium ${row.isOpenSlot ? "text-muted-foreground italic" : ""}`}
                        data-testid={`teams-tab-name-${row.team_id}`}
                      >
                        {row.displayName}
                      </span>
                      {row.isOpenSlot && (
                        <Badge variant="outline" className="border-amber-500/40 text-amber-300 bg-amber-500/10 text-[9px]">
                          Open
                        </Badge>
                      )}
                      {/* Iter 231ae — Pending invites tally chip so the
                          commissioner can spot outstanding tokens at a
                          glance without expanding the row. */}
                      {row.pending_invite_count > 0 && (
                        <Badge
                          variant="outline"
                          className="border-sky-500/40 text-sky-300 bg-sky-500/10 text-[9px]"
                          data-testid={`teams-tab-pending-chip-${row.team_id}`}
                        >
                          {row.pending_invite_count} pending
                        </Badge>
                      )}
                      {/* Iter 231ae — Admin-managed badge. Different from
                          "Open" because an owner-removed team will be
                          ownerless + admin-managed (e.g. continuity flow). */}
                      {row.admin_managed && (
                        <Badge
                          variant="outline"
                          className="border-violet-500/40 text-violet-300 bg-violet-500/10 text-[9px] gap-1"
                          data-testid={`teams-tab-admin-managed-badge-${row.team_id}`}
                        >
                          <ShieldCheck className="h-2.5 w-2.5" />
                          Admin-managed
                        </Badge>
                      )}
                    </div>
                  )}
                </TableCell>
                <TableCell>
                  {isEditing ? (
                    <Input
                      value={editAbbr}
                      onChange={(e) => setEditAbbr(e.target.value.toUpperCase().slice(0, 4))}
                      className="h-8 bg-secondary border-border w-20"
                      maxLength={4}
                      data-testid={`teams-tab-abbr-input-${row.team_id}`}
                    />
                  ) : (
                    <Badge variant="outline" className="text-xs">{row.abbreviation || "—"}</Badge>
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex flex-col gap-1.5">
                    {row.owner_id && row.owner_name && (
                      <div className="flex items-center gap-2" data-testid={`teams-tab-owner-${row.team_id}`}>
                        <span className="text-sm">{row.owner_email || row.owner_name}</span>
                      </div>
                    )}
                    {teamInvites.map((inv) => (
                      <div
                        key={inv.id}
                        className="flex items-center gap-1.5 rounded border border-border/60 bg-secondary/40 px-2 py-0.5 text-xs"
                        data-testid={`teams-tab-invite-${inv.id}`}
                      >
                        <Badge
                          variant="outline"
                          className={`text-[9px] px-1.5 py-0 ${inv.role === "co_owner" ? "border-purple-500/50 text-purple-300 bg-purple-500/10" : "border-emerald-500/50 text-emerald-300 bg-emerald-500/10"}`}
                        >
                          {inv.role === "co_owner" ? "Co-owner" : "Owner"}
                        </Badge>
                        <span className="text-muted-foreground truncate max-w-[160px]">
                          {inv.email || "open link"}
                        </span>
                        <button
                          type="button"
                          className="ml-auto inline-flex items-center text-muted-foreground hover:text-primary"
                          onClick={() => copyInviteUrl(inv)}
                          aria-label="Copy invite link"
                          data-testid={`teams-tab-invite-copy-${inv.id}`}
                        >
                          <Copy className="h-3 w-3" />
                        </button>
                        <button
                          type="button"
                          className="inline-flex items-center text-muted-foreground hover:text-destructive"
                          onClick={() => setRevokeTarget(inv)}
                          disabled={isBusy}
                          aria-label="Revoke invite"
                          data-testid={`teams-tab-invite-revoke-${inv.id}`}
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                    ))}
                    {!row.owner_id && teamInvites.length === 0 && (
                      <span className="text-xs text-muted-foreground italic">No owners assigned</span>
                    )}
                    {/* Iter 231ae — Per-row admin-managed checkbox.
                        Visible whenever the team has no primary owner so
                        the commissioner can run the team during the
                        owner-removal continuity window. Hidden when the
                        team has a real owner (admin-management is a
                        no-owner thing — primary owner picks instead). */}
                    {row.isOpenSlot && (
                      <label
                        className="mt-1 flex items-center gap-2 text-xs text-muted-foreground cursor-pointer select-none w-fit"
                        data-testid={`teams-tab-admin-managed-row-${row.team_id}`}
                      >
                        <Checkbox
                          checked={!!row.admin_managed}
                          disabled={isBusy}
                          onCheckedChange={(checked) => toggleAdminManaged(row, checked === true)}
                          className="h-3.5 w-3.5"
                          data-testid={`teams-tab-admin-managed-toggle-${row.team_id}`}
                        />
                        <span>League admin runs this team</span>
                      </label>
                    )}
                    {addingOwnerFor === row.team_id ? (
                      <div className="flex items-center gap-1 mt-1">
                        <Input
                          placeholder="email@example.com"
                          value={newOwnerEmail}
                          onChange={(e) => setNewOwnerEmail(e.target.value)}
                          className="h-7 text-xs bg-secondary border-border"
                          onKeyDown={(e) => e.key === "Enter" && mintInviteForRow(row, row.isOpenSlot ? "owner" : "co_owner")}
                          data-testid={`teams-tab-add-owner-input-${row.team_id}`}
                          autoFocus
                        />
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              size="icon"
                              variant="ghost"
                              className="h-7 w-7 text-primary"
                              onClick={() => mintInviteForRow(row, row.isOpenSlot ? "owner" : "co_owner")}
                              disabled={isBusy}
                              data-testid={`teams-tab-add-owner-submit-${row.team_id}`}
                            >
                              <Link2 className="h-3 w-3" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            <p className="text-xs">{row.isOpenSlot ? "Mint owner invite link" : "Mint co-owner invite link"}</p>
                          </TooltipContent>
                        </Tooltip>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7"
                          onClick={() => { setAddingOwnerFor(null); setNewOwnerEmail(""); }}
                          data-testid={`teams-tab-add-owner-cancel-${row.team_id}`}
                        >
                          <X className="h-3 w-3" />
                        </Button>
                      </div>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 text-xs text-primary hover:text-primary/80 w-fit gap-1 p-0"
                        onClick={() => setAddingOwnerFor(row.team_id)}
                        data-testid={`teams-tab-add-owner-${row.team_id}`}
                      >
                        <Plus className="h-3 w-3" /> {row.owner_id ? "Add co-owner" : "Add owner"}
                      </Button>
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-center">
                  {row.status === "accepted" ? (
                    <Badge className="bg-green-500/20 text-green-400 border-green-500/30 text-[10px]">Yes</Badge>
                  ) : row.status === "invited" || row.invite_email ? (
                    <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/30 text-[10px]">Invited</Badge>
                  ) : (
                    <Badge variant="outline" className="text-[10px] text-muted-foreground">N/A</Badge>
                  )}
                </TableCell>
                <TableCell className="text-center">
                  {isEditing ? (
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 text-primary"
                      onClick={() => saveEditing(row)}
                      disabled={isBusy}
                      data-testid={`teams-tab-save-${row.team_id}`}
                    >
                      <Check className="h-4 w-4" />
                    </Button>
                  ) : (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7"
                          onClick={() => startEditing(row)}
                          data-testid={`teams-tab-edit-${row.team_id}`}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p className="text-xs">{row.isOpenSlot ? "Set team name + abbreviation" : "Edit team"}</p>
                      </TooltipContent>
                    </Tooltip>
                  )}
                </TableCell>
              </TableRow>
              );
            })}
          </TableBody>
        </Table>
        )}
      </CardContent>
      {/* Iter 231p — Revoke-invite confirmation. Replaces window.confirm so
          the modal works reliably across browsers/embedded WebViews. */}
      <AlertDialog
        open={!!revokeTarget}
        onOpenChange={(open) => !open && setRevokeTarget(null)}
      >
        <AlertDialogContent data-testid="teams-tab-revoke-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke this invite link?</AlertDialogTitle>
            <AlertDialogDescription>
              Anyone who already has this link won&apos;t be able to claim the team.
              {revokeTarget?.email ? ` Invite was for ${revokeTarget.email}.` : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="teams-tab-revoke-cancel">Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => revokeTarget && revokeInvite(revokeTarget)}
              data-testid="teams-tab-revoke-confirm"
            >
              Yes, revoke
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
};

export default TeamsTab;
