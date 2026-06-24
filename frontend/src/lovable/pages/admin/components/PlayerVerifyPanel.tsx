/**
 * Iter 228e — Admin Player Verification Panel.
 *
 * Lets a platform admin quickly verify whether a player is already on
 * file (across NHL / AHL / Europe / Junior / Draft-eligible pools)
 * before manually inserting a new record. Includes a quick-add form
 * for players missing from the upstream NHL feed (Europe-league
 * prospects, AHL call-ups, etc.).
 *
 * Endpoints used:
 *   GET  /api/admin/players/verify
 *   POST /api/admin/players
 */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Search, Plus, Users, RefreshCcw, Download, Loader2, Upload } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import api from "@/lib/api";

const STATUS_OPTIONS = [
  { v: "", label: "All leagues" },
  { v: "NHL", label: "NHL" },
  { v: "AHL", label: "AHL" },
  { v: "Europe", label: "Europe (KHL/SHL/Liiga/etc.)" },
  { v: "Junior", label: "Junior / CHL" },
  { v: "Draft Eligible", label: "Draft Eligible" },
  { v: "Retired", label: "Retired" },
];

const STATUS_BADGE: Record<string, string> = {
  NHL: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  AHL: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  Europe: "bg-violet-500/20 text-violet-300 border-violet-500/40",
  Junior: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  "Draft Eligible": "bg-rose-500/20 text-rose-300 border-rose-500/40",
  Retired: "bg-muted text-muted-foreground border-border",
};

