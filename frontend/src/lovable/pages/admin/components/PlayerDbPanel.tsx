/**
 * Iter 232N.64 — Admin Player DB panel.
 *
 * Sits under the "Player DB" tab in the platform-admin dashboard. Gives
 * admins full CRUD over `db.players` + a recent-edits audit strip +
 * three refresh actions (reseed / NHL API / CSV upload).
 *
 * Authoritative endpoints:
 *   • GET    /admin/players?q=&position=&is_prospect=&skip=&limit=
 *   • POST   /admin/players            (create)
 *   • PUT    /admin/players/{id}       (update — allow-listed fields)
 *   • DELETE /admin/players/{id}       (409 when on any roster)
 *   • GET    /admin/players/audit      (recent edits feed)
 *   • POST   /admin/players/refresh    ({source: reseed|nhl_api})
 *   • POST   /admin/players/refresh/csv (multipart CSV upload)
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Database, RefreshCw, Plus, Trash2, Pencil, AlertTriangle,
  ScrollText, Upload, CheckCircle2,
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

  useEffect(() => {
    load();
  }, [load]);

  // ── Refresh actions ───────────────────────────────────────────
  const refreshSource = async (source: "reseed" | "nhl_api") => {
    setRefreshing(true);
    try {
      const { data } = await api.post("/admin/players/refresh", { source });
      if (data?.ok) {
        toast.success(
          `${source === "reseed" ? "Reseed" : "NHL API"} refresh complete · ${data.upserted} rows touched · ${data.duration_ms}ms`,
        );
      } else {
        toast.error(`Refresh error: ${data?.error || "unknown"}`);
      }
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  };

  const uploadCsv = async (file: File) => {
    setRefreshing(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post("/admin/players/refresh/csv", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(
        `CSV import complete · ${data.upserted} rows${data.errors?.length ? ` · ${data.errors.length} errors` : ""}`,
      );
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "CSV upload failed");
    } finally {
      setRefreshing(false);
    }
  };

  // ── Delete ─────────────────────────────────────────────────────
  const deletePlayer = async (p: Player) => {
    if (!window.confirm(`Delete ${p.name}? This can't be undone.`)) return;
    try {
      await api.delete(`/admin/players/${p.id}`);
      toast.success(`Deleted ${p.name}`);
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Delete failed");
    }
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
                Full CRUD over the ~3,300-player DB. Edits are audited.
                Refresh actions upsert by <code className="text-[10px]">nhl_id</code> so leagues stay intact.
              </CardDescription>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <Select onValueChange={(v: any) => refreshSource(v)} disabled={refreshing}>
                <SelectTrigger className="h-8 text-xs w-[160px]" data-testid="player-db-refresh-select">
                  <SelectValue placeholder={refreshing ? "Refreshing…" : "Refresh from…"} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="reseed">Reseed script</SelectItem>
                  <SelectItem value="nhl_api">NHL API (statsapi)</SelectItem>
                </SelectContent>
              </Select>
              <label className="cursor-pointer">
                <Button
                  variant="outline" size="sm"
                  disabled={refreshing}
                  data-testid="player-db-csv-btn"
                  className="h-8" asChild
                >
                  <span><Upload className="h-3 w-3 mr-1" /> CSV</span>
                </Button>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) uploadCsv(f);
                    e.currentTarget.value = "";
                  }}
                  data-testid="player-db-csv-input"
                />
              </label>
              <Button
                variant="outline" size="sm" onClick={load}
                disabled={loading} className="h-8"
                data-testid="player-db-reload-btn"
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

          {/* Table */}
          <div className="overflow-x-auto rounded-md border border-border/60">
            <table className="w-full text-[11px]" data-testid="player-db-table">
              <thead>
                <tr className="text-left text-muted-foreground bg-secondary/30">
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
                    className="border-t border-border/40 hover:bg-secondary/20"
                    data-testid={`player-db-row-${p.id}`}
                  >
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
                        data-testid={`player-db-edit-${p.id}`}
                      >
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <Button
                        variant="ghost" size="sm"
                        onClick={() => deletePlayer(p)}
                        className="h-6 w-6 p-0 text-rose-300 hover:text-rose-400"
                        data-testid={`player-db-delete-${p.id}`}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </td>
                  </tr>
                ))}
                {players.length === 0 && !loading && (
                  <tr>
                    <td colSpan={8} className="py-4 text-center text-muted-foreground italic">
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

      {/* Edit / Create modal */}
      {(editing || creating) && (
        <PlayerEditModal
          player={editing}
          onClose={() => { setEditing(null); setCreating(false); }}
          onSaved={() => { setEditing(null); setCreating(false); load(); }}
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
