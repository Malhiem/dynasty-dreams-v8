// @ts-nocheck
/**
 * Iter 157 — DraftTab extracted from CommissionerSettings.tsx using a
 * typed context-bundle pattern (lower noise than 16-prop drilling).
 *
 * The parent assembles `DraftTabContext` from its existing state hooks
 * and passes it as a single prop. Any future field added to the tab body
 * just needs an entry on the interface — no signature churn at the call site.
 */
import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table, TableHeader, TableRow, TableHead, TableBody, TableCell,
} from "@/components/ui/table";
import { ChevronDown, ChevronRight, Trophy, Calendar, Users, Plus, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import TransactionsConfigCards, { TransactionsDraftRulesCard } from "@/lovable/pages/commissioner/TransactionsConfigCards";
import DraftOrderConfigCard from "@/lovable/pages/commissioner/DraftOrderConfigCard";
import KeeperSettingsCard from "@/lovable/pages/commissioner/KeeperSettingsCard";
import ExpansionDraftSettingsCard from "@/lovable/pages/commissioner/ExpansionDraftSettingsCard";
import CommissionerProtectionOverridePanel from "@/lovable/pages/commissioner/CommissionerProtectionOverridePanel";
import { toast } from "sonner";

export interface DraftTabContext {
  // State
  draftType: string;
  firstDraftCompleted: boolean;
  draftRounds: number;
  setDraftRounds: (v: number) => void;
  roundTimes: number[];
  setRoundTimes: (v: number[]) => void;
  draftClockEnabled: boolean;
  setDraftClockEnabled: (v: boolean) => void;
  draftClockStart: string;
  setDraftClockStart: (v: string) => void;
  draftClockEnd: string;
  setDraftClockEnd: (v: string) => void;
  selectedPlayerCriteria: string[];
  setSelectedPlayerCriteria: (v: string[]) => void;
  createDraftPickTrading: boolean;
  setCreateDraftPickTrading: (v: boolean) => void;
  expandedDraft: string | null;
  setExpandedDraft: (v: string | null) => void;
  expandedDraftResults: string | null;
  setExpandedDraftResults: (v: string | null) => void;
  // Helpers + references
  activeLeague: any;
  persistDraftType: (v: string) => void;
  completedDraftResults: any[];
  playerCriteriaOptions: any[];
  scheduledDrafts: any[];
}

interface DraftTabProps {
  ctx: DraftTabContext;
}

export default function DraftTab({ ctx }: DraftTabProps) {
  const navigate = useNavigate();
  const {
    draftType, firstDraftCompleted, draftRounds, setDraftRounds, roundTimes, setRoundTimes,
    draftClockEnabled, setDraftClockEnabled, draftClockStart, setDraftClockStart,
    draftClockEnd, setDraftClockEnd, selectedPlayerCriteria, setSelectedPlayerCriteria,
    createDraftPickTrading, setCreateDraftPickTrading,
    expandedDraft, setExpandedDraft, expandedDraftResults, setExpandedDraftResults,
    activeLeague, persistDraftType, completedDraftResults, playerCriteriaOptions, scheduledDrafts,
  } = ctx;
  return (
    <div className="space-y-6" data-testid="commissioner-draft-tab">
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle>Create a Draft</CardTitle>
            <CardDescription>Select the type of draft and player eligibility</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Draft Type</Label>
              <Select value={draftType} onValueChange={persistDraftType}>
                <SelectTrigger className="bg-secondary border-border" data-testid="draft-type-trigger">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem
                    value="startup"
                    disabled={firstDraftCompleted}
                    data-testid="draft-type-startup"
                  >
                    First-Time Team Draft
                    {firstDraftCompleted && (
                      <span className="ml-2 text-[10px] italic text-muted-foreground">
                        — already occurred
                      </span>
                    )}
                  </SelectItem>
                  <SelectItem value="redraft" data-testid="draft-type-redraft">Redraft</SelectItem>
                  <SelectItem value="entry">NHL Entry Draft</SelectItem>
                  <SelectItem value="supplemental">Supplemental Draft</SelectItem>
                  <SelectItem value="expansion">Expansion Draft</SelectItem>
                  <SelectItem value="keeper" data-testid="draft-type-keeper">Keeper Draft</SelectItem>
                </SelectContent>
              </Select>
              {firstDraftCompleted && (
                <p
                  className="text-[11px] italic text-muted-foreground"
                  data-testid="draft-type-startup-disabled-note"
                >
                  The First-Time Team Draft has already been completed for this league.
                  Use <strong>Redraft</strong> to run a full draft with the same settings.
                </p>
              )}
            </div>
            <Separator />
            <DraftOrderConfigCard
              leagueId={activeLeague?.id}
              isCommish={true}
              embedded={true}
            />
            {/* Iter 141 — Keeper settings appear only for keeper drafts */}
            {draftType === "keeper" && (
              <>
                <Separator />
                <KeeperSettingsCard leagueId={activeLeague?.id} isCommish={true} />
              </>
            )}
            {/* Iter 142 — Expansion settings appear only for expansion drafts */}
            {draftType === "expansion" && (
              <>
                <Separator />
                <ExpansionDraftSettingsCard leagueId={activeLeague?.id} isCommish={true} />
                <Separator />
                <CommissionerProtectionOverridePanel leagueId={activeLeague?.id} draftType="expansion" />
              </>
            )}
            {/* Iter 144 — Commissioner override for keeper drafts too */}
            {draftType === "keeper" && (
              <>
                <Separator />
                <CommissionerProtectionOverridePanel leagueId={activeLeague?.id} draftType="keeper" />
              </>
            )}
            <Separator />
            <div className="space-y-3">
              <Label>Player Criteria</Label>
              <p className="text-sm text-muted-foreground">Select one or more criteria to define which players are eligible for this draft</p>
              {selectedPlayerCriteria.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {selectedPlayerCriteria.map((c) => (
                    <Badge key={c} variant="secondary" className="gap-1">
                      {playerCriteriaOptions.find((o) => o.value === c)?.label}
                      <X className="h-3 w-3 cursor-pointer" onClick={() => setSelectedPlayerCriteria(selectedPlayerCriteria.filter((v) => v !== c))} />
                    </Badge>
                  ))}
                </div>
              )}
              <div className="grid gap-2 sm:grid-cols-2">
                {playerCriteriaOptions.map((option) => (
                  <div key={option.value} className="flex items-center space-x-2">
                    <Checkbox
                      id={`criteria-${option.value}`}
                      checked={selectedPlayerCriteria.includes(option.value)}
                      onCheckedChange={(checked) => {
                        if (checked) {
                          setSelectedPlayerCriteria([...selectedPlayerCriteria, option.value]);
                        } else {
                          setSelectedPlayerCriteria(selectedPlayerCriteria.filter((v) => v !== option.value));
                        }
                      }}
                    />
                    <Label htmlFor={`criteria-${option.value}`} className="text-sm font-normal cursor-pointer">{option.label}</Label>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle>Draft Format</CardTitle>
            <CardDescription>Configure rounds, timing, and draft order</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Draft Name</Label>
              <Input placeholder="e.g. 2026 NHL Entry Draft" defaultValue="" className="bg-secondary border-border" />
            </div>
            <Separator />
            <div className="grid gap-4 md:grid-cols-3">
               <div className="space-y-2">
                <Label>Number of Rounds</Label>
                <Input type="number" min={1} max={30} value={draftRounds} onChange={(e) => setDraftRounds(Math.max(1, Math.min(30, parseInt(e.target.value) || 1)))} className="bg-secondary border-border" />
              </div>
              <div className="space-y-2">
                <Label>Default Time Per Pick</Label>
                <Select defaultValue="120" onValueChange={(v) => {
                  const newTimes: Record<number, string> = {};
                  for (let i = 1; i <= draftRounds; i++) newTimes[i] = v;
                  setRoundTimes(newTimes);
                }}>
                  <SelectTrigger className="bg-secondary border-border">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="120">2 minutes</SelectItem>
                    <SelectItem value="150">2.5 minutes</SelectItem>
                    <SelectItem value="300">5 minutes</SelectItem>
                    <SelectItem value="600">10 minutes</SelectItem>
                    <SelectItem value="900">15 minutes</SelectItem>
                    <SelectItem value="1200">20 minutes</SelectItem>
                    <SelectItem value="1800">30 minutes</SelectItem>
                    <SelectItem value="2700">45 minutes</SelectItem>
                    <SelectItem value="3600">1 hour</SelectItem>
                    <SelectItem value="5400">1.5 hours</SelectItem>
                    <SelectItem value="7200">2 hours</SelectItem>
                    <SelectItem value="9000">2.5 hours</SelectItem>
                    <SelectItem value="10800">3 hours</SelectItem>
                    <SelectItem value="12600">3.5 hours</SelectItem>
                    <SelectItem value="14400">4 hours</SelectItem>
                    <SelectItem value="18000">5 hours</SelectItem>
                    <SelectItem value="21600">6 hours</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Draft Order</Label>
                <Select defaultValue="snake">
                  <SelectTrigger className="bg-secondary border-border">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="snake">Snake Draft</SelectItem>
                    <SelectItem value="linear">Linear Draft</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Separator />
            <div className="space-y-3">
              <Label>Time Per Pick by Round</Label>
              <p className="text-sm text-muted-foreground">Customize the pick timer for each round individually</p>
              <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
                {Array.from({ length: draftRounds }, (_, i) => i + 1).map((round) => (
                  <div key={round} className="flex items-center gap-2">
                    <Label className="text-sm text-muted-foreground whitespace-nowrap w-14">Rd {round}</Label>
                    <Select value={roundTimes[round] || "120"} onValueChange={(v) => setRoundTimes({ ...roundTimes, [round]: v })}>
                      <SelectTrigger className="bg-secondary border-border h-8 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="120">2 min</SelectItem>
                        <SelectItem value="150">2.5 min</SelectItem>
                        <SelectItem value="300">5 min</SelectItem>
                        <SelectItem value="600">10 min</SelectItem>
                        <SelectItem value="900">15 min</SelectItem>
                        <SelectItem value="1200">20 min</SelectItem>
                        <SelectItem value="1800">30 min</SelectItem>
                        <SelectItem value="2700">45 min</SelectItem>
                        <SelectItem value="3600">1 hr</SelectItem>
                        <SelectItem value="5400">1.5 hr</SelectItem>
                        <SelectItem value="7200">2 hr</SelectItem>
                        <SelectItem value="9000">2.5 hr</SelectItem>
                        <SelectItem value="10800">3 hr</SelectItem>
                        <SelectItem value="12600">3.5 hr</SelectItem>
                        <SelectItem value="14400">4 hr</SelectItem>
                        <SelectItem value="18000">5 hr</SelectItem>
                        <SelectItem value="21600">6 hr</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            </div>
            <Separator />
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <Label>Draft Clock Active Hours</Label>
                  <p className="text-sm text-muted-foreground">Set the daily window when the draft pick timer is running. Outside these hours, the clock pauses.</p>
                </div>
                <Switch checked={draftClockEnabled} onCheckedChange={setDraftClockEnabled} />
              </div>
              {draftClockEnabled && (
                <div className="grid grid-cols-2 gap-4 mt-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Clock Starts At</Label>
                    <Input
                      type="time"
                      value={draftClockStart}
                      onChange={(e) => setDraftClockStart(e.target.value)}
                      className="bg-secondary border-border"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Clock Stops At</Label>
                    <Input
                      type="time"
                      value={draftClockEnd}
                      onChange={(e) => setDraftClockEnd(e.target.value)}
                      className="bg-secondary border-border"
                    />
                  </div>
                  <p className="col-span-2 text-xs text-muted-foreground">
                    Example: 9:00 AM – 11:00 PM means pick timers only count down during those hours each day.
                  </p>
                </div>
              )}
            </div>
            <Separator />
            <div className="space-y-2">
                <Label>Draft Order</Label>
                <Select defaultValue="reverse-standings">
                  <SelectTrigger className="bg-secondary border-border">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="nhl-lottery">NHL Draft Lottery Representation</SelectItem>
                    <SelectItem value="lottery-generator">Draft Lottery Generator</SelectItem>
                    <SelectItem value="manual">Manual Entry</SelectItem>
                    <SelectItem value="reverse-standings">Reverse Order of Standings</SelectItem>
                  </SelectContent>
                </Select>
            </div>
            <Separator />
            <div className="space-y-4">
              <div>
                <Label>Draft Order Tiebreakers</Label>
                <p className="text-sm text-muted-foreground">
                  Determine draft lottery positioning when two or more teams finish with identical records
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">1st Tiebreaker</Label>
                  <Select defaultValue="lowest-pf">
                    <SelectTrigger className="bg-secondary border-border">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="highest-pf">Highest Points For</SelectItem>
                      <SelectItem value="lowest-pf">Lowest Points For</SelectItem>
                      <SelectItem value="h2h-record">Head-to-Head Record</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">2nd Tiebreaker</Label>
                  <Select defaultValue="h2h-record">
                    <SelectTrigger className="bg-secondary border-border">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="highest-pf">Highest Points For</SelectItem>
                      <SelectItem value="lowest-pf">Lowest Points For</SelectItem>
                      <SelectItem value="h2h-record">Head-to-Head Record</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">3rd Tiebreaker</Label>
                  <div className="h-10 rounded-md border border-border bg-secondary/50 flex items-center px-3">
                    <span className="text-sm text-muted-foreground">Manual (League Administrator)</span>
                  </div>
                  <p className="text-xs text-muted-foreground">Determined by the League Administrator outside the system</p>
                </div>
              </div>
            </div>
            <Separator />
            <div className="space-y-2">
              <Label>If a Team Misses Their Pick</Label>
              <p className="text-sm text-muted-foreground">What happens when the pick timer expires</p>
              <Select defaultValue="auto-select">
                <SelectTrigger className="bg-secondary border-border">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto-select">Auto-select best available player</SelectItem>
                  <SelectItem value="pick-anytime">Allow pick anytime when they return</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div>
                <Label>Allow Pick Trading</Label>
                <p className="text-sm text-muted-foreground">Teams can trade draft picks before and during the draft</p>
              </div>
              <Switch checked={createDraftPickTrading} onCheckedChange={setCreateDraftPickTrading} />
            </div>
            {createDraftPickTrading && (
              <div className="space-y-2 mt-4">
                <Label>Trading Window Opens</Label>
                <p className="text-xs text-muted-foreground">Draft picks become visible to teams and available for use in trades when the trading window opens.</p>
                <Select defaultValue="immediately">
                  <SelectTrigger className="bg-secondary border-border">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="league-renews">When League Renews</SelectItem>
                    <SelectItem value="immediately">Immediately</SelectItem>
                    <SelectItem value="1-week">1 Week Before Draft</SelectItem>
                    <SelectItem value="2-weeks">2 Weeks Before Draft</SelectItem>
                    <SelectItem value="1-month">1 Month Before Draft</SelectItem>
                    <SelectItem value="2-months">2 Months Before Draft</SelectItem>
                    <SelectItem value="3-months">3 Months Before Draft</SelectItem>
                    <SelectItem value="6-months">6 Months Before Draft</SelectItem>
                    <SelectItem value="1-year">1 Year Before Draft</SelectItem>
                    <SelectItem value="2-years">2 Years Before Draft</SelectItem>
                    <SelectItem value="3-years">3 Years Before Draft</SelectItem>
                    <SelectItem value="4-years">4 Years Before Draft</SelectItem>
                    <SelectItem value="5-years">5 Years Before Draft</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex justify-end">
          <Button onClick={() => toast.success("Draft created successfully! It has been added to your scheduled drafts.")} className="gap-2">
            <Plus className="h-4 w-4" />
            Create Draft
          </Button>
        </div>

        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5" />
              Scheduled Drafts
            </CardTitle>
            <CardDescription>View and manage drafts that have been created or are upcoming</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {scheduledDrafts.map((draft) => (
              <div key={draft.id} className="border border-border rounded-lg overflow-hidden">
                <button
                  className="w-full flex items-center justify-between p-4 bg-secondary/50 hover:bg-secondary transition-colors text-left"
                  onClick={() => setExpandedDraft(expandedDraft === draft.id ? null : draft.id)}
                >
                  <div className="flex items-center gap-3">
                    <Badge variant={draft.status === "completed" ? "default" : draft.status === "in-progress" ? "destructive" : "secondary"}>
                      {draft.status === "completed" ? "Completed" : draft.status === "in-progress" ? "In Progress" : "Scheduled"}
                    </Badge>
                    <span className="font-medium">{draft.name}</span>
                  </div>
                  <div className="flex items-center gap-3 text-sm text-muted-foreground">
                    <span>{draft.scheduledDate}</span>
                    <svg className={`h-4 w-4 transition-transform ${expandedDraft === draft.id ? "rotate-180" : ""}`} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /></svg>
                  </div>
                </button>
                {expandedDraft === draft.id && (
                  <div className="p-4 space-y-4 border-t border-border">
                    <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
                      <div>
                        <p className="text-xs text-muted-foreground">Draft Type</p>
                        <p className="text-sm font-medium">{draft.type}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Format</p>
                        <p className="text-sm font-medium">{draft.format}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Rounds</p>
                        <p className="text-sm font-medium">{draft.rounds}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Default Time Per Pick</p>
                        <p className="text-sm font-medium">{draft.timePerPick}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Player Criteria</p>
                        <p className="text-sm font-medium">{draft.playerCriteria}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Missed Pick Action</p>
                        <p className="text-sm font-medium">{draft.missedPickAction}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Scheduled Date & Time</p>
                        <p className="text-sm font-medium">{draft.scheduledDate} at {draft.scheduledTime}</p>
                      </div>
                      {draft.completedDate && (
                        <div>
                          <p className="text-xs text-muted-foreground">Completed</p>
                          <p className="text-sm font-medium">{draft.completedDate}</p>
                        </div>
                      )}
                    </div>

                    {draft.status === "completed" && (
                      <>
                        <Separator />
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <Label className="text-sm font-semibold">Draft Results</Label>
                            <Button variant="outline" size="sm" onClick={() => setExpandedDraftResults(expandedDraftResults === draft.id ? null : draft.id)}>
                              {expandedDraftResults === draft.id ? "Hide Results" : "See Results"}
                            </Button>
                          </div>
                          {expandedDraftResults === draft.id && (
                            <div className="rounded-md border border-border overflow-hidden">
                              <Table>
                                <TableHeader>
                                  <TableRow className="bg-secondary/50">
                                    <TableHead className="w-16">Pick</TableHead>
                                    <TableHead>Round</TableHead>
                                    <TableHead>Team</TableHead>
                                    <TableHead>Player Selected</TableHead>
                                    <TableHead>Position</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {completedDraftResults
                                    .filter((r) => r.draftId === draft.id)
                                    .map((result) => (
                                      <TableRow key={result.pick}>
                                        <TableCell className="font-medium">{result.pick}</TableCell>
                                        <TableCell>{result.round}</TableCell>
                                        <TableCell>{result.team}</TableCell>
                                        <TableCell className="font-medium">{result.player}</TableCell>
                                        <TableCell><Badge variant="secondary">{result.position}</Badge></TableCell>
                                      </TableRow>
                                    ))}
                                </TableBody>
                              </Table>
                            </div>
                          )}
                        </div>
                      </>
                    )}

                    {draft.status === "scheduled" && (
                      <>
                        <Separator />
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <div>
                              <Label>Allow Pick Trading Before Draft</Label>
                              <p className="text-sm text-muted-foreground">Teams can trade their picks for this draft before it begins</p>
                            </div>
                            <Switch defaultChecked={draft.pickTradingEnabled} />
                          </div>
                          {draft.pickTradingEnabled && (
                            <div className="space-y-2">
                              <Label>Trading Window Opens</Label>
                              <p className="text-xs text-muted-foreground">Draft picks become visible to teams and available for use in trades when the trading window opens.</p>
                              <Select defaultValue={draft.tradingWindowOpens || "immediately"}>
                                <SelectTrigger className="bg-secondary border-border">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="immediately">Immediately</SelectItem>
                                  <SelectItem value="1-week">1 Week Before Draft</SelectItem>
                                  <SelectItem value="2-weeks">2 Weeks Before Draft</SelectItem>
                                  <SelectItem value="1-month">1 Month Before Draft</SelectItem>
                                  <SelectItem value="2-months">2 Months Before Draft</SelectItem>
                                  <SelectItem value="3-months">3 Months Before Draft</SelectItem>
                                  <SelectItem value="6-months">6 Months Before Draft</SelectItem>
                                  <SelectItem value="1-year">1 Year Before Draft</SelectItem>
                                  <SelectItem value="2-years">2 Years Before Draft</SelectItem>
                                  <SelectItem value="3-years">3 Years Before Draft</SelectItem>
                                  <SelectItem value="4-years">4 Years Before Draft</SelectItem>
                                  <SelectItem value="5-years">5 Years Before Draft</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>

        <div className="flex justify-end gap-3">
          <Button variant="outline">Reset to Defaults</Button>
          <Button>Save Draft Settings</Button>
        </div>

        <TransactionsDraftRulesCard leagueId={activeLeague?.id} />
    </div>
  );
}
