// Iter 230j — Extracted from DraftRoom.tsx. Thin wrapper around the
// shared PlayerCardModal that maps a lean draft-room player record
// (id/name/team/position/age/pts/...) into the modal's expected shape
// and renders the window-within-window expansion. Renders nothing
// when `player` is null so callers can keep the conditional in JSX
// terse.
import PlayerCardModal from "@/lovable/components/dashboard/PlayerCardModal";

type Props = {
  player: any | null;
  onClose: () => void;
};

export default function ExpandedPlayerModal({ player, onClose }: Props) {
  if (!player) return null;
  return (
    <PlayerCardModal
      open={!!player}
      onOpenChange={(o) => !o && onClose()}
      player={{
        id: player.id,
        name: player.name,
        team: player.team || player.nhl_team || player.league || "—",
        position: player.position,
        age: player.age ?? 19,
        points: player.pts || 0,
        contract: { type: "Rookie", salary: 0, yearsRemaining: 0 },
        schedule: [],
        categoryBreakdown: {
          G: player.g || 0,
          A: player.a || 0,
          PTS: player.pts || 0,
          PPP: 0,
          SOG: player.shots || 0,
          HIT: 0,
          BLK: 0,
          PIM: player.pim || 0,
        },
        statsByPeriod: {
          "1d": 0,
          "7d": 0,
          "14d": 0,
          "30d": 0,
          "60d": 0,
          "100d": 0,
          season: player.pts || 0,
        },
      } as any}
    />
  );
}
