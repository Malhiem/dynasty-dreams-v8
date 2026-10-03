// @ts-nocheck
import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { DollarSign, CheckCircle2, AlertCircle, CreditCard, Users, UserMinus, Clock, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

const STORAGE_KEY = "dynasty-ice-league-payments";
const REFUND_STORAGE_KEY = "dynasty-ice-league-refunds";
const ADMIN_FEE = 75;
const CURRENT_USER_TEAM = "Arctic Wolves";
const IS_COMMISSIONER = true; // simulate admin view
const REFUND_DEADLINE_DAYS = 7;

interface TeamPayment {
  teamName: string;
  ownerName: string;
  paid: boolean;
  paidBy?: string;
  paidDate?: string;
}

interface RefundRequest {
  teamName: string;
  ownerName: string;
  status: "pending" | "refunded" | "held";
  requestedDate: string;
  deadlineDate: string;
  resolvedDate?: string;
}

const DEFAULT_PAYMENTS: TeamPayment[] = [
  { teamName: "Arctic Wolves", ownerName: "You", paid: false },
  { teamName: "Blizzard Kings", ownerName: "Mike Johnson", paid: false },
  { teamName: "Frost Giants", ownerName: "Sarah Chen", paid: true, paidBy: "Sarah Chen", paidDate: "2026-01-15" },
  { teamName: "Ice Phantoms", ownerName: "Jake Williams", paid: false },
  { teamName: "Glacier Bears", ownerName: "Tom Davis", paid: true, paidBy: "Tom Davis", paidDate: "2026-02-01" },
  { teamName: "Snow Hawks", ownerName: "Lisa Park", paid: false },
  { teamName: "Tundra Wolves", ownerName: "Chris Brown", paid: false },
  { teamName: "Polar Storms", ownerName: "Amy Garcia", paid: true, paidBy: "Amy Garcia", paidDate: "2026-01-20" },
  { teamName: "Northern Lights", ownerName: "Dan Miller", paid: false },
  { teamName: "Avalanche", ownerName: "Rob Wilson", paid: false },
  { teamName: "Icebreakers", ownerName: "Jen Taylor", paid: true, paidBy: "Jen Taylor", paidDate: "2026-02-10" },
  { teamName: "Frozen Fury", ownerName: "Matt Anderson", paid: false },
];

function loadPayments(): TeamPayment[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return JSON.parse(stored);
  } catch {}
  return DEFAULT_PAYMENTS;
}

function savePayments(payments: TeamPayment[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payments));
}

function loadRefunds(): RefundRequest[] {
  try {
    const stored = localStorage.getItem(REFUND_STORAGE_KEY);
    if (stored) return JSON.parse(stored);
  } catch {}
  return [];
}

function saveRefunds(refunds: RefundRequest[]) {
  localStorage.setItem(REFUND_STORAGE_KEY, JSON.stringify(refunds));
}

export function getOutstandingCount(): number {
  return loadPayments().filter((p) => !p.paid).length;
}

export function getCurrentUserPaid(): boolean {
  const mine = loadPayments().find((p) => p.teamName === CURRENT_USER_TEAM);
  return mine?.paid ?? false;
}

export function getPendingRefunds(): RefundRequest[] {
  return loadRefunds().filter((r) => r.status === "pending");
}

