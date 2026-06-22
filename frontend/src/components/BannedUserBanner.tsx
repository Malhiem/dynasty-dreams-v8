// @ts-nocheck
/**
 * Iter 207 — Banned/Suspended User Banner.
 *
 * Shown app-wide when the current user's `status` is "banned" or
 * "suspended" (covers cases where a user is sanctioned mid-session).
 * Provides an inline appeal form so the user can request reinstatement
 * without bouncing back to the support inbox.
 *
 * The auth/login endpoint already blocks banned users at the gate;
 * this banner handles the in-session case where the AuthContext still
 * holds a stale session.
 */
import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

export default function BannedUserBanner() {
  const { user } = useAuth();
  const status = (user as any)?.status;
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [appeal, setAppeal] = useState<any>(null);

  useEffect(() => {
    if (status !== "banned" && status !== "suspended") return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/appeals/mine");
        const openAppeal = (data?.appeals || []).find((a: any) => a.status === "open");
        if (!cancelled) setAppeal(openAppeal || null);
      } catch { /* noop */ }
    })();
    return () => { cancelled = true; };
  }, [status]);

  if (status !== "banned" && status !== "suspended") return null;

  const submit = async () => {
    if (!message.trim()) {
      toast.error("Please describe why your ban should be lifted");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post("/appeals", { message: message.trim() });
      if (data?.deduped) {
        toast.info("You already have an open appeal");
      } else {
        toast.success("Appeal submitted. We'll review it shortly.");
      }
      setOpen(false);
      // Refresh the appeal state
      const { data: mine } = await api.get("/appeals/mine");
      const openAppeal = (mine?.appeals || []).find((a: any) => a.status === "open");
      setAppeal(openAppeal || null);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Could not submit appeal");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="bg-rose-950/40 border-b border-rose-500/40 px-4 py-3 text-rose-100"
      data-testid="banned-user-banner"
      role="alert"
    >
      <div className="max-w-6xl mx-auto flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <ShieldAlert className="h-5 w-5 text-rose-300 mt-0.5 shrink-0" />
          <div className="text-sm min-w-0">
            <div className="font-semibold">
              Your account is {status === "banned" ? "banned" : "suspended"}.
            </div>
            <div className="text-rose-200/80 text-xs mt-0.5 break-words">
              Reason: <span className="capitalize">{(user as any)?.ban_reason_code || "unspecified"}</span>
              {(user as any)?.ban_reason && <> — {(user as any).ban_reason}</>}
              {status === "suspended" && (user as any)?.ban_expires_at && (
                <> · Until {new Date((user as any).ban_expires_at).toLocaleString()}</>
              )}
            </div>
            {appeal && (
              <div className="text-amber-300 text-xs mt-1" data-testid="banner-appeal-pending">
                ⏳ Appeal pending review — submitted {new Date(appeal.created_at).toLocaleDateString()}
              </div>
            )}
          </div>
        </div>
        {!appeal && (
          <Button
            size="sm"
            variant="outline"
            className="border-rose-300/40 text-rose-100 hover:bg-rose-500/20"
            onClick={() => setOpen((v) => !v)}
            data-testid="banner-appeal-btn"
          >
            {open ? "Cancel" : "Submit appeal"}
          </Button>
        )}
      </div>
      {open && !appeal && (
        <div className="max-w-6xl mx-auto mt-3 space-y-2" data-testid="appeal-form">
          <Textarea
            placeholder="Explain why your account should be reinstated…"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            maxLength={2000}
            rows={4}
            className="bg-background/40 border-rose-500/30"
            data-testid="appeal-message-textarea"
          />
          <div className="flex items-center justify-end gap-2">
            <span className="text-[10px] text-rose-200/60">{message.length}/2000</span>
            <Button
              size="sm"
              onClick={submit}
              disabled={submitting || !message.trim()}
              className="bg-rose-500 hover:bg-rose-600"
              data-testid="appeal-submit-btn"
            >
              {submitting ? "Submitting…" : "Submit appeal"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
