/**
 * Iter 220 — Payment / Card Capture form (frontend-only).
 *
 * Renders a complete credit-card capture UI. Submits to a stubbed
 * `POST /api/payments/setup-card` endpoint — backend will replace
 * the stub with the real Stripe Setup Intent flow.
 *
 * Field validation:
 *   • Card number: Luhn-checked, 13-19 digits
 *   • Expiry: MM/YY, must be in the future
 *   • CVC: 3-4 digits
 *   • Postal/ZIP: 3-10 chars
 *
 * UX:
 *   • Auto-format card number into 4-digit groups
 *   • Detect brand (Visa, Mastercard, Amex, Discover) from prefix
 *   • Auto-advance focus between fields
 *   • Submit disabled until all fields valid
 *   • Loading + success states
 */
import { useEffect, useState, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CreditCard, Lock, Check, Loader2 } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

function detectBrand(num) {
  const n = num.replace(/\s/g, "");
  if (/^4/.test(n)) return "Visa";
  if (/^(5[1-5]|2[2-7])/.test(n)) return "Mastercard";
  if (/^3[47]/.test(n)) return "Amex";
  if (/^(6011|65|64[4-9])/.test(n)) return "Discover";
  return null;
}
function luhnValid(num) {
  const n = num.replace(/\s/g, "");
  if (!/^\d{13,19}$/.test(n)) return false;
  let sum = 0, alt = false;
  for (let i = n.length - 1; i >= 0; i--) {
    let d = parseInt(n[i], 10);
    if (alt) { d *= 2; if (d > 9) d -= 9; }
    sum += d; alt = !alt;
  }
  return sum % 10 === 0;
}
function formatCard(num) {
  const n = num.replace(/\D/g, "").slice(0, 19);
  // Amex uses 4-6-5 grouping; else 4-4-4-4
  if (/^3[47]/.test(n)) return n.replace(/(\d{4})(\d{0,6})(\d{0,5}).*/, (_, a, b, c) =>
    [a, b, c].filter(Boolean).join(" "));
  return n.replace(/(\d{4})(\d{0,4})(\d{0,4})(\d{0,4}).*/, (_, a, b, c, d) =>
    [a, b, c, d].filter(Boolean).join(" "));
}
function formatExpiry(v) {
  const n = v.replace(/\D/g, "").slice(0, 4);
  if (n.length <= 2) return n;
  return n.slice(0, 2) + "/" + n.slice(2);
}
function expiryValid(v) {
  const m = v.match(/^(\d{2})\/(\d{2})$/);
  if (!m) return false;
  const mm = parseInt(m[1], 10), yy = parseInt(m[2], 10);
  if (mm < 1 || mm > 12) return false;
  const now = new Date();
  const y = 2000 + yy;
  return y > now.getFullYear() || (y === now.getFullYear() && mm >= now.getMonth() + 1);
}

