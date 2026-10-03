// Iter 230j — TradeBlock data layer extracted from TradeBlock.tsx.
// Owns the live `/trade-block` fetch (with socket-driven invalidation),
// "my roster" fetch, ownership decorators (name + abbr + theme color)
// and the two derived collections downstream UI consumes:
//   • `realTradeItems` — every league listing mapped into the card shape.
//   • `myOnBlockPlayers` — only the current user's listings (My Players tab).
//   • `realOwners` — dynamic owner select dropdown options.
import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { useSocket } from "@/hooks/use-socket";
import type { TradeBlockItem, ItemType, MyOnBlockPlayer } from "@/lovable/pages/trade-block/types";

type LeagueTeam = {
  id?: string;
  owner_id?: string;
  name?: string;
  logo_abbr?: string;
  theme_color?: string | null;
};

type Args = {
  leagueId?: string | null;
  leagueTeams: LeagueTeam[] | undefined;
  myTeamId?: string | null;
  userIdForSocket?: string | null;
};

export default function useTradeBlockData({
  leagueId,
  leagueTeams,
  myTeamId,
  userIdForSocket,
}: Args) {
  const [liveItems, setLiveItems] = useState<any[]>([]);
  const [myRoster, setMyRoster] = useState<any[]>([]);
  // Iter 228z — Bump a tick to re-fetch whenever a `trade_block_changed`
  // socket event arrives, so the page lights up the instant any league
  // member adds/removes/updates a listing.
  const [tradeBlockTick, setTradeBlockTick] = useState(0);

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    api
      .get(`/trade-block?league_id=${leagueId}`)
      .then(({ data }) => {
        if (cancelled) return;
        setLiveItems(Array.isArray(data) ? data : []);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [leagueId, tradeBlockTick]);

  useSocket(
    leagueId ? `league_${leagueId}` : null,
    { trade_block_changed: () => setTradeBlockTick((t) => t + 1) },
    userIdForSocket,
  );

  useEffect(() => {
    if (!myTeamId) return;
    let cancelled = false;
    api
      .get(`/roster/${myTeamId}/detail`)
      .then(({ data }) => {
        if (!cancelled) setMyRoster(data?.players || []);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [myTeamId]);

  // Iter 229k — Surface the owner team's preset theme color so the
  // trade-block owner chip renders in their brand tint.
  const ownership = useMemo(() => {
    const byOwner = new Map<string, LeagueTeam>();
    (leagueTeams || []).forEach((t) => {
      if (t.owner_id) byOwner.set(t.owner_id, t);
    });
    return {
      nameFor: (oid: string) => byOwner.get(oid)?.name || "Unknown",
      abbrFor: (oid: string) => byOwner.get(oid)?.logo_abbr || "TBD",
      themeColorFor: (oid: string) => byOwner.get(oid)?.theme_color || null,
    };
  }, [leagueTeams]);

  const realTradeItems: TradeBlockItem[] = useMemo(
    () =>
      (liveItems || []).map((it: any, idx: number) => ({
        id: it._id || idx,
        name: it.name || "Unknown",
        position: it.position || "—",
        team: it.nhl_team || (it.item_type === "pick" ? "Own" : ""),
        team_id: it.team_id,
        age: it.age || undefined,
        aav: it.aav || null,
        dynastyValue: Math.round((it.points || 0) * 80 + 1000),
        owner: ownership.nameFor(it.owner_id),
        owner_id: it.owner_id,
        ownerAvatar: ownership.abbrFor(it.owner_id),
        ownerThemeColor: ownership.themeColorFor(it.owner_id),
        lookingFor: (it.looking_for || []).length ? it.looking_for : ["Best Offer"],
        trend: "stable" as const,
        weeklyPoints: 0,
        type: (it.item_type || "player") as ItemType,
        year: it.pick_year,
        round: it.pick_round,
        gp: it.games_played,
        g: it.goals,
        a: it.assists,
        plusMinus: it.plus_minus,
        sog: it.points, // placeholder; real sog not stored on trade-block row
      })),
    [liveItems, ownership],
  );

  const realOwners = useMemo(
    () => ["All Teams", ...((leagueTeams || []).map((t) => t.name || ""))],
    [leagueTeams],
  );

  // Single source of truth: backend `db.trade_block`. We surface ONLY this
  // user's currently-listed players (filtered by owner_id) so the tab is in
  // lockstep with the roster-page bullhorn toggle. When a trade executes,
  // the backend wipes those rows, so this list updates automatically.
  const myOnBlockPlayers: MyOnBlockPlayer[] = useMemo(() => {
    if (!myTeamId) return [];
    const rosterById = new Map(
      (myRoster || []).map((p: any) => [String(p.player_id || p.id), p]),
    );
    return (liveItems || [])
      .filter((it: any) => it.team_id === myTeamId && it.player_id)
      .map((it: any) => {
        const r: any = rosterById.get(String(it.player_id));
        return {
          id: it._id || it.player_id,
          player_id: String(it.player_id),
          name: it.name || r?.name || "Unknown",
          position: it.position || r?.position || "—",
          team: it.nhl_team || r?.nhl_team || "",
          nhl_team: r?.nhl_team,
          lookingFor: it.looking_for || [],
          minor_eligible: r?.minor_eligible,
          player_type: r?.player_type,
        };
      });
  }, [liveItems, myRoster, myTeamId]);

  return { liveItems, realTradeItems, realOwners, myOnBlockPlayers };
}
