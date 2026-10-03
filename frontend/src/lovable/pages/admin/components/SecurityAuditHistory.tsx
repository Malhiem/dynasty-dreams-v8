// Iter 230n — Security audit history widget.
//
// Renders the compliance-friendly cadence of security audits +
// remediation passes (audit-2026-02 → iter 230L → iter 230m → …)
// stored in `db.security_audits`. Sits above the SECURITY.md doc
// inside the admin "Security" tab. Used for:
//   • Showing reviewers that audits happen + are remediated promptly.
//   • Linking each finding (SEC-001, P3a, …) to the iteration that
//     closed it so anyone can `git log` the exact change.
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { History, ShieldCheck, ShieldAlert, ShieldQuestion, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type Finding = {
  id: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
  status: "open" | "in_progress" | "fixed";
  title: string;
  remediated_in?: string | null;
};

type Audit = {
  iteration: string;
  audited_at: string;
  auditor?: string;
  scope?: string;
  verdict?: string;
  findings?: Finding[];
  regression_tests?: string[];
};

type Resp = { audits: Audit[]; totals: { open: number; in_progress: number; fixed: number } };

const SEV_STYLES: Record<Finding["severity"], string> = {
  CRITICAL: "bg-rose-500/20 text-rose-200 border-rose-500/40",
  HIGH:     "bg-orange-500/20 text-orange-200 border-orange-500/40",
  MEDIUM:   "bg-amber-500/20 text-amber-200 border-amber-500/40",
  LOW:      "bg-sky-500/20 text-sky-200 border-sky-500/40",
  INFO:     "bg-zinc-500/20 text-zinc-200 border-zinc-500/40",
};

const STATUS_STYLES: Record<Finding["status"], string> = {
  fixed:        "bg-emerald-500/20 text-emerald-200 border-emerald-500/40",
  in_progress:  "bg-amber-500/20 text-amber-200 border-amber-500/40",
  open:         "bg-rose-500/20 text-rose-200 border-rose-500/40",
};

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric", month: "short", day: "numeric",
    });
  } catch { return iso; }
}

export default function SecurityAuditHistory() {
  const [resp, setResp] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api.get<Resp>("/admin/platform/security-audits")
      .then(({ data }) => {
        if (!cancelled) setResp(data);
      })
      .catch((e) => {
        if (cancelled) return;
        toast.error(e?.response?.data?.detail || "Failed to load audit history");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, []);

  return (
    <Card className="bg-card border-border" data-testid="security-audit-history">
      <CardHeader>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <History className="h-6 w-6 text-cyan-400" />
            <div>
              <CardTitle className="flex items-center gap-2">
                Audit History
                <Badge variant="outline" className="text-[10px] uppercase tracking-wider">
                  Compliance
                </Badge>
              </CardTitle>
              <CardDescription>
                Cadence of security audits + remediation iterations. Each finding
                links back to the iter that closed it so reviewers can trace the
                fix in <code className="rounded bg-secondary/60 px-1 text-[11px]">git log</code>.
              </CardDescription>
            </div>
          </div>
          {resp?.totals && (
            <div className="flex items-center gap-2 shrink-0">
              <TotalPill label="Fixed"      value={resp.totals.fixed}       tone="emerald" icon={ShieldCheck} />
              <TotalPill label="In progress" value={resp.totals.in_progress} tone="amber"   icon={ShieldQuestion} />
              <TotalPill label="Open"       value={resp.totals.open}        tone="rose"    icon={ShieldAlert} />
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-3">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading audit history…
          </div>
        )}
        {!loading && resp && resp.audits.length === 0 && (
          <p className="text-sm text-muted-foreground py-3" data-testid="audit-history-empty">
            No audits recorded yet.
          </p>
        )}
        {!loading && resp && resp.audits.length > 0 && (
          <ol className="relative border-l border-border/60 ml-3 space-y-5">
            {resp.audits.map((a) => (
              <li
                key={a.iteration}
                className="ml-4"
                data-testid={`audit-row-${a.iteration}`}
              >
                <span className="absolute -left-1.5 mt-1 h-3 w-3 rounded-full bg-cyan-400 ring-4 ring-cyan-400/20" />
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="font-mono text-sm font-semibold text-foreground">
                    {a.iteration}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    · {fmtDate(a.audited_at)}
                  </span>
                  {a.auditor && (
                    <span className="text-[11px] text-muted-foreground/70">
                      by {a.auditor}
                    </span>
                  )}
                </div>
                {a.scope && (
                  <p className="text-xs text-muted-foreground mt-0.5">{a.scope}</p>
                )}
                {a.verdict && (
                  <p className="text-xs text-emerald-300/90 italic mt-0.5">
                    {a.verdict}
                  </p>
                )}
                {(a.findings || []).length > 0 && (
                  <ul className="mt-2 space-y-1.5">
                    {(a.findings || []).map((f, idx) => (
                      <li
                        key={`${a.iteration}-${f.id}-${idx}`}
                        data-testid={`finding-${a.iteration}-${f.id}`}
                        className="rounded-md border border-border/60 bg-secondary/20 px-2.5 py-1.5 flex items-center gap-2 flex-wrap"
                      >
                        <span className="font-mono text-[11px] font-semibold text-cyan-300 shrink-0">
                          {f.id}
                        </span>
                        <Badge variant="outline" className={`text-[9px] uppercase tracking-wider ${SEV_STYLES[f.severity] || SEV_STYLES.INFO}`}>
                          {f.severity}
                        </Badge>
                        <Badge variant="outline" className={`text-[9px] uppercase tracking-wider ${STATUS_STYLES[f.status] || STATUS_STYLES.open}`}>
                          {f.status.replace("_", " ")}
                        </Badge>
                        <span className="text-xs text-muted-foreground flex-1 min-w-0">{f.title}</span>
                        {f.remediated_in && (
                          <span className="text-[10px] text-muted-foreground/70 font-mono shrink-0">
                            → iter {f.remediated_in}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                {(a.regression_tests || []).length > 0 && (
                  <p className="mt-1.5 text-[10px] text-muted-foreground/70 font-mono">
                    Tests: {(a.regression_tests || []).join(" · ")}
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

function TotalPill({
  label, value, tone, icon: Icon,
}: {
  label: string; value: number;
  tone: "emerald" | "amber" | "rose";
  icon: React.ComponentType<{ className?: string }>;
}) {
  const cls =
    tone === "emerald" ? "bg-emerald-500/15 text-emerald-200 border-emerald-500/30" :
    tone === "amber"   ? "bg-amber-500/15 text-amber-200 border-amber-500/30" :
                          "bg-rose-500/15 text-rose-200 border-rose-500/30";
  return (
    <div
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs ${cls}`}
      data-testid={`audit-total-${tone}`}
    >
      <Icon className="h-3.5 w-3.5" />
      <span className="font-semibold tabular-nums">{value}</span>
      <span className="text-[10px] uppercase tracking-wider opacity-80">{label}</span>
    </div>
  );
}
