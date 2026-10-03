// @ts-nocheck
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send, MessageSquare, Hash } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

interface ChatMessage {
  id: number;
  user: string;
  avatar: string;
  content: string;
  timestamp: string;
  isSystem?: boolean;
}

const recentMessages: ChatMessage[] = [
  { id: 1, user: "Ice Crushers", avatar: "IC", content: "Anyone want to trade for McDavid? I'm rebuilding 👀", timestamp: "2:30 PM" },
  { id: 2, user: "Puck Masters", avatar: "PM", content: "What are you looking for?", timestamp: "2:32 PM" },
  { id: 3, user: "Ice Crushers", avatar: "IC", content: "2 firsts + a young forward", timestamp: "2:33 PM" },
  { id: 4, user: "Team Frostbite", avatar: "TF", content: "That's not enough for McDavid lol", timestamp: "2:35 PM" },
  { id: 5, user: "Glacier Kings", avatar: "GK", content: "Nice trade!", timestamp: "2:41 PM" },
];

const ChatWidget = () => {
  const [message, setMessage] = useState("");
  const navigate = useNavigate();

  const handleSend = () => {
    if (!message.trim()) return;
    setMessage("");
  };

  return (
    <Card className="border-border bg-card">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-primary" />
            League Chat
          </CardTitle>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Hash className="h-3 w-3" />general
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="text-xs text-muted-foreground hover:text-foreground h-6 px-2"
              onClick={() => navigate("/chat")}
            >
              Open Chat
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <ScrollArea className="h-[220px] pr-2 mb-3">
          <div className="space-y-3">
            {recentMessages.map((msg) => (
              <div key={msg.id} className="flex items-start gap-2">
                <Avatar className="h-6 w-6 flex-shrink-0 mt-0.5">
                  <AvatarFallback className="text-[10px] bg-secondary text-secondary-foreground">
                    {msg.avatar}
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-xs font-semibold text-foreground truncate">{msg.user}</span>
                    <span className="text-[10px] text-muted-foreground flex-shrink-0">{msg.timestamp}</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">{msg.content}</p>
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
        <div className="flex gap-2">
          <Input
            placeholder="Type a message..."
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            className="h-8 text-xs bg-secondary border-border"
          />
          <Button size="icon" className="h-8 w-8 flex-shrink-0" onClick={handleSend} disabled={!message.trim()}>
            <Send className="h-3.5 w-3.5" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

export default ChatWidget;
