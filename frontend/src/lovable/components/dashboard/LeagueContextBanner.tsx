// @ts-nocheck
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowRight, Database } from "lucide-react";

/**
 * Tiny "this page is now live" banner. Shows:
 *   - which league is active (with switcher if user has >1)
 *   - real-time count + stat tied to the page context
 *   - link to the most relevant data-driven page we already ship
 *
 * Used atop the ported Lovable pages while their internals still use seeded
 * sample data — gives a quick entry-point into the real backend values.
 */
export default function LeagueContextBanner({
  title,
  kpiLabel,
  kpiValue,
  primaryHref,
  primaryLabel,
}: any) {
  const { league, myLeagues, leagueId, switchLeague } = useActiveLeague();
  if (!league) return null;

  return (
    <div
      data-testid="league-context-banner"
      className="surface p-4 mb-6 border border-white/10 flex items-center justify-between gap-4 flex-wrap"
    >
      <div className="flex items-center gap-3 min-w-[200px]">
        <Database size={16} className="text-[#00D2FF]" />
        <div>
          <div className="text-[10px] uppercase text-[#52525B] tracking-wider">{title || 'Active League'}</div>
          <div className="text-white text-sm font-semibold">{league.name}</div>
        </div>
      </div>

      {kpiLabel && (
        <div>
          <div className="text-[10px] uppercase text-[#52525B]">{kpiLabel}</div>
          <div className="text-lg font-bold text-white tabular-nums">{kpiValue}</div>
        </div>
      )}

      <div className="flex items-center gap-3 ml-auto flex-wrap">
        {myLeagues?.length > 1 && (
          <Select value={leagueId || undefined} onValueChange={switchLeague}>
            <SelectTrigger className="w-[220px] h-8 text-xs" data-testid="league-context-switcher">
              <SelectValue placeholder="Switch league" />
            </SelectTrigger>
            <SelectContent>
              {myLeagues.map((l: any) => (
                <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {primaryHref && (
          <Link
            to={primaryHref}
            data-testid="league-context-cta"
            className="text-[#00D2FF] text-xs font-semibold flex items-center gap-1 hover:gap-2 transition-all"
          >
            {primaryLabel || 'View live data'} <ArrowRight size={12} />
          </Link>
        )}
      </div>
    </div>
  );
}
