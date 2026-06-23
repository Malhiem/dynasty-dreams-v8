// @ts-nocheck
/* ModNotesPanel — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/* ─── Iter 209 — Mod Notes side-panel (lives inside the Reports tab) ──── */
export function ModNotesPanel({ userId, userEmail }: { userId: string; userEmail?: string }) {
  const [notes, setNotes] = useState<any[]>([]);
  const [body, setBody] = useState("");
  const [category, setCategory] = useState<"general" | "warning" | "positive" | "other">("general");

  const load = useCallback(async () => {
    if (!userId) return;
    try {
      const { data } = await api.get(`/admin/platform/users/${userId}/mod-notes`);
      setNotes(data?.notes || []);
    } catch { /* noop */ }
  }, [userId]);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!body.trim()) return;
    try {
      await api.post(`/admin/platform/users/${userId}/mod-notes`, { body: body.trim(), category });
      setBody("");
      toast.success("Note added");
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const remove = async (id: string) => {
    try {
      await api.delete(`/admin/platform/users/${userId}/mod-notes/${id}`);
      await load();
    } catch { /* noop */ }
  };

  return (
    <div className="mt-3 border-t border-border pt-3" data-testid={`mod-notes-${userId}`}>
      <div className="text-xs font-semibold mb-2 flex items-center gap-2">
        Mod notes
        <span className="text-[10px] px-1.5 rounded bg-secondary/50 text-muted-foreground">
          {notes.length}
        </span>
        <span className="text-[10px] text-muted-foreground font-normal">
          for {userEmail || userId}
        </span>
      </div>
      <div className="space-y-1 mb-2 max-h-40 overflow-y-auto">
        {notes.length === 0 && (
          <div className="text-[11px] text-muted-foreground italic">No notes yet.</div>
        )}
        {notes.map((n: any) => (
          <div key={n.note_id} className="text-xs flex items-start gap-2 border-l-2 border-border pl-2 py-0.5">
            <span className={`text-[9px] uppercase shrink-0 mt-0.5 ${
              n.category === "warning" ? "text-amber-300" :
              n.category === "positive" ? "text-emerald-300" :
              "text-muted-foreground"
            }`}>{n.category}</span>
            <div className="flex-1 min-w-0">
              <div className="break-words">{n.body}</div>
              <div className="text-[10px] text-muted-foreground">
                {n.author_email} · {new Date(n.created_at).toLocaleString()}
              </div>
            </div>
            <button
              onClick={() => remove(n.note_id)}
              className="text-rose-400 hover:text-rose-300 text-[10px] shrink-0"
              data-testid={`mod-note-remove-${n.note_id}`}
            >✕</button>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <Input
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Add a moderator note…"
          onKeyDown={(e) => e.key === "Enter" && add()}
          maxLength={2000}
          className="text-xs h-8"
          data-testid={`mod-note-input-${userId}`}
        />
        <Select value={category} onValueChange={(v: any) => setCategory(v)}>
          <SelectTrigger className="w-24 h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="general">General</SelectItem>
            <SelectItem value="warning">Warning</SelectItem>
            <SelectItem value="positive">Positive</SelectItem>
            <SelectItem value="other">Other</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" onClick={add} disabled={!body.trim()} data-testid={`mod-note-add-${userId}`}>
          Add
        </Button>
      </div>
    </div>
  );
}













