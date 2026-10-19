import { Button } from "@/components/ui/button";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";

import { Loader2, UserPlus } from "lucide-react";

import type React from "react";

interface GroupDmComposerProps {
  groupOpen: boolean;
  setGroupOpen: (open: boolean) => void;
  setGroupPicked: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  leagueTeams: Array<{ id: string; name: string }>;
  myTeam: { id: string } | null;
  groupPicked: Record<string, boolean>;
  handleCreateGroupDm: () => void;
  groupCreating: boolean;
}

export default function GroupDmComposer({ groupOpen, setGroupOpen, setGroupPicked, leagueTeams, myTeam, groupPicked, handleCreateGroupDm, groupCreating }: GroupDmComposerProps) {
  return (
                  <Dialog open={groupOpen} onOpenChange={(open) => {
                    setGroupOpen(open);
                    if (!open) setGroupPicked({});
                  }}>
                    <DialogTrigger asChild>
                      <button
                        data-testid="chat-new-group-dm-btn"
                        className="hover:bg-secondary rounded p-1"
                        title="New group DM (3+ teams)"
                      >
                        <UserPlus className="h-3.5 w-3.5" />
                      </button>
                    </DialogTrigger>
                    <DialogContent data-testid="chat-new-group-dm-modal">
                      <DialogHeader>
                        <DialogTitle>New group DM</DialogTitle>
                      </DialogHeader>
                      <div className="space-y-2">
                        <p className="text-xs text-muted-foreground">
                          Pick at least <strong>2 other teams</strong> — your
                          team is included automatically. Perfect for 3-way
                          trade talks.
                        </p>
                        <div className="max-h-72 overflow-y-auto space-y-1 border border-border rounded-md p-2">
                          {(leagueTeams || [])
                            .filter((t) => t.id !== myTeam?.id)
                            .map((t) => (
                              <label
                                key={t.id}
                                className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-secondary/50 cursor-pointer"
                                data-testid={`chat-group-dm-pick-${t.id}`}
                              >
                                <input
                                  type="checkbox"
                                  className="accent-primary"
                                  checked={!!groupPicked[t.id]}
                                  onChange={(e) => setGroupPicked((prev) => ({
                                    ...prev, [t.id]: e.target.checked,
                                  }))}
                                />
                                <span className="text-sm">{t.name}</span>
                              </label>
                            ))}
                        </div>
                        <p className="text-[11px] text-muted-foreground">
                          Selected: {Object.values(groupPicked).filter(Boolean).length + 1}{" "}
                          teams (including you)
                        </p>
                      </div>
                      <DialogFooter>
                        <Button
                          variant="outline"
                          onClick={() => { setGroupOpen(false); setGroupPicked({}); }}
                          data-testid="chat-new-group-dm-cancel"
                        >
                          Cancel
                        </Button>
                        <Button
                          onClick={handleCreateGroupDm}
                          disabled={
                            groupCreating ||
                            Object.values(groupPicked).filter(Boolean).length < 2
                          }
                          data-testid="chat-new-group-dm-submit"
                        >
                          {groupCreating ? (
                            <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Opening…</>
                          ) : "Open group DM"}
                        </Button>
                      </DialogFooter>
                    </DialogContent>
                  </Dialog>
  );
}
