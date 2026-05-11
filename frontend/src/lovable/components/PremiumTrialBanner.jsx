// @ts-nocheck
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Sparkles, Clock, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";

/**
 * Banner that surfaces when the league has premium features enabled
 * but hasn't paid. Shows a live countdown:
 *   - Days remaining when > 24h left.
 *   - Hours remaining on the last day.
 *
 * When trial has expired, the banner switches to a hard error tone
 * stating premium features are now read-only until payment.
 *
 * Pass `leagueId`. The component fetches `/leagues/{id}/premium-status`,
 * refreshes every 60s, and re-renders.
 *
 * Renders nothing if the league is paid OR has no premium features
 * enabled.
 */
export default function PremiumTrialBanner({ leagueId, isCommissioner = false }) {
  const [status, setStatus] = useState(null);
  const [now, setNow] = useState(Date.now());
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    const load = () =>
      api.get(`/leagues/${leagueId}/premium-status`)
        .then(({ data }) => !cancelled && setStatus(data))
        .catch(() => {});
    load();
    const interval = setInterval(load, 60_000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [leagueId]);

  // Tick every 30s so the countdown stays live
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  if (!status || dismissed) return null;
  if (status.paid) return null;
  if (!status.enabled_features?.length) return null;

  // Compute live seconds_left from trial_expires_at so the UI feels responsive
  const expiresAt = status.trial_expires_at ? new Date(status.trial_expires_at).getTime() : null;
  const secondsLeft = expiresAt ? Math.max(0, Math.floor((expiresAt - now) / 1000)) : status.trial_seconds_left ?? 0;
  const expired = status.trial_expired || secondsLeft <= 0;
  const days = Math.floor(secondsLeft / 86400);
  const hours = Math.floor((secondsLeft % 86400) / 3600);
  const minutes = Math.floor((secondsLeft % 3600) / 60);

  // Friendly time string
  let countdown;
  if (expired) countdown = "Trial ended";
  else if (days >= 1) countdown = `${days} day${days === 1 ? "" : "s"} left`;
  else if (hours >= 1) countdown = `${hours} hr ${minutes} min left`;
  else countdown = `${minutes} min left`;

  const features = status.enabled_features.map(f => f.replace(/_/g, " ")).join(" · ");

  const tone = expired
    ? "border-rose-500/40 bg-rose-500/10 text-rose-100"
    : days >= 3
      ? "border-amber-500/40 bg-amber-500/10 text-amber-100"
      : "border-orange-500/50 bg-orange-500/15 text-orange-50";

  return (
    <div
      data-testid={`premium-trial-banner-${leagueId}`}
      className={`mb-4 flex items-start gap-3 p-4 rounded-xl border ${tone}`}
    >
      <Sparkles className="h-5 w-5 flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold">
            {expired ? "Premium trial has ended" : "Premium trial active"}
          </span>
          <span
            data-testid={`premium-trial-countdown-${leagueId}`}
            className={`text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${
              expired ? "bg-rose-500/30 border-rose-300/40" : "bg-black/30 border-white/20"
            }`}
          >
            <Clock className="h-3 w-3 inline mr-1 -mt-0.5" />
            {countdown}
          </span>
        </div>
        <p className="text-xs mt-1 opacity-90">
          {expired
            ? <>Player contract information will not be updated until premium is paid for. Currently enabled: <strong>{features}</strong>.</>
            : <>You have <strong>{countdown}</strong> to pay the premium fee, otherwise <strong>{features}</strong> will become read-only and player contracts will stop updating.</>}
        </p>
        {isCommissioner && (
          <div className="flex gap-2 mt-3 flex-wrap">
            <Button
              asChild
              size="sm"
              className="bg-white text-black hover:bg-white/90"
              data-testid={`premium-trial-pay-${leagueId}`}
            >
              <Link to={`/leagues/${leagueId}/billing`}>
                Set up payment
              </Link>
            </Button>
            {!expired && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setDismissed(true)}
                className="text-current hover:bg-white/5"
                data-testid={`premium-trial-dismiss-${leagueId}`}
              >
                Dismiss
              </Button>
            )}
          </div>
        )}
      </div>
      {!isCommissioner && !expired && (
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="text-current opacity-70 hover:opacity-100"
          data-testid={`premium-trial-dismiss-${leagueId}`}
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
