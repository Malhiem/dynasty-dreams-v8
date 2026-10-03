// @ts-nocheck
import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Input } from "@/components/ui/input";
import { ArrowRightLeft, Loader2, Plus, X, MessageSquare, Save } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import api from "@/lib/api";

const RETENTION_OPTIONS = [
  { value: "willing_to_retain", label: "A · Willing to retain", color: "text-emerald-400" },
  { value: "no_preference", label: "B · No preference", color: "text-muted-foreground" },
  { value: "seeking_retention", label: "C · Seeking retention", color: "text-amber-400" },
];

export default function TradeBlockManager({ team, league, isOwnTeam, reloadKey = 0, onItemsChange }) {
  const [items, setItems] = useState([]);
  const [picks, setPicks] = useState([]);
  const [pickToAdd, setPickToAdd] = useState("");
  const [retention, setRetention] = useState(team?.salary_retention_pref || "no_preference");
  const [busy, setBusy] = useState(false);
  const [retentionSaving, setRetentionSaving] = useState(false);
  // Public note shown to anyone viewing this team's trade block (max 200 chars).
  const [note, setNote] = useState("");
  const [savedNote, setSavedNote] = useState("");
  const [noteSaving, setNoteSaving] = useState(false);
  const noteRemaining = 200 - note.length;
  const noteDirty = note !== savedNote;

  // Local set of player_ids on the block (for fast toggle highlight)
  const onBlockSet = useMemo(() => new Set(items.filter(i => i.item_type === "player").map(i => i.player_id)), [items]);

  // Notify parent every time `items` changes so the bullhorn highlight on
  // the roster table above stays in sync with the card below.
  useEffect(() => {
    if (onItemsChange) onItemsChange(items);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  const fetchItems = async () => {
    if (!team?.id) return;
    try {
      const { data } = await api.get(`/trade-block?team_id=${team.id}`);
      setItems(Array.isArray(data) ? data : (data?.items || []));
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    fetchItems();
    // Load this team's draft picks for the dropdown
    if (team?.id && league?.id) {
      api.get(`/drafts/${league.id}/picks`).then(({ data }) => {
        const owned = (data?.picks || []).filter(p => p.current_team_id === team.id);
        setPicks(owned);
      }).catch(() => {});
    }
    setRetention(team?.salary_retention_pref || "no_preference");
    // Load the team's public trade block note
    if (team?.id) {
      api.get(`/teams/${team.id}/trade-block-note`)
        .then(({ data }) => {
          const n = data?.note || "";
          setNote(n);
          setSavedNote(n);
        })
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [team?.id, league?.id, reloadKey]);

  const saveNote = async () => {
    if (!isOwnTeam || !team?.id || noteSaving) return;
    setNoteSaving(true);
    try {
      const { data } = await api.put(`/teams/${team.id}/trade-block-note`, {
        note: note.slice(0, 200),
      });
      setSavedNote(data?.note ?? note);
      toast.success("Trade block note saved");
    } catch (e) {
      toast.error("Failed to save note", {
        description: e?.response?.data?.detail || e?.message,
      });
    } finally {
      setNoteSaving(false);
    }
  };

  const togglePlayer = async (player) => {
    if (!isOwnTeam || busy || !team?.id) return;
    setBusy(true);
    try {
      const existing = items.find(i => i.item_type === "player" && i.player_id === player.id);
      if (existing) {
        await api.delete(`/trade-block/${existing._id}`);
        toast.success(`${player.name} removed from trade block`);
      } else {
        await api.post(`/trade-block`, {
          item_type: "player", player_id: player.id,
          league_id: league?.id, team_id: team.id,
        });
        toast.success(`${player.name} added to trade block`);
      }
      await fetchItems();
    } catch (e) {
      toast.error("Trade block toggle failed", { description: e?.response?.data?.detail || e?.message });
    } finally {
      setBusy(false);
    }
  };

  const commitPick = async () => {
    if (!pickToAdd || busy) return;
    setBusy(true);
    try {
      await api.post(`/trade-block`, {
        item_type: "pick", pick_id: pickToAdd, league_id: league?.id, team_id: team.id,
      });
      toast.success("Pick added to trade block");
      setPickToAdd("");
      await fetchItems();
    } catch (e) {
      toast.error("Failed to add pick", { description: e?.response?.data?.detail || e?.message });
    } finally {
      setBusy(false);
    }
  };

  const removeItem = async (item) => {
    if (!isOwnTeam || busy) return;
    setBusy(true);
    try {
      await api.delete(`/trade-block/${item._id}`);
      toast.success(`${item.name} removed from trade block`);
      await fetchItems();
    } catch (e) {
      toast.error("Removal failed", { description: e?.response?.data?.detail || e?.message });
    } finally {
      setBusy(false);
    }
  };

  const updateRetention = async (next) => {
    if (!next || !team?.id || retentionSaving) return;
    setRetentionSaving(true);
    try {
      await api.put(`/teams/${team.id}/trade-block-preference`, { preference: next });
      setRetention(next);
      const opt = RETENTION_OPTIONS.find(o => o.value === next);
      toast.success(`Salary retention: ${opt?.label || next}`);
      await fetchItems();
    } catch (e) {
      toast.error("Failed to update preference", { description: e?.response?.data?.detail || e?.message });
    } finally {
      setRetentionSaving(false);
    }
  };

  return (
    <Card className="bg-card border-border" data-testid="team-trade-block-manager">
      <CardHeader>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <ArrowRightLeft className="h-5 w-5 text-primary" />
              Trade Block
            </CardTitle>
            <p className="text-xs text-muted-foreground mt-1">
              {isOwnTeam
                ? "Click any player on your roster to toggle them on/off the block. Pick selector below for draft assets."
                : `Showing ${team?.name || "team"}'s trade block.`}
            </p>
          </div>
          {isOwnTeam && (
            <div className="flex flex-col items-end gap-1.5">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Salary Retention</span>
              <ToggleGroup
                type="single"
                value={retention}
                onValueChange={updateRetention}
                disabled={retentionSaving}
                className="border border-border rounded-md"
                data-testid="team-retention-toggle"
              >
                {RETENTION_OPTIONS.map(o => (
                  <ToggleGroupItem
                    key={o.value}
                    value={o.value}
                    className={`text-[11px] px-3 py-1.5 ${o.color}`}
                    data-testid={`team-retention-${o.value}`}
                    aria-label={o.label}
                  >
                    {o.label.split("·")[0].trim()}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
              <span className="text-[10px] text-muted-foreground">
                {RETENTION_OPTIONS.find(o => o.value === retention)?.label}
              </span>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Public trade block note (max 200 chars). Owner can edit; visitors
            see it as a read-only message. Hidden entirely when there's no
            note and the viewer doesn't own the team. */}
        {(isOwnTeam || (savedNote && savedNote.length > 0)) && (
          <div
            className="rounded-md border border-border bg-secondary/30 p-3"
            data-testid="trade-block-note-section"
          >
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground">
                <MessageSquare className="h-3 w-3" />
                Note from {isOwnTeam ? "you" : (team?.name || "owner")}
              </div>
              {isOwnTeam && (
                <span className={`text-[10px] ${noteRemaining < 20 ? "text-amber-300" : "text-muted-foreground"}`}>
                  {noteRemaining}/200
                </span>
              )}
            </div>
            {isOwnTeam ? (
              <>
                <Textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value.slice(0, 200))}
                  placeholder="What are you looking for? (e.g., '2C with 30+ pts; willing to overpay for top-pair LD'). Visible to all league members."
                  rows={2}
                  className="text-xs resize-none bg-background/40"
                  maxLength={200}
                  data-testid="trade-block-note-input"
                />
                <div className="flex items-center justify-end gap-2 mt-2">
                  {noteDirty && (
                    <button
                      type="button"
                      onClick={() => setNote(savedNote)}
                      className="text-[11px] text-muted-foreground hover:text-foreground"
                      data-testid="trade-block-note-undo"
                    >
                      Undo
                    </button>
                  )}
                  <Button
                    size="sm"
                    onClick={saveNote}
                    disabled={!noteDirty || noteSaving}
                    className="h-7 text-[11px]"
                    data-testid="trade-block-note-save"
                  >
                    {noteSaving ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Save className="h-3 w-3 mr-1" />}
                    Save Note
                  </Button>
                </div>
              </>
            ) : (
              <p className="text-sm text-foreground/85 whitespace-pre-wrap" data-testid="trade-block-note-readonly">
                {savedNote}
              </p>
            )}
          </div>
        )}

        {/* Current items */}
        {items.length === 0 ? (
          <div className="text-center py-6 text-sm text-muted-foreground border border-dashed border-border rounded-md" data-testid="trade-block-empty">
            Nothing on the block yet.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2" data-testid="trade-block-items">
            {items.map(item => (
              <div
                key={item._id}
                className="border border-border bg-secondary/30 rounded-md px-3 py-2 flex items-center justify-between gap-2"
                data-testid={`trade-block-item-${item._id}`}
              >
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-sm truncate">{item.name}</div>
                  <div className="text-[10px] text-muted-foreground flex items-center gap-1.5">
                    <span className="font-bold text-primary">{item.position || (item.item_type === "pick" ? "PICK" : "—")}</span>
                    {item.nhl_team && <span>· {item.nhl_team}</span>}
                    {item.fantasy_points != null && item.item_type === "player" && (
                      <span>· {item.fantasy_points.toFixed(0)} fpts · {(item.fantasy_ppg || 0).toFixed(2)} ppg</span>
                    )}
                  </div>
                </div>
                {isOwnTeam && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0"
                    onClick={() => removeItem(item)}
                    disabled={busy}
                    data-testid={`trade-block-remove-${item._id}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Pick selector */}
        {isOwnTeam && (
          <div className="border-t border-border pt-3 flex flex-col sm:flex-row gap-2 items-stretch sm:items-end">
            <div className="flex-1 space-y-1.5">
              <label className="text-[10px] uppercase tracking-wider text-muted-foreground">Add Draft Pick</label>
              <Select value={pickToAdd} onValueChange={setPickToAdd}>
                <SelectTrigger data-testid="trade-block-pick-select">
                  <SelectValue placeholder={picks.length === 0 ? "No picks owned" : "Select a pick…"} />
                </SelectTrigger>
                <SelectContent>
                  {picks.length === 0 && (
                    <SelectItem value="__none" disabled>No picks owned by this team</SelectItem>
                  )}
                  {picks.map(p => (
                    <SelectItem key={p._id} value={p._id}>
                      {p.year} R{p.round}{p.pick_number ? ` · #${p.pick_number}` : ""}
                      {p.pick_type === "compensation" ? " · COMP" : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={commitPick}
              disabled={!pickToAdd || pickToAdd === "__none" || busy}
              data-testid="trade-block-commit-pick"
              className="gap-2"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Commit to Block
            </Button>
          </div>
        )}

        {/* Roster toggle helper (for owner) */}
        {isOwnTeam && team?._players?.length > 0 && (
          <div className="border-t border-border pt-3">
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2 block">
              Quick-toggle from Roster
            </label>
            <div className="flex flex-wrap gap-1.5">
              {team._players.slice(0, 30).map(p => {
                const on = onBlockSet.has(p.id);
                return (
                  <button
                    key={p.id}
                    onClick={() => togglePlayer(p)}
                    disabled={busy}
                    data-testid={`trade-block-toggle-${p.id}`}
                    className={`text-[11px] px-2 py-1 rounded border transition-all ${
                      on
                        ? "bg-primary/20 text-primary border-primary"
                        : "bg-card text-muted-foreground border-border hover:border-primary/40"
                    }`}
                  >
                    {p.name} {on && <span className="ml-1">✓</span>}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
