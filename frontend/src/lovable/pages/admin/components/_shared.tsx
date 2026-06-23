// @ts-nocheck
/* Small layout primitives shared across the admin sub-panels. */
import React from "react";

export function DetailGrid({ children }) {
  return <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">{children}</div>;
}

export function DetailRow({ k, v }) {
  return (
    <div className="flex items-baseline gap-2 text-sm">
      <span className="text-xs text-muted-foreground min-w-[100px]">{k}</span>
      <span className="flex-1 break-all">{v}</span>
    </div>
  );
}

export function StatusPill({ status }) {
  const palette: Record<string, string> = {
    active: "border-emerald-500/40 text-emerald-300",
    suspended: "border-amber-500/40 text-amber-300",
    banned: "border-rose-500/40 text-rose-300",
    deactivated: "border-muted text-muted-foreground",
    pending_verification: "border-sky-500/40 text-sky-300",
  };
  const cls = palette[status] || "border-border text-muted-foreground";
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${cls}`} data-testid={`user-status-${status}`}>
      {status?.replace(/_/g, " ")}
    </span>
  );
}

export function SyncStat({ label, value }: { label: string; value: any }) {
  return (
    <div className="rounded-lg border border-border bg-muted/20 p-3">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold">{value ?? "—"}</div>
    </div>
  );
}
