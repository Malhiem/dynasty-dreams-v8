// @ts-nocheck
/**
 * UserDetailDrawer — modal drawer rendering Identity, Security, Admin Actions,
 * Extended sections + Action History for a single user.
 * Extracted from AdminDashboard.tsx during Iter 223 refactor. Also owns
 * `AdminActionHistorySection` (the per-user audit-trail rail) since it is
 * only used inside the drawer.
 */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { DetailGrid, DetailRow, StatusPill } from "./_shared";
import { AdminActionsPanel } from "./AdminActionsPanel";
import { UserExtensionsSection } from "./UserExtensionsSection";

export function UserDetailDrawer({ loading, detail, onClose, onRefresh, onRowsRefresh }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-stretch justify-end" onClick={onClose} data-testid="user-detail-drawer">
      <div
        className="w-full max-w-[760px] bg-background border-l border-border h-full overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-5 border-b border-border flex items-center justify-between sticky top-0 bg-background z-10">
          <h3 className="text-base font-semibold">User detail</h3>
          <Button variant="outline" size="sm" onClick={onClose} data-testid="user-detail-close">Close</Button>
        </div>
        {loading && <div className="p-6 text-sm text-muted-foreground">Loading user…</div>}
        {!loading && detail && (
          <div className="p-5 space-y-6 text-sm">
            <section className="space-y-2" data-testid="user-detail-identity">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Identity & Account Core</h4>
              <DetailGrid>
                <DetailRow k="User ID" v={<code className="text-xs">{detail.id}</code>} />
                <DetailRow k="Username" v={detail.username || "—"} />
                <DetailRow k="Display name" v={detail.name || "—"} />
                <DetailRow k="Email" v={<span>{detail.email} {detail.email_verified ? <span className="text-emerald-300 text-[10px] ml-1">verified</span> : <span className="text-amber-300 text-[10px] ml-1">unverified</span>}</span>} />
                <DetailRow k="Phone" v={detail.phone ? <span>{detail.phone} {detail.phone_verified ? <span className="text-emerald-300 text-[10px] ml-1">verified</span> : <span className="text-amber-300 text-[10px] ml-1">unverified</span>}</span> : "—"} />
                <DetailRow k="Auth method" v={detail.auth_method} />
                <DetailRow k="Password set" v={detail.password_hash_present ? "yes" : "no (SSO only)"} />
                <DetailRow k="Role" v={detail.role} />
                <DetailRow k="Status" v={<StatusPill status={detail.status} />} />
                <DetailRow k="Created" v={detail.created_at ? new Date(detail.created_at).toLocaleString() : "—"} />
                {detail.ban_reason_code && <DetailRow k="Ban reason" v={`${detail.ban_reason_code}${detail.ban_reason ? ` — ${detail.ban_reason}` : ""}`} />}
                {detail.ban_expires_at && <DetailRow k="Ban expires" v={new Date(detail.ban_expires_at).toLocaleString()} />}
              </DetailGrid>
              {detail.username_change_history?.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs text-muted-foreground mb-1">Name / email change history</p>
                  <ul className="space-y-1 text-xs">
                    {detail.username_change_history.map((h, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <span className="text-muted-foreground">{h.ts ? new Date(h.ts).toLocaleDateString() : "—"}</span>
                        <span className="text-foreground/80">{h.event_type}:</span>
                        <code className="text-rose-300">{h.from || "∅"}</code>
                        <span>→</span>
                        <code className="text-emerald-300">{h.to || "∅"}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>

            <section className="space-y-2" data-testid="user-detail-security">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Authentication & Security</h4>
              <DetailGrid>
                <DetailRow k="Last login" v={detail.last_login_at ? new Date(detail.last_login_at).toLocaleString() : "—"} />
                <DetailRow k="Failed login attempts" v={String(detail.failed_login_attempts || 0)} />
                {detail.lockout_until && <DetailRow k="Locked out until" v={new Date(detail.lockout_until).toLocaleString()} />}
                <DetailRow k="2FA" v={detail.two_factor_enabled ? <span className="text-emerald-300">enabled · {detail.two_factor_method || "totp"}</span> : <span className="text-muted-foreground">disabled</span>} />
                <DetailRow k="Linked SSO" v={detail.linked_sso_accounts?.length ? detail.linked_sso_accounts.join(", ") : "—"} />
                <DetailRow k="Recovery email" v={detail.recovery_email || "—"} />
                <DetailRow k="Security questions" v={detail.security_questions_set ? "set" : "not set"} />
              </DetailGrid>

              {detail.login_history?.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-muted-foreground mb-1">Login history (last {detail.login_history.length})</p>
                  <div className="rounded border border-border max-h-[260px] overflow-y-auto" data-testid="user-detail-login-history">
                    <table className="w-full text-xs">
                      <thead className="bg-secondary/40 sticky top-0">
                        <tr>
                          <th className="text-left px-2 py-1">When</th>
                          <th className="text-left px-2 py-1">IP</th>
                          <th className="text-left px-2 py-1">Device hash</th>
                          <th className="text-left px-2 py-1">User agent</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.login_history.map((h, i) => (
                          <tr key={i} className="border-t border-border/40">
                            <td className="px-2 py-1 whitespace-nowrap text-muted-foreground">{h.ts ? new Date(h.ts).toLocaleString() : "—"}</td>
                            <td className="px-2 py-1 font-mono">{h.ip || "—"}</td>
                            <td className="px-2 py-1 font-mono">{h.device_hash ? h.device_hash.slice(0, 12) + "…" : "—"}</td>
                            <td className="px-2 py-1 truncate max-w-[220px]" title={h.user_agent || ""}>{h.user_agent || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {detail.password_reset_history?.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-muted-foreground mb-1">Password reset history</p>
                  <ul className="space-y-1 text-xs">
                    {detail.password_reset_history.map((p, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <span className="text-muted-foreground">{p.ts ? new Date(p.ts).toLocaleString() : "—"}</span>
                        <code>{p.ip || "—"}</code>
                        <span className={p.outcome === "success" ? "text-emerald-300" : "text-amber-300"}>{p.outcome || "—"}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {detail.active_sessions?.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-muted-foreground mb-1">Active sessions</p>
                  <ul className="space-y-1 text-xs">
                    {detail.active_sessions.map((s) => (
                      <li key={s.session_id} className="flex items-center gap-2">
                        <code className="text-muted-foreground">{s.session_id.slice(-8)}</code>
                        <span>issued {s.issued_at ? new Date(s.issued_at).toLocaleString() : "—"}</span>
                        {s.ip && <code>{s.ip}</code>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>

            <AdminActionsPanel
              userId={detail.id}
              userEmail={detail.email}
              userStatus={detail.status}
              permissionTier={detail.permission_tier}
              refresh={() => { onRefresh?.(); onRowsRefresh?.(); }}
            />

            <UserExtensionsSection detail={detail} />

            <AdminActionHistorySection userId={detail.id} />
          </div>
        )}
      </div>
    </div>
  );
}

/* Iter 215 — Per-user audit trail of admin actions. Only consumed by the drawer. */
function AdminActionHistorySection({ userId }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/admin/platform/users/${userId}/admin-actions`);
        if (!cancelled) setRows(data.actions || []);
      } catch {
        // non-fatal
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [userId]);

  return (
    <section className="space-y-2" data-testid="user-action-history">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Action History</h4>
      {loading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-xs text-muted-foreground italic">No admin actions on this user yet.</p>
      ) : (
        <div className="rounded border border-border max-h-[260px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-secondary/40 sticky top-0">
              <tr className="text-left">
                <th className="px-2 py-1">When</th>
                <th className="px-2 py-1">Action</th>
                <th className="px-2 py-1">By</th>
                <th className="px-2 py-1">Reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: any) => (
                <tr key={r.id} className={`border-t border-border/40 ${r.mocked ? "opacity-70" : ""}`}>
                  <td className="px-2 py-1 whitespace-nowrap text-muted-foreground">
                    {r.ts ? new Date(r.ts).toLocaleString() : "—"}
                  </td>
                  <td className="px-2 py-1 font-mono">
                    {r.action}
                    {r.mocked && <span className="ml-1 text-[10px] text-amber-300">MOCKED</span>}
                  </td>
                  <td className="px-2 py-1 truncate max-w-[160px]" title={r.admin_email}>{r.admin_email || "—"}</td>
                  <td className="px-2 py-1 italic text-foreground/80 max-w-[260px] truncate" title={r.reason || ""}>
                    {r.reason || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