const LeaguePayments = () => {
  const [payments, setPayments] = useState<TeamPayment[]>(loadPayments);
  const [selectedTeams, setSelectedTeams] = useState<Set<string>>(new Set());
  const [processing, setProcessing] = useState(false);
  const [refunds, setRefunds] = useState<RefundRequest[]>(loadRefunds);
  const [departDialogOpen, setDepartDialogOpen] = useState(false);
  const [departTeam, setDepartTeam] = useState<string>("");

  useEffect(() => { savePayments(payments); }, [payments]);
  useEffect(() => { saveRefunds(refunds); }, [refunds]);

  const myPayment = payments.find((p) => p.teamName === CURRENT_USER_TEAM);
  const myPaid = myPayment?.paid ?? false;
  const unpaidTeams = payments.filter((p) => !p.paid);
  const paidTeams = payments.filter((p) => p.paid);
  const totalCollected = paidTeams.length * ADMIN_FEE;
  const totalOutstanding = unpaidTeams.length * ADMIN_FEE;
  const pendingRefunds = refunds.filter((r) => r.status === "pending");

  const toggleSelect = (teamName: string) => {
    setSelectedTeams((prev) => {
      const next = new Set(prev);
      if (next.has(teamName)) next.delete(teamName); else next.add(teamName);
      return next;
    });
  };

  const selectAll = () => {
    if (selectedTeams.size === unpaidTeams.length) setSelectedTeams(new Set());
    else setSelectedTeams(new Set(unpaidTeams.map((t) => t.teamName)));
  };

  const handlePay = () => {
    if (selectedTeams.size === 0) { toast.error("Select at least one team to pay for."); return; }
    setProcessing(true);
    setTimeout(() => {
      const now = new Date().toISOString().split("T")[0];
      setPayments((prev) =>
        prev.map((p) =>
          selectedTeams.has(p.teamName)
            ? { ...p, paid: true, paidBy: CURRENT_USER_TEAM + " (You)", paidDate: now }
            : p
        )
      );
      setSelectedTeams(new Set());
      setProcessing(false);
      toast.success(`Payment of $${selectedTeams.size * ADMIN_FEE} processed successfully!`);
    }, 1500);
  };

  const handleDepartOpen = () => {
    setDepartTeam("");
    setDepartDialogOpen(true);
  };

  const handleDepartConfirm = () => {
    if (!departTeam) return;
    const team = payments.find((p) => p.teamName === departTeam);
    if (!team || !team.paid) {
      toast.error("This team hasn't paid — no refund needed.");
      setDepartDialogOpen(false);
      return;
    }
    const existing = refunds.find((r) => r.teamName === departTeam && r.status === "pending");
    if (existing) {
      toast.error("A refund request already exists for this team.");
      setDepartDialogOpen(false);
      return;
    }
    const now = new Date();
    const deadline = new Date(now);
    deadline.setDate(deadline.getDate() + REFUND_DEADLINE_DAYS);
    setRefunds((prev) => [
      ...prev,
      {
        teamName: departTeam,
        ownerName: team.ownerName,
        status: "pending",
        requestedDate: now.toISOString().split("T")[0],
        deadlineDate: deadline.toISOString().split("T")[0],
      },
    ]);
    toast.success(`Departure initiated for ${departTeam}. You have ${REFUND_DEADLINE_DAYS} days to resolve.`);
    setDepartDialogOpen(false);
  };

  const handleRefundAction = (teamName: string, action: "refunded" | "held") => {
    const now = new Date().toISOString().split("T")[0];
    setRefunds((prev) =>
      prev.map((r) =>
        r.teamName === teamName && r.status === "pending"
          ? { ...r, status: action, resolvedDate: now }
          : r
      )
    );
    if (action === "refunded") {
      setPayments((prev) =>
        prev.map((p) => (p.teamName === teamName ? { ...p, paid: false, paidBy: undefined, paidDate: undefined } : p))
      );
      toast.success(`Refund issued for ${teamName}.`);
    } else {
      toast.success(`Fee held for ${teamName}. No refund issued.`);
    }
  };

  const getDaysRemaining = (deadlineDate: string) => {
    const diff = new Date(deadlineDate).getTime() - Date.now();
    return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
  };

  const selectedTotal = selectedTeams.size * ADMIN_FEE;
  const paidTeamsForDepart = payments.filter(
    (p) => p.paid && !refunds.some((r) => r.teamName === p.teamName && r.status === "pending")
  );

  return (
    <AppLayout>
      <div className="container py-8 max-w-4xl">
        <div className="mb-8 animate-fade-in">
          <h1 className="text-3xl font-bold mb-2">
            <span className="text-gradient-ice">League Payments</span>
          </h1>
          <p className="text-muted-foreground">
            Manage admin fee payments for the 2025-26 season — ${ADMIN_FEE} per team.
          </p>
        </div>

        {/* Pending Refund Banner */}
        {pendingRefunds.length > 0 && (
          <Card className="mb-6 border-amber-500/30 bg-amber-500/5">
            <CardContent className="py-4">
              <div className="flex items-center gap-3 mb-2">
                <ShieldAlert className="h-5 w-5 text-amber-500 shrink-0" />
                <span className="font-semibold text-sm">
                  {pendingRefunds.length} pending refund{pendingRefunds.length !== 1 ? "s" : ""} — action required within deadline to avoid league disruption
                </span>
              </div>
              <div className="space-y-2 mt-3">
                {pendingRefunds.map((r) => {
                  const daysLeft = getDaysRemaining(r.deadlineDate);
                  return (
                    <div key={r.teamName} className="flex items-center gap-3 p-3 rounded-lg border border-amber-500/20 bg-background">
                      <UserMinus className="h-4 w-4 text-amber-500 shrink-0" />
                      <div className="flex-1">
                        <p className="font-medium text-sm">{r.teamName} <span className="text-muted-foreground">({r.ownerName})</span></p>
                        <p className="text-xs text-muted-foreground flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {daysLeft > 0 ? `${daysLeft} day${daysLeft !== 1 ? "s" : ""} remaining` : "Deadline passed!"} — due by {r.deadlineDate}
                        </p>
                      </div>
                      {IS_COMMISSIONER && (
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" onClick={() => handleRefundAction(r.teamName, "refunded")}>
                            Refund ${ADMIN_FEE}
                          </Button>
                          <Button size="sm" variant="secondary" onClick={() => handleRefundAction(r.teamName, "held")}>
                            Hold Fee
                          </Button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <Card>
            <CardContent className="pt-6 flex items-center gap-4">
              <div className="h-10 w-10 rounded-lg bg-primary/20 flex items-center justify-center">
                <DollarSign className="h-5 w-5 text-primary" />
              </div>
              <div>
                <p className="text-2xl font-bold">${totalCollected}</p>
                <p className="text-xs text-muted-foreground">Collected ({paidTeams.length}/{payments.length})</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6 flex items-center gap-4">
              <div className="h-10 w-10 rounded-lg bg-destructive/20 flex items-center justify-center">
                <AlertCircle className="h-5 w-5 text-destructive" />
              </div>
              <div>
                <p className="text-2xl font-bold">${totalOutstanding}</p>
                <p className="text-xs text-muted-foreground">Outstanding ({unpaidTeams.length} teams)</p>
              </div>
            </CardContent>
          </Card>
          <Card className={myPaid ? "border-green-500/30" : "border-destructive/30"}>
            <CardContent className="pt-6 flex items-center gap-4">
              <div className={`h-10 w-10 rounded-lg flex items-center justify-center ${myPaid ? "bg-green-500/20" : "bg-accent/20"}`}>
                {myPaid ? <CheckCircle2 className="h-5 w-5 text-green-500" /> : <CreditCard className="h-5 w-5 text-accent" />}
              </div>
              <div>
                <p className="text-2xl font-bold">{myPaid ? "Paid" : "Unpaid"}</p>
                <p className="text-xs text-muted-foreground">Your status ({CURRENT_USER_TEAM})</p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Commissioner: Departing Owner */}
        {IS_COMMISSIONER && (
          <Card className="mb-6">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <UserMinus className="h-5 w-5 text-muted-foreground" />
                    Owner Departure
                  </CardTitle>
                  <CardDescription>
                    If an owner is leaving, initiate their departure to refund or hold their fee. A 1-week deadline applies.
                  </CardDescription>
                </div>
                <Button variant="outline" onClick={handleDepartOpen} disabled={paidTeamsForDepart.length === 0}>
                  <UserMinus className="h-4 w-4 mr-2" />
                  Initiate Departure
                </Button>
              </div>
            </CardHeader>
            {refunds.filter((r) => r.status !== "pending").length > 0 && (
              <CardContent>
                <p className="text-xs text-muted-foreground mb-2 font-medium">Resolved</p>
                <div className="space-y-1">
                  {refunds.filter((r) => r.status !== "pending").map((r) => (
                    <div key={r.teamName + r.resolvedDate} className="flex items-center gap-3 p-2 rounded-md bg-secondary/30 text-sm">
                      <span className="font-medium">{r.teamName}</span>
                      <Badge variant={r.status === "refunded" ? "outline" : "secondary"} className="text-xs">
                        {r.status === "refunded" ? "Refunded" : "Fee Held"}
                      </Badge>
                      <span className="text-xs text-muted-foreground ml-auto">{r.resolvedDate}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            )}
          </Card>
        )}

        {/* My Status Banner */}
        {myPaid && (
          <Card className="mb-6 border-green-500/30 bg-green-500/5">
            <CardContent className="py-4 flex items-center gap-3">
              <CheckCircle2 className="h-5 w-5 text-green-500" />
              <span className="font-medium">Your admin fee has been paid. Thank you!</span>
              {myPayment?.paidDate && (
                <span className="text-xs text-muted-foreground ml-auto">Paid on {myPayment.paidDate}</span>
              )}
            </CardContent>
          </Card>
        )}

        {/* Unpaid Teams */}
        {unpaidTeams.length > 0 && (
          <Card className="mb-6">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <AlertCircle className="h-5 w-5 text-destructive" />
                    Outstanding Fees
                  </CardTitle>
                  <CardDescription>Select teams to pay their admin fee.</CardDescription>
                </div>
                <Button variant="outline" size="sm" onClick={selectAll}>
                  {selectedTeams.size === unpaidTeams.length ? "Deselect All" : "Select All"}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {unpaidTeams.map((team) => (
                  <label
                    key={team.teamName}
                    className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                      selectedTeams.has(team.teamName)
                        ? "border-primary/50 bg-primary/5"
                        : "border-border hover:bg-secondary/50"
                    }`}
                  >
                    <Checkbox
                      checked={selectedTeams.has(team.teamName)}
                      onCheckedChange={() => toggleSelect(team.teamName)}
                    />
                    <div className="flex-1 flex items-center justify-between">
                      <div>
                        <span className="font-medium">{team.teamName}</span>
                        {team.teamName === CURRENT_USER_TEAM && (
                          <Badge variant="outline" className="ml-2 text-xs border-primary/50 text-primary">You</Badge>
                        )}
                        <p className="text-xs text-muted-foreground">{team.ownerName}</p>
                      </div>
                      <span className="font-semibold text-foreground">${ADMIN_FEE}</span>
                    </div>
                  </label>
                ))}
              </div>
              <Separator className="my-4" />
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">{selectedTeams.size} team{selectedTeams.size !== 1 ? "s" : ""} selected</p>
                  <p className="text-xl font-bold">${selectedTotal}</p>
                </div>
                <Button size="lg" disabled={selectedTeams.size === 0 || processing} onClick={handlePay} className="min-w-[160px]">
                  {processing ? (
                    <span className="flex items-center gap-2">
                      <span className="h-4 w-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                      Processing…
                    </span>
                  ) : (
                    <><CreditCard className="h-4 w-4" /> Pay ${selectedTotal}</>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* All Paid */}
        {unpaidTeams.length === 0 && (
          <Card className="mb-6 border-green-500/30 bg-green-500/5">
            <CardContent className="py-8 text-center">
              <CheckCircle2 className="h-12 w-12 text-green-500 mx-auto mb-3" />
              <h3 className="text-xl font-bold mb-1">All Fees Collected!</h3>
              <p className="text-muted-foreground">Every team has paid their admin fee for the 2025-26 season.</p>
            </CardContent>
          </Card>
        )}

        {/* Paid Teams */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-500" />
              Paid ({paidTeams.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {paidTeams.map((team) => (
                <div key={team.teamName} className="flex items-center gap-3 p-3 rounded-lg border border-border/50 bg-secondary/20">
                  <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                  <div className="flex-1 flex items-center justify-between">
                    <div>
                      <span className="font-medium">{team.teamName}</span>
                      {team.teamName === CURRENT_USER_TEAM && (
                        <Badge variant="outline" className="ml-2 text-xs border-primary/50 text-primary">You</Badge>
                      )}
                      <p className="text-xs text-muted-foreground">{team.ownerName}</p>
                    </div>
                    <div className="text-right">
                      <Badge variant="secondary" className="text-xs">Paid</Badge>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {team.paidDate} {team.paidBy && team.paidBy !== team.ownerName && `• by ${team.paidBy}`}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Departure Dialog */}
      <Dialog open={departDialogOpen} onOpenChange={setDepartDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Initiate Owner Departure</DialogTitle>
            <DialogDescription>
              Select the team whose owner is leaving. You'll have {REFUND_DEADLINE_DAYS} days to refund or hold their ${ADMIN_FEE} fee.
            </DialogDescription>
          </DialogHeader>
          <Select value={departTeam} onValueChange={setDepartTeam}>
            <SelectTrigger>
              <SelectValue placeholder="Select a team…" />
            </SelectTrigger>
            <SelectContent>
              {paidTeamsForDepart.map((t) => (
                <SelectItem key={t.teamName} value={t.teamName}>
                  {t.teamName} — {t.ownerName}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDepartDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleDepartConfirm} disabled={!departTeam}>
              <UserMinus className="h-4 w-4 mr-2" /> Confirm Departure
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
};

export default LeaguePayments;
