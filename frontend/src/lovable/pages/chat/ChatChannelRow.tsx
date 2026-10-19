import { Avatar, AvatarFallback } from "@/components/ui/avatar";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Users,
  Hash,
  BellOff,
  Bell,
  Trash2,
  MoreHorizontal,
  Check,
  Archive,
} from "lucide-react";

import SwipeableRow from "@/components/SwipeableRow";

import { MUTE_OPTIONS, initialsFor } from "./chatFormatting";

interface ChatChannelRowProps {
  c: any;
  selectedId: string;
  setSelectedId: (id: string) => void;
  isCommish: boolean;
  handleMute: (id: string, duration: string | null) => void;
  handleDeleteChannel: (channel: any) => void;
  handleToggleArchive: (channel: any) => void;
  hintActive: boolean;
  hintRowId: string | null;
  markHintShown: () => void;
  handleMarkChannelRead: (id: string) => void;
}

export default function ChatChannelRow({ c, selectedId, setSelectedId, isCommish, handleMute, handleDeleteChannel, handleToggleArchive, hintActive, hintRowId, markHintShown, handleMarkChannelRead }: ChatChannelRowProps) {
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
  }
