// Iter 231j — Cross-league pending-trades banner shown at the top of the
// dashboard. Splits open trades into two action buckets:
//
//   - "Pending Response" — user is the recipient on a `proposed` trade;
//     the banner CTA opens the trade detail so they can Accept / Reject.
//   - "Pending Review"   — user is the proposer on a `pending` trade;
//     the banner CTA opens the trade detail so they can monitor the
//     review window or cancel.
//
// Renders nothing when both buckets are empty so the dashboard stays
// tidy for users with no open trades.
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '@/lib/api';
import { ArrowRightLeft, Clock, AlertCircle } from 'lucide-react';

function relativeTime(iso) {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const seconds = Math.round((then - Date.now()) / 1000);
  const abs = Math.abs(seconds);
  const future = seconds > 0;
  if (abs < 60) return future ? `in <1m` : 'just now';
  if (abs < 3600) {
    const m = Math.round(abs / 60);
    return future ? `in ${m}m` : `${m}m ago`;
  }
  if (abs < 86400) {
    const h = Math.round(abs / 3600);
    return future ? `in ${h}h` : `${h}h ago`;
  }
  const d = Math.round(abs / 86400);
  return future ? `in ${d}d` : `${d}d ago`;
}

function TradeRow({ trade, sideLabel, icon: Icon }) {
  return (
    <Link
      to={`/transactions/trade/${trade.trade_id}`}
      data-testid={`pending-trade-row-${trade.trade_id}`}
      className="flex items-center gap-3 rounded-md bg-white/5 hover:bg-white/10 transition-colors px-3 py-2 group"
    >
      <Icon className="h-4 w-4 text-[#00D2FF] shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-sm text-white truncate">
          <span className="font-semibold">{trade.proposer_team_name || '—'}</span>
          <span className="text-[#52525B] mx-1.5">↔</span>
          <span className="font-semibold">{trade.target_team_name || '—'}</span>
        </p>
        <p className="text-xs text-[#A1A1AA] truncate">
          {sideLabel}
          {trade.asset_count ? ` · ${trade.asset_count} asset${trade.asset_count === 1 ? '' : 's'}` : ''}
          {trade.processes_at ? ` · auto-processes ${relativeTime(trade.processes_at)}` : ''}
          {!trade.processes_at && trade.submitted_at ? ` · proposed ${relativeTime(trade.submitted_at)}` : ''}
        </p>
      </div>
      <span className="text-xs text-[#00D2FF] opacity-0 group-hover:opacity-100 transition-opacity">
        Open →
      </span>
    </Link>
  );
}

export default function PendingTradesBanner() {
  const [data, setData] = useState({ awaiting_response: [], in_review: [] });
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .get('/users/me/pending-trades')
      .then((res) => {
        if (cancelled) return;
        setData(res.data || { awaiting_response: [], in_review: [] });
      })
      .catch(() => {
        /* silent — banner is best-effort */
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!loaded) return null;
  const awaiting = data.awaiting_response || [];
  const inReview = data.in_review || [];
  if (awaiting.length === 0 && inReview.length === 0) return null;

  return (
    <div
      className="mb-6 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4"
      data-testid="pending-trades-banner"
    >
      <div className="flex items-center gap-2 mb-3">
        <ArrowRightLeft className="h-4 w-4 text-amber-300" />
        <h3 className="text-sm font-semibold text-amber-200 uppercase tracking-wider">
          Open trades need your attention
        </h3>
      </div>

      {awaiting.length > 0 && (
        <div className="mb-3" data-testid="pending-trades-awaiting-response">
          <p className="text-xs text-amber-200/80 mb-2 flex items-center gap-1.5">
            <AlertCircle className="h-3 w-3" />
            <span className="font-semibold">{awaiting.length}</span> pending response &mdash; review the offer and Accept or Reject
          </p>
          <div className="space-y-1.5">
            {awaiting.slice(0, 3).map((t) => (
              <TradeRow key={t.trade_id} trade={t} sideLabel="You are the recipient" icon={AlertCircle} />
            ))}
            {awaiting.length > 3 && (
              <p className="text-xs text-[#A1A1AA] pl-7">
                + {awaiting.length - 3} more awaiting response
              </p>
            )}
          </div>
        </div>
      )}

      {inReview.length > 0 && (
        <div data-testid="pending-trades-in-review">
          <p className="text-xs text-cyan-200/80 mb-2 flex items-center gap-1.5">
            <Clock className="h-3 w-3" />
            <span className="font-semibold">{inReview.length}</span> pending review &mdash; accepted and now in the league review window
          </p>
          <div className="space-y-1.5">
            {inReview.slice(0, 3).map((t) => (
              <TradeRow key={t.trade_id} trade={t} sideLabel="Your proposal — under review" icon={Clock} />
            ))}
            {inReview.length > 3 && (
              <p className="text-xs text-[#A1A1AA] pl-7">
                + {inReview.length - 3} more under review
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
