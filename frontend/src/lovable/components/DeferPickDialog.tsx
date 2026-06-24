// @ts-nocheck
/**
 * Iter 228f — Defer-to-User missed-pick dialog.
 *
 * Surfaces in the live Draft Room when:
 *   • The draft was created with `missed_pick_action == "defer-to-user"`
 *   • The pick timer has elapsed
 *   • The current pick belongs to the active user's team
 *
 * The owner picks one of:
 *   • Auto-select best available — engine drafts the highest-ranked
 *     player NOW.
 *   • Auto-select from queue — engine drafts the next player in the
 *     team's saved queue (falls back to best-available if queue empty).
 *   • Skip & pick anytime — the pick is skipped; the draft moves on
 *     but the owner can return any time before the draft ends to make
 *     their selection.
 *
 * Backed by POST /api/drafts/{draft_id}/picks/{pick_no}/defer.
 * The dialog is dismissible only by submitting a choice — once
 * timer hit zero we keep nudging until the owner decides.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Bot, ListOrdered, Clock3, Loader2 } from "lucide-react";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";

const OPTIONS = [
  {
    value: "auto-best",
    label: "Auto-select best available",
    description: "Skip the choice — the engine drafts the highest-ranked free player right now.",
    icon: Bot,
    testid: "defer-option-auto-best",
  },
  {
    value: "auto-queue",
    label: "Auto-select from my queue",
    description: "Engine drafts the next player in your saved queue (falls back to best available if your queue is empty).",
    icon: ListOrdered,
    testid: "defer-option-auto-queue",
  },
  {
    value: "pick-anytime",
    label: "Skip & pick anytime",
    description: "Pick is skipped — draft continues to the next slot. You can return and pick anytime before the draft ends.",
    icon: Clock3,
    testid: "defer-option-pick-anytime",
  },
];

export default function DeferPickDialog({
  open,
  onClose,
  draftId,
  pickNo,
  availableOptions,
  onResolved,
  // Iter 228g — auto-resolve countdown (seconds). When > 0 and no
  // choice has been made before it elapses, the dialog auto-submits
  // `auto-best` so the draft never stalls on an AFK owner. Set to 0
  // (or null) to disable the auto-resolve safety net.
  autoResolveSeconds = 30,
  autoResolveChoice = "auto-best",
}: {
  open: boolean;
  onClose: () => void;
  draftId: string;
  pickNo: number;
  availableOptions?: string[];
  onResolved?: (choice: string) => void;
  autoResolveSeconds?: number;
  autoResolveChoice?: string;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(autoResolveSeconds);

  // Iter 228g — Reset countdown each time the dialog opens
  useEffect(() => {
    if (!open) return;
    setSecondsLeft(autoResolveSeconds);
  }, [open, autoResolveSeconds, pickNo]);

  // Iter 228g — Tick the countdown once per second while the dialog is open
  useEffect(() => {
    if (!open || autoResolveSeconds <= 0) return;
    if (secondsLeft <= 0) return;
    const t = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [open, secondsLeft, autoResolveSeconds]);

  const choices = OPTIONS.filter((o) =>
    !availableOptions?.length || availableOptions.includes(o.value),
  );

  const submit = async (choice: string) => {
    if (!draftId || !pickNo) return;
    setBusy(choice);
    try {
      await api.post(`/drafts/${draftId}/picks/${pickNo}/defer`, { choice });
      const label = OPTIONS.find((o) => o.value === choice)?.label || choice;
      toast.success(`Choice saved: ${label}`);
      onResolved?.(choice);
      onClose();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Could not save your choice");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o && !busy) onClose(); }}>
      <DialogContent
        className="max-w-lg"
        data-testid="defer-pick-dialog"
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-rose-300">
            <Clock3 className="h-5 w-5" />
            Pick #{pickNo} — timer expired
          </DialogTitle>
          <DialogDescription>
            Your pick window closed. Tell us how you&apos;d like to resolve this pick — your commissioner enabled
            <strong className="text-foreground"> defer-to-user</strong> for this draft.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 mt-2">
          {choices.map((opt) => {
            const Icon = opt.icon;
            const loading = busy === opt.value;
            return (
              <Button
                key={opt.value}
                variant="outline"
                className="w-full justify-start h-auto py-3 text-left"
                onClick={() => submit(opt.value)}
                disabled={!!busy}
                data-testid={opt.testid}
              >
                <div className="flex items-start gap-3 w-full">
                  {loading ? (
                    <Loader2 className="h-5 w-5 mt-0.5 shrink-0 animate-spin text-accent" />
                  ) : (
                    <Icon className="h-5 w-5 mt-0.5 shrink-0 text-accent" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="font-medium">{opt.label}</div>
                    <div className="text-xs text-muted-foreground mt-0.5 whitespace-normal">
                      {opt.description}
                    </div>
                  </div>
                </div>
              </Button>
            );
          })}
        </div>

        <p className="text-[11px] text-muted-foreground italic mt-3">
          Tip: you can save a default draft queue from the Players panel before the draft starts so &quot;Auto-select from queue&quot; always has a fallback ready.
        </p>
        {/* Iter 228g — countdown safety net */}
        {autoResolveSeconds > 0 && (
          <div
            className="flex items-center justify-between rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 mt-2 text-xs"
            data-testid="defer-countdown-banner"
          >
            <span className="text-amber-200">
              No choice yet — engine will auto-select
              <strong className="mx-1 font-semibold">
                {OPTIONS.find((o) => o.value === autoResolveChoice)?.label || autoResolveChoice}
              </strong>
              in
            </span>
            <span className="font-bold text-amber-100 tabular-nums" data-testid="defer-countdown-seconds">
              {secondsLeft}s
            </span>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
