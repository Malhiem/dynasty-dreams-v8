// @ts-nocheck
/**
 * Iter 210/211 — Critical Alert Banner with Acknowledge button.
 */
import { useEffect, useState } from "react";
import { useSocket } from "@/hooks/use-socket";
import { useAuth } from "@/contexts/AuthContext";
import { AlertTriangle, Activity, BellOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import api from "@/lib/api";

interface AlertItem {
  id: string;
  severity: "critical" | "warning";
  title: string;
  detail: string;
  since: string;
}

export default function CriticalAlertBanner() {
  const { user } = useAuth();
  const [alerts, setAlerts] = useState<AlertItem[]>([]);

  useEffect(() => {
    if (user?.role !== "admin") return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/admin/platform/alerts/active");
        if (!cancelled) setAlerts(data?.alerts || []);
      } catch { /* noop */ }
    })();
    return () => { cancelled = true; };
  }, [user?.role]);

  useSocket(
    user?.role === "admin" ? "platform_admins" : null,
    {
      critical_alerts: (payload: any) => setAlerts(payload?.alerts || []),
    },
    user?.id,
  );

  if (user?.role !== "admin" || alerts.length === 0) return null;

  const acknowledge = async (id: string) => {
    try {
      await api.post(`/admin/platform/alerts/${id}/acknowledge`, { duration_minutes: 60 });
      toast.success("Alert silenced for 60 minutes");
      setAlerts((prev) => prev.filter((a) => a.id !== id));
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to acknowledge");
    }
  };

  const renderRow = (a: AlertItem, isCritical: boolean) => {
    const Icon = isCritical ? AlertTriangle : Activity;
    const boxClass = isCritical
      ? "border-rose-500/60 bg-rose-950/40 text-rose-100"
      : "border-amber-500/60 bg-amber-950/30 text-amber-100";
    const iconClass = isCritical ? "text-rose-300 animate-pulse" : "text-amber-300";
    const ackClass = isCritical
      ? "text-rose-200 hover:bg-rose-500/20"
      : "text-amber-200 hover:bg-amber-500/20";
    const tag = isCritical ? "text-rose-300" : "text-amber-300";
    return (
      <div
        key={a.id}
        className={`rounded-lg border p-3 flex items-start gap-3 ${boxClass}`}
        data-testid={`alert-${isCritical ? "critical" : "warning"}-${a.id}`}
      >
        <Icon className={`h-5 w-5 mt-0.5 shrink-0 ${iconClass}`} />
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm">{a.title}</div>
          <div className="text-xs opacity-80 mt-0.5">{a.detail}</div>
        </div>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => acknowledge(a.id)}
          className={`shrink-0 h-7 px-2 ${ackClass}`}
          data-testid={`alert-ack-${a.id}`}
          title="Silence this alert for 60 minutes"
        >
          <BellOff className="h-3.5 w-3.5 mr-1" /> Acknowledge
        </Button>
        <span className={`text-[10px] uppercase tracking-wider shrink-0 self-center ${tag}`}>
          {isCritical ? "critical" : "warning"}
        </span>
      </div>
    );
  };

  return (
    <div className="space-y-2" data-testid="critical-alerts">
      {alerts.filter((a) => a.severity === "critical").map((a) => renderRow(a, true))}
      {alerts.filter((a) => a.severity === "warning").map((a) => renderRow(a, false))}
    </div>
  );
}
