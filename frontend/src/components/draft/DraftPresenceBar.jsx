// Iter 232N.36 — Draft Presence Bar.
// Compact ribbon of owner avatars at the top of the Draft Room. Uses the
// same `onlineUserIds` Set that lights up the column headers so commissioners
// can spot "N of M owners are here" before firing up the clock.
import { Card, CardContent } from "@/components/ui/card";
import TeamLogo from "@/lovable/components/TeamLogo";
import { Users } from "lucide-react";
import { cn } from "@/lib/utils";

export default function DraftPresenceBar({ teams, onlineUserIds }) {
  if (!teams?.length) return null;
  // Iter 232N.38 — Consider a team "here" if the primary owner OR any
  // co-owner has an active socket in the draft room. Previously only
  // `owner_id` counted, so a co-owner (e.g. a commissioner-installed
  // deputy) opening the war room wouldn't turn their team's dot green.
  const isTeamOnline = (t) => {
    if (!onlineUserIds) return false;
    if (t.owner_id && onlineUserIds.has(String(t.owner_id))) return true;
    for (const cid of (t.co_owner_ids || [])) {
      if (onlineUserIds.has(String(cid))) return true;
    }
    return false;
  };
  const onlineCount = teams.filter(isTeamOnline).length;
  const totalCount = teams.length;
  return (
    <Card className="border-white/10 bg-[#141414]" data-testid="draft-presence-bar">
      <CardContent className="p-3 flex items-center gap-3">
        <div className="flex items-center gap-1.5 shrink-0">
          <Users className="h-3.5 w-3.5 text-[#00D2FF]" />
          <span
            className="text-xs font-semibold text-white"
            data-testid="draft-presence-count"
          >
            {onlineCount} <span className="text-[#A1A1AA]">of {totalCount} here</span>
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5 flex-1 min-w-0" data-testid="draft-presence-list">
          {teams.map((t) => {
            const abbr = t.logo_abbr || (t.name || "").slice(0, 3).toUpperCase();
            const online = isTeamOnline(t);
            return (
              <div
                key={t.id || abbr}
                title={`${t.name}${t.owner_name ? " — " + t.owner_name : ""} · ${online ? "online" : "offline"}`}
                data-testid={`draft-presence-team-${abbr}`}
                data-online={online ? "true" : "false"}
                className={cn(
                  "relative rounded-full transition-opacity",
                  online ? "opacity-100" : "opacity-40 grayscale",
                )}
              >
                <TeamLogo logo={t.logo_url} name={t.name} abbr={abbr} size="sm" />
                {online && (
                  <span
                    className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full bg-[#34C759] ring-2 ring-[#141414]"
                    data-testid={`draft-presence-online-dot-${abbr}`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