export default function PlayerVerifyPanel() {
  const [players, setPlayers] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  // Iter 228g — page size selector (10/25/100/250/500)
  const [pageSize, setPageSize] = useState(100);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);

  const [addOpen, setAddOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPosition, setNewPosition] = useState("C");
  const [newTeam, setNewTeam] = useState("");
  const [newStatus, setNewStatus] = useState("Europe");
  const [creating, setCreating] = useState(false);

  // Iter 228g — NHL draft-class sync button state
  const [syncYear, setSyncYear] = useState(2026);
  const [syncing, setSyncing] = useState(false);

  const fetchPlayers = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { limit: String(pageSize) };
      if (search) params.search = search;
      if (statusFilter) params.league_status = statusFilter;
      const { data } = await api.get("/admin/players/verify", { params });
      setPlayers(Array.isArray(data?.players) ? data.players : []);
      setTotal(Number(data?.total ?? 0));
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to load players");
    } finally {
      setLoading(false);
    }
  }, [search, statusFilter, pageSize]);

  useEffect(() => {
    const t = setTimeout(() => { void fetchPlayers(); }, 250);
    return () => clearTimeout(t);
  }, [fetchPlayers]);

  const handleCreate = async () => {
    if (!newName.trim()) {
      toast.error("Player name is required");
      return;
    }
    setCreating(true);
    try {
      await api.post("/admin/players", {
        name: newName.trim(), position: newPosition,
        team: newTeam.trim() || null, league_status: newStatus,
        player_type: newPosition === "G" ? "goalie" : "skater",
      });
      toast.success(`${newName} added to ${newStatus} pool`);
      setNewName(""); setNewTeam(""); setAddOpen(false);
      await fetchPlayers();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Create failed");
    } finally {
      setCreating(false);
    }
  };

  // Iter 228h — NHL Central Scouting draft-class sync handler
  const handleSyncDraftClass = async () => {
    if (!window.confirm(
      `Pull all NHL Central Scouting prospects for the ${syncYear} draft? New players will be added; existing ones left alone (use "Overwrite" if you also want to refresh rankings).`,
    )) return;
    setSyncing(true);
    try {
      const { data } = await api.post("/admin/players/sync-draft-class", {
        year: syncYear, overwrite: false,
      });
      toast.success(
        `Sync complete — ${data.added} added, ${data.updated} updated (${data.errors?.length || 0} category errors)`,
        { duration: 8000 },
      );
      await fetchPlayers();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Draft-class sync failed");
    } finally {
      setSyncing(false);
    }
  };

  // Iter 228h — CSV bulk import handler. Expects header row:
  // name, position, team, league_status, date_of_birth, jersey_number
  const handleCsvImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (ev) => {
      const text = String(ev.target?.result || "");
      const lines = text.split(/\r?\n/).filter((l) => l.trim());
      if (lines.length < 2) {
        toast.error("CSV must include a header row + at least one data row");
        return;
      }
      const header = lines[0].split(",").map((h) => h.trim().toLowerCase());
      const idx = (k: string) => header.indexOf(k);
      const rows = lines.slice(1).map((line) => {
        const parts = line.split(",").map((p) => p.trim());
        return {
          name: parts[idx("name")] || "",
          position: parts[idx("position")] || "C",
          team: parts[idx("team")] || "",
          league_status: parts[idx("league_status")] || "NHL",
          date_of_birth: parts[idx("date_of_birth")] || undefined,
          jersey_number: parts[idx("jersey_number")] ? parseInt(parts[idx("jersey_number")], 10) : undefined,
        };
      }).filter((r) => r.name);
      try {
        const { data } = await api.post("/admin/players/bulk-import", {
          rows, skip_duplicates: true,
        });
        toast.success(
          `Imported ${data.added} of ${data.received} rows (${data.skipped?.length || 0} duplicates skipped, ${data.errors?.length || 0} errors)`,
          { duration: 8000 },
        );
        await fetchPlayers();
      } catch (err: any) {
        toast.error(err?.response?.data?.detail || "CSV import failed");
      } finally {
        if (e.target) e.target.value = "";
      }
    };
    reader.readAsText(file);
  };

  return (
    <Card className="hover-glow" data-testid="player-verify-panel">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <Users className="h-4 w-4" />
          Player Verification
          <Badge variant="secondary" className="ml-2" data-testid="player-verify-total">
            {total} on file
          </Badge>
        </CardTitle>
        <div className="flex gap-2">
          <Button
            size="sm" variant="outline" onClick={fetchPlayers} disabled={loading}
            data-testid="player-verify-refresh"
          >
            <RefreshCcw className={`h-3.5 w-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button
            size="sm" variant="outline" asChild
            data-testid="player-verify-csv-import-label"
          >
            <label className="cursor-pointer">
              <Upload className="h-3.5 w-3.5 mr-1.5" />
              Import CSV
              <input
                type="file" accept=".csv,text/csv"
                onChange={handleCsvImport}
                className="hidden"
                data-testid="player-verify-csv-import-input"
              />
            </label>
          </Button>
          <Button
            size="sm" onClick={() => setAddOpen((v) => !v)}
            data-testid="player-verify-add-toggle"
          >
            <Plus className="h-3.5 w-3.5 mr-1.5" />
            {addOpen ? "Cancel" : "Add Player"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Iter 228g — NHL Central Scouting draft-class sync */}
        <div className="flex items-center gap-2 flex-wrap p-3 border border-violet-500/40 bg-violet-500/5 rounded-lg" data-testid="draft-class-sync-row">
          <span className="text-xs font-semibold uppercase tracking-wider text-violet-300">
            NHL Draft Class Sync
          </span>
          <span className="text-xs text-muted-foreground">
            Pulls Central Scouting rankings + adds new prospects with status &quot;Draft Eligible&quot;.
          </span>
          <div className="ml-auto flex items-center gap-2">
            <Input
              type="number" min={2008} max={2030} value={syncYear}
              onChange={(e) => setSyncYear(parseInt(e.target.value || "2026", 10))}
              className="w-20 h-8"
              data-testid="draft-class-sync-year"
            />
            <Button
              size="sm" onClick={handleSyncDraftClass} disabled={syncing}
              data-testid="draft-class-sync-btn"
            >
              {syncing ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <Download className="h-3.5 w-3.5 mr-1.5" />}
              Sync {syncYear}
            </Button>
          </div>
        </div>
        {/* Quick-add form */}
        {addOpen && (
          <div
            className="grid grid-cols-1 sm:grid-cols-12 gap-2 p-3 border border-accent/40 bg-accent/5 rounded-lg"
            data-testid="player-verify-add-form"
          >
            <div className="sm:col-span-4">
              <Label className="text-xs">Name</Label>
              <Input
                placeholder="e.g. Ivan Demidov"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                data-testid="player-verify-add-name"
              />
            </div>
            <div className="sm:col-span-2">
              <Label className="text-xs">Position</Label>
              <Select value={newPosition} onValueChange={setNewPosition}>
                <SelectTrigger data-testid="player-verify-add-position"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["C", "LW", "RW", "D", "G"].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="sm:col-span-3">
              <Label className="text-xs">Team / Club</Label>
              <Input
                placeholder="e.g. SKA"
                value={newTeam}
                onChange={(e) => setNewTeam(e.target.value)}
                data-testid="player-verify-add-team"
              />
            </div>
            <div className="sm:col-span-2">
              <Label className="text-xs">League</Label>
              <Select value={newStatus} onValueChange={setNewStatus}>
                <SelectTrigger data-testid="player-verify-add-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {STATUS_OPTIONS.filter((s) => s.v).map((s) => <SelectItem key={s.v} value={s.v}>{s.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="sm:col-span-1 flex items-end">
              <Button
                size="sm" onClick={handleCreate} disabled={creating}
                className="w-full"
                data-testid="player-verify-add-save"
              >
                Save
              </Button>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="grid grid-cols-1 sm:grid-cols-12 gap-2">
          <div className="sm:col-span-8 relative">
            <Search className="h-4 w-4 absolute left-2.5 top-2.5 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Search by name or NHL team abbr…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-testid="player-verify-search"
            />
          </div>
          <div className="sm:col-span-3">
            <Select value={statusFilter || "__all__"}
                    onValueChange={(v) => setStatusFilter(v === "__all__" ? "" : v)}>
              <SelectTrigger data-testid="player-verify-status-filter"><SelectValue /></SelectTrigger>
              <SelectContent>
                {STATUS_OPTIONS.map((s) => (
                  <SelectItem key={s.v || "__all__"} value={s.v || "__all__"}>{s.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {/* Iter 228g — page size selector */}
          <div className="sm:col-span-1">
            <Select value={String(pageSize)} onValueChange={(v) => setPageSize(parseInt(v, 10))}>
              <SelectTrigger data-testid="player-verify-page-size"><SelectValue /></SelectTrigger>
              <SelectContent>
                {[10, 25, 100, 250, 500].map((n) => (
                  <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Results */}
        <div className="overflow-x-auto border border-border rounded-lg">
          <table className="w-full text-sm">
            <thead className="text-xs font-medium text-muted-foreground bg-muted/20 border-b border-border">
              <tr>
                <th className="text-left py-2 pl-3">Player</th>
                <th className="text-left py-2">Pos</th>
                <th className="text-left py-2">Team</th>
                <th className="text-left py-2">League</th>
                <th className="text-left py-2 pr-3">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {players.length === 0 && !loading && (
                <tr><td colSpan={5} className="text-center py-6 text-muted-foreground text-sm italic" data-testid="player-verify-empty">
                  No players match these filters.
                </td></tr>
              )}
              {players.map((p) => (
                <tr key={p.id} className="hover:bg-muted/10" data-testid={`player-verify-row-${p.id}`}>
                  <td className="py-1.5 pl-3 font-medium">{p.name}</td>
                  <td className="py-1.5">{p.position}</td>
                  <td className="py-1.5">{p.team || "—"}</td>
                  <td className="py-1.5">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                      STATUS_BADGE[p.league_status] || STATUS_BADGE.NHL
                    }`}>
                      {p.league_status || "NHL"}
                    </span>
                  </td>
                  <td className="py-1.5 pr-3 text-xs text-muted-foreground">
                    {p.source === "admin_manual" ? "Manual" : "NHL API"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
