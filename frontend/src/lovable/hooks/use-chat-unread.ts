// Re-export the live hook from the canonical location so any Lovable
// imports go through the same /api/chat/unread polling code.
export { useChatUnread } from "@/hooks/use-chat-unread";
