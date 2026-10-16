/**
 * Iter 232N.65 — Admin Player DB panel (upgraded).
 *
 * Adds four capabilities on top of 232N.64:
 *   1) Full NHL API sync with a Dry-Run diff modal (selective apply).
 *   2) CSV validation preview → commit modal.
 *   3) Bulk actions (mark_prospect, unmark_prospect, delete) via
 *      multi-select checkboxes on the table.
 *   4) A "Sync" button distinct from the legacy Reseed action.
 *
 * Endpoints used:
 *   • GET    /admin/players
 *   • POST   /admin/players
 *   • PUT    /admin/players/{id}
 *   • DELETE /admin/players/{id}
 *   • GET    /admin/players/audit
 *   • POST   /admin/players/refresh       (reseed only)
 *   • POST   /admin/players/sync          (dry_run diff)
 *   • POST   /admin/players/sync/apply    (selective apply)
 *   • POST   /admin/players/csv/preview   (multipart)
 *   • POST   /admin/players/csv/commit
 *   • POST   /admin/players/bulk
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import type React from "react";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Database, RefreshCw, Plus, Trash2, Pencil, ScrollText, Upload,
  CheckCircle2, X, GitPullRequest, AlertTriangle, Sparkles, Users2,
  Download,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

interface Player {
  id: string;
  name: string;
  position?: string;
  team?: string;
  team_name?: string;
  league?: string;
  age?: number;
  is_prospect?: boolean;
  cap_hit?: number;
  nhl_id?: string;
  contract?: { aav?: number };
}

interface AuditRow {
  id: string;
  actor_email?: string;
  action: string;
  player_id: string;
  at: string;
  note?: string;
}

function fmtMoney(n: number | undefined | null): string {
  if (!n) return "—";
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}k`;
  return `$${n}`;
}

export default function PlayerDbPanel() {
  const [players, setPlayers] = useState<Player[]>([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const LIMIT = 25;
  const [q, setQ] = useState("");
  const [position, setPosition] = useState<string>("");
  const [isProspect, setIsProspect] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const [editing, setEditing] = useState<Player | null>(null);
  const [creating, setCreating] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [audit, setAudit] = useState<AuditRow[]>([]);

  // Multi-select state for bulk actions
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Modals
  const [syncModal, setSyncModal] = useState<any | null>(null);
  const [csvModal, setCsvModal] = useState<any | null>(null);
  const [dupModal, setDupModal] = useState<any | null>(null);
  const [dupLoading, setDupLoading] = useState(false);

  // Iter 232N.77 — Download the CSV template so admins get the exact
  // headers the /csv/preview endpoint accepts. Uses the axios blob
  // path so we inherit the same auth cookie as every other admin
  // call.
  const downloadCsvTemplate = async () => {
    try {
      const res = await api.get("/admin/players/csv/template", { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "player_db_cap_import_template.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Template downloaded");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Template download failed");
    }
  };

  const scanDuplicates = async () => {
    toast.info("Scanning DB for name+birth_date duplicates…");
    try {
      const { data } = await api.get("/admin/players/duplicates", { params: { limit: 500 } });
      toast.success(
        `Found ${data.total_clusters} duplicate cluster(s) across ${data.total_rows_flagged} rows`,
      );
      setDupModal({
        clusters: data.clusters,
        total_clusters: data.total_clusters,
        total_rows_flagged: data.total_rows_flagged,
      });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Scan failed");
    } finally {
      setDupLoading(false);
    }
  };

  // ── Load list + audit ─────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { skip, limit: LIMIT };
      if (q.trim()) params.q = q.trim();
      if (position) params.position = position;
      if (isProspect === "true") params.is_prospect = true;
      if (isProspect === "false") params.is_prospect = false;
      const [pRes, aRes] = await Promise.all([
        api.get("/admin/players", { params }),
        api.get("/admin/players/audit", { params: { limit: 15 } }),
      ]);
      setPlayers(pRes.data?.players ?? []);
      setTotal(pRes.data?.total ?? 0);
      setAudit(aRes.data?.rows ?? []);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to load players");
    } finally {
      setLoading(false);
    }
  }, [skip, q, position, isProspect]);

  useEffect(() => { load(); }, [load]);

  // ── Legacy reseed (kept for parity) ───────────────────────────
  const reseed = async () => {
    setRefreshing(true);
    try {
      const { data } = await api.post("/admin/players/refresh", { source: "reseed" });
      if (data?.ok) {
        toast.success(`Reseed complete · ${data.upserted} rows · ${data.duration_ms}ms`);
      } else {
        toast.error(`Reseed error: ${data?.error || "unknown"}`);
      }
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Reseed failed");
    } finally {
      setRefreshing(false);
    }
  };

  // ── NHL API dry-run ───────────────────────────────────────────
  const startNhlDryRun = async () => {
    setRefreshing(true);
    toast.info("Fetching all 32 NHL rosters + prospect pools…");
    try {
      const { data } = await api.post("/admin/players/sync", { dry_run: true });
      if (!data?.ok) {
        toast.error("Sync failed");
        return;
      }
      const c = data.diff.counts;
      toast.success(
        `Dry-run ready: ${c.new_players} new · ${c.age_changes} age · ${c.team_changes} team · ${c.removed} missing (${data.duration_ms}ms)`,
      );
      setSyncModal({
        token: data.sync_token,
        diff: data.diff,
        errors: data.fetch_errors ?? [],
        duration_ms: data.duration_ms,
      });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "NHL sync failed");
    } finally {
      setRefreshing(false);
    }
  };

  // ── CSV preview ───────────────────────────────────────────────
  const previewCsv = async (file: File) => {
    setRefreshing(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post("/admin/players/csv/preview", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(
        `Preview ready · ${data.totals.valid} valid · ${data.totals.errors} errors`,
      );
      setCsvModal({
        token: data.preview_token,
        totals: data.totals,
        rows: data.rows,
        truncated: data.truncated_preview,
      });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "CSV preview failed");
    } finally {
      setRefreshing(false);
    }
  };

  // ── Delete single ─────────────────────────────────────────────
  const deletePlayer = async (p: Player) => {
    if (!window.confirm(`Delete ${p.name}? This can't be undone.`)) return;
    try {
      await api.delete(`/admin/players/${p.id}`);
      toast.success(`Deleted ${p.name}`);
      setSelected((s) => { const n = new Set(s); n.delete(p.id); return n; });
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Delete failed");
    }
  };

  // ── Bulk actions ──────────────────────────────────────────────
  const bulk = async (action: "mark_prospect" | "unmark_prospect" | "delete") => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    if (action === "delete" && !window.confirm(
      `Delete ${ids.length} player(s)? Roster-safe: players on active rosters will be skipped.`,
    )) return;
    try {
      const { data } = await api.post("/admin/players/bulk", { action, player_ids: ids });
      const skipped = data.skipped_on_roster ? ` · ${data.skipped_on_roster} skipped (on roster)` : "";
      toast.success(`Bulk ${action} · ${data.affected} affected${skipped}`);
      setSelected(new Set());
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Bulk action failed");
    }
  };

  // ── Selection helpers ─────────────────────────────────────────
  const toggleRow = (id: string) => {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };
  const allOnPageSelected = players.length > 0 && players.every((p) => selected.has(p.id));
  const togglePage = () => {
    setSelected((s) => {
      const n = new Set(s);
      if (allOnPageSelected) players.forEach((p) => n.delete(p.id));
      else players.forEach((p) => n.add(p.id));
      return n;
    });
  };

  const rangeText = useMemo(() => {
    if (total === 0) return "0";
    const from = skip + 1;
    const to = Math.min(skip + LIMIT, total);
    return `${from.toLocaleString()}–${to.toLocaleString()} of ${total.toLocaleString()}`;
  }, [skip, total]);

  return (
    <div className="space-y-4" data-testid="player-db-panel">
      <Card className="bg-card border-border">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Database className="h-4 w-4 text-cyan-400" />
                Player Database
                <Badge variant="outline" className="text-[10px] bg-cyan-500/10 text-cyan-300 border-cyan-500/30">
                  {total.toLocaleString()} players
                </Badge>
              </CardTitle>
              <CardDescription className="text-[11px]">
                Full CRUD over the player DB. NHL sync runs a dry-run diff first;
                CSV uploads validate before commit. All writes are audited.
              </CardDescription>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant="outline" size="sm" onClick={startNhlDryRun}
                disabled={refreshing} className="h-8"
                data-testid="player-db-nhl-sync-btn"
              >
                <GitPullRequest className="h-3 w-3 mr-1" />
                {refreshing ? "Syncing…" : "NHL sync (dry-run)"}
              </Button>
              <Button
                variant="outline" size="sm" onClick={scanDuplicates}
                disabled={dupLoading} className="h-8"
                data-testid="player-db-dupes-btn"
              >
                <Users2 className="h-3 w-3 mr-1" />
                {dupLoading ? "Scanning…" : "Scan duplicates"}
              </Button>
              <Button
                variant="outline" size="sm" onClick={reseed}
                disabled={refreshing} className="h-8"
                data-testid="player-db-reseed-btn"
              >
                <Sparkles className="h-3 w-3 mr-1" />
                Reseed
              </Button>
              <Button
                variant="outline" size="sm" onClick={downloadCsvTemplate}
                className="h-8"
                data-testid="player-db-csv-template-btn"
                title="Download the exact CSV headers for bulk cap imports"
              >
                <Download className="h-3 w-3 mr-1" />
                CSV template
              </Button>
              <label className="cursor-pointer">
                <Button
                  variant="outline" size="sm"
                  disabled={refreshing}
                  data-testid="player-db-csv-btn"
                  className="h-8" asChild
                >
                  <span><Upload className="h-3 w-3 mr-1" /> CSV preview</span>
                </Button>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) previewCsv(f);
                    e.currentTarget.value = "";
                  }}
                  data-testid="player-db-csv-input"
                />
              </label>
              <Button
                variant="outline" size="sm" onClick={load}
                disabled={loading} className="h-8"
                aria-label="Refresh player database" data-testid="player-db-reload-btn"
              >
                <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
              </Button>
              <Button
                variant="default" size="sm" onClick={() => setCreating(true)}
                data-testid="player-db-add-btn" className="h-8"
              >
                <Plus className="h-3 w-3 mr-1" /> Add
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Filters */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <Input
              value={q}
              onChange={(e) => { setSkip(0); setQ(e.target.value); }}
              placeholder="Search by name…"
              className="h-9 text-xs"
              data-testid="player-db-search"
            />
            <Select value={position || "any"} onValueChange={(v) => { setSkip(0); setPosition(v === "any" ? "" : v); }}>
              <SelectTrigger className="h-9 text-xs" data-testid="player-db-position-filter">
                <SelectValue placeholder="Any position" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="any">Any position</SelectItem>
                <SelectItem value="C">C</SelectItem>
                <SelectItem value="LW">LW</SelectItem>
                <SelectItem value="RW">RW</SelectItem>
                <SelectItem value="D">D</SelectItem>
                <SelectItem value="G">G</SelectItem>
              </SelectContent>
            </Select>
            <Select value={isProspect || "any"} onValueChange={(v) => { setSkip(0); setIsProspect(v === "any" ? "" : v); }}>
              <SelectTrigger className="h-9 text-xs" data-testid="player-db-prospect-filter">
                <SelectValue placeholder="Prospect / non-prospect" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="any">Any player</SelectItem>
                <SelectItem value="true">Prospects only</SelectItem>
                <SelectItem value="false">Non-prospects only</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Bulk action toolbar */}
          {selected.size > 0 && (
            <div
              className="flex items-center gap-2 rounded-md border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-[11px]"
              data-testid="player-db-bulk-bar"
            >
              <Badge variant="outline" className="text-[10px] bg-cyan-500/20 text-cyan-100 border-cyan-500/40">
                {selected.size} selected
              </Badge>
              <span className="text-muted-foreground">Bulk actions:</span>
              <Button size="sm" variant="outline" className="h-6 text-[10px]"
                onClick={() => bulk("mark_prospect")}
                data-testid="player-db-bulk-mark-prospect">
                Mark prospect
              </Button>
              <Button size="sm" variant="outline" className="h-6 text-[10px]"
                onClick={() => bulk("unmark_prospect")}
                data-testid="player-db-bulk-unmark-prospect">
                Unmark prospect
              </Button>
              <Button size="sm" variant="outline"
                className="h-6 text-[10px] text-rose-300 border-rose-500/40"
                onClick={() => bulk("delete")}
                data-testid="player-db-bulk-delete">
                <Trash2 className="h-3 w-3 mr-1" /> Delete
              </Button>
              <Button size="sm" variant="ghost" className="h-6 text-[10px] ml-auto"
                onClick={() => setSelected(new Set())}
                data-testid="player-db-bulk-clear">
                Clear
              </Button>
            </div>
          )}

          {/* Table */}
          <div className="overflow-x-auto rounded-md border border-border/60">
            <table className="w-full text-[11px]" data-testid="player-db-table">
              <thead>
                <tr className="text-left text-muted-foreground bg-secondary/30">
                  <th className="py-1.5 px-2 w-8">
                    <Checkbox
                      checked={allOnPageSelected}
                      onCheckedChange={togglePage}
                      data-testid="player-db-select-all"
                    />
                  </th>
                  <th className="py-1.5 px-2">Name</th>
                  <th className="py-1.5 px-2">Pos</th>
                  <th className="py-1.5 px-2">Team</th>
                  <th className="py-1.5 px-2">League</th>
                  <th className="py-1.5 px-2">Age</th>
                  <th className="py-1.5 px-2">Cap Hit / AAV</th>
                  <th className="py-1.5 px-2">Prospect</th>
                  <th className="py-1.5 px-2 w-24 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {players.map((p) => (
                  <tr
                    key={p.id}
                    className={`border-t border-border/40 hover:bg-secondary/20 ${
                      selected.has(p.id) ? "bg-cyan-500/5" : ""
                    }`}
                    data-testid={`player-db-row-${p.id}`}
                  >
                    <td className="py-1 px-2">
                      <Checkbox
                        checked={selected.has(p.id)}
                        onCheckedChange={() => toggleRow(p.id)}
                        data-testid={`player-db-select-${p.id}`}
                      />
                    </td>
                    <td className="py-1 px-2 font-medium truncate max-w-[220px]">{p.name}</td>
                    <td className="py-1 px-2">{p.position || "—"}</td>
                    <td className="py-1 px-2">{p.team || "—"}</td>
                    <td className="py-1 px-2">{p.league || "NHL"}</td>
                    <td className="py-1 px-2 font-mono">{p.age ?? "—"}</td>
                    <td className="py-1 px-2 font-mono">
                      {fmtMoney(p.contract?.aav || p.cap_hit)}
                    </td>
                    <td className="py-1 px-2">
                      {p.is_prospect ? (
                        <Badge variant="outline" className="text-[9px] bg-emerald-500/10 text-emerald-300 border-emerald-500/30">yes</Badge>
                      ) : "—"}
                    </td>
                    <td className="py-1 px-2 text-right">
                      <Button
                        variant="ghost" size="sm"
                        onClick={() => setEditing(p)}
                        className="h-6 w-6 p-0"
                        aria-label={`Edit ${p.name}`} data-testid={`player-db-edit-${p.id}`}
                      >
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <Button
                        variant="ghost" size="sm"
                        onClick={() => deletePlayer(p)}
                        className="h-6 w-6 p-0 text-rose-300 hover:text-rose-400"
                        aria-label={`Delete ${p.name}`} data-testid={`player-db-delete-${p.id}`}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </td>
                  </tr>
                ))}
                {players.length === 0 && !loading && (
                  <tr>
                    <td colSpan={9} className="py-4 text-center text-muted-foreground italic">
                      No players match those filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pager */}
          <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
            <span>{rangeText}</span>
            <div className="flex items-center gap-1">
              <Button
                variant="outline" size="sm" className="h-7 text-[10px]"
                disabled={skip === 0}
                onClick={() => setSkip(Math.max(0, skip - LIMIT))}
                data-testid="player-db-prev"
              >Prev</Button>
              <Button
                variant="outline" size="sm" className="h-7 text-[10px]"
                disabled={skip + LIMIT >= total}
                onClick={() => setSkip(skip + LIMIT)}
                data-testid="player-db-next"
              >Next</Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Audit strip */}
      <Card className="bg-card border-border">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <ScrollText className="h-3.5 w-3.5 text-amber-400" />
            Recent edits
            <Badge variant="outline" className="text-[9px]">{audit.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="text-[11px] space-y-1 max-h-[200px] overflow-y-auto">
          {audit.length === 0 ? (
            <div className="text-muted-foreground italic">No player edits yet.</div>
          ) : audit.map((a) => (
            <div key={a.id} className="flex items-center gap-2" data-testid={`player-audit-row-${a.id}`}>
              <Badge variant="outline" className={`text-[9px] ${
                a.action === "create" ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30" :
                a.action === "delete" ? "bg-rose-500/10 text-rose-300 border-rose-500/30" :
                a.action === "refresh" ? "bg-cyan-500/10 text-cyan-300 border-cyan-500/30" :
                a.action === "bulk" ? "bg-amber-500/10 text-amber-300 border-amber-500/30" :
                "bg-secondary/40"
              }`}>
                {a.action}
              </Badge>
              <span className="text-muted-foreground truncate">{a.actor_email || "?"}</span>
              <span className="text-muted-foreground shrink-0">·</span>
              <span className="font-mono text-muted-foreground truncate">{a.player_id}</span>
              <span className="text-muted-foreground ml-auto shrink-0">
                {new Date(a.at).toLocaleString()}
              </span>
            </div>
          ))}
        </CardContent>
      </Card>

      {(editing || creating) && (
        <PlayerEditModal
          player={editing}
          onClose={() => { setEditing(null); setCreating(false); }}
          onSaved={() => { setEditing(null); setCreating(false); load(); }}
        />
      )}
      {syncModal && (
        <NhlSyncModal
          data={syncModal}
          onClose={() => setSyncModal(null)}
          onApplied={() => { setSyncModal(null); load(); }}
        />
      )}
      {csvModal && (
        <CsvPreviewModal
          data={csvModal}
          onClose={() => setCsvModal(null)}
          onCommitted={() => { setCsvModal(null); load(); }}
        />
      )}
      {dupModal && (
        <DuplicatesModal
          data={dupModal}
          onClose={() => setDupModal(null)}
          onMerged={() => { setDupModal(null); load(); }}
        />
      )}
    </div>
  );
}

