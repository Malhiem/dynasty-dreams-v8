// Extracted from pages/DraftRoomPage.jsx (Iter 232N.35 refactor).
// Draft chat panel — scroll list of messages with pick-highlight styling +
// send-on-Enter input row. Iter 232N.27 leaderboard is composed alongside
// this in DraftRoomPage but stays outside this component so the layout can
// swap components independently.
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageSquare, Send } from "lucide-react";
import { cn } from "@/lib/utils";

export default function DraftChatPanel({
  chatMessages,
  chatInput,
  onChatInputChange,
  onSendChat,
}) {
  return (
    <Card className="border-white/10">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2 text-white">
          <MessageSquare className="h-4 w-4 text-[#00D2FF]" />Draft Chat
        </CardTitle>
      </CardHeader>
      <CardContent className="p-2 space-y-2">
        <ScrollArea className="h-[200px]">
          <div className="space-y-2 p-1">
            {chatMessages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "text-xs rounded-md p-2",
                  msg.type === "pick" ? "bg-[#00D2FF]/10 border border-[#00D2FF]/20" : "bg-[#1A1A1A]/40",
                )}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span className={cn("font-semibold text-[11px]", msg.type === "pick" ? "text-[#00D2FF]" : "text-white")}>
                    {msg.sender}
                  </span>
                  <span className="text-[9px] text-[#A1A1AA]">
                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
                <p className="text-[#A1A1AA]">{msg.text}</p>
              </div>
            ))}
          </div>
        </ScrollArea>
        <div className="flex gap-2">
          <Input
            placeholder="Type a message..."
            className="h-8 text-sm bg-[#1A1A1A] border-white/10 text-white flex-1"
            value={chatInput}
            onChange={(e) => onChatInputChange(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSendChat()}
            data-testid="draft-chat-input"
          />
          <Button
            size="icon"
            className="h-8 w-8 bg-[#00D2FF] text-black"
            onClick={onSendChat}
            data-testid="draft-chat-send"
          >
            <Send className="h-3.5 w-3.5" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
