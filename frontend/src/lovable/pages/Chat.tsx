// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
  DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Send, Users, Hash, Plus, BellOff, Bell, Trash2, MoreHorizontal, Loader2, Check,
  UserPlus, Archive,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { useAuth } from "@/contexts/AuthContext";
import { useChatUnread } from "@/hooks/use-chat-unread";
// Iter 230au — Generic swipe-to-action primitive for the channel list.
import SwipeableRow from "@/components/SwipeableRow";
// Iter 230aw — First-time onboarding pulse for the swipe gestures.
import useOnboardingHint from "@/hooks/use-onboarding-hint";
import ReportUserButton from "@/components/ReportUserButton";
// Iter 232b — Live presence on the League Chat header + per-member dots.
import { useLeagueSocket } from "@/hooks/use-socket";
import { OnlinePresenceBadge, OnlineDot } from "@/components/OnlinePresenceBadge";

const MUTE_OPTIONS = [
  { value: "30m", label: "30 minutes" },
  { value: "1h", label: "1 hour" },
  { value: "4h", label: "4 hours" },
  { value: "12h", label: "12 hours" },
  { value: "24h", label: "24 hours" },
  { value: "indefinite", label: "Until I unmute" },
];

function fmtTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const now = new Date();
    const same = d.toDateString() === now.toDateString();
    if (same) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return d.toLocaleDateString([], { month: "short", day: "numeric" }) +
      " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
}

function initialsFor(name) {
  if (!name) return "?";
  return name.split(/\s+/).slice(0, 2).map((s) => s[0]?.toUpperCase()).join("");
}

