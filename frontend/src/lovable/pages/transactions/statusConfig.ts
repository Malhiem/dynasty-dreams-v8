// @ts-nocheck
// Iter 232L (refactor) — Trade status → badge config used by TradeCard.
// Extracted so status glyphs + colours have a single source of truth.
import { Clock, CheckCircle2, XCircle, GitBranch, MinusCircle } from "lucide-react";

export const statusConfig: Record<string, { label: string; icon: any; variant: "outline" | "destructive"; className: string }> = {
  pending: { label: "Pending Review", icon: Clock, variant: "outline", className: "border-amber-500/50 text-amber-400" },
  accepted: { label: "Accepted", icon: CheckCircle2, variant: "outline", className: "border-emerald-500/50 text-emerald-400" },
  vetoed: { label: "Vetoed", icon: XCircle, variant: "destructive", className: "" },
  processed: { label: "Processed", icon: CheckCircle2, variant: "outline", className: "border-muted-foreground/50 text-muted-foreground" },
  // Iter 168 — backend canonical statuses returned by /api/leagues/{id}/trades
  executed: { label: "Executed", icon: CheckCircle2, variant: "outline", className: "border-emerald-500/50 text-emerald-400" },
  voting: { label: "Voting", icon: Clock, variant: "outline", className: "border-amber-500/50 text-amber-400" },
  conditional: { label: "Conditional", icon: GitBranch, variant: "outline", className: "border-sky-500/50 text-sky-400" },
  withdrawn: { label: "Withdrawn", icon: MinusCircle, variant: "outline", className: "border-muted-foreground/50 text-muted-foreground" },
  rejected: { label: "Rejected", icon: XCircle, variant: "destructive", className: "" },
};
