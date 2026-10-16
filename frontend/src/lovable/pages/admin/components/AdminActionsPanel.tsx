// @ts-nocheck
/**
 * AdminActionsPanel — config-driven action buttons + dialog for User Detail Drawer.
 *
 * Extracted from AdminDashboard.tsx during Iter 222 refactor. Contains:
 *   • REASON_CODES / ACTION_CONFIGS — declarative action schemas
 *   • AdminActionsPanel              — 6 grouped action buttons + dispatcher
 *   • ActionDialog                   — generic dialog driven by config
 *   • FieldRenderer                  — input/textarea/select/number/checkbox
 *   • ActionGroup / ActionBtn        — visual layout primitives
 */
import { useState, useRef } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

const newOperationKey = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("");

const REASON_CODES = [
  { value: "harassment", label: "Harassment" },
  { value: "fraud", label: "Fraud" },
  { value: "cheating", label: "Cheating" },
  { value: "collusion", label: "Collusion" },
  { value: "spam", label: "Spam" },
  { value: "other", label: "Other" },
];

const ACTION_CONFIGS = {
  suspend: {
    title: "Suspend account", tone: "warn", path: "/suspend",
    description: "Temporary suspension. Auto-expires after duration.",
    fields: [
      { name: "duration_days", label: "Duration (days)", type: "number", required: true, default: 7 },
      { name: "reason_code", label: "Reason code", type: "select", options: REASON_CODES, default: "other" },
      { name: "reason", label: "Reason (visible to user)", type: "textarea", required: true },
    ],
    success: "User suspended",
  },
  ban_permanent: {
    title: "Permanent ban", tone: "danger", path: "/ban-permanent",
    description: "Irreversible. Senior-admin only. We strongly recommend a second-admin sign-off.",
    requireConfirm: true,
    fields: [
      { name: "reason_code", label: "Reason code", type: "select", options: REASON_CODES, default: "other" },
      { name: "reason", label: "Reason (visible to user)", type: "textarea", required: true },
      { name: "second_signoff_admin_email", label: "Second admin sign-off email (recommended)", type: "text" },
    ],
    extraBody: { confirm: true },
    success: "User permanently banned",
  },
  reinstate: {
    title: "Reinstate account", tone: "success", path: "/reinstate",
    description: "Lift any active ban or suspension.",
    fields: [{ name: "note", label: "Reinstatement note (esp. for appeals)", type: "textarea", required: true }],
    success: "User reinstated",
  },
  force_logout: {
    title: "Force logout all sessions", tone: "warn", path: "/force-logout",
    description: "Revokes every active session for this user. JWT token_version is bumped.",
    fields: [], success: "All sessions revoked",
  },
  deactivate: {
    title: "Deactivate account", tone: "warn", path: "/deactivate",
    description: "Soft deactivation — account hidden, login blocked. Reversible.",
    fields: [{ name: "reason", label: "Reason", type: "textarea" }],
    success: "Account deactivated",
  },
  reactivate: {
    title: "Reactivate account", tone: "success", path: "/reactivate",
    description: "Restore a deactivated account.",
    fields: [], success: "Account reactivated",
  },
  delete: {
    title: "Hard delete (anonymise)", tone: "danger", path: "/delete",
    description: "IRREVERSIBLE. PII anonymised; rare action — usually legal/compliance only.",
    requireConfirm: true,
    fields: [{ name: "reason", label: "Reason", type: "textarea", required: true }],
    extraBody: { confirm: true },
    success: "User hard-deleted (anonymised)",
  },
  reset_password: {
    title: "Reset password", tone: "default", path: "/reset-password",
    description: "Trigger a password-reset email. Admin never sees the new password.",
    fields: [], success: "Reset email queued",
  },
  verify_email: {
    title: "Verify email", tone: "default", path: "/verify-email",
    description: "Mark the email as verified (manual override).",
    fields: [], success: "Email marked verified",
  },
  verify_phone: {
    title: "Verify phone", tone: "default", path: "/verify-phone",
    description: "Mark the phone number as verified.",
    fields: [], success: "Phone marked verified",
  },
  edit_username: {
    title: "Edit username", tone: "default", path: "/edit-username",
    description: "Override the normal change-frequency limits. Recorded in change history.",
    fields: [
      { name: "username", label: "New username", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "Username updated",
  },
  merge_accounts: {
    title: "Merge accounts", tone: "danger", path: "/merge-accounts",
    description: "Transfers source ownership, history and credits into this account. The source account is disabled. This data transfer cannot be undone.",
    requireConfirm: true,
    fields: [
      { name: "source_user_id", label: "Source user id", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "Accounts merged",
  },
  unlink_sso: {
    title: "Unlink SSO provider", tone: "warn", path: "/unlink-sso",
    fields: [
      { name: "provider", label: "Provider", type: "select",
        options: [{ value: "google", label: "Google" }, { value: "apple", label: "Apple" },
                  { value: "facebook", label: "Facebook" }, { value: "github", label: "GitHub" }],
        required: true },
    ],
    success: "SSO unlinked",
  },
  permission_tier: {
    title: "Set permission tier", tone: "warn", path: "/permission-tier",
    description: "Grant or revoke admin tooling access. Requires senior_admin to perform.",
    fields: [
      { name: "tier", label: "New tier", type: "select", required: true,
        options: [
          { value: "user", label: "user (no admin access)" },
          { value: "moderator", label: "moderator (mute/warn/flag only)" },
          { value: "admin", label: "admin (most actions)" },
          { value: "senior_admin", label: "senior_admin (irreversible actions)" },
        ], default: "moderator" },
      { name: "reason", label: "Reason", type: "textarea", required: true },
    ],
    success: "Permission tier updated",
  },
  remove_from_league: {
    title: "Remove from league", tone: "warn", path: "/remove-from-league",
    fields: [
      { name: "league_id", label: "League id", type: "text", required: true },
      { name: "handover_mode", label: "Handover mode", type: "select", required: true,
        options: [{ value: "commissioner", label: "Commissioner takes over" },
                  { value: "ai", label: "AI auto-manages" },
                  { value: "pause", label: "Pause league" }] },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "User removed from league",
  },
  transfer_commissioner: {
    title: "Transfer commissioner", tone: "warn", path: "/transfer-commissioner",
    fields: [
      { name: "league_id", label: "League id", type: "text", required: true },
      { name: "new_commissioner_user_id", label: "New commissioner user id", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "Commissioner transferred",
  },
  force_remove_draft: {
    title: "Force-remove from draft", tone: "warn", path: "/force-remove-from-draft",
    description: "Flips the user's team to autopick AND drains any picks they currently owe on the clock. Live.",
    fields: [
      { name: "draft_id", label: "Draft id", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "User evicted from draft",
  },
  reset_team: {
    title: "Reset team", tone: "danger", path: "/reset-team",
    description: "STUBBED — versioned snapshot rollback. Audit-only.",
    fields: [
      { name: "team_id", label: "Team id", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "Reset queued",
  },
  warning: {
    title: "Issue warning", tone: "warn", path: "/warning",
    description: "Tiered. 3rd warning auto-suspends 3 days. User is notified.",
    fields: [{ name: "reason", label: "Warning reason", type: "textarea", required: true }],
    success: "Warning issued",
  },
  mute: {
    title: "Mute (chat only)", tone: "warn", path: "/mute",
    description: "Restricts chat without suspending play.",
    fields: [
      { name: "duration_hours", label: "Duration (hours)", type: "number", required: true, default: 24 },
      { name: "reason", label: "Reason", type: "textarea", required: true },
    ],
    success: "User muted",
  },
  unmute: {
    title: "Unmute user", tone: "success", path: "/unmute",
    fields: [], success: "User unmuted",
  },
  flag_review: {
    title: "Flag for review", tone: "default", path: "/flag-for-review",
    description: "Adds to admin watchlist. No visible action to the user.",
    fields: [{ name: "reason", label: "Reason for watchlisting", type: "textarea", required: true }],
    success: "Added to watchlist",
  },
  unflag: {
    title: "Remove from watchlist", tone: "default", path: "/unflag",
    fields: [], success: "Removed from watchlist",
  },
  delete_content: {
    title: "Delete content", tone: "warn", path: "/delete-content",
    description: "STUBBED — delegate to existing moderation-queue flow.",
    fields: [
      { name: "content_type", label: "Content type", type: "select", required: true,
        options: [{ value: "chat_message", label: "Chat message" },
                  { value: "forum_post", label: "Forum post" },
                  { value: "team_name", label: "Team name" },
                  { value: "avatar", label: "Avatar" }] },
      { name: "content_id", label: "Content id", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "Content delete queued",
  },
  refund: {
    title: "Issue refund", tone: "warn", path: "/refund",
    description: "STUBBED — Stripe API call deferred.",
    fields: [
      { name: "amount_cents", label: "Amount (cents)", type: "number", required: true, default: 999 },
      { name: "currency", label: "Currency", type: "text", default: "usd" },
      { name: "reason", label: "Reason", type: "textarea", required: true },
      { name: "transaction_id", label: "Transaction id (optional)", type: "text" },
    ],
    success: "Refund recorded",
  },
  adjust_tier: {
    title: "Adjust subscription tier", tone: "default", path: "/adjust-tier",
    fields: [
      { name: "tier", label: "New tier", type: "select", required: true,
        options: [{ value: "free", label: "Free" }, { value: "pro", label: "Pro" },
                  { value: "commish", label: "Commish" }, { value: "premium", label: "Premium" }] },
      { name: "reason", label: "Reason", type: "textarea" },
      { name: "comp", label: "Goodwill comp?", type: "checkbox" },
    ],
    success: "Tier adjusted",
  },
  promo_credit: {
    title: "Add/remove promo credit", tone: "default", path: "/promo-credit",
    description: "Negative amount removes credit.",
    fields: [
      { name: "amount_cents", label: "Amount (cents, neg=remove)", type: "number", required: true, default: 500 },
      { name: "currency", label: "Currency", type: "text", default: "usd" },
      { name: "note", label: "Note", type: "textarea" },
    ],
    success: "Promo credit updated",
  },
  void_payout: {
    title: "Void pending payout", tone: "warn", path: "/void-payout",
    description: "STUBBED.",
    fields: [
      { name: "payout_id", label: "Payout id", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "Payout voided",
  },
  manual_payout: {
    title: "Manual payout", tone: "warn", path: "/manual-payout",
    description: "STUBBED — for edge cases where automated payout failed.",
    fields: [
      { name: "amount_cents", label: "Amount (cents)", type: "number", required: true },
      { name: "currency", label: "Currency", type: "text", default: "usd" },
      { name: "reason", label: "Reason", type: "textarea", required: true },
    ],
    success: "Manual payout queued",
  },
  impersonate: {
    title: "Impersonate (view-as)", tone: "warn", path: "/impersonate",
    description: "Issues a 15-min READ-ONLY cookie swap. The user is notified, and a persistent red banner shows across the app while in view-as mode.",
    fields: [{ name: "reason", label: "Reason", type: "textarea", required: true }],
    success: "Now viewing as target user · banner will appear",
    useCookieSwap: true,
  },
  resend_verification: {
    title: "Resend verification email", tone: "default", path: "/resend-verification",
    fields: [], success: "Verification email resent",
  },
  link_ticket: {
    title: "Link support ticket", tone: "default", path: "/link-support-ticket",
    fields: [
      { name: "ticket_id", label: "Ticket id", type: "text", required: true },
      { name: "ticket_url", label: "Ticket URL (optional)", type: "text" },
      { name: "note", label: "Note", type: "textarea" },
    ],
    success: "Ticket linked",
  },
  gdpr_delete: {
    title: "GDPR / CCPA delete", tone: "danger", path: "/gdpr-delete",
    description: "Right-to-be-forgotten deletion. PII anonymised; data-retention compliant.",
    requireConfirm: true,
    fields: [{ name: "reason", label: "Deletion reason", type: "textarea", required: true,
               default: "GDPR/CCPA data deletion request" }],
    extraBody: { confirm: true },
    success: "GDPR deletion executed",
  },
};

export function AdminActionsPanel({ userId, userEmail, userStatus, permissionTier, refresh }) {
  const [active, setActive] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const operation = useRef({ key: "", payload: "" });
  const submitting = useRef(false);
  const open = (key) => { operation.current = { key: newOperationKey(), payload: "" }; setActive(key); };
  const close = () => setActive(null);

  const submit = async (cfg, values) => {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    try {
      const body = { ...(cfg.extraBody || {}), ...values };
      let res;
      if (cfg.path === "/export-data") {
        res = await api.get(`/admin/platform/users/${userId}${cfg.path}`);
        const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: "application/json" });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = `user-data-${userId}.json`; a.click();
        window.URL.revokeObjectURL(url);
      } else if (cfg.useCookieSwap) {
        // Iter 216b — Impersonation uses cookie-swap endpoint so the
        // banner can take over the whole app session.
        res = await api.post("/auth/impersonate-start", {
          target_user_id: userId, reason: values.reason || "",
        });
        try {
          window.dispatchEvent(new Event("auth-impersonation-started"));
        } catch { /* noop */ }
      } else {
        const payload = JSON.stringify(body);
        if (operation.current.payload && operation.current.payload !== payload) operation.current.key = newOperationKey();
        operation.current.payload = payload;
        res = await api.post(`/admin/platform/users/${userId}${cfg.path}`, body,
          cfg.path === "/promo-credit" ? { headers: { "Idempotency-Key": operation.current.key } } : undefined);
      }
      const note = res.data?.mocked ? " (MOCKED)" : "";
      toast.success((cfg.success || "Action complete") + note);
      close();
      refresh?.();
      if (cfg.useCookieSwap) {
        setTimeout(() => { window.location.href = "/dashboard"; }, 400);
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Action failed");
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  };

  const renderBtn = (k, label, tone?) => (
    <ActionBtn testid={`action-${k.replace(/_/g, "-")}`} tone={tone} onClick={() => open(k)} key={k}>
      {label}
    </ActionBtn>
  );

  return (
    <section className="space-y-3" data-testid="user-actions-panel">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Admin Actions <span className="text-foreground/60 normal-case font-normal">· every action is logged</span>
        {permissionTier && (
          <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full border border-border" data-testid="target-permission-tier">
            current tier: {permissionTier}
          </span>
        )}
      </h4>

      <ActionGroup label="Account Status" testid="actions-account-status">
        {renderBtn("suspend", "Suspend")}
        {renderBtn("ban_permanent", "Ban (permanent)", "danger")}
        {(userStatus === "banned" || userStatus === "suspended") && renderBtn("reinstate", "Reinstate", "success")}
        {renderBtn("force_logout", "Force logout")}
        {userStatus !== "deactivated" && renderBtn("deactivate", "Deactivate")}
        {userStatus === "deactivated" && renderBtn("reactivate", "Reactivate", "success")}
        {renderBtn("delete", "Delete", "danger")}
      </ActionGroup>

      <ActionGroup label="Identity & Access" testid="actions-identity">
        {renderBtn("reset_password", "Reset password")}
        {renderBtn("verify_email", "Verify email")}
        {renderBtn("verify_phone", "Verify phone")}
        {renderBtn("edit_username", "Edit username")}
        {renderBtn("merge_accounts", "Merge accounts")}
        {renderBtn("unlink_sso", "Unlink SSO")}
        {renderBtn("permission_tier", "Set permission tier", "warn")}
      </ActionGroup>

      <ActionGroup label="League / Team" testid="actions-league">
        {renderBtn("remove_from_league", "Remove from league")}
        {renderBtn("transfer_commissioner", "Transfer commissioner")}
        {renderBtn("force_remove_draft", "Force-remove from draft")}
        {renderBtn("reset_team", "Reset team")}
      </ActionGroup>

      <ActionGroup label="Moderation" testid="actions-moderation">
        {renderBtn("warning", "Issue warning")}
        {renderBtn("mute", "Mute")}
        {renderBtn("unmute", "Unmute")}
        {renderBtn("flag_review", "Flag for review")}
        {renderBtn("unflag", "Unflag")}
        {renderBtn("delete_content", "Delete content")}
      </ActionGroup>

      <ActionGroup label="Financial" testid="actions-financial">
        {renderBtn("refund", "Refund")}
        {renderBtn("adjust_tier", "Adjust tier")}
        {renderBtn("promo_credit", "Promo credit")}
        {renderBtn("void_payout", "Void payout")}
        {renderBtn("manual_payout", "Manual payout")}
      </ActionGroup>

      <ActionGroup label="Support" testid="actions-support">
        {renderBtn("impersonate", "Impersonate (view-as)")}
        {renderBtn("resend_verification", "Resend verification")}
        {renderBtn("link_ticket", "Link support ticket")}
        <ActionBtn testid="action-export-data" onClick={async () => {
          setBusy(true);
          try {
            const { data } = await api.get(`/admin/platform/users/${userId}/export-data`);
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url; a.download = `user-data-${userId}.json`; a.click();
            window.URL.revokeObjectURL(url);
            toast.success("Data export downloaded");
          } catch (e: any) {
            toast.error(e?.response?.data?.detail || "Export failed");
          } finally { setBusy(false); }
        }}>Export data (GDPR)</ActionBtn>
        {renderBtn("gdpr_delete", "GDPR delete", "danger")}
      </ActionGroup>

      {active && (
        <ActionDialog
          config={ACTION_CONFIGS[active]}
          userEmail={userEmail}
          busy={busy}
          onClose={close}
          onSubmit={(values) => submit(ACTION_CONFIGS[active], values)}
        />
      )}
    </section>
  );
}

function ActionDialog({ config, userEmail, busy, onClose, onSubmit }) {
  const [values, setValues] = useState<Record<string, any>>(() => {
    const init: any = {};
    (config.fields || []).forEach((f) => {
      init[f.name] = f.default ?? (f.type === "checkbox" ? false : "");
    });
    return init;
  });
  const [acknowledged, setAcknowledged] = useState(false);

  const update = (name, val) => setValues((prev) => ({ ...prev, [name]: val }));

  const isValid = () => {
    for (const f of config.fields || []) {
      if (f.required) {
        const v = values[f.name];
        if (v === undefined || v === null || v === "" || typeof v === "string" && !v.trim()) return false;
      }
    }
    if (config.requireConfirm && !acknowledged) return false;
    return true;
  };

  const toneCls = config.tone === "danger" ? "border-rose-500/40"
    : config.tone === "warn" ? "border-amber-500/40"
    : config.tone === "success" ? "border-emerald-500/40"
    : "";

  const submitCls = config.tone === "danger" ? "bg-rose-500 hover:bg-rose-600 text-white"
    : config.tone === "warn" ? "bg-amber-500 hover:bg-amber-600 text-white"
    : "bg-primary hover:bg-primary/90 text-primary-foreground";

  return (
    <Dialog open={true} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent
        className={`max-w-[520px] ${toneCls}`}
        data-testid={`action-dialog-${config.path?.replace(/^\//, "")}`}
      >
        <DialogHeader>
          <DialogTitle>{config.title}</DialogTitle>
          <DialogDescription>
            Target: <code className="text-foreground">{userEmail}</code>
            {config.description && <span className="block mt-2 text-xs">{config.description}</span>}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {(config.fields || []).map((f) => (
            <FieldRenderer
              key={f.name}
              field={f}
              value={values[f.name]}
              onChange={(v) => update(f.name, v)}
            />
          ))}
          {config.requireConfirm && (
            <label className="flex items-start gap-2 text-xs text-rose-300 mt-2 cursor-pointer" data-testid="dialog-confirm-checkbox">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
                className="mt-0.5"
              />
              <span>I understand this action is irreversible and proceed at my own accountability.</span>
            </label>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy} data-testid="dialog-cancel-btn">
            Cancel
          </Button>
          <Button
            onClick={() => onSubmit(values)}
            disabled={!isValid() || busy}
            className={submitCls}
            data-testid="dialog-submit-btn"
          >
            {busy ? "Working…" : "Confirm"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FieldRenderer({ field, value, onChange }) {
  if (field.type === "select") {
    return (
      <div className="space-y-1">
        <Label className="text-xs">{field.label}{field.required && <span className="text-rose-300 ml-0.5">*</span>}</Label>
        <Select value={value || ""} onValueChange={onChange}>
          <SelectTrigger className="h-9" data-testid={`field-${field.name}`}>
            <SelectValue placeholder={field.placeholder || `Select ${field.label.toLowerCase()}`} />
          </SelectTrigger>
          <SelectContent>
            {field.options.map((o) => (<SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>))}
          </SelectContent>
        </Select>
      </div>
    );
  }
  if (field.type === "textarea") {
    return (
      <div className="space-y-1">
        <Label className="text-xs">{field.label}{field.required && <span className="text-rose-300 ml-0.5">*</span>}</Label>
        <Textarea
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          rows={3}
          data-testid={`field-${field.name}`}
        />
      </div>
    );
  }
  if (field.type === "number") {
    return (
      <div className="space-y-1">
        <Label className="text-xs">{field.label}{field.required && <span className="text-rose-300 ml-0.5">*</span>}</Label>
        <Input
          type="number"
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value === "" ? "" : parseInt(e.target.value, 10))}
          data-testid={`field-${field.name}`}
        />
      </div>
    );
  }
  if (field.type === "checkbox") {
    return (
      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} data-testid={`field-${field.name}`} />
        <span>{field.label}</span>
      </label>
    );
  }
  return (
    <div className="space-y-1">
      <Label className="text-xs">{field.label}{field.required && <span className="text-rose-300 ml-0.5">*</span>}</Label>
      <Input
        type="text"
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={field.placeholder}
        data-testid={`field-${field.name}`}
      />
    </div>
  );
}

function ActionGroup({ label, testid, children }) {
  return (
    <div className="rounded-lg border border-border p-3 space-y-2" data-testid={testid}>
      <p className="text-[11px] font-semibold uppercase tracking-wider text-foreground/70">{label}</p>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

function ActionBtn({ children, onClick, tone = "default", testid }: any) {
  const toneCls = tone === "danger"
    ? "border-rose-500/40 text-rose-300 hover:bg-rose-500/10"
    : tone === "warn"
      ? "border-amber-500/40 text-amber-300 hover:bg-amber-500/10"
      : tone === "success"
        ? "border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10"
        : "border-border text-foreground hover:bg-secondary/40";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-xs px-2.5 py-1.5 rounded border transition-colors ${toneCls}`}
      data-testid={testid}
    >
      {children}
    </button>
  );
}
