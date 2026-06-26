import { useEffect, useState } from 'react';
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
import { GripVertical, Loader2, Trophy, Users as UsersIcon, ArrowRight, MoreVertical, EyeOff } from 'lucide-react';

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
  const [loading, setLoading] = useState(true);
  const [dragId, setDragId] = useState(null);
  const [dragOverId, setDragOverId] = useState(null);

  useEffect(() => {
    // Iter 230am — Fetch leagues + the server-side order preference
    // in parallel. Server order wins; localStorage is the fallback.
    Promise.all([
      api.get('/leagues?my_leagues=true&exclude_archived=true&exclude_test=true'),
      api.get('/notifications/preferences').catch(() => ({ data: null })),
    ])
      .then(([leaguesRes, prefsRes]) => {
        const data = leaguesRes.data;
        const serverOrder = prefsRes.data?.league_order;
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
      .catch(() => setLeagues([]))
      .finally(() => setLoading(false));
  }, []);

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
  // removes the row locally so the surface decltters without a refetch.
  const handleHideLeague = async (leagueId, leagueName) => {
    const prev = leagues;
    setLeagues((cur) => cur.filter((l) => l.id !== leagueId));
    try {
      await api.put('/notifications/preferences/league-hide', {
        league_id: leagueId,
        hidden: true,
      });
      toast.success(`${leagueName || 'League'} hidden from dashboard`, {
        description: 'Restore any time from Notification Settings.',
      });
    } catch (e) {
      setLeagues(prev);
      toast.error("Couldn't hide that league");
    }
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

  if (!leagues.length) return null;

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
        </div>
        <span className="text-[11px] text-[#52525B] italic hidden sm:block">
          Drag to reorder • your preference is saved locally
        </span>
      </div>

      <div className="space-y-2">
        {leagues.map((lg) => {
          const isDragging = dragId === lg.id;
          const isDragOver = dragOverId === lg.id;
          return (
            <div
              key={lg.id}
              draggable
              onDragStart={(e) => onDragStart(e, lg.id)}
              onDragOver={(e) => onDragOver(e, lg.id)}
              onDragLeave={onDragLeave}
              onDrop={(e) => onDrop(e, lg.id)}
              onDragEnd={onDragEnd}
              data-testid={`my-leagues-row-${lg.id}`}
              className={`surface border border-white/5 p-3 flex items-center gap-3 transition-all select-none ${
                isDragging ? 'opacity-50 border-[#00D2FF]/50' : ''
              } ${
                isDragOver && !isDragging ? 'border-[#00D2FF] bg-[#00D2FF]/5' : ''
              } hover:border-[#00D2FF]/40 cursor-grab active:cursor-grabbing`}
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
                    className="h-7 w-7 rounded-md text-[#52525B] hover:text-white hover:bg-white/5 flex items-center justify-center shrink-0 transition-colors"
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
                    onSelect={() => handleHideLeague(lg.id, lg.name)}
                    data-testid={`my-leagues-hide-${lg.id}`}
                    className="text-rose-300 focus:bg-rose-500/10 focus:text-rose-200 cursor-pointer"
                  >
                    <EyeOff size={14} className="mr-2" />
                    Hide from my dashboard
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          );
        })}
      </div>
    </div>
  );
}
