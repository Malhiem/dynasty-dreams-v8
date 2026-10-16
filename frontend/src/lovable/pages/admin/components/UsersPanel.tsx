// @ts-nocheck
/**
 * UsersPanel — Iter 214 admin user directory: paginated table + filters
 * + per-user drilldown via UserDetailDrawer.
 * Extracted from AdminDashboard.tsx during Iter 223 refactor.
 */
import { useCallback, useEffect, useState, useRef } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusPill } from "./_shared";
import { UserDetailDrawer } from "./UserDetailDrawer";

export function UsersPanel() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [skip, setSkip] = useState(0);
  const limit = 25;
  const [selected, setSelected] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [listError, setListError] = useState("");

  const listRequest = useRef(0);
  const detailRequest = useRef(0);

  const load = useCallback(async () => {
    const request = ++listRequest.current;
    setLoading(true); setListError("");
    try {
      const q = new URLSearchParams();
      if (query.trim()) q.set("q", query.trim());
      if (statusFilter) q.set("status", statusFilter);
      q.set("limit", String(limit));
      q.set("skip", String(skip));
      const { data } = await api.get(`/admin/platform/users?${q.toString()}`);
      if (request !== listRequest.current) return;
      setRows(data.users || []);
      setTotal(data.total || 0);
    } catch (e: any) {
      if (request === listRequest.current) {
        setListError("Could not load users. Retry to refresh this list.");
        if ([401, 403].includes(e?.response?.status)) { setRows([]); setTotal(0); detailRequest.current++; setSelected(null); setSelectedDetail(null); }
      }
    } finally {
      if (request === listRequest.current) setLoading(false);
    }
  }, [query, statusFilter, skip]);

  useEffect(() => { load(); return () => { listRequest.current++; }; }, [load]);
  useEffect(() => () => { detailRequest.current++; }, []);

  const openDetail = async (userId) => {
    const request = ++detailRequest.current;
    setSelected(userId);
    setSelectedDetail(null);
    setDetailLoading(true); setDetailError("");
    try {
      const { data } = await api.get(`/admin/platform/users/${userId}`);
      if (request === detailRequest.current) setSelectedDetail(data);
    } catch (e: any) {
      if (request === detailRequest.current) setDetailError("Could not load user details. Retry to refresh this account.");
    } finally {
      if (request === detailRequest.current) setDetailLoading(false);
    }
  };

  const closeDetail = () => { detailRequest.current++; setSelected(null); setSelectedDetail(null); };

  return (
    <section className="space-y-4" data-testid="users-section">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Users <span className="text-foreground/70">· {total.toLocaleString()} total</span>
        </h2>
        <div className="flex items-center gap-2 flex-wrap">
          <Input
            placeholder="Search email or username"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSkip(0); }}
            className="h-8 w-[240px] text-xs"
            data-testid="users-search-input"
          />
          <Select
            value={statusFilter || "_all"}
            onValueChange={(v) => { setStatusFilter(v === "_all" ? "" : v); setSkip(0); }}
          >
            <SelectTrigger className="h-8 w-[160px] text-xs" data-testid="users-status-filter">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_all">All statuses</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="suspended">Suspended</SelectItem>
              <SelectItem value="banned">Banned</SelectItem>
              <SelectItem value="deactivated">Deactivated</SelectItem>
              <SelectItem value="pending_verification">Pending verification</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {listError && <div role="alert"><p>{listError}</p><Button onClick={load} disabled={loading}>Retry users</Button></div>}
      <div className="rounded-lg border border-border overflow-x-auto">
        <table className="w-full text-sm" data-testid="users-table">
          <thead className="bg-secondary/40">
            <tr className="text-left">
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">User</th>
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">Email</th>
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">Role</th>
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">Status</th>
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">Created</th>
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">Last login</th>
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">2FA</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-xs text-muted-foreground">Loading…</td></tr>
            )}
            {!loading && !listError && rows.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-xs text-muted-foreground">No users match</td></tr>
            )}
            {!loading && rows.map((u: any) => (
              <tr
                key={u.id}
                className="border-t border-border/60 hover:bg-secondary/30 cursor-pointer transition-colors"
                onClick={() => openDetail(u.id)}
                data-testid={`users-row-${u.id}`}
              >
                <td className="px-3 py-2 font-medium text-primary hover:underline" data-testid={`users-view-${u.id}`}>
                  <button type="button" className="rounded text-left underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                    aria-label={`View details for ${u.username || u.name || u.email}`}
                    onClick={(event) => { event.stopPropagation(); openDetail(u.id); }}>
                    {u.username || u.name || "—"}
                  </button>
                </td>
                <td className="px-3 py-2 text-muted-foreground max-w-[240px] truncate" title={u.email}>
                  {u.email}
                  {u.email_verified && <span className="ml-1 text-[10px] text-emerald-300">✓</span>}
                </td>
                <td className="px-3 py-2">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                    u.role === "admin" ? "border-rose-500/40 text-rose-300" : "border-border text-muted-foreground"
                  }`}>{u.role}</span>
                </td>
                <td className="px-3 py-2">
                  <StatusPill status={u.status} />
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                  {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "—"}
                </td>
                <td className="px-3 py-2 text-xs">
                  {u.two_factor_enabled ? <span className="text-emerald-300">ON</span> : <span className="text-muted-foreground">off</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Showing {rows.length ? skip + 1 : 0}–{skip + rows.length} of {total.toLocaleString()}</span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={skip === 0 || loading}
            onClick={() => setSkip(Math.max(0, skip - limit))}
            data-testid="users-prev-btn"
          >Prev</Button>
          <Button
            variant="outline"
            size="sm"
            disabled={skip + limit >= total || loading}
            onClick={() => setSkip(skip + limit)}
            data-testid="users-next-btn"
          >Next</Button>
        </div>
      </div>

      {selected && (
        <UserDetailDrawer
          loading={detailLoading}
          error={detailError}
          detail={selectedDetail}
          onClose={closeDetail}
          onRefresh={() => openDetail(selected)}
          onRowsRefresh={load}
        />
      )}
    </section>
  );
}
