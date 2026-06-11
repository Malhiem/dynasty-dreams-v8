/**
 * Iter 158 — SalaryCapContractsTab extracted from CommissionerSettings.tsx.
 *
 * Thin presentational wrapper that renders the three cap/contract cards
 * for the active league, with a friendly empty state when none is selected.
 */
import { Card, CardContent } from "@/components/ui/card";
import { SalaryCapCard, SalaryRetentionCard, ContractBuyoutsCard } from "@/lovable/pages/commissioner/RulesScheduleTab";

interface SalaryCapContractsTabProps {
  activeLeague: any;
  reloadLeague: () => void;
}

export default function SalaryCapContractsTab({ activeLeague, reloadLeague }: SalaryCapContractsTabProps) {
  if (!activeLeague?.id) {
    return (
      <Card className="bg-card border-border" data-testid="commissioner-salary-cap-tab">
        <CardContent className="py-6 text-sm text-muted-foreground italic">
          Select a league to edit salary cap &amp; contract settings.
        </CardContent>
      </Card>
    );
  }
  return (
    <div className="space-y-6" data-testid="commissioner-salary-cap-tab">
      <SalaryCapCard league={activeLeague} reloadLeague={reloadLeague} />
      <SalaryRetentionCard league={activeLeague} reloadLeague={reloadLeague} />
      <ContractBuyoutsCard league={activeLeague} reloadLeague={reloadLeague} />
    </div>
  );
}
