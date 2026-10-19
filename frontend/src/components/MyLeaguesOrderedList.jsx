import LeaveLeagueDialog from '@/components/LeaveLeagueDialog';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '@/lib/api';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { GripVertical, Loader2, Trophy, Users as UsersIcon, ArrowRight, MoreVertical, EyeOff, Star } from 'lucide-react';
// Iter 230av — Generic swipe-to-action primitive for the dashboard
// list. Swipe RIGHT → set as default (pins to position 0 in the
// saved order + activates immediately); swipe LEFT → hide.
import SwipeableRow from '@/components/SwipeableRow';
import { useActiveLeague } from '@/hooks/use-active-league';
// Iter 230aw — One-time onboarding pulse for the swipe gestures.
import useOnboardingHint from '@/hooks/use-onboarding-hint';
// Iter 232N.23 — Read the parent SortableSections' customize state so
// we can disable the row-level HTML5 drag + swipe gestures while the
// user is trying to reorder the WHOLE widget on the dashboard.
import { useSortableCustomize } from '@/components/SortableSections';

const ORDER_KEY = 'dd_league_order_v1';

function loadSavedOrder() {
  try {
    const raw = localStorage.getItem(ORDER_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function saveOrder(ids) {
  try { localStorage.setItem(ORDER_KEY, JSON.stringify(ids)); } catch (e) { /* noop */ }
  // Iter 230am — Persist server-side too so the order follows the
  // user across devices. Best-effort; localStorage still has it on
  // failure.
  api.put('/notifications/preferences/league-order', { ordered_ids: ids })
    .catch(() => { /* noop */ });
}

function fmtScoring(v) {
  return (v || '').replace(/_/g, ' ').toUpperCase();
}

export default function MyLeaguesOrderedList() {
  const [leagues, setLeagues] = useState([]);
  const [leaving, setLeaving] = useState(null);
  const leaveReturnFocus = useRef(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [retry, setRetry] = useState(0);
  // Iter 231i — Surface a "Recently hidden" indicator so accidental
  // swipe-to-hide actions remain obvious + recoverable from the
  // Dashboard without users having to hunt through Settings.
  const [hiddenCount, setHiddenCount] = useState(0);
  const [dragId, setDragId] = useState(null);
  const [dragOverId, setDragOverId] = useState(null);
  // Iter 230av — Pull the active league + switchLeague helper so a
  // swipe-right can immediately make a league the default (active +
  // pinned to position 0 in the saved order).
  const { leagueId: activeLeagueId, switchLeague } = useActiveLeague();
  // Iter 230av — Detect coarse-pointer (touch) devices so we can
  // disable the conflicting HTML5 `draggable` reorder on mobile (the
  // browser's drag start intercepts pointerdown before the
  // SwipeableRow's gesture engine can lock in). Desktop / mouse users
  // keep the drag-to-reorder affordance; mobile users get the swipe
  // gestures + the ⋯ menu instead.
  const isTouch = typeof window !== 'undefined'
    && !!window.matchMedia
    && window.matchMedia('(pointer: coarse)').matches;
  // Iter 230aw — One-time pulse on the first row so touch users
  // discover the swipe gestures.
  const [hintActive, markHintShown] = useOnboardingHint('my-leagues');
  // Iter 232N.23 — When the dashboard is in Customize layout mode,
  // suppress the widget's OWN row-level drag + swipe gestures so the
  // whole section can be grabbed for widget reorder. Without this,
  // HTML5 native `draggable` on each row wins the pointer event first
  // and the parent dnd-kit section drag never activates.
  const customizingLayout = useSortableCustomize();

  useEffect(() => {
    const refresh = () => setRetry(value => value + 1);
    const storage = event => { if (event.key === 'dd_leagues_revision') refresh(); };
    window.addEventListener('dd:leagues-changed', refresh);window.addEventListener('storage', storage);
    return () => {window.removeEventListener('dd:leagues-changed', refresh);window.removeEventListener('storage', storage);};
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(false);
    // Iter 230am — Fetch leagues + the server-side order preference
    // in parallel. Server order wins; localStorage is the fallback.
    Promise.all([
      api.get('/leagues?my_leagues=true&exclude_archived=true&exclude_test=true'),
      api.get('/notifications/preferences').catch(() => ({ data: null })),
    ])
      .then(([leaguesRes, prefsRes]) => {
        if (!active) return;
        const data = leaguesRes.data;
        const serverOrder = prefsRes.data?.league_order;
        // Iter 231i — Track the count of currently-hidden leagues so
        // the Dashboard can advertise their existence.
        const hidden = Array.isArray(prefsRes.data?.hidden_league_ids)
          ? prefsRes.data.hidden_league_ids
          : Array.isArray(prefsRes.data?.hidden_leagues)
            ? prefsRes.data.hidden_leagues
            : [];
        setHiddenCount(hidden.length);
        const savedOrder = Array.isArray(serverOrder) && serverOrder.length
          ? serverOrder
          : loadSavedOrder();
        if (Array.isArray(serverOrder) && serverOrder.length) {
          try { localStorage.setItem(ORDER_KEY, JSON.stringify(serverOrder)); } catch (e) { /* noop */ }
        }
        const byId = {};
        (data || []).forEach(l => { byId[l.id] = l; });
        const ordered = [
          ...savedOrder.map(id => byId[id]).filter(Boolean),
          ...(data || []).filter(l => !savedOrder.includes(l.id)),
        ];
        setLeagues(ordered);
      })
      .catch(() => { if (active) setLoadError(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [retry]);

  const onDragStart = (e, id) => {
    setDragId(id);
    e.dataTransfer.effectAllowed = 'move';
  };
  const onDragOver = (e, id) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dragOverId !== id) setDragOverId(id);
  };
  const onDragLeave = () => setDragOverId(null);
  const onDrop = (e, targetId) => {
    e.preventDefault();
    if (!dragId || dragId === targetId) return;
    setLeagues(prev => {
      const next = [...prev];
      const fromIdx = next.findIndex(l => l.id === dragId);
      const toIdx = next.findIndex(l => l.id === targetId);
      if (fromIdx < 0 || toIdx < 0) return prev;
      const [moved] = next.splice(fromIdx, 1);
      next.splice(toIdx, 0, moved);
      saveOrder(next.map(l => l.id));
      return next;
    });
    setDragId(null);
    setDragOverId(null);
  };
  const onDragEnd = () => { setDragId(null); setDragOverId(null); };

  // Iter 230h — Hide league from dashboard. Persists to the user's
  // notification_preferences.hidden_league_ids list and immediately
  // removes the row locally so the surface declutters without a refetch.
  // Iter 231i — Sonner toast now offers a 5-second Undo action so an
  // accidental swipe-to-hide is one click away from being reversed.
  const handleHideLeague = async (leagueId, leagueName) => {
    const prev = leagues;
    setLeagues((cur) => cur.filter((l) => l.id !== leagueId));
    setHiddenCount((c) => c + 1);
    try {
      await api.put('/notifications/preferences/league-hide', {
        league_id: leagueId,
        hidden: true,
      });
      toast.success(`${leagueName || 'League'} hidden from dashboard`, {
        description: 'Click Undo to restore. Otherwise manage anytime from Settings.',
        duration: 5000,
        action: {
          label: 'Undo',
          onClick: async () => {
            try {
              await api.put('/notifications/preferences/league-hide', {
                league_id: leagueId,
                hidden: false,
              });
              setLeagues(prev);
              setHiddenCount((c) => Math.max(0, c - 1));
              toast.success(`${leagueName || 'League'} restored`);
            } catch {
              toast.error("Couldn't undo hide — open Settings to restore.");
            }
          },
        },
      });
    } catch (e) {
      setLeagues(prev);
      setHiddenCount((c) => Math.max(0, c - 1));
      toast.error("Couldn't hide that league");
    }
  };

  // Iter 230av — Set a league as the user's default. Pins it to
  // position 0 in the saved order (so the switcher lands here on
  // future loads), and immediately activates it for the current
  // session via `switchLeague`.
  const handleSetDefault = (leagueId, leagueName) => {
    if (leagueId === activeLeagueId && leagues[0]?.id === leagueId) {
      toast.info(`${leagueName || 'League'} is already your default`);
      return;
    }
    setLeagues((prev) => {
      const target = prev.find((l) => l.id === leagueId);
      if (!target) return prev;
      const rest = prev.filter((l) => l.id !== leagueId);
      const next = [target, ...rest];
      saveOrder(next.map((l) => l.id));
      return next;
    });
    try { switchLeague?.(leagueId); } catch { /* noop */ }
    toast.success(`${leagueName || 'League'} set as default`, {
      description: 'Now the first league in your switcher.',
    });
  };

  if (loading) {
    return (
      <div className="surface p-6 mb-8 border border-white/5" data-testid="my-leagues-loading">
        <div className="flex items-center gap-2 text-[#A1A1AA]">
          <Loader2 size={16} className="animate-spin" /> Loading your leagues…
        </div>
      </div>
    );
  }

  if (loadError) return <section className="surface p-6 mb-8" aria-label="My leagues">
    <p role="alert">Unable to load your leagues. Please try again.</p>
    <button type="button" className="mt-3 rounded border px-3 py-2" onClick={() => setRetry(value => value + 1)}>Retry loading leagues</button>
  </section>;
  if (!leagues.length) return <section className="surface p-6 mb-8" aria-label="My leagues"><h2>My Leagues</h2><p>You have no visible leagues yet.</p></section>;

  return (
    <div data-testid="my-leagues-ordered" className="mb-8">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <Trophy size={18} className="text-[#00D2FF]" />
          <h2 className="font-heading text-xl font-bold text-white tracking-wide">
            MY LEAGUES
          </h2>
          <Badge className="bg-white/5 border-white/10 text-[#A1A1AA] text-[10px]">
            {leagues.length} {leagues.length === 1 ? 'LEAGUE' : 'LEAGUES'}
          </Badge>
          {/* Iter 231i — Recently hidden indicator. Clicking opens the
              notification preferences modal where the user can unhide. */}
          {hiddenCount > 0 && (
            <button
              type="button"
              onClick={() => {
                try {
                  window.dispatchEvent(new CustomEvent('open-notification-settings'));
                } catch { /* noop */ }
              }}
              className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-md border border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 transition-colors"
              data-testid="my-leagues-hidden-indicator"
              title="You have hidden leagues — click to manage in Settings"
            >
              {hiddenCount} hidden — restore
            </button>
          )}
        </div>
        <span className="text-[11px] text-[#52525B] italic hidden sm:block">
          {customizingLayout
            ? 'Customize mode — drag the whole card to reorder widgets'
            : 'Drag to reorder • your preference is saved locally'}
        </span>
      </div>

      <div className="space-y-2">
        {leagues.map((lg, idx) => {
          const isDragging = dragId === lg.id;
          const isDragOver = dragOverId === lg.id;
          // Iter 230av — Pre-compute swipe action flags. Right-swipe
          // is a no-op when the league is already pinned + active
          // (we still let the gesture commit so the user gets a
          // "already default" toast for clarity).
          const isDefault = (leagues[0]?.id === lg.id) && (lg.id === activeLeagueId);
          // Iter 232N.23 — Row body extracted so we can either drop it
          // straight in (customize mode → the outer dashboard section
          // owns all pointer events) or wrap it in SwipeableRow +
          // HTML5-draggable behaviour (normal mode).
          const rowBody = (
            <div
              draggable={!isTouch && !customizingLayout}
              onDragStart={(isTouch || customizingLayout) ? undefined : (e) => onDragStart(e, lg.id)}
              onDragOver={(isTouch || customizingLayout) ? undefined : (e) => onDragOver(e, lg.id)}
              onDragLeave={(isTouch || customizingLayout) ? undefined : onDragLeave}
              onDrop={(isTouch || customizingLayout) ? undefined : (e) => onDrop(e, lg.id)}
              onDragEnd={(isTouch || customizingLayout) ? undefined : onDragEnd}
              data-testid={`my-leagues-row-${lg.id}`}
              className={`surface border border-white/5 p-3 flex items-center gap-3 transition-all select-none ${
                isDragging ? 'opacity-50 border-[#00D2FF]/50' : ''
              } ${
                isDragOver && !isDragging ? 'border-[#00D2FF] bg-[#00D2FF]/5' : ''
              } hover:border-[#00D2FF]/40 ${(isTouch || customizingLayout) ? '' : 'cursor-grab active:cursor-grabbing'}`}
            >
              <GripVertical size={16} className="text-[#52525B] shrink-0" />
              <div className="min-w-0 flex-1">
                <Link
                  to={`/leagues/${lg.id}`}
                  data-testid={`my-leagues-link-${lg.id}`}
                  onClick={(e) => e.stopPropagation()}
                  className="text-white font-bold text-sm hover:text-[#00D2FF] transition-colors block truncate"
                >
                  {lg.name}
                </Link>
                <div className="flex items-center gap-2 text-[11px] text-[#A1A1AA] mt-0.5 flex-wrap">
                  <span className="uppercase tracking-wider text-[#52525B]">
                    {fmtScoring(lg.scoring_format)}
                  </span>
                  <span className="text-[#52525B]">·</span>
                  <span className="uppercase tracking-wider text-[#52525B]">
                    {(lg.format || '').toUpperCase()}
                  </span>
                  <span className="text-[#52525B]">·</span>
                  <span className="flex items-center gap-1">
                    <UsersIcon size={10} />
                    {lg.current_teams}/{lg.max_teams}
                  </span>
                  {lg.commissioner_vacant && <Badge variant="outline">Commissioner vacant</Badge>}
                  {lg.status && (
                    <>
                      <span className="text-[#52525B]">·</span>
                      <Badge
                        variant="outline"
                        className={`text-[10px] h-4 ${
                          lg.status === 'active'
                            ? 'border-emerald-500/40 text-emerald-400 bg-emerald-500/10'
                            : 'border-white/10 text-[#A1A1AA] bg-white/5'
                        }`}
                      >
                        {(lg.status || '').toUpperCase()}
                      </Badge>
                    </>
                  )}
                </div>
              </div>
              <Link
                to={`/leagues/${lg.id}`}
                data-testid={`my-leagues-open-${lg.id}`}
                onClick={(e) => e.stopPropagation()}
                className="text-[#00D2FF] text-xs font-semibold flex items-center gap-1 hover:gap-2 transition-all shrink-0"
              >
                Open <ArrowRight size={12} />
              </Link>
              <DropdownMenu>
                <DropdownMenuTrigger
                  asChild
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    type="button"
                    data-testid={`my-leagues-menu-btn-${lg.id}`}
                    aria-label="League options"
                    onClick={event => { leaveReturnFocus.current = event.currentTarget; }}
                    className="h-11 w-11 rounded-md text-[#52525B] hover:text-white hover:bg-white/5 flex items-center justify-center shrink-0 transition-colors"
                    onPointerDown={(e) => e.stopPropagation()}
                    draggable={false}
                  >
                    <MoreVertical size={14} />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="end"
                  className="bg-[#141414] border border-white/10 text-white"
                >
                  <DropdownMenuItem
                    onSelect={() => handleSetDefault(lg.id, lg.name)}
                    data-testid={`my-leagues-default-${lg.id}`}
                    className="focus:bg-amber-500/10 focus:text-amber-200 cursor-pointer"
                  >
                    <Star size={14} className="mr-2" />
                    Set as default
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={() => handleHideLeague(lg.id, lg.name)}
                    data-testid={`my-leagues-hide-${lg.id}`}
                    className="text-rose-300 focus:bg-rose-500/10 focus:text-rose-200 cursor-pointer"
                  >
                    <EyeOff size={14} className="mr-2" />
                    Hide from my dashboard
                  </DropdownMenuItem>
                  <DropdownMenuItem onSelect={() => setLeaving(lg)} className="min-h-11 text-rose-300 cursor-pointer" data-testid={`my-leagues-leave-${lg.id}`}>Leave league</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          );
          if (customizingLayout) {
            return <div key={lg.id}>{rowBody}</div>;
          }
          return (
            <SwipeableRow
              key={lg.id}
              testId={`my-leagues-swipe-row-${lg.id}`}
              showOnboardingHint={hintActive && idx === 0}
              onHintShown={markHintShown}
              rightAction={{
                label: isDefault ? 'Already default' : 'Set as default',
                icon: <Star className="h-4 w-4" />,
                bg: 'bg-amber-500/25',
                color: 'text-amber-200',
                testId: `my-leagues-swipe-default-hint-${lg.id}`,
              }}
              leftAction={{
                label: 'Hide',
                icon: <EyeOff className="h-4 w-4" />,
                bg: 'bg-rose-600/25',
                color: 'text-rose-200',
                testId: `my-leagues-swipe-hide-hint-${lg.id}`,
              }}
              onSwipeRight={() => { markHintShown(); handleSetDefault(lg.id, lg.name); }}
              onSwipeLeft={() => { markHintShown(); handleHideLeague(lg.id, lg.name); }}
            >
              {rowBody}
            </SwipeableRow>
          );
        })}
      </div>
      <LeaveLeagueDialog league={leaving} onClose={() => setLeaving(null)} returnFocus={leaveReturnFocus} onLeft={id => {setLeagues(previous => previous.filter(league => league.id !== id));setLeaving(null);}} />
    </div>
  );
}
