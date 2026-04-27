// @ts-nocheck
import { useNavigate } from "react-router-dom";
import { ArrowUpDown, ChevronDown, ChevronUp, Plus, Send, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Slider } from "@/components/ui/slider";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { TradeConditionsEditor } from "./TradeConditionsEditor";
import { PickUpgradeEditor } from "./PickUpgradeEditor";
import { useTradeBuilder } from "@/lovable/state/TradeBuilderContext";
import { useActiveLeague } from "@/hooks/use-active-league";

/**
 * GlobalTradeBuilder
 *
 * A persistent floating panel mounted at AppLayout level. Reads state from
 * the TradeBuilderContext so the panel survives route changes — clicking
 * a partner team's name navigates the user to that team's roster while
 * keeping the trade in progress visible.
 */

const formatSalary = (salary) => `$${((salary || 0) / 1_000_000).toFixed(1)}M`;

function PartnerSection({ partner, isProposer, ownAssets, ownPicks, partners, onNavigate, builder }) {
  const others = partners.filter((p) => p.id !== partner.id);
  return (
    <div
      className="rounded-lg border border-border bg-card/40 overflow-hidden"
      data-testid={`tb-partner-${partner.id}`}
    >
      <div className="flex items-center gap-2 px-3 py-2 bg-secondary/30 border-b border-border/50">
        <button
          type="button"
          onClick={() => onNavigate(partner.id)}
          className="text-sm font-bold text-primary hover:underline truncate max-w-[180px]"
          data-testid={`tb-partner-link-${partner.id}`}
          title="Open team roster (trade stays open)"
        >
          {partner.name}
        </button>
        {isProposer && (
          <Badge className="text-[9px] bg-primary/20 text-primary">PROPOSER</Badge>
        )}
        <span className="text-[10px] text-muted-foreground ml-auto">
          {ownAssets.length + ownPicks.length} sending
        </span>
        {!isProposer && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground hover:text-destructive"
            onClick={() => builder.removePartner(partner.id)}
            data-testid={`tb-remove-partner-${partner.id}`}
            title="Remove team from trade"
          >
            <X className="h-3 w-3" />
          </Button>
        )}
      </div>

      <div className="p-2 space-y-2">
        {ownAssets.length === 0 && ownPicks.length === 0 ? (
          <p className="text-[11px] text-muted-foreground italic px-1 py-1">
            No assets from this team yet — open the team roster and click trade icons to add.
          </p>
        ) : (
          <>
            {ownAssets.map((a) => (
              <div
                key={a.player.id}
                className="rounded border border-border/50 bg-background/40 p-2 space-y-1.5"
                data-testid={`tb-asset-${a.player.id}`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold flex-1 truncate">{a.player.name}</span>
                  <span className="text-[9px] text-muted-foreground">{a.player.position}</span>
                  <Button
                    variant="ghost" size="icon"
                    className="h-5 w-5 text-muted-foreground hover:text-destructive"
                    onClick={() => builder.removeAsset(a.player.id)}
                    data-testid={`tb-remove-asset-${a.player.id}`}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                </div>
                {/* Recipient routing: only when 3+ parties and there are 2+ choices */}
                {others.length > 1 && (
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-muted-foreground">to →</span>
                    <Select
                      value={a.toTeamId || ""}
                      onValueChange={(v) => builder.setAssetRecipient(a.player.id, v)}
                    >
                      <SelectTrigger
                        className="h-7 text-[11px] flex-1"
                        data-testid={`tb-asset-recipient-${a.player.id}`}
                      >
                        <SelectValue placeholder="Choose recipient" />
                      </SelectTrigger>
                      <SelectContent>
                        {others.map((o) => (
                          <SelectItem key={o.id} value={o.id}>{o.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                {others.length === 1 && (
                  <p className="text-[10px] text-muted-foreground">→ {others[0].name}</p>
                )}
                {/* Salary retention */}
                {a.player.contract && (
                  <div className="flex items-center gap-2 pt-1 border-t border-border/30">
                    <Checkbox
                      id={`tb-retain-${a.player.id}`}
                      checked={a.retainSalary}
                      onCheckedChange={() => builder.toggleRetain(a.player.id)}
                      className="h-3 w-3"
                    />
                    <label
                      htmlFor={`tb-retain-${a.player.id}`}
                      className="text-[10px] cursor-pointer text-muted-foreground"
                    >
                      Retain salary
                    </label>
                    {a.retainSalary && (
                      <div className="flex-1 flex items-center gap-2">
                        <Slider
                          value={[a.retainedPercentage]}
                          onValueChange={(v) => builder.updateRetention(a.player.id, v[0])}
                          max={50} step={5}
                          className="flex-1"
                        />
                        <span className="text-[10px] font-semibold text-destructive w-10 text-right">
                          {a.retainedPercentage}%
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
            {ownPicks.map((p) => (
              <div
                key={p.pick.id}
                className="flex items-center gap-2 rounded border border-border/50 bg-background/40 p-2"
                data-testid={`tb-pick-${p.pick.id}`}
              >
                <span className="text-xs font-semibold flex-1">{p.pick.year} Rd {p.pick.round}</span>
                {others.length > 1 ? (
                  <Select
                    value={p.toTeamId || ""}
                    onValueChange={(v) => builder.setPickRecipient(p.pick.id, v)}
                  >
                    <SelectTrigger className="h-7 text-[11px] w-32"
                      data-testid={`tb-pick-recipient-${p.pick.id}`}>
                      <SelectValue placeholder="to →" />
                    </SelectTrigger>
                    <SelectContent>
                      {others.map((o) => (
                        <SelectItem key={o.id} value={o.id}>{o.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <span className="text-[10px] text-muted-foreground">
                    {others[0] ? `→ ${others[0].name}` : ""}
                  </span>
                )}
                <Button
                  variant="ghost" size="icon"
                  className="h-5 w-5 text-muted-foreground hover:text-destructive"
                  onClick={() => builder.removePick(p.pick.id)}
                  data-testid={`tb-remove-pick-${p.pick.id}`}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

export default function GlobalTradeBuilder() {
  const builder = useTradeBuilder();
  const navigate = useNavigate();
  const { leagueTeams } = useActiveLeague();
  const [showAddPartner, setShowAddPartner] = useState(false);

  const partners = builder.partners;
  // Teams available to add (in current league, not already a partner) — must be
  // declared before any early return to keep hook order stable.
  const addable = useMemo(() => {
    const ids = new Set(partners.map((p) => p.id));
    return (leagueTeams || []).filter((t) => !ids.has(t.id));
  }, [leagueTeams, partners]);

  if (!builder.open) return null;

  const onNavigate = (teamId) => {
    navigate(`/team?team=${teamId}`);
  };

  const totalAssets = builder.assets.length + builder.picks.length;
  const isMulti = partners.length > 2;

  return (
    <div
      className="fixed bottom-4 right-4 z-50 w-[440px] max-h-[88vh] flex flex-col rounded-xl border border-border bg-card shadow-2xl shadow-primary/5 animate-in slide-in-from-bottom-4 duration-300"
      data-testid="global-trade-builder"
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-secondary/30 rounded-t-xl">
        <ArrowUpDown className="h-4 w-4 text-primary" />
        <h3 className="font-bold text-sm flex-1">
          Trade Builder
          {isMulti && (
            <Badge className="ml-2 text-[9px] bg-primary/20 text-primary align-middle">
              {partners.length}-TEAM
            </Badge>
          )}
        </h3>
        {totalAssets > 0 && (
          <Badge variant="outline" className="text-[10px] bg-primary/10 text-primary">
            {totalAssets} asset{totalAssets > 1 ? "s" : ""}
          </Badge>
        )}
        <Button
          variant="ghost" size="icon" className="h-7 w-7"
          onClick={() => builder.setCollapsed(!builder.collapsed)}
          data-testid="tb-toggle-collapse"
        >
          {builder.collapsed ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </Button>
        <Button
          variant="ghost" size="icon"
          className="h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={builder.closeBuilder}
          data-testid="tb-close"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {!builder.collapsed && (
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {/* Partner sections */}
          {partners.map((partner, idx) => {
            const ownAssets = builder.assets.filter((a) => a.player.ownerTeamId === partner.id);
            const ownPicks = builder.picks.filter((p) => p.pick.ownerTeamId === partner.id);
            return (
              <PartnerSection
                key={partner.id}
                partner={partner}
                isProposer={idx === 0}
                ownAssets={ownAssets}
                ownPicks={ownPicks}
                partners={partners}
                onNavigate={onNavigate}
                builder={builder}
              />
            );
          })}

          {/* Add Team button / selector */}
          {!showAddPartner ? (
            <Button
              variant="outline"
              size="sm"
              className="w-full text-xs"
              onClick={() => setShowAddPartner(true)}
              disabled={addable.length === 0}
              data-testid="tb-add-team-btn"
            >
              <Plus className="h-3.5 w-3.5 mr-1.5" />
              Add Team to Trade
            </Button>
          ) : (
            <div className="rounded-lg border border-dashed border-primary/40 bg-primary/5 p-2 space-y-2">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Choose team to add</p>
              <Select
                onValueChange={(teamId) => {
                  const t = (leagueTeams || []).find((x) => x.id === teamId);
                  if (t) {
                    builder.addPartner({
                      id: t.id, name: t.name,
                      logo_abbr: t.logo_abbr,
                      owner_id: t.owner_id, owner_name: t.owner_name,
                    });
                  }
                  setShowAddPartner(false);
                }}
              >
                <SelectTrigger className="h-8 text-xs" data-testid="tb-add-team-select">
                  <SelectValue placeholder="Select team..." />
                </SelectTrigger>
                <SelectContent>
                  {addable.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      <span className="flex items-center gap-2">
                        <span className="font-mono text-[10px] text-muted-foreground w-8">
                          {t.logo_abbr || t.name?.slice(0,3).toUpperCase()}
                        </span>
                        <span>{t.name}</span>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="ghost" size="sm" className="w-full text-[10px] h-7"
                onClick={() => setShowAddPartner(false)}
              >
                Cancel
              </Button>
            </div>
          )}

          {/* Optional message */}
          <div>
            <Textarea
              value={builder.message}
              onChange={(e) => builder.setMessage(e.target.value)}
              placeholder="Optional message to partners..."
              rows={2}
              className="text-xs resize-none"
              data-testid="tb-message"
            />
          </div>

          {/* Conditional triggers (existing component, expects window-globals) */}
          <div className="rounded-lg border border-border/50 bg-secondary/10 p-3">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-semibold">Conditional Triggers</h4>
              <div className="flex items-center gap-1">
                <Button size="sm" variant="outline" className="text-[10px] h-6"
                  onClick={() => window.__addTradeCondition?.("player")}
                  data-testid="tb-add-player-condition">
                  + Player stat
                </Button>
                <Button size="sm" variant="outline" className="text-[10px] h-6"
                  onClick={() => window.__addTradeCondition?.("team")}
                  data-testid="tb-add-team-condition">
                  + Team result
                </Button>
                <Button size="sm" variant="outline" className="text-[10px] h-6"
                  onClick={() => window.__addPickUpgrade?.()}
                  data-testid="add-pick-upgrade-btn">
                  + Pick upgrade
                </Button>
              </div>
            </div>
            <p className="text-[10px] text-muted-foreground mb-2">
              Trade executes only when all conditions are satisfied. Pick upgrades rewrite a draft pick already in the trade when its trigger fires (e.g., "if my team wins the championship, the 2nd round pick becomes a 1st").
            </p>
            <TradeConditionsEditor />
            <div className="mt-2">
              <PickUpgradeEditor />
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      {!builder.collapsed && (
        <div className="flex items-center justify-between gap-2 px-4 py-3 border-t border-border bg-secondary/20 rounded-b-xl">
          <Button variant="outline" size="sm" className="text-xs"
            onClick={builder.closeBuilder} data-testid="tb-cancel">
            Cancel
          </Button>
          <Button
            size="sm"
            className="text-xs bg-primary hover:bg-primary/90"
            disabled={partners.length < 2 || totalAssets === 0}
            onClick={builder.sendProposal}
            data-testid="tb-send-proposal"
          >
            <Send className="h-3.5 w-3.5 mr-1.5" />
            Send Proposal
          </Button>
        </div>
      )}
    </div>
  );
}