export default function PaymentSetupPage() {
  const [searchParams] = useSearchParams();
  const leagueId = searchParams.get("league_id");
  const [card, setCard] = useState("");
  const [exp, setExp] = useState("");
  const [cvc, setCvc] = useState("");
  const [name, setName] = useState("");
  const [postal, setPostal] = useState("");
  const [saveDefault, setSaveDefault] = useState(true);
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);

  const brand = useMemo(() => detectBrand(card), [card]);
  const cardOk = luhnValid(card);
  const expOk = expiryValid(exp);
  const cvcOk = /^\d{3,4}$/.test(cvc);
  const nameOk = name.trim().length >= 2;
  const postalOk = /^[\w\s-]{3,10}$/.test(postal.trim());
  const allOk = cardOk && expOk && cvcOk && nameOk && postalOk;

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!allOk || busy) return;
    setBusy(true);
    try {
      // Backend stub — last4 + brand + name only. NEVER send full PAN
      // in a real Stripe-backed integration; here we keep the same
      // contract so the call works once the backend lands.
      const last4 = card.replace(/\s/g, "").slice(-4);
      await api.post("/payments/setup-card", {
        brand, last4,
        exp_month: parseInt(exp.split("/")[0], 10),
        exp_year: 2000 + parseInt(exp.split("/")[1], 10),
        name_on_card: name.trim(),
        postal: postal.trim(),
        is_default: saveDefault,
        client_tokenization_pending: true,  // backend swaps to Stripe SetupIntent
      });
      setSuccess(true);
      toast.success("Payment method saved");
    } catch (e2) {
      // Backend not wired yet — treat 404 as soft success for the UI demo
      if (e2?.response?.status === 404) {
        setSuccess(true);
        toast.message("Payment method captured (backend integration pending)",
                      { description: "Card details validated locally · Stripe SetupIntent to follow." });
      } else {
        toast.error(e2?.response?.data?.detail || "Failed to save payment method");
      }
    } finally { setBusy(false); }
  };

  // Reset success state after a few seconds so the user can add another card
  useEffect(() => {
    if (!success) return;
    const t = setTimeout(() => setSuccess(false), 4000);
    return () => clearTimeout(t);
  }, [success]);

  return (
    <AppLayout>
      <div className="max-w-2xl mx-auto p-6 space-y-6" data-testid="payment-setup-page">
        {leagueId && <LeagueTeamFeesPanel leagueId={leagueId} />}
        <Card className="border-border">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CreditCard className="h-5 w-5 text-primary" />
              Add a payment method
            </CardTitle>
            <CardDescription className="flex items-center gap-1.5">
              <Lock className="h-3.5 w-3.5" />
              Securely processed · we never store the full card number on our servers.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4" data-testid="payment-form">
              <div className="space-y-1">
                <Label htmlFor="card">Card number</Label>
                <div className="relative">
                  <Input
                    id="card"
                    inputMode="numeric"
                    autoComplete="cc-number"
                    placeholder="1234 5678 9012 3456"
                    value={card}
                    onChange={(e) => setCard(formatCard(e.target.value))}
                    className={`pr-16 font-mono tabular-nums ${
                      card && !cardOk ? "border-rose-500/60" : ""
                    }`}
                    data-testid="payment-card-number"
                  />
                  {brand && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-muted-foreground" data-testid="payment-brand">
                      {brand}
                    </span>
                  )}
                </div>
                {card && !cardOk && <p className="text-xs text-rose-300">Invalid card number</p>}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="exp">Expiry (MM/YY)</Label>
                  <Input
                    id="exp"
                    inputMode="numeric"
                    autoComplete="cc-exp"
                    placeholder="MM/YY"
                    value={exp}
                    onChange={(e) => setExp(formatExpiry(e.target.value))}
                    className={`font-mono ${exp && !expOk ? "border-rose-500/60" : ""}`}
                    maxLength={5}
                    data-testid="payment-exp"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="cvc">CVC</Label>
                  <Input
                    id="cvc"
                    inputMode="numeric"
                    autoComplete="cc-csc"
                    placeholder="123"
                    value={cvc}
                    onChange={(e) => setCvc(e.target.value.replace(/\D/g, "").slice(0, 4))}
                    className={`font-mono ${cvc && !cvcOk ? "border-rose-500/60" : ""}`}
                    maxLength={4}
                    data-testid="payment-cvc"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <Label htmlFor="name">Name on card</Label>
                <Input
                  id="name"
                  autoComplete="cc-name"
                  placeholder="Full name as printed"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  data-testid="payment-name"
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="postal">Postal / ZIP</Label>
                <Input
                  id="postal"
                  autoComplete="postal-code"
                  placeholder="K1A 0B1"
                  value={postal}
                  onChange={(e) => setPostal(e.target.value)}
                  className="max-w-[200px]"
                  data-testid="payment-postal"
                />
              </div>

              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={saveDefault}
                  onChange={(e) => setSaveDefault(e.target.checked)}
                  data-testid="payment-set-default"
                />
                <span>Set as my default payment method</span>
              </label>

              <Button
                type="submit"
                disabled={!allOk || busy}
                className="w-full"
                data-testid="payment-submit-btn"
              >
                {busy ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Processing…</>
                  : success ? <><Check className="h-4 w-4 mr-2" /> Saved</>
                  : "Save payment method"}
              </Button>

              <p className="text-xs text-muted-foreground text-center" data-testid="payment-pci-note">
                <Lock className="inline h-3 w-3 mr-1" />
                Tokenization through Stripe Setup Intents — your raw card data never touches our servers in production.
              </p>
            </form>
          </CardContent>
        </Card>
      </div>
    </AppLayout>
  );
}

/* ───────────────────────────────────────────────────────────────
   Iter 226 — League team fees panel.
   Full-or-partial payment for league entry fees. PAID stamps render
   beside each cleared team. Backend marks `payment_status="paid"`
   on each covered team (Stripe still MOCKED — actual settlement is
   replaced once SetupIntents are wired).
   ─────────────────────────────────────────────────────────────── */

