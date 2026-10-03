// @ts-nocheck
/**
 * Iter 206 — Reusable "Report User" dialog component.
 *
 * Drop this anywhere a user appears in the UI (chat avatars,
 * trade-block member rows, league standings, etc.). Renders a small
 * flag button that opens a Dialog with a category dropdown + reason
 * textarea, then POSTs to `/api/reports`.
 *
 * Usage:
 *   <ReportUserButton
 *     targetUserId={user.id}
 *     targetUserEmail={user.email}
 *     leagueId={league?.id}
 *     contextUrl={`/chat#msg-${msg.id}`}
 *   />
 */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Flag } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

const CATEGORIES = [
  { value: "harassment", label: "Harassment / abusive language" },
  { value: "spam", label: "Spam / advertising" },
  { value: "offensive_username", label: "Offensive username" },
  { value: "offensive_team_name", label: "Offensive team name" },
  { value: "offensive_avatar", label: "Offensive avatar" },
  { value: "trade_collusion", label: "Trade collusion" },
  { value: "cheating", label: "Cheating / multi-account" },
  { value: "other", label: "Other" },
];

export default function ReportUserButton({
  targetUserId,
  targetUserEmail,
  targetTeamId,
  leagueId,
  contextUrl,
  variant = "icon",
}: {
  targetUserId: string;
  targetUserEmail?: string;
  targetTeamId?: string;
  leagueId?: string;
  contextUrl?: string;
  variant?: "icon" | "text";
}) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState("harassment");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!reason.trim()) {
      toast.error("Please add a short reason");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post("/reports", {
        target_user_id: targetUserId,
        target_team_id: targetTeamId,
        league_id: leagueId,
        category,
        reason: reason.trim(),
        context_url: contextUrl,
      });
      if (data?.deduped) {
        toast.info(data.message || "You already have an open report against this user.");
      } else {
        toast.success("Report submitted. Our moderators will review it.");
      }
      setOpen(false);
      setReason("");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Could not submit report");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {variant === "icon" ? (
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6 text-muted-foreground hover:text-rose-400"
            data-testid={`report-btn-${targetUserId}`}
            title="Report this user"
            onClick={(e) => e.stopPropagation()}
          >
            <Flag className="h-3.5 w-3.5" />
          </Button>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            className="text-rose-300 hover:text-rose-200"
            data-testid={`report-btn-${targetUserId}`}
          >
            <Flag className="h-3.5 w-3.5 mr-1.5" />
            Report
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-w-md" data-testid="report-user-dialog">
        <DialogHeader>
          <DialogTitle>Report user</DialogTitle>
          <DialogDescription>
            Reporting {targetUserEmail || "this user"} sends a ticket to the
            moderation team. False reports may result in action against your
            own account.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div>
            <label className="text-xs uppercase tracking-wider text-muted-foreground mb-1 block">
              Category
            </label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger data-testid="report-category-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CATEGORIES.map((c) => (
                  <SelectItem key={c.value} value={c.value}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-muted-foreground mb-1 block">
              What happened?
            </label>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Describe the issue (max 2000 chars)..."
              maxLength={2000}
              rows={5}
              data-testid="report-reason-textarea"
            />
            <div className="text-[10px] text-muted-foreground text-right mt-1">
              {reason.length}/2000
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => setOpen(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={submitting || !reason.trim()}
            className="bg-rose-500/80 hover:bg-rose-500"
            data-testid="report-submit-btn"
          >
            {submitting ? "Submitting…" : "Submit report"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
