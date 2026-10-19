// @ts-nocheck
import useChatSubmission from "./chat/useChatSubmission";
import GroupDmComposer from "./chat/GroupDmComposer";
import ChatChannelRow from "./chat/ChatChannelRow";
import ChatMessages from "./chat/ChatMessages";
import { initialsFor } from "./chat/chatFormatting";
import { AppLayout } from "@/components/layout/AppLayout";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";

import {
  Send,
  Users,
  Hash,
  Plus,
  BellOff,
  Loader2,
  Archive,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  useCallback,
} from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { useAuth } from "@/contexts/AuthContext";
import { useChatUnread } from "@/hooks/use-chat-unread";
// Iter 230au — Generic swipe-to-action primitive for the channel list.

// Iter 230aw — First-time onboarding pulse for the swipe gestures.
import useOnboardingHint from "@/hooks/use-onboarding-hint";

// Iter 232b — Live presence on the League Chat header + per-member dots.
import { useLeagueSocket } from "@/hooks/use-socket";
import { OnlinePresenceBadge } from "@/components/OnlinePresenceBadge";

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
  const [channelsOpen, setChannelsOpen] = useState(false);
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

  const { send: handleSend, sending } = useChatSubmission({
    selectedId, draft, setDraft,
    onSent: async () => { setMention({ open: false, query: "" }); await loadMessages(); },
  });

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

  const renderRow = (c) => (
    <ChatChannelRow key={c._id}
      c={c}
      selectedId={selectedId}
      setSelectedId={(id) => { setSelectedId(id); setChannelsOpen(false); }}
      isCommish={isCommish}
      handleMute={handleMute}
      handleDeleteChannel={handleDeleteChannel}
      handleToggleArchive={handleToggleArchive}
      hintActive={hintActive}
      hintRowId={hintRowId}
      markHintShown={markHintShown}
      handleMarkChannelRead={handleMarkChannelRead}
    />
  );

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
      <div className="h-[calc(100dvh-7rem)] sm:h-[calc(100dvh-3.5rem)] min-w-0 flex flex-col sm:flex-row" data-testid="chat-page">
        {/* Channels Sidebar */}
        <div className={`${channelsOpen ? "flex" : "hidden"} sm:flex w-full sm:w-64 shrink-0 max-h-[40dvh] sm:max-h-none border-r border-border bg-card/50 flex-col`}>
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
                  <GroupDmComposer
                    groupOpen={groupOpen}
                    setGroupOpen={setGroupOpen}
                    setGroupPicked={setGroupPicked}
                    leagueTeams={leagueTeams}
                    myTeam={myTeam}
                    groupPicked={groupPicked}
                    handleCreateGroupDm={handleCreateGroupDm}
                    groupCreating={groupCreating}
                  />
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
        <div className="flex-1 min-w-0 min-h-0 flex flex-col">
          <div className="p-4 border-b border-border flex items-center justify-between">
            <div className="flex min-w-0 items-center gap-2">
              <Button variant="outline" size="sm" className="sm:hidden shrink-0" aria-expanded={channelsOpen} onClick={() => setChannelsOpen(v => !v)}>Channels</Button>
              {selected?.kind === "dm" ? (
                <Avatar className="h-6 w-6"><AvatarFallback className="text-xs bg-secondary">{initialsFor(selected?.name)}</AvatarFallback></Avatar>
              ) : selected?.kind === "group_dm" ? (
                <Users className="h-5 w-5 text-primary" />
              ) : (
                <Hash className="h-5 w-5 text-muted-foreground" />
              )}
              <h2 className="font-semibold truncate" data-testid="chat-active-channel-name">
                {selected?.name || "Select a channel"}
              </h2>
              {selected?.muted && (
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <BellOff className="h-3 w-3" />Muted
                </span>
              )}
            </div>
          </div>

          <ChatMessages
            scrollRef={scrollRef}
            loadingMsgs={loadingMsgs}
            messages={messages}
            selected={selected}
            onlineUserIds={onlineUserIds}
            user={user}
          />
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
                className="flex-1 min-w-0"
                aria-label="Message"
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
                disabled={sending || !selected || !draft.trim()}
                aria-label="Send message"
                aria-busy={sending}
                className="bg-primary hover:bg-primary/90"
              >
                {sending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
};

export default Chat;