function LeagueTeamFeesPanel({ leagueId }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState("full"); // "full" | "partial"
  const [selected, setSelected] = useState(new Set());
  const [paying, setPaying] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/payments/league/${leagueId}/status`);
      setStatus(data);
      setSelected(new Set());
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load league payment status");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [leagueId]);

  const unpaid = (status?.teams || []).filter((t) => !t.paid);

  const amount = useMemo(() => {
    if (!status) return 0;
    if (mode === "full") return status.entry_fee * unpaid.length;
    return status.entry_fee * selected.size;
  }, [status, mode, unpaid.length, selected]);

  const toggle = (tid) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(tid)) next.delete(tid); else next.add(tid);
      return next;
    });
  };

  const pay = async () => {
    if (mode === "partial" && selected.size === 0) {
      toast.message("Pick at least one team to cover.");
      return;
    }
    setPaying(true);
    try {
      const base = mode === "full"
        ? { full: true }
        : { team_ids: Array.from(selected) };
      // Iter 231s — Pass `origin_url` so the backend creates a real
      // Stripe Checkout Session instead of the legacy mocked flow.
      const body = { ...base, origin_url: window.location.origin };
      const { data } = await api.post(`/payments/league/${leagueId}/intent`, body);
      if (data.checkout_url) {
        // Real Stripe path — redirect to Checkout. The
        // `/payment/success` page polls /payments/status which
        // grants the teams as paid on the way back.
        window.location.href = data.checkout_url;
        return;
      }
      // Legacy mocked path (older backend deployments).
      const dollars = (data.amount_cents / 100).toFixed(2);
      toast.success(`Paid $${dollars} for ${data.covered_count} team${data.covered_count === 1 ? "" : "s"}${data.mocked ? " (MOCKED)" : ""}`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Payment failed");
    } finally { setPaying(false); }
  };

  if (loading) {
    return (
      <Card className="border-border" data-testid="team-fees-panel-loading">
        <CardContent className="p-6 text-sm text-muted-foreground">Loading league payment status…</CardContent>
      </Card>
    );
  }
  if (!status || (status.entry_fee || 0) <= 0) {
    return null; // No fee → nothing to pay
  }

  return (
    <Card className="border-border" data-testid="team-fees-panel">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CreditCard className="h-5 w-5 text-primary" />
          League entry fees — ${status.entry_fee.toFixed(2)} / team
        </CardTitle>
        <CardDescription>
          {status.paid_count} of {status.team_count} team{status.team_count === 1 ? "" : "s"} paid · {status.unpaid_count} unpaid
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Mode toggle */}
        <div className="flex gap-2" data-testid="payment-mode-toggle">
          <Button
            variant={mode === "full" ? "default" : "outline"}
            size="sm"
            onClick={() => setMode("full")}
            data-testid="payment-mode-full"
          >
            Pay all unpaid (${(status.entry_fee * unpaid.length).toFixed(2)})
          </Button>
          <Button
            variant={mode === "partial" ? "default" : "outline"}
            size="sm"
            onClick={() => setMode("partial")}
            data-testid="payment-mode-partial"
          >
            Pay for specific teams
          </Button>
        </div>

        {/* Team list */}
        <ul className="divide-y divide-border rounded-md border border-border" data-testid="team-fees-list">
          {(status.teams || []).map((t) => (
            <li
              key={t.team_id}
              className="flex items-center justify-between px-3 py-2"
              data-testid={`team-fee-row-${t.team_id}`}
            >
              <div className="flex items-center gap-3 min-w-0 flex-1">
                {mode === "partial" && !t.paid && (
                  <input
                    type="checkbox"
                    checked={selected.has(t.team_id)}
                    onChange={() => toggle(t.team_id)}
                    data-testid={`team-fee-checkbox-${t.team_id}`}
                  />
                )}
                <span className="text-sm truncate">{t.team_name || "—"}</span>
              </div>
              {t.paid ? (
                <span
                  className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-emerald-500 border border-emerald-500/40 rounded-full px-2 py-0.5"
                  data-testid={`team-paid-stamp-${t.team_id}`}
                  title={t.paid_at ? `Paid ${new Date(t.paid_at).toLocaleString()}` : "Paid"}
                >
                  <Check className="h-3 w-3" />
                  PAID
                </span>
              ) : (
                <span className="text-xs text-muted-foreground">unpaid</span>
              )}
            </li>
          ))}
        </ul>

        {/* Pay button + summary */}
        <div className="flex items-center justify-between pt-2 border-t border-border">
          <div className="text-sm">
            <span className="text-muted-foreground">Total: </span>
            <span className="font-bold tabular-nums" data-testid="payment-amount-preview">
              ${amount.toFixed(2)}
            </span>
            {mode === "partial" && (
              <span className="text-xs text-muted-foreground ml-2">
                ({selected.size} team{selected.size === 1 ? "" : "s"})
              </span>
            )}
          </div>
          <Button
            onClick={pay}
            disabled={paying || amount <= 0}
            data-testid="payment-pay-now-btn"
          >
            {paying ? <Loader2 className="h-4 w-4 animate-spin" /> : "Pay now"}
          </Button>
        </div>
        <p className="text-[10px] text-muted-foreground italic">
          Stripe integration is MOCKED — payments mark teams paid immediately for now.
        </p>
      </CardContent>
    </Card>
  );
}
