import { Avatar, AvatarFallback } from "@/components/ui/avatar";

import ReportUserButton from "@/components/ReportUserButton";

import { OnlineDot } from "@/components/OnlinePresenceBadge";

import type React from "react";
import { initialsFor, fmtTime } from "./chatFormatting";

interface ChatMessagesProps {
  scrollRef: React.RefObject<HTMLDivElement | null>;
  loadingMsgs: boolean;
  messages: any[];
  selected: any;
  onlineUserIds: Set<string>;
  user: { id?: string } | null;
}

export default function ChatMessages({ scrollRef, loadingMsgs, messages, selected, onlineUserIds, user }: ChatMessagesProps) {
  return (
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

  );
}