// ────────────────────────── Edit / create modal ─────────────────────────

function PlayerEditModal({
  player, onClose, onSaved,
}: {
  player: Player | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isCreate = !player;
  const [name, setName] = useState(player?.name ?? "");
  const [position, setPosition] = useState(player?.position ?? "");
  const [team, setTeam] = useState(player?.team ?? "");
  const [league, setLeague] = useState(player?.league ?? "NHL");
  const [age, setAge] = useState<number>(player?.age ?? 24);
  const [isProspect, setIsProspect] = useState<boolean>(!!player?.is_prospect);
  const [capHit, setCapHit] = useState<number>(
    player?.cap_hit ?? player?.contract?.aav ?? 950_000,
  );
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const payload: any = {
        name, position, team, league, age, is_prospect: isProspect,
        cap_hit: capHit,
        contract: { aav: capHit },
      };
      if (isCreate) {
        await api.post("/admin/players", payload);
        toast.success(`Added ${name}`);
      } else {
        await api.put(`/admin/players/${player!.id}`, payload);
        toast.success(`Updated ${name}`);
      }
      onSaved();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
      data-testid="player-db-modal"
    >
      <Card
        className="max-w-md w-full bg-card border-border"
        onClick={(e) => e.stopPropagation()}
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            {isCreate ? (
              <><Plus className="h-4 w-4 text-emerald-400" /> Add missing player</>
            ) : (
              <><Pencil className="h-4 w-4 text-cyan-400" /> Edit {player?.name}</>
            )}
          </CardTitle>
          <CardDescription className="text-[11px]">
            {isCreate ? "Useful for AHL / minor-league players not in the source feed." : "Only allow-listed fields are written. Every edit is audited."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-xs">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground">Name *</label>
            <Input value={name} onChange={(e) => setName(e.target.value)}
                   className="h-8 text-xs" data-testid="player-db-modal-name" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px] uppercase tracking-wider text-muted-foreground">Position</label>
              <Select value={position} onValueChange={setPosition}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="Position" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="C">C</SelectItem>
                  <SelectItem value="LW">LW</SelectItem>
                  <SelectItem value="RW">RW</SelectItem>
                  <SelectItem value="D">D</SelectItem>
                  <SelectItem value="G">G</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider text-muted-foreground">Age</label>
              <Input type="number" value={age} onChange={(e) => setAge(Number(e.target.value) || 0)}
                     className="h-8 text-xs font-mono" data-testid="player-db-modal-age" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px] uppercase tracking-wider text-muted-foreground">Team code</label>
              <Input value={team} onChange={(e) => setTeam(e.target.value.toUpperCase())}
                     placeholder="TOR" className="h-8 text-xs font-mono" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider text-muted-foreground">League</label>
              <Select value={league} onValueChange={setLeague}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="NHL">NHL</SelectItem>
                  <SelectItem value="AHL">AHL</SelectItem>
                  <SelectItem value="CHL">CHL</SelectItem>
                  <SelectItem value="OTHER">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground">Cap hit / AAV ($)</label>
            <Input type="number" step={50_000} value={capHit}
                   onChange={(e) => setCapHit(Number(e.target.value) || 0)}
                   className="h-8 text-xs font-mono" data-testid="player-db-modal-cap-hit" />
          </div>
          <label className="flex items-center gap-2 text-xs cursor-pointer">
            <input type="checkbox" checked={isProspect} onChange={(e) => setIsProspect(e.target.checked)}
                   data-testid="player-db-modal-prospect" />
            <span>Is prospect (age &lt; 24 or explicitly flagged)</span>
          </label>
          <div className="flex items-center justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={onClose} disabled={saving} className="h-8">
              Cancel
            </Button>
            <Button
              variant="default" size="sm" onClick={save}
              disabled={saving || !name.trim()}
              className="h-8"
              data-testid="player-db-modal-save"
            >
              {saving ? <RefreshCw className="h-3 w-3 animate-spin mr-1" /> : <CheckCircle2 className="h-3 w-3 mr-1" />}
              {isCreate ? "Add player" : "Save changes"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ────────────────────────── NHL Sync (dry-run) modal ─────────────────

function NhlSyncModal({
  data, onClose, onApplied,
}: { data: any; onClose: () => void; onApplied: () => void; }) {
  const diff = data.diff;
  const [applyNew, setApplyNew] = useState<Set<string>>(new Set(diff.new_players.map((r: any) => r.nhl_id)));
  const [applyAge, setApplyAge] = useState<Set<string>>(new Set(diff.age_changes.map((r: any) => r.nhl_id)));
  const [applyTeam, setApplyTeam] = useState<Set<string>>(new Set(diff.team_changes.map((r: any) => r.nhl_id)));
  const [applyPos, setApplyPos] = useState<Set<string>>(new Set(diff.position_changes.map((r: any) => r.nhl_id)));
  const [applyProsp, setApplyProsp] = useState<Set<string>>(new Set(diff.prospect_changes.map((r: any) => r.nhl_id)));
  const [applyDup, setApplyDup] = useState<Set<string>>(
    new Set((diff.duplicates ?? []).map((d: any) => d.stale_id)),
  );
  const [applyRemoved, setApplyRemoved] = useState<Set<string>>(new Set());  // opt-in
  const [committing, setCommitting] = useState(false);

  const toggle = (setter: any, id: string) => {
    setter((s: Set<string>) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const commit = async () => {
    setCommitting(true);
    try {
      const { data: res } = await api.post("/admin/players/sync/apply", {
        sync_token: data.token,
        apply_new: Array.from(applyNew),
        apply_age: Array.from(applyAge),
        apply_team: Array.from(applyTeam),
        apply_position: Array.from(applyPos),
        apply_prospect: Array.from(applyProsp),
        apply_duplicates: Array.from(applyDup),
        apply_removed: Array.from(applyRemoved),
      });
      const dupNote = res.duplicates_merged ? ` · ${res.duplicates_merged} dupes merged` : "";
      toast.success(
        `Applied · +${res.inserted} new · ${res.updated_age} age · ${res.updated_team} team${dupNote} · ${res.deleted} removed`,
      );
      onApplied();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Apply failed");
    } finally {
      setCommitting(false);
    }
  };

  const totalSelected = applyNew.size + applyAge.size + applyTeam.size +
                        applyPos.size + applyProsp.size + applyDup.size + applyRemoved.size;

  const section = (title: string, rows: any[], sel: Set<string>, setter: any,
                   renderCell: (r: any) => React.ReactNode, tone: string) => (
    <div className="space-y-1" data-testid={`sync-section-${title.replace(/\s+/g, "-").toLowerCase()}`}>
      <div className="flex items-center gap-2">
        <Badge variant="outline" className={`text-[10px] ${tone}`}>{title}</Badge>
        <span className="text-[10px] text-muted-foreground">{sel.size}/{rows.length} selected</span>
        {rows.length > 0 && (
          <>
            <Button size="sm" variant="ghost" className="h-5 text-[9px] px-1"
              onClick={() => setter(new Set(rows.map((r) => r.nhl_id)))}>All</Button>
            <Button size="sm" variant="ghost" className="h-5 text-[9px] px-1"
              onClick={() => setter(new Set())}>None</Button>
          </>
        )}
      </div>
      {rows.length === 0 ? (
        <div className="text-[10px] text-muted-foreground italic pl-1">none</div>
      ) : (
        <div className="max-h-[140px] overflow-y-auto border border-border/40 rounded-md">
          {rows.slice(0, 500).map((r: any) => (
            <label key={r.nhl_id} className="flex items-center gap-2 text-[11px] px-2 py-0.5 hover:bg-secondary/30 cursor-pointer">
              <Checkbox
                checked={sel.has(r.nhl_id)}
                onCheckedChange={() => toggle(setter, r.nhl_id)}
                data-testid={`sync-row-${r.nhl_id}`}
              />
              <span className="font-medium truncate max-w-[160px]">{r.name}</span>
              {renderCell(r)}
              <span className="text-muted-foreground ml-auto font-mono text-[9px]">{r.nhl_id}</span>
            </label>
          ))}
          {rows.length > 500 && (
            <div className="text-[10px] text-center text-muted-foreground py-1">
              (+ {rows.length - 500} more — apply &ldquo;All&rdquo; to include them)
            </div>
          )}
        </div>
      )}
    </div>
  );

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
      data-testid="nhl-sync-modal"
    >
      <Card
        className="max-w-4xl w-full max-h-[90vh] flex flex-col bg-card border-border"
        onClick={(e) => e.stopPropagation()}
      >
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <GitPullRequest className="h-4 w-4 text-cyan-400" />
                NHL API sync — Dry run
              </CardTitle>
              <CardDescription className="text-[11px]">
                Feed vs DB comparison. Check the rows you want to apply.
                Nothing is written until you press Commit.
                {" "}Feed: <span className="font-mono">{diff.counts.feed_total}</span>{" "}
                · DB: <span className="font-mono">{diff.counts.existing_total}</span>{" "}
                · Fetched in {data.duration_ms}ms
              </CardDescription>
            </div>
            <Button variant="ghost" size="sm" onClick={onClose} className="h-7 w-7 p-0">
              <X className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 overflow-y-auto flex-1">
          {data.errors?.length > 0 && (
            <div className="rounded-md bg-amber-500/10 border border-amber-500/30 p-2 text-[10px] text-amber-200 flex items-start gap-2">
              <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />
              <div>
                <div className="font-medium">{data.errors.length} team endpoint(s) failed:</div>
                <div className="font-mono text-[9px] max-h-[40px] overflow-y-auto">
                  {data.errors.slice(0, 5).join(" · ")}
                </div>
              </div>
            </div>
          )}
          {section("New players", diff.new_players, applyNew, setApplyNew,
            (r) => <span className="text-emerald-300 text-[10px]">{r.team} · {r.position ?? "?"} · age {r.age ?? "?"}</span>,
            "bg-emerald-500/10 text-emerald-300 border-emerald-500/30")}
          {section("Age changes", diff.age_changes, applyAge, setApplyAge,
            (r) => <span className="text-cyan-300 text-[10px]">age {r.old_age ?? "?"} → {r.new_age}</span>,
            "bg-cyan-500/10 text-cyan-300 border-cyan-500/30")}
          {section("Team changes", diff.team_changes, applyTeam, setApplyTeam,
            (r) => <span className="text-cyan-300 text-[10px]">{r.old_team ?? "—"} → {r.new_team}</span>,
            "bg-cyan-500/10 text-cyan-300 border-cyan-500/30")}
          {section("Position changes", diff.position_changes, applyPos, setApplyPos,
            (r) => <span className="text-cyan-300 text-[10px]">{r.old_position ?? "—"} → {r.new_position}</span>,
            "bg-cyan-500/10 text-cyan-300 border-cyan-500/30")}
          {section("Prospect flag changes", diff.prospect_changes, applyProsp, setApplyProsp,
            (r) => <span className="text-cyan-300 text-[10px]">prospect {String(r.old_is_prospect)} → {String(r.new_is_prospect)}</span>,
            "bg-cyan-500/10 text-cyan-300 border-cyan-500/30")}
          {/* Duplicates: stale rows with the same (name+birth_date) as a
              fresh candidate but a different nhl_id. Merging drops the
              stale row (roster-safe). */}
          <div className="space-y-1" data-testid="sync-section-duplicates">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-[10px] bg-fuchsia-500/10 text-fuchsia-300 border-fuchsia-500/30">
                Duplicates (merge stale row)
              </Badge>
              <span className="text-[10px] text-muted-foreground">
                {applyDup.size}/{(diff.duplicates ?? []).length} selected
              </span>
              {(diff.duplicates ?? []).length > 0 && (
                <>
                  <Button size="sm" variant="ghost" className="h-5 text-[9px] px-1"
                    onClick={() => setApplyDup(new Set((diff.duplicates ?? []).map((d: any) => d.stale_id)))}>All</Button>
                  <Button size="sm" variant="ghost" className="h-5 text-[9px] px-1"
                    onClick={() => setApplyDup(new Set())}>None</Button>
                </>
              )}
            </div>
            {((diff.duplicates ?? []).length === 0) ? (
              <div className="text-[10px] text-muted-foreground italic pl-1">none</div>
            ) : (
              <div className="max-h-[160px] overflow-y-auto border border-border/40 rounded-md">
                {(diff.duplicates ?? []).slice(0, 500).map((d: any) => (
                  <label key={d.stale_id}
                    className="flex items-center gap-2 text-[11px] px-2 py-0.5 hover:bg-secondary/30 cursor-pointer"
                  >
                    <Checkbox
                      checked={applyDup.has(d.stale_id)}
                      onCheckedChange={() => toggle(setApplyDup, d.stale_id)}
                      data-testid={`sync-dup-${d.stale_id}`}
                    />
                    <span className="font-medium truncate max-w-[160px]">{d.name}</span>
                    <span className="text-fuchsia-300 text-[10px]">
                      drop {d.stale_team ?? "—"} (id {d.stale_nhl_id}) → keep {d.fresh_team ?? "—"} (id {d.fresh_nhl_id})
                    </span>
                    <span className="text-muted-foreground ml-auto font-mono text-[9px]">{d.birth_date}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
          {section("Removed (not in feed)", diff.removed, applyRemoved, setApplyRemoved,
            (r) => <span className="text-rose-300 text-[10px]">{r.team ?? "—"} · orphan</span>,
            "bg-rose-500/10 text-rose-300 border-rose-500/30")}
        </CardContent>
        <div className="border-t border-border p-3 flex items-center justify-between gap-2">
          <span className="text-[11px] text-muted-foreground">
            <span className="font-mono">{totalSelected}</span> row(s) selected for apply
          </span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={onClose} disabled={committing}>
              Cancel
            </Button>
            <Button
              variant="default" size="sm"
              onClick={commit}
              disabled={committing || totalSelected === 0}
              data-testid="nhl-sync-commit-btn"
            >
              {committing ? <RefreshCw className="h-3 w-3 animate-spin mr-1" /> : <CheckCircle2 className="h-3 w-3 mr-1" />}
              Commit {totalSelected} change{totalSelected === 1 ? "" : "s"}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

// ────────────────────────── CSV preview modal ────────────────────────

function CsvPreviewModal({
  data, onClose, onCommitted,
}: { data: any; onClose: () => void; onCommitted: () => void; }) {
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(
    () => new Set(data.rows.filter((r: any) => r.valid).map((r: any) => r.index)),
  );
  const [committing, setCommitting] = useState(false);

  const toggle = (i: number) => {
    setSelectedIndices((s) => {
      const n = new Set(s);
      if (n.has(i)) n.delete(i); else n.add(i);
      return n;
    });
  };

  const commit = async () => {
    setCommitting(true);
    try {
      const { data: res } = await api.post("/admin/players/csv/commit", {
        preview_token: data.token,
        apply_indices: Array.from(selectedIndices),
      });
      toast.success(`CSV committed · ${res.upserted} rows${res.skipped_invalid ? ` · ${res.skipped_invalid} skipped invalid` : ""}`);
      onCommitted();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Commit failed");
    } finally {
      setCommitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
      data-testid="csv-preview-modal"
    >
      <Card
        className="max-w-4xl w-full max-h-[90vh] flex flex-col bg-card border-border"
        onClick={(e) => e.stopPropagation()}
      >
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Upload className="h-4 w-4 text-cyan-400" />
                CSV validation preview
              </CardTitle>
              <CardDescription className="text-[11px]">
                <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-300 border-emerald-500/30 mr-1">
                  {data.totals.valid} valid
                </Badge>
                <Badge variant="outline" className="text-[10px] bg-rose-500/10 text-rose-300 border-rose-500/30 mr-1">
                  {data.totals.errors} errors
                </Badge>
                <Badge variant="outline" className="text-[10px] mr-1">
                  {data.totals.read} read
                </Badge>
                {data.truncated && <span className="text-amber-300">· preview truncated to first 500 rows (all rows still commit)</span>}
              </CardDescription>
            </div>
            <Button variant="ghost" size="sm" onClick={onClose} className="h-7 w-7 p-0">
              <X className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="overflow-y-auto flex-1 text-[11px]">
          <table className="w-full" data-testid="csv-preview-table">
            <thead className="sticky top-0 bg-card">
              <tr className="text-left text-muted-foreground border-b border-border/40">
                <th className="w-8 py-1"></th>
                <th className="py-1 pr-2">#</th>
                <th className="py-1 pr-2">Name</th>
                <th className="py-1 pr-2">Team</th>
                <th className="py-1 pr-2">Pos</th>
                <th className="py-1 pr-2">Age</th>
                <th className="py-1 pr-2">Errors</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r: any) => (
                <tr key={r.index}
                    className={`border-t border-border/20 ${r.valid ? "" : "bg-rose-500/10"}`}
                    data-testid={`csv-row-${r.index}`}>
                  <td className="py-1">
                    <Checkbox
                      checked={selectedIndices.has(r.index)}
                      onCheckedChange={() => toggle(r.index)}
                      disabled={!r.valid}
                      data-testid={`csv-select-${r.index}`}
                    />
                  </td>
                  <td className="py-1 pr-2 font-mono text-muted-foreground">{r.index}</td>
                  <td className="py-1 pr-2 truncate max-w-[180px]">{r.raw_name ?? "—"}</td>
                  <td className="py-1 pr-2 font-mono">{r.raw_team ?? "—"}</td>
                  <td className="py-1 pr-2">{r.raw_position ?? "—"}</td>
                  <td className="py-1 pr-2 font-mono">{r.raw_age ?? "—"}</td>
                  <td className="py-1 pr-2 text-rose-300 text-[10px]">
                    {r.errors.length > 0 ? r.errors.join("; ") : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
        <div className="border-t border-border p-3 flex items-center justify-between gap-2">
          <span className="text-[11px] text-muted-foreground">
            <span className="font-mono">{selectedIndices.size}</span> valid row(s) will be upserted
          </span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={onClose} disabled={committing}>
              Cancel
            </Button>
            <Button
              variant="default" size="sm"
              onClick={commit}
              disabled={committing || selectedIndices.size === 0}
              data-testid="csv-commit-btn"
            >
              {committing ? <RefreshCw className="h-3 w-3 animate-spin mr-1" /> : <CheckCircle2 className="h-3 w-3 mr-1" />}
              Commit {selectedIndices.size} row{selectedIndices.size === 1 ? "" : "s"}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}



// ────────────────────────── Duplicates scan modal ────────────────────

interface DupRow {
  id: string;
  nhl_id: string;
  name?: string;
  team?: string;
  league?: string;
  age?: number;
  birth_date?: string | null;
  is_prospect?: boolean;
}
interface DupCluster {
  name: string;
  birth_date: string | null;
  match_reason: string;
  rows: DupRow[];
}

function DuplicatesModal({
  data, onClose, onMerged,
}: { data: any; onClose: () => void; onMerged: () => void; }) {
  const clusters: DupCluster[] = data.clusters ?? [];
  // Per-cluster state: keep id (defaults to first row = recommended
  // survivor) and a set of drop ids (defaults to every other row).
  const [selections, setSelections] = useState<Record<number, {
    keepId: string; dropIds: Set<string>;
  }>>(() => {
    const initial: Record<number, { keepId: string; dropIds: Set<string> }> = {};
    clusters.forEach((c, i) => {
      initial[i] = {
        keepId: c.rows[0]?.id ?? "",
        dropIds: new Set(c.rows.slice(1).map((r) => r.id)),
      };
    });
    return initial;
  });
  const [committing, setCommitting] = useState(false);

  const setKeep = (ci: number, id: string) => {
    setSelections((s) => {
      const cluster = clusters[ci];
      const dropIds = new Set(cluster.rows
        .filter((r) => r.id !== id && s[ci]?.dropIds.has(r.id))
        .map((r) => r.id));
      // Make sure the new keep isn't in the drop set.
      dropIds.delete(id);
      return { ...s, [ci]: { keepId: id, dropIds } };
    });
  };
  const toggleDrop = (ci: number, id: string) => {
    setSelections((s) => {
      const cur = s[ci];
      if (!cur || cur.keepId === id) return s;
      const dropIds = new Set(cur.dropIds);
      if (dropIds.has(id)) dropIds.delete(id); else dropIds.add(id);
      return { ...s, [ci]: { ...cur, dropIds } };
    });
  };

  const totalMerges = Object.values(selections)
    .reduce((acc, s) => acc + (s?.dropIds.size ?? 0), 0);

  const commit = async () => {
    const merges = Object.values(selections)
      .filter((s) => s && s.keepId && s.dropIds.size > 0)
      .map((s) => ({ keep_id: s.keepId, drop_ids: Array.from(s.dropIds) }));
    if (merges.length === 0) return;
    if (!window.confirm(
      `Merge ${totalMerges} duplicate row(s) into ${merges.length} survivor(s)? Roster references will be repointed automatically.`,
    )) return;
    setCommitting(true);
    try {
      const { data: res } = await api.post("/admin/players/duplicates/merge", { merges });
      toast.success(
        `Merged ${res.merged} · ${res.roster_repointed} roster refs repointed${res.errors?.length ? ` · ${res.errors.length} errors` : ""}`,
      );
      onMerged();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Merge failed");
    } finally {
      setCommitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
      data-testid="duplicates-modal"
    >
      <Card
        className="max-w-5xl w-full max-h-[92vh] flex flex-col bg-card border-border"
        onClick={(e) => e.stopPropagation()}
      >
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Users2 className="h-4 w-4 text-fuchsia-400" />
                Duplicate players — merge candidates
              </CardTitle>
              <CardDescription className="text-[11px]">
                Rows grouped by (name + birth_date), or by name-only when
                one sibling is missing a DOB. First row in each cluster is
                the recommended survivor (real NHL id, real team code).
                Pick a keep row, tick the rows to drop. Rosters + contracts
                get repointed to the survivor automatically.
                {" "}<Badge variant="outline" className="text-[10px] ml-1">
                  {data.total_clusters} clusters · {data.total_rows_flagged} rows
                </Badge>
              </CardDescription>
            </div>
            <Button variant="ghost" size="sm" onClick={onClose} className="h-7 w-7 p-0">
              <X className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="overflow-y-auto flex-1 text-[11px] space-y-2">
          {clusters.length === 0 ? (
            <div className="text-center text-muted-foreground italic py-8">
              No duplicates found. Nice job!
            </div>
          ) : clusters.map((c, ci) => {
            const sel = selections[ci];
            return (
              <div key={ci}
                className="rounded-md border border-border/40 bg-secondary/10 p-2"
                data-testid={`dup-cluster-${ci}`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant="outline" className="text-[10px] bg-fuchsia-500/10 text-fuchsia-300 border-fuchsia-500/30">
                    {c.name}
                  </Badge>
                  <span className="text-[10px] text-muted-foreground font-mono">
                    {c.birth_date ?? "no DOB"}
                  </span>
                  <Badge variant="outline" className={`text-[9px] ${
                    c.match_reason === "name+birth_date"
                      ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                      : "bg-amber-500/10 text-amber-300 border-amber-500/30"
                  }`}>
                    {c.match_reason}
                  </Badge>
                  <span className="text-[10px] text-muted-foreground ml-auto">
                    {c.rows.length} rows · will drop {sel?.dropIds.size ?? 0}
                  </span>
                </div>
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-muted-foreground text-[10px]">
                      <th className="py-0.5 pr-2 w-16">Keep</th>
                      <th className="py-0.5 pr-2 w-16">Drop</th>
                      <th className="py-0.5 pr-2">Team</th>
                      <th className="py-0.5 pr-2">League</th>
                      <th className="py-0.5 pr-2">Age</th>
                      <th className="py-0.5 pr-2">Birth</th>
                      <th className="py-0.5 pr-2">Prospect</th>
                      <th className="py-0.5 pr-2">nhl_id</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.rows.map((r) => {
                      const isKeep = sel?.keepId === r.id;
                      const isDrop = sel?.dropIds.has(r.id) ?? false;
                      return (
                        <tr key={r.id}
                          className={`border-t border-border/20 ${
                            isKeep ? "bg-emerald-500/10" : isDrop ? "bg-rose-500/10" : ""
                          }`}
                          data-testid={`dup-row-${ci}-${r.id}`}
                        >
                          <td className="py-0.5 pr-2">
                            <input
                              type="radio"
                              name={`keep-${ci}`}
                              checked={isKeep}
                              onChange={() => setKeep(ci, r.id)}
                              data-testid={`dup-keep-${ci}-${r.id}`}
                            />
                          </td>
                          <td className="py-0.5 pr-2">
                            <Checkbox
                              checked={isDrop}
                              disabled={isKeep}
                              onCheckedChange={() => toggleDrop(ci, r.id)}
                              data-testid={`dup-drop-${ci}-${r.id}`}
                            />
                          </td>
                          <td className="py-0.5 pr-2 truncate max-w-[140px]">{r.team || "—"}</td>
                          <td className="py-0.5 pr-2">{r.league || "—"}</td>
                          <td className="py-0.5 pr-2 font-mono">{r.age ?? "—"}</td>
                          <td className="py-0.5 pr-2 font-mono">{r.birth_date || "—"}</td>
                          <td className="py-0.5 pr-2">{r.is_prospect ? "yes" : "—"}</td>
                          <td className="py-0.5 pr-2 font-mono text-[9px]">{r.nhl_id}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            );
          })}
        </CardContent>
        <div className="border-t border-border p-3 flex items-center justify-between gap-2">
          <span className="text-[11px] text-muted-foreground">
            <span className="font-mono">{totalMerges}</span> row(s) will be dropped
          </span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={onClose} disabled={committing}>
              Cancel
            </Button>
            <Button
              variant="default" size="sm"
              onClick={commit}
              disabled={committing || totalMerges === 0}
              data-testid="dup-commit-btn"
            >
              {committing ? <RefreshCw className="h-3 w-3 animate-spin mr-1" /> : <CheckCircle2 className="h-3 w-3 mr-1" />}
              Merge {totalMerges} duplicate{totalMerges === 1 ? "" : "s"}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
