// @ts-nocheck
/**
 * Iter 208 — Trust Score badge.
 *
 * Compact pill showing a user's computed trust score (0-100) + tier
 * (trusted / neutral / watch / risky). Fetched from `/users/{id}/
 * trust-score`. Admin requesters automatically receive a breakdown
 * payload; hover the badge to view it.
 */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { ShieldCheck, ShieldQuestion, ShieldAlert, ShieldX } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const TIER_STYLES: Record<string, { color: string; Icon: any; label: string }> = {
  trusted: { color: "border-emerald-500/40 text-emerald-300", Icon: ShieldCheck, label: "Trusted" },
  neutral: { color: "border-sky-500/40 text-sky-300", Icon: ShieldQuestion, label: "Neutral" },
  watch: { color: "border-amber-500/40 text-amber-300", Icon: ShieldAlert, label: "Watch" },
  risky: { color: "border-rose-500/40 text-rose-300", Icon: ShieldX, label: "Risky" },
};

export default function TrustScoreBadge({ userId }: { userId: string }) {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/users/${userId}/trust-score`);
        if (!cancelled) setData(data);
      } catch { /* noop */ }
    })();
    return () => { cancelled = true; };
  }, [userId]);

  if (!data) return null;
  const style = TIER_STYLES[data.tier] || TIER_STYLES.neutral;
  const Icon = style.Icon;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border ${style.color} cursor-help`}
            data-testid={`trust-score-${userId}`}
          >
            <Icon className="h-3 w-3" />
            <span>{data.score}</span>
            <span className="uppercase tracking-wider">{data.tier}</span>
          </span>
        </TooltipTrigger>
        {data.breakdown && (
          <TooltipContent className="max-w-xs">
            <div className="text-xs space-y-0.5">
              <div className="font-semibold mb-1">Trust score breakdown</div>
              <div>Account age: {data.breakdown.account_age_days ?? 0}d (+{data.breakdown.account_age_bonus ?? 0})</div>
              <div>Reports against: {data.breakdown.reports_resolved_against} (-{data.breakdown.reports_resolved_against * 10})</div>
              <div>Mod-queue hits: {data.breakdown.mod_queue_hits} (-{data.breakdown.mod_queue_hits * 5})</div>
              <div>IP aliases: {data.breakdown.ip_aliases} (-{data.breakdown.ip_aliases * 15})</div>
              <div>Device aliases: {data.breakdown.device_aliases} (-{data.breakdown.device_aliases * 15})</div>
              <div>Chargebacks: {data.breakdown.chargeback_flags} (-{data.breakdown.chargeback_flags * 25})</div>
              <div className="capitalize">Status: {data.breakdown.status}</div>
            </div>
          </TooltipContent>
        )}
      </Tooltip>
    </TooltipProvider>
  );
}