const Chat = () => {
  const { user } = useAuth();
  const { leagueId, league, myLeagues, leagueTeams, myTeam } = useActiveLeague();
  const { refresh: refreshUnread } = useChatUnread();

  // Iter 232b — Subscribe to the league socket room so the header
  // can show how many league members are currently online. The same
  // `onlineUserIds` set is threaded down into the members list so
  // each row gets a live green/grey presence dot. No new backend
  // work — `presence_state` / `user_joined` / `user_left` already
  // emit on every connect/join/leave (see backend/server.py).
  const { onlineUserIds } = useLeagueSocket(leagueId, { userId: user?.id });

  const [channels, setChannels] = useState([]);
  const [maxChannels, setMaxChannels] = useState(12);
  const [members, setMembers] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loadingChans, setLoadingChans] = useState(false);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const [draft, setDraft] = useState("");
  const [creating, setCreating] = useState(false);
  const [newChanName, setNewChanName] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  // Iter 232N.13 — Group DM composer state (multi-team picker).
  const [groupOpen, setGroupOpen] = useState(false);
  const [groupPicked, setGroupPicked] = useState<Record<string, boolean>>({});
  const [groupCreating, setGroupCreating] = useState(false);
  // Iter 230aw — One-time onboarding pulse for the channel swipes.
  const [hintActive, markHintShown] = useOnboardingHint("chat-channels");

  const isCommish = useMemo(() => {
    if (!league || !user) return false;
    return league.commissioner_id === user.id ||
      (league.co_commissioners || []).includes(user.id);
  }, [league, user]);

  // Iter 232N.14 — Show/hide archived channels (per-user state).
  const [showArchived, setShowArchived] = useState(false);

  // ── Load channels ─────────────────────────────────────────
  const loadChannels = useCallback(async () => {
    if (!leagueId) return;
    setLoadingChans(true);
    try {
      const { data } = await api.get(
        `/chat/channels?league_id=${leagueId}&show_archived=${showArchived}`,
      );
      const list = data?.channels || [];
      setChannels(list);
      setMaxChannels(data?.max_channels || 12);
      if (list.length && !list.find((c) => c._id === selectedId)) {
        setSelectedId(list[0]._id);
      }
    } catch (e) {
      console.error("chat load channels", e);
    } finally {
      setLoadingChans(false);
    }
  }, [leagueId, selectedId, showArchived]);

  useEffect(() => { loadChannels(); }, [loadChannels]);

  // Iter 232N.14 — Toggle archive state for a channel (per-user).
  const handleToggleArchive = async (chan) => {
    try {
      if (chan.archived) {
        await api.delete(`/chat/channels/${chan._id}/archive`);
        toast.success(`Unarchived ${chan.name}`);
      } else {
        await api.post(`/chat/channels/${chan._id}/archive`);
        toast.success(`Archived ${chan.name}`, {
          description: "Toggle 'Show archived' to see it again.",
          duration: 5000,
        });
        if (selectedId === chan._id) setSelectedId(null);
      }
      await loadChannels();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update archive");
    }
  };

  // ── Load members for @mention ─────────────────────────────
  useEffect(() => {
    if (!leagueId) return;
    api.get(`/chat/league/${leagueId}/members`).then(({ data }) => {
      setMembers(data?.members || []);
    }).catch(() => setMembers([]));
  }, [leagueId]);

  // ── Load messages for selected channel ────────────────────
  const loadMessages = useCallback(async () => {
    if (!selectedId) { setMessages([]); return; }
    setLoadingMsgs(true);
    try {
      const { data } = await api.get(`/chat/channels/${selectedId}/messages?limit=200`);
      setMessages(data?.messages || []);
      // Refresh unread count after the read cursor moves server-side.
      refreshUnread();
    } catch (e) {
      console.error("chat load messages", e);
    } finally {
      setLoadingMsgs(false);
    }
  }, [selectedId, refreshUnread]);

  useEffect(() => { loadMessages(); }, [loadMessages]);

  // Poll messages every 10s when on the page.
  useEffect(() => {
    if (!selectedId) return;
    const id = setInterval(loadMessages, 10000);
    return () => clearInterval(id);
  }, [selectedId, loadMessages]);

  const selected = channels.find((c) => c._id === selectedId) || null;

  // Scroll bottom on new messages
  const scrollRef = useRef(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, selectedId]);

  // ── Send message + @mention autocomplete ──────────────────
  const inputRef = useRef(null);
  const [mention, setMention] = useState({ open: false, query: "" });

  const handleDraftChange = (e) => {
    const v = e.target.value;
    setDraft(v);
    // detect @ at end of last token
    const m = /(^|\s)@([\w-]*)$/.exec(v);
    if (m) setMention({ open: true, query: m[2].toLowerCase() });
    else setMention({ open: false, query: "" });
  };

  const insertMention = (memberName) => {
    const v = draft;
    const next = v.replace(/(^|\s)@([\w-]*)$/, (_, lead) => `${lead}@${memberName} `);
    setDraft(next);
    setMention({ open: false, query: "" });
    inputRef.current?.focus();
  };

  const filteredMentions = useMemo(() => {
    if (!mention.open) return [];
    const q = mention.query;
    return members
      .filter((m) => !q || m.team_name.toLowerCase().includes(q) || m.owner_name.toLowerCase().includes(q))
      .slice(0, 6);
  }, [members, mention]);

  const handleSend = async () => {
    const text = draft.trim();
    if (!text || !selectedId) return;
    try {
      await api.post(`/chat/channels/${selectedId}/messages`, { content: text });
      setDraft("");
      setMention({ open: false, query: "" });
      await loadMessages();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not send message");
    }
  };

  // ── Mute / unmute ─────────────────────────────────────────
  // Iter 231i — Mute toast now includes a 5-second Undo action so an
  // accidental swipe-to-mute is one click away from being reversed.
  const handleMute = async (chanId, duration) => {
    try {
      await api.post(`/chat/channels/${chanId}/mute`, { duration });
      const isMuting = !!duration;
      const label = isMuting
        ? `Muted ${duration === "indefinite" ? "indefinitely" : `for ${duration}`}`
        : "Unmuted";
      toast.success(label, {
        duration: 5000,
        action: isMuting
          ? {
              label: "Undo",
              onClick: async () => {
                try {
                  await api.post(`/chat/channels/${chanId}/mute`, { duration: null });
                  toast.success("Unmuted");
                  loadChannels();
                  refreshUnread();
                } catch (e) {
                  toast.error(e?.response?.data?.detail || "Could not undo mute");
                }
              },
            }
          : undefined,
      });
      loadChannels();
      refreshUnread();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update mute");
    }
  };

  // ── Create channel (commissioner-only) ────────────────────
  const handleCreateChannel = async () => {
    if (!leagueId || !newChanName.trim()) return;
    setCreating(true);
    try {
      await api.post(`/chat/channels`, { league_id: leagueId, name: newChanName.trim() });
      toast.success(`#${newChanName.trim()} created`);
      setNewChanName("");
      setCreateOpen(false);
      await loadChannels();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not create channel");
    } finally {
      setCreating(false);
    }
  };

  // ── Delete channel (commissioner-only, non-default) ───────
  const handleDeleteChannel = async (chan) => {
    if (chan.is_default) return;
    if (chan.kind === "dm" || chan.kind === "group_dm") return;
    if (!window.confirm(`Delete #${chan.name}? This will remove all messages.`)) return;
    try {
      await api.delete(`/chat/channels/${chan._id}`);
      toast.success(`#${chan.name} deleted`);
      if (selectedId === chan._id) setSelectedId(null);
      await loadChannels();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete channel");
    }
  };

  // Iter 232N.13 — Create/open a 3+ team group DM. Auto-selects the
  // caller's own team (they must always be in the group they open).
  const handleCreateGroupDm = async () => {
    if (!leagueId || !myTeam?.id) return;
    const teamIds = Array.from(new Set([
      myTeam.id,
      ...Object.entries(groupPicked)
        .filter(([_, v]) => v)
        .map(([k]) => k),
    ]));
    if (teamIds.length < 3) {
      toast.error("Pick at least 2 other teams to start a group DM");
      return;
    }
    setGroupCreating(true);
    try {
      const { data } = await api.post(`/chat/group-dm`, {
        league_id: leagueId,
        team_ids: teamIds,
      });
      toast.success("Group DM opened");
      setGroupOpen(false);
      setGroupPicked({});
      await loadChannels();
      if (data?._id) setSelectedId(data._id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not open group DM");
    } finally {
      setGroupCreating(false);
    }
  };

  // Iter 230au — Mark all messages in a channel as read without
  // fetching the message list. Powers the swipe-right gesture in the
  // channel sidebar and the row's "Mark as read" affordance.
  const handleMarkChannelRead = async (chanId) => {
    // Optimistic — zero out unread + last_read_at locally.
    setChannels((prev) =>
      prev.map((c) =>
        c._id === chanId ? { ...c, unread: 0, last_read_at: new Date().toISOString() } : c,
      ),
    );
    try {
      await api.post(`/chat/channels/${chanId}/mark-read`);
      refreshUnread();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not mark channel read");
      loadChannels();
    }
  };

  // Iter 230aw — `hintRowId` is computed below from `channelList[0]`
  // / `dmList[0]` so only ONE row across both maps gets the pulse.

  const renderRow = (c) => {
    const isSelected = c._id === selectedId;
    // Iter 230au — Swipe RIGHT to mark all-read (disabled when
    // already at 0 unread or muted, since there's nothing to clear).
    // Swipe LEFT to toggle mute: when currently muted → unmute; when
    // unmuted → mute for 24h (sensible default; long-press the row's
    // ⋯ menu for finer durations).
    const swipeRightDisabled = !(c.unread > 0) || c.muted;
    const swipeLeftAction = c.muted
      ? { label: "Unmute", icon: <Bell className="h-4 w-4" />, bg: "bg-sky-600/25", color: "text-sky-200", testId: `chat-swipe-unmute-hint-${c._id}` }
      : { label: "Mute 24h", icon: <BellOff className="h-4 w-4" />, bg: "bg-amber-600/25", color: "text-amber-200", testId: `chat-swipe-mute-hint-${c._id}` };

    const innerRow = (
      <div
        key={c._id}
        className={`group flex items-center justify-between gap-2 rounded-lg text-sm transition-colors ${
          isSelected ? "bg-primary/10 text-primary" : "hover:bg-secondary text-muted-foreground hover:text-foreground"
        }`}
      >
        <button
          data-testid={
            c.kind === "dm" ? `chat-dm-${c._id}`
            : c.kind === "group_dm" ? `chat-group-dm-${c._id}`
            : `chat-channel-${c.name}`
          }
          onClick={() => setSelectedId(c._id)}
          className="flex-1 flex items-center justify-between px-3 py-2 truncate"
        >
          <span className="flex items-center gap-2 truncate">
            {c.kind === "dm" ? (
              <Avatar className="h-5 w-5"><AvatarFallback className="text-[10px] bg-secondary">{initialsFor(c.name)}</AvatarFallback></Avatar>
            ) : c.kind === "group_dm" ? (
              // Iter 232N.13 — Group DMs use the multi-person icon +
              // a small participant count so 3-way trade threads read
              // differently from 1:1 DMs in the sidebar.
              <span className="relative shrink-0">
                <Users className="h-4 w-4 text-primary" />
                {Array.isArray(c.team_ids) && (
                  <span className="absolute -top-1 -right-2 text-[9px] font-bold text-muted-foreground">
                    {c.team_ids.length}
                  </span>
                )}
              </span>
            ) : (
              <Hash className="h-4 w-4 shrink-0" />
            )}
            <span className="truncate">{c.name}</span>
            {c.muted && <BellOff className="h-3 w-3 text-muted-foreground/70" />}
          </span>
          <span className="flex items-center gap-1">
            {c.unread > 0 && !c.muted && (
              <span
                data-testid={`chat-unread-${c._id}`}
                className="h-5 min-w-5 px-1.5 rounded-full bg-[#FF3B5C] text-white text-[10px] font-bold flex items-center justify-center"
              >
                {c.unread > 99 ? "99+" : c.unread}
              </span>
            )}
          </span>
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              data-testid={`chat-channel-actions-${c._id}`}
              className="opacity-0 group-hover:opacity-100 hover:bg-background/40 rounded p-1 mr-1"
              onClick={(e) => e.stopPropagation()}
            >
              <MoreHorizontal className="h-3.5 w-3.5" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuLabel className="text-xs">{c.muted ? "Muted" : "Mute notifications"}</DropdownMenuLabel>
            {MUTE_OPTIONS.map((opt) => (
              <DropdownMenuItem
                key={opt.value}
                data-testid={`chat-mute-${c._id}-${opt.value}`}
                onClick={() => handleMute(c._id, opt.value)}
              >
                <BellOff className="h-3.5 w-3.5 mr-2" />{opt.label}
              </DropdownMenuItem>
            ))}
            {c.muted && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem data-testid={`chat-unmute-${c._id}`} onClick={() => handleMute(c._id, null)}>
                  <Bell className="h-3.5 w-3.5 mr-2" />Unmute
                </DropdownMenuItem>
              </>
            )}
            {isCommish && c.kind === "channel" && !c.is_default && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  data-testid={`chat-delete-${c._id}`}
                  onClick={() => handleDeleteChannel(c)}
                  className="text-destructive focus:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5 mr-2" />Delete channel
                </DropdownMenuItem>
              </>
            )}
            {/* Iter 232N.14 — Per-user archive so each manager can
                curate their own sidebar without hiding the channel
                from others. Default channels can be archived too. */}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              data-testid={`chat-archive-${c._id}`}
              onClick={() => handleToggleArchive(c)}
            >
              <Archive className="h-3.5 w-3.5 mr-2" />
              {c.archived ? "Unarchive" : "Archive"}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    );
    return (
      <SwipeableRow
        key={c._id}
        testId={`chat-swipe-row-${c._id}`}
        showOnboardingHint={hintActive && c._id === hintRowId}
        onHintShown={markHintShown}
        rightAction={{
          label: "Mark read",
          icon: <Check className="h-4 w-4" />,
          bg: "bg-emerald-600/25",
          color: "text-emerald-200",
          disabled: swipeRightDisabled,
          testId: `chat-swipe-read-hint-${c._id}`,
        }}
        leftAction={swipeLeftAction}
        onSwipeRight={() => { markHintShown(); handleMarkChannelRead(c._id); }}
        onSwipeLeft={() => { markHintShown(); handleMute(c._id, c.muted ? null : "24h"); }}
      >
        {innerRow}
      </SwipeableRow>
    );
  };

  const channelList = channels.filter((c) => c.kind === "channel");
  const dmList = channels.filter((c) => c.kind === "dm");
  // Iter 232N.13 — Group DMs rendered in their own list below the 1:1
  // DMs so managers can distinguish multi-team trade threads at a
  // glance without changing the row layout.
  const groupDmList = channels.filter((c) => c.kind === "group_dm");
  // Iter 230aw — Single row across BOTH lists that gets the
  // onboarding pulse (prefer the first regular channel, fall back to
  // the first DM if the league has none).
  const hintRowId = channelList[0]?._id || dmList[0]?._id || null;
  const channelCap = `${channelList.length}/${maxChannels}`;

  if (!leagueId) {
    return (
      <AppLayout>
        <div className="h-[calc(100vh-3.5rem)] flex items-center justify-center text-muted-foreground">
          {myLeagues?.length === 0 ? "Join a league to start chatting." : "Loading league…"}
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="h-[calc(100vh-3.5rem)] flex" data-testid="chat-page">
        {/* Channels Sidebar */}
        <div className="w-64 border-r border-border bg-card/50 flex flex-col">
          <div className="p-4 border-b border-border">
            <h2 className="font-semibold flex items-center gap-2">
              <Users className="h-4 w-4 text-primary" />
              <span className="truncate">{league?.name || "League Chat"}</span>
            </h2>
            {/* Iter 232b — Live presence pill below the league name.
                Shows how many league members are currently connected
                to the league socket room. Updates in real time as
                managers open/close the page. */}
            <div className="mt-2" data-testid="chat-presence-bar">
              <OnlinePresenceBadge
                onlineUserIds={onlineUserIds}
                label="online"
                testIdSuffix="league-chat"
              />
            </div>
            {/* Iter 232N.14 — Show archived toggle. Per-user state; the
                sidebar defaults to hiding archived threads so long-time
                managers can tidy stale DMs without losing history. */}
            <button
              type="button"
              onClick={() => setShowArchived((v) => !v)}
              className={`mt-3 w-full flex items-center justify-center gap-2 rounded-md border px-2 py-1.5 text-[11px] uppercase tracking-wider font-semibold transition-colors ${
                showArchived
                  ? "bg-sky-500/15 border-sky-500/40 text-sky-300"
                  : "bg-transparent border-border text-muted-foreground hover:text-foreground"
              }`}
              data-testid="chat-show-archived-toggle"
              aria-pressed={showArchived}
            >
              <Archive className="h-3.5 w-3.5" />
              {showArchived ? "Hide archived" : "Show archived"}
            </button>
          </div>

          <ScrollArea className="flex-1 p-3">
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-2 px-2">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Channels <span className="ml-1 text-[10px] opacity-70" data-testid="chat-channel-cap">({channelCap})</span>
                  </h3>
                  {isCommish && (
                    <Dialog open={createOpen} onOpenChange={setCreateOpen}>
                      <DialogTrigger asChild>
                        <button
                          data-testid="chat-new-channel-btn"
                          disabled={channelList.length >= maxChannels}
                          className="hover:bg-secondary rounded p-1 disabled:opacity-40"
                          title={channelList.length >= maxChannels ? `Max ${maxChannels} channels reached` : "New channel"}
                        >
                          <Plus className="h-3.5 w-3.5" />
                        </button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader><DialogTitle>Create channel</DialogTitle></DialogHeader>
                        <div className="space-y-3">
                          <p className="text-sm text-muted-foreground">
                            Lowercase letters, numbers, hyphens. Max 32 characters. Up to {maxChannels} channels per league.
                          </p>
                          <Input
                            data-testid="chat-new-channel-input"
                            placeholder="e.g. waivers-talk"
                            value={newChanName}
                            onChange={(e) => setNewChanName(e.target.value)}
                            maxLength={32}
                          />
                        </div>
                        <DialogFooter>
                          <Button
                            data-testid="chat-new-channel-submit"
                            onClick={handleCreateChannel}
                            disabled={creating || !newChanName.trim()}
                          >
                            {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create"}
                          </Button>
                        </DialogFooter>
                      </DialogContent>
                    </Dialog>
                  )}
                </div>
                <div className="space-y-1" data-testid="chat-channels-list">
                  {loadingChans && <div className="px-2 text-xs text-muted-foreground">Loading…</div>}
                  {!loadingChans && channelList.length === 0 && (
                    <div className="px-2 text-xs text-muted-foreground">No channels yet</div>
                  )}
                  {channelList.map(renderRow)}
                </div>
              </div>

              <div>
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2 px-2">
                  Direct Messages
                </h3>
                <div className="space-y-1" data-testid="chat-dms-list">
                  {dmList.length === 0 && (
                    <div className="px-2 text-xs text-muted-foreground">No direct messages</div>
                  )}
                  {dmList.map(renderRow)}
                </div>
              </div>

              {/* Iter 232N.13 — Group DMs (3+ team threads) with a
                  "New group DM" affordance that opens the multi-team
                  picker. Rendered as its own section so 1:1 vs group
                  threads are visually distinguishable. */}
              <div>
                <div className="flex items-center justify-between mb-2 px-2">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Group DMs
                  </h3>
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
                </div>
                <div className="space-y-1" data-testid="chat-group-dms-list">
                  {groupDmList.length === 0 && (
                    <div className="px-2 text-xs text-muted-foreground">
                      No group DMs yet
                    </div>
                  )}
                  {groupDmList.map(renderRow)}
                </div>
              </div>
            </div>
          </ScrollArea>
        </div>

        {/* Chat Area */}
        <div className="flex-1 flex flex-col">
          <div className="p-4 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-2">
              {selected?.kind === "dm" ? (
                <Avatar className="h-6 w-6"><AvatarFallback className="text-xs bg-secondary">{initialsFor(selected?.name)}</AvatarFallback></Avatar>
              ) : selected?.kind === "group_dm" ? (
                <Users className="h-5 w-5 text-primary" />
              ) : (
                <Hash className="h-5 w-5 text-muted-foreground" />
              )}
              <h2 className="font-semibold" data-testid="chat-active-channel-name">
                {selected?.name || "Select a channel"}
              </h2>
              {selected?.muted && (
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <BellOff className="h-3 w-3" />Muted
                </span>
              )}
            </div>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4">
            <div className="space-y-3">
              {loadingMsgs && messages.length === 0 && (
                <div className="text-center text-muted-foreground text-sm">Loading…</div>
              )}
              {!loadingMsgs && messages.length === 0 && (
                <div className="text-center text-muted-foreground text-sm">
                  {selected ? "No messages yet — say hi 👋" : "Pick a channel to start chatting"}
                </div>
              )}
              {messages.map((msg) => (
                <div
                  key={msg._id}
                  data-testid={`chat-message-${msg._id}`}
                  className={`flex gap-3 ${msg.is_system ? "justify-center" : ""}`}
                >
                  {msg.is_system ? (
                    <div className="bg-accent/10 text-accent text-sm px-4 py-2 rounded-lg whitespace-pre-wrap max-w-[80%]">
                      {msg.content}
                    </div>
                  ) : (
                    <>
                      <Avatar className="h-9 w-9 shrink-0">
                        <AvatarFallback className="bg-secondary text-xs font-medium">
                          {initialsFor(msg.sender_name)}
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex-1">
                        <div className="flex items-baseline gap-2">
                          <span className="font-semibold text-sm" data-testid={`chat-msg-sender-${msg._id}`}>
                            {msg.sender_name}
                          </span>
                          {/* Iter 232b — Live online dot next to the
                              author. Reflects current socket-room
                              presence, not any historical "active"
                              state. */}
                          {msg.user_id && (
                            <OnlineDot
                              online={onlineUserIds?.has(String(msg.user_id))}
                              testId={`chat-msg-presence-${msg._id}`}
                            />
                          )}
                          <span className="text-[11px] text-muted-foreground">{fmtTime(msg.created_at)}</span>
                          {/* Iter 206 — Report this user (hidden for self) */}
                          {msg.user_id && msg.user_id !== user?.id && (
                            <ReportUserButton
                              targetUserId={msg.user_id}
                              targetUserEmail={msg.sender_name}
                              leagueId={msg.league_id}
                              contextUrl={`/chat#msg-${msg._id}`}
                            />
                          )}
                        </div>
                        <p className="text-sm text-foreground/90 whitespace-pre-wrap break-words">{msg.content}</p>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="p-4 border-t border-border relative">
            {mention.open && filteredMentions.length > 0 && (
              <div
                data-testid="chat-mention-popup"
                className="absolute bottom-16 left-4 right-4 max-w-md bg-card border border-border rounded-lg shadow-lg overflow-hidden"
              >
                {filteredMentions.map((m) => (
                  <button
                    key={m.team_id}
                    data-testid={`chat-mention-option-${m.team_id}`}
                    onClick={() => insertMention(m.team_name)}
                    className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm hover:bg-secondary"
                  >
                    <span className="flex items-center gap-2">
                      <Avatar className="h-5 w-5"><AvatarFallback className="text-[10px] bg-secondary">{m.abbr}</AvatarFallback></Avatar>
                      <span className="font-medium">{m.team_name}</span>
                      <span className="text-muted-foreground text-xs">{m.owner_name}</span>
                    </span>
                  </button>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <Input
                ref={inputRef}
                data-testid="chat-message-input"
                value={draft}
                onChange={handleDraftChange}
                placeholder={selected ? `Message ${selected.kind === "dm" ? selected.name : "#" + selected.name}` : "Pick a channel"}
                disabled={!selected}
                className="flex-1"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  } else if (e.key === "Escape") {
                    setMention({ open: false, query: "" });
                  }
                }}
              />
              <Button
                data-testid="chat-send-btn"
                onClick={handleSend}
                disabled={!selected || !draft.trim()}
                className="bg-primary hover:bg-primary/90"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
};

export default Chat;
