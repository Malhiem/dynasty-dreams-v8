// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Send, Users, Hash, Pin } from "lucide-react";
import { useState, useEffect } from "react";
import { useChatUnread } from "@/hooks/use-chat-unread";

interface Message {
  id: number;
  user: string;
  avatar: string;
  content: string;
  timestamp: string;
  isSystem?: boolean;
}

interface Channel {
  id: number;
  name: string;
  unread: number;
  type: "league" | "dm";
}

const channels: Channel[] = [
  { id: 1, name: "general", unread: 5, type: "league" },
  { id: 2, name: "trades", unread: 2, type: "league" },
  { id: 3, name: "trash-talk", unread: 0, type: "league" },
  { id: 4, name: "Ice Crushers", unread: 1, type: "dm" },
  { id: 5, name: "Puck Masters", unread: 0, type: "dm" },
];

const mockMessages: Message[] = [
  { id: 1, user: "Ice Crushers", avatar: "IC", content: "Anyone want to trade for McDavid? I'm rebuilding 👀", timestamp: "2:30 PM" },
  { id: 2, user: "Puck Masters", avatar: "PM", content: "What are you looking for?", timestamp: "2:32 PM" },
  { id: 3, user: "Ice Crushers", avatar: "IC", content: "2 firsts + a young forward", timestamp: "2:33 PM" },
  { id: 4, user: "Team Frostbite", avatar: "TF", content: "That's not enough for McDavid lol", timestamp: "2:35 PM" },
  { id: 5, user: "System", avatar: "🔔", content: "Trade completed: Ice Crushers sent Alex Ovechkin to Puck Masters for 2025 1st + 2026 2nd", timestamp: "2:40 PM", isSystem: true },
  { id: 6, user: "Glacier Kings", avatar: "GK", content: "Nice trade!", timestamp: "2:41 PM" },
  { id: 7, user: "Ice Crushers", avatar: "IC", content: "Thanks! Building for the future", timestamp: "2:42 PM" },
];

const Chat = () => {
  const [selectedChannel, setSelectedChannel] = useState(channels[0]);
  const [message, setMessage] = useState("");
  const { markRead } = useChatUnread();

  useEffect(() => {
    markRead();
  }, [markRead]);
  const [messages, setMessages] = useState(mockMessages);

  const handleSend = () => {
    if (!message.trim()) return;
    
    const newMessage: Message = {
      id: messages.length + 1,
      user: "Team Frostbite",
      avatar: "TF",
      content: message,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    
    setMessages([...messages, newMessage]);
    setMessage("");
  };

  return (
    <AppLayout>
      <div className="h-[calc(100vh-3.5rem)] flex">
        {/* Channels Sidebar */}
        <div className="w-64 border-r border-border bg-card/50 flex flex-col">
          <div className="p-4 border-b border-border">
            <h2 className="font-semibold flex items-center gap-2">
              <Users className="h-4 w-4 text-primary" />
              Dynasty League Chat
            </h2>
          </div>
          
          <ScrollArea className="flex-1 p-3">
            <div className="space-y-4">
              <div>
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2 px-2">
                  Channels
                </h3>
                <div className="space-y-1">
                  {channels.filter(c => c.type === "league").map((channel) => (
                    <button
                      key={channel.id}
                      onClick={() => setSelectedChannel(channel)}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                        selectedChannel.id === channel.id 
                          ? "bg-primary/10 text-primary" 
                          : "hover:bg-secondary text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        <Hash className="h-4 w-4" />
                        {channel.name}
                      </span>
                      {channel.unread > 0 && (
                        <span className="h-5 min-w-5 px-1.5 rounded-full bg-primary text-primary-foreground text-xs flex items-center justify-center">
                          {channel.unread}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2 px-2">
                  Direct Messages
                </h3>
                <div className="space-y-1">
                  {channels.filter(c => c.type === "dm").map((channel) => (
                    <button
                      key={channel.id}
                      onClick={() => setSelectedChannel(channel)}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                        selectedChannel.id === channel.id 
                          ? "bg-primary/10 text-primary" 
                          : "hover:bg-secondary text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        <Avatar className="h-5 w-5">
                          <AvatarFallback className="text-[10px] bg-secondary">
                            {channel.name.slice(0, 2).toUpperCase()}
                          </AvatarFallback>
                        </Avatar>
                        {channel.name}
                      </span>
                      {channel.unread > 0 && (
                        <span className="h-5 min-w-5 px-1.5 rounded-full bg-primary text-primary-foreground text-xs flex items-center justify-center">
                          {channel.unread}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </ScrollArea>
        </div>

        {/* Chat Area */}
        <div className="flex-1 flex flex-col">
          <div className="p-4 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Hash className="h-5 w-5 text-muted-foreground" />
              <h2 className="font-semibold">{selectedChannel.name}</h2>
            </div>
            <Button variant="ghost" size="sm">
              <Pin className="h-4 w-4 mr-2" />
              Pinned
            </Button>
          </div>

          <ScrollArea className="flex-1 p-4">
            <div className="space-y-4">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3 ${msg.isSystem ? "justify-center" : ""}`}
                >
                  {msg.isSystem ? (
                    <div className="bg-accent/10 text-accent text-sm px-4 py-2 rounded-full">
                      {msg.content}
                    </div>
                  ) : (
                    <>
                      <Avatar className="h-10 w-10 shrink-0">
                        <AvatarFallback className="bg-secondary text-sm font-medium">
                          {msg.avatar}
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex-1">
                        <div className="flex items-baseline gap-2">
                          <span className="font-semibold">{msg.user}</span>
                          <span className="text-xs text-muted-foreground">{msg.timestamp}</span>
                        </div>
                        <p className="text-muted-foreground">{msg.content}</p>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>

          <div className="p-4 border-t border-border">
            <div className="flex gap-2">
              <Input
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder={`Message #${selectedChannel.name}`}
                className="flex-1"
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
              />
              <Button onClick={handleSend} className="bg-primary hover:bg-primary/90">
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
