// @ts-nocheck
/**
 * Iter 155 — TankMonitorTab + RosterMonitorTab extracted from CommissionerSettings.tsx.
 *
 * Both tabs are thin wrappers around their existing self-contained inner
 * tables (`TankMonitorTable`, `RosterMonitorTable`), but lifting the wrapper
 * Cards out of the giant parent file is part of the per-tab refactor.
 */
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AlertTriangle, ClipboardCheck } from "lucide-react";

interface TankMonitorTabProps {
  TankMonitorTable: React.ComponentType<any>;
}
export function TankMonitorTab({ TankMonitorTable }: TankMonitorTabProps) {
  return (
    <Card className="bg-card border-border" data-testid="commissioner-tank-monitor-tab">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-yellow-500" />
          Tanking Analysis
        </CardTitle>
        <CardDescription>
          Compare team scoring across roster sections. A high total/starting ratio may indicate a team is benching strong players to lose intentionally.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <TankMonitorTable />
      </CardContent>
    </Card>
  );
}

interface RosterMonitorTabProps {
  RosterMonitorTable: React.ComponentType<any>;
  onAuditLog: (entry: any) => void;
}
export function RosterMonitorTab({ RosterMonitorTable, onAuditLog }: RosterMonitorTabProps) {
  return (
    <Card className="bg-card border-border" data-testid="commissioner-roster-monitor-tab">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ClipboardCheck className="h-5 w-5 text-primary" />
          Roster Monitor
        </CardTitle>
        <CardDescription>
          Review all teams for roster compliance. Red flags indicate teams over the roster limit. Yellow flags indicate eligibility concerns or inactive starters.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <RosterMonitorTable onAuditLog={onAuditLog} />
      </CardContent>
    </Card>
  );
}
