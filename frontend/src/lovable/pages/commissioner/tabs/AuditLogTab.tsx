// @ts-nocheck
/**
 * Iter 154 — Audit Log tab extracted from CommissionerSettings.tsx.
 *
 * Renders the full audit-log table with the "Filter by" dropdown.
 * All state (auditLog + auditFilterCategory) is owned by the parent so
 * other tabs can still push entries via the existing `addAuditEntry`
 * helper. This file is a pure presentation layer.
 *
 * NOTE: The first tab extracted from the monolithic CommissionerSettings.tsx
 * file (~2,630 lines) as a refactor proof-of-concept. The same pattern can
 * be applied to the remaining 11 tabs in follow-up iterations.
 */
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Table, TableHeader, TableRow, TableHead, TableBody, TableCell,
} from "@/components/ui/table";
import {
  Tooltip, TooltipContent, TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  ScrollText, Wrench, ArrowRightLeft, X, Plus, Sliders, Target, FileText,
} from "lucide-react";

export interface AuditLogEntry {
  id: string;
  timestamp: Date;
  action:
    | "auto-fix"
    | "roster-move"
    | "player-drop"
    | "player-add"
    | "setting-change"
    | "trade-override"
    | "scoring-update"
    | "draft-change";
  category: "Roster" | "League Settings" | "Scoring" | "Draft" | "Trade";
  description: string;
  team?: string;
  performedBy: string;
}

interface AuditLogTabProps {
  auditLog: AuditLogEntry[];
  auditFilterCategory: string;
  setAuditFilterCategory: (v: string) => void;
}

function formatTimestamp(date: Date) {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

const ACTION_ICON: Record<string, JSX.Element> = {
  "auto-fix":        <Wrench className="h-3.5 w-3.5 text-primary" />,
  "roster-move":     <ArrowRightLeft className="h-3.5 w-3.5 text-blue-400" />,
  "player-drop":     <X className="h-3.5 w-3.5 text-destructive" />,
  "player-add":      <Plus className="h-3.5 w-3.5 text-green-400" />,
  "setting-change":  <Sliders className="h-3.5 w-3.5 text-yellow-400" />,
  "trade-override":  <ArrowRightLeft className="h-3.5 w-3.5 text-orange-400" />,
  "scoring-update":  <Target className="h-3.5 w-3.5 text-purple-400" />,
  "draft-change":    <FileText className="h-3.5 w-3.5 text-cyan-400" />,
};

const CATEGORY_COLOR: Record<string, string> = {
  "Roster":          "bg-blue-500/20 text-blue-400 border-blue-500/30",
  "League Settings": "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  "Scoring":         "bg-purple-500/20 text-purple-400 border-purple-500/30",
  "Draft":           "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  "Trade":           "bg-orange-500/20 text-orange-400 border-orange-500/30",
};

export default function AuditLogTab({
  auditLog,
  auditFilterCategory,
  setAuditFilterCategory,
}: AuditLogTabProps) {
  const filtered = auditLog.filter(
    (e) => auditFilterCategory === "all" || e.category === auditFilterCategory,
  );
  return (
    <Card className="bg-card border-border" data-testid="commissioner-audit-log-tab">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ScrollText className="h-5 w-5 text-primary" />
          Audit Log
        </CardTitle>
        <CardDescription>
          Complete history of all commissioner and system actions. All changes are timestamped and categorized.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <Label className="text-sm whitespace-nowrap">Filter by</Label>
          <Select value={auditFilterCategory} onValueChange={setAuditFilterCategory}>
            <SelectTrigger
              className="w-[180px] h-9 bg-secondary border-border"
              data-testid="audit-log-filter"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Categories</SelectItem>
              <SelectItem value="Roster">Roster</SelectItem>
              <SelectItem value="League Settings">League Settings</SelectItem>
              <SelectItem value="Scoring">Scoring</SelectItem>
              <SelectItem value="Draft">Draft</SelectItem>
              <SelectItem value="Trade">Trade</SelectItem>
            </SelectContent>
          </Select>
          <span className="text-xs text-muted-foreground ml-auto" data-testid="audit-log-count">
            {filtered.length} entries
          </span>
        </div>

        <ScrollArea className="w-full">
          <Table>
            <TableHeader>
              <TableRow className="border-border">
                <TableHead className="text-muted-foreground w-[180px]">Timestamp</TableHead>
                <TableHead className="text-muted-foreground w-[110px]">Category</TableHead>
                <TableHead className="text-muted-foreground w-[130px]">Team</TableHead>
                <TableHead className="text-muted-foreground">Description</TableHead>
                <TableHead className="text-muted-foreground w-[150px]">Performed By</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((entry) => (
                <TableRow key={entry.id} className="border-border" data-testid={`audit-log-row-${entry.id}`}>
                  <TableCell className="text-xs text-muted-foreground">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="cursor-help">{formatTimestamp(entry.timestamp)}</span>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p className="text-xs">{entry.timestamp.toLocaleString()}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-[10px] ${CATEGORY_COLOR[entry.category] || ""}`}>
                      {entry.category}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">
                    {entry.team || <span className="text-muted-foreground/50">—</span>}
                  </TableCell>
                  <TableCell className="text-sm">
                    <span className="inline-flex items-center gap-1.5">
                      {ACTION_ICON[entry.action]}
                      {entry.description}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{entry.performedBy}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
