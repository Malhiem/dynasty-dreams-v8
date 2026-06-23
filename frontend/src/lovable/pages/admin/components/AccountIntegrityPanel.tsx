// @ts-nocheck
/* AccountIntegrityPanel — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/* ─── Iter 206 — Account Integrity Panel ─────────────────────────────── */
export function AccountIntegrityPanel() {
  const [groups, setGroups] = useState<any[]>([]);
  const [deviceGroups, setDeviceGroups] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [banFor, setBanFor] = useState<{ userId: string; email: string } | null>(null);
  const [tab, setTab] = useState<"ip" | "device">("ip");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ipRes, devRes] = await Promise.all([
        api.get("/admin/platform/account-integrity"),
        api.get("/admin/platform/device-integrity"),
      ]);
      setGroups(ipRes.data?.groups || []);
      setDeviceGroups(devRes.data?.groups || []);
    } catch {
      toast.error("Failed to load integrity report");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const activeGroups = tab === "ip" ? groups : deviceGroups;

  return (
    <section className="space-y-3" data-testid="integrity-section">
      <div>
        <h2 className="text-lg font-semibold">Account Integrity</h2>
        <p className="text-xs text-muted-foreground">
          Distinct users sharing the same IP or device fingerprint. Strong signal for multi-account abuse.
        </p>
      </div>
      <div className="flex gap-2 border-b border-border">
        <button
          type="button"
          onClick={() => setTab("ip")}
          className={`px-3 py-1.5 text-sm border-b-2 -mb-px ${
            tab === "ip"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
          data-testid="integrity-tab-ip"
        >
          Shared IP
          <span className="ml-2 text-[10px] px-1.5 rounded bg-secondary/50">{groups.length}</span>
        </button>
        <button
          type="button"
          onClick={() => setTab("device")}
          className={`px-3 py-1.5 text-sm border-b-2 -mb-px ${
            tab === "device"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
          data-testid="integrity-tab-device"
        >
          Shared Device
          <span className="ml-2 text-[10px] px-1.5 rounded bg-secondary/50">{deviceGroups.length}</span>
        </button>
      </div>
      {loading && <div className="text-sm text-muted-foreground py-4 text-center">Scanning login audit…</div>}
      {!loading && activeGroups.length === 0 && (
        <div className="text-sm text-muted-foreground py-6 text-center border border-dashed border-border rounded-lg" data-testid="integrity-empty">
          No shared-{tab === "ip" ? "IP" : "device"} groups detected.
        </div>
      )}
      {!loading && activeGroups.length > 0 && (
        <div className="space-y-3" data-testid="integrity-list">
          {activeGroups.map((g: any, idx: number) => (
            <div key={g.ip || g.device_hash || idx} className="rounded-lg border border-border bg-muted/20 p-3" data-testid={`integrity-group-${idx}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-mono break-all">
                  {tab === "ip" ? g.ip : (
                    <span title={g.device_hash}>
                      {String(g.device_hash || "").slice(0, 16)}…
                    </span>
                  )}
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded-full border border-amber-500/40 text-amber-300">
                  {g.distinct_users} accounts · {g.login_count} logins
                </span>
              </div>
              <div className="space-y-1">
                {g.users.map((u: any) => (
                  <div key={u.user_id} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <span>{u.email || u.user_id}</span>
                      <span className={`text-[10px] px-1.5 rounded ${
                        u.status === "banned" ? "bg-rose-500/20 text-rose-300" :
                        u.status === "suspended" ? "bg-amber-500/20 text-amber-300" :
                        "bg-emerald-500/20 text-emerald-300"
                      }`}>
                        {u.status || "active"}
                      </span>
                    </div>
                    {u.status !== "banned" && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="border-rose-500/50 text-rose-300 hover:bg-rose-500/10"
                        onClick={() => setBanFor({ userId: u.user_id, email: u.email })}
                        data-testid={`integrity-ban-${u.user_id}`}
                      >
                        Ban
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {banFor && <BanUserDialog target={banFor} onClose={() => setBanFor(null)} onDone={load} />}
    </section>
  );
}


export function BanUserDialog({ target, onClose, onDone }: { target: { userId: string; email: string }; onClose: () => void; onDone: () => void }) {
  const [reasonCode, setReasonCode] = useState("harassment");
  const [reason, setReason] = useState("");
  const [durationDays, setDurationDays] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      await api.post(`/admin/platform/users/${target.userId}/ban`, {
        reason_code: reasonCode,
        reason,
        duration_days: durationDays ? Number(durationDays) : null,
      });
      toast.success(`${target.email} ${durationDays ? "suspended" : "banned"}`);
      onClose();
      onDone();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-background border border-border rounded-lg p-5 max-w-md w-full space-y-3" onClick={(e) => e.stopPropagation()} data-testid="ban-dialog">
        <h3 className="text-lg font-semibold">Ban {target.email}</h3>
        <div className="space-y-2">
          <Select value={reasonCode} onValueChange={setReasonCode}>
            <SelectTrigger data-testid="ban-reason-code"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="harassment">Harassment</SelectItem>
              <SelectItem value="fraud">Payment fraud</SelectItem>
              <SelectItem value="cheating">Cheating</SelectItem>
              <SelectItem value="collusion">Collusion</SelectItem>
              <SelectItem value="other">Other</SelectItem>
            </SelectContent>
          </Select>
          <Input
            placeholder="Reason (visible to user)…"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            data-testid="ban-reason-input"
          />
          <Input
            type="number"
            placeholder="Duration days (blank = permanent)"
            value={durationDays}
            onChange={(e) => setDurationDays(e.target.value)}
            data-testid="ban-duration-input"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={submitting || !reason.trim()} className="bg-rose-500/80 hover:bg-rose-500" data-testid="ban-submit-btn">
            {submitting ? "…" : "Apply"}
          </Button>
        </div>
      </div>
    </div>
  );
}


