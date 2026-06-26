import { useState, useEffect, useCallback } from "react";
import { Bell, X, RotateCcw, Mail, Smartphone, Megaphone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import api from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

/**
 * Iter 230 — Notification Settings modal.
 *
 * Reads `/api/notifications/preferences` (returns events + categories +
 * current user prefs). Renders one row per event with three channel
 * toggles: In-App / Push / Email. Push + Email are saved as preferences
 * for future Expo/SendGrid delivery — only In-App fires today.
 *
 * Each toggle PUTs `/api/notifications/preferences` with a single
 * event_id + channel update so we don't ship the entire blob on every
 * click. A "Reset to defaults" button calls POST /preferences/reset.
 */

const CHANNEL_META = {
  in_app: { label: "In-App", icon: Megaphone, color: "text-cyan-300" },
  push:   { label: "Push",   icon: Smartphone, color: "text-violet-300" },
  email:  { label: "Email",  icon: Mail,       color: "text-emerald-300" },
};

export default function NotificationSettings({ open, onOpenChange }) {
  const [loading, setLoading] = useState(true);
  const [events, setEvents] = useState([]);
  const [categories, setCategories] = useState([]);
  const [prefs, setPrefs] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/notifications/preferences");
      setEvents(data.events || []);
      setCategories(data.categories || []);
      setPrefs(data.preferences || {});
    } catch (e) {
      toast.error("Couldn't load notification preferences");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (open) load(); }, [open, load]);

  const handleToggle = async (eventId, channel, value) => {
    // Optimistic UI; revert if the PUT fails.
    const prev = prefs[eventId] || { in_app: false, push: false, email: false };
    setPrefs((p) => ({ ...p, [eventId]: { ...prev, [channel]: value } }));
    try {
      await api.put("/notifications/preferences", { event_id: eventId, [channel]: value });
    } catch (e) {
      setPrefs((p) => ({ ...p, [eventId]: prev }));
      toast.error("Couldn't save that change");
    }
  };

  const handleReset = async () => {
    try {
      const { data } = await api.post("/notifications/preferences/reset");
      setPrefs(data.preferences || {});
      toast.success("Notification settings reset to defaults");
    } catch (e) {
      toast.error("Reset failed");
    }
  };

  const eventsByCategory = categories.map((c) => ({
    ...c,
    events: events.filter((e) => e.category === c.id),
  }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-3xl bg-[#0e0e10] border-white/10 text-white p-0 overflow-hidden"
        data-testid="notification-settings-modal"
      >
        <DialogHeader className="p-6 pb-3 border-b border-white/10 flex flex-row items-center justify-between space-y-0">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-cyan-500/15 flex items-center justify-center">
              <Bell className="h-5 w-5 text-cyan-300" />
            </div>
            <div>
              <DialogTitle className="text-lg">Notification Settings</DialogTitle>
              <DialogDescription className="text-xs text-[#A1A1AA]">
                Choose how you'd like to hear from us. In-App fires today; Push & Email are saved for future delivery.
              </DialogDescription>
            </div>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={handleReset}
            className="text-[#A1A1AA] hover:text-white"
            data-testid="notification-settings-reset-btn"
          >
            <RotateCcw className="h-3.5 w-3.5 mr-1" />
            Reset defaults
          </Button>
        </DialogHeader>

        <div className="px-6 pt-3 pb-2 grid grid-cols-[1fr_repeat(3,72px)] gap-2 text-[10px] uppercase tracking-wider text-[#71717A] border-b border-white/5">
          <span>Event</span>
          {Object.entries(CHANNEL_META).map(([key, meta]) => {
            const Icon = meta.icon;
            return (
              <span key={key} className="flex items-center justify-center gap-1">
                <Icon className={cn("h-3 w-3", meta.color)} />
                {meta.label}
              </span>
            );
          })}
        </div>

        <ScrollArea className="max-h-[60vh]">
          {loading ? (
            <div className="p-8 text-center text-sm text-[#A1A1AA]">Loading…</div>
          ) : (
            <div className="px-6 py-4 space-y-6">
              {eventsByCategory.map((cat) => (
                <section key={cat.id} data-testid={`notif-cat-${cat.id}`}>
                  <h3 className="text-sm font-semibold text-cyan-300 mb-2 uppercase tracking-wider">
                    {cat.label}
                    <Badge variant="outline" className="ml-2 text-[10px] border-white/10 text-[#A1A1AA]">
                      {cat.events.length}
                    </Badge>
                  </h3>
                  <div className="divide-y divide-white/5">
                    {cat.events.map((ev) => {
                      const p = prefs[ev.id] || { in_app: false, push: false, email: false };
                      return (
                        <div
                          key={ev.id}
                          className="grid grid-cols-[1fr_repeat(3,72px)] gap-2 items-center py-2.5"
                          data-testid={`notif-row-${ev.id}`}
                        >
                          <div className="min-w-0">
                            <p className="text-sm text-white truncate">{ev.label}</p>
                            <p className="text-[11px] text-[#71717A] truncate">{ev.description}</p>
                          </div>
                          {["in_app", "push", "email"].map((ch) => (
                            <div key={ch} className="flex justify-center">
                              <Switch
                                checked={!!p[ch]}
                                onCheckedChange={(v) => handleToggle(ev.id, ch, v)}
                                data-testid={`notif-toggle-${ev.id}-${ch}`}
                              />
                            </div>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
