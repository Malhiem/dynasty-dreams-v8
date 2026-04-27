// @ts-nocheck
import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

/**
 * Global state for the persistent Trade Builder panel.
 *
 * Responsibilities:
 *   • Holds the open/closed state of the trade panel so it survives route changes
 *     (mounted in AppLayout, not inside any specific page).
 *   • Tracks an array of `partners` (teams in the trade), the assets each
 *     partner is sending, and the recipient (`toTeamId`) of each asset.
 *   • Submits to /api/trades/multi when there are 3+ parties; falls back to
 *     legacy /api/trades for 2-party trades.
 */

const TradeBuilderContext = createContext(null);

const initialState = {
  open: false,
  leagueId: null,
  myTeamId: null,
  // partners[0] is always the proposer (my team)
  partners: [],          // [{id, name, abbr, owner, owner_id}]
  assets: [],            // [{player, retainSalary, retainedPercentage, toTeamId}]
  picks: [],             // [{pick, toTeamId}]
  message: "",
};

export function TradeBuilderProvider({ children }) {
  const [state, setState] = useState(initialState);
  const [collapsed, setCollapsed] = useState(false);

  const openBuilder = useCallback(({ leagueId, myTeam }) => {
    setState((prev) => {
      // If already open with same context, keep state; otherwise initialize.
      if (prev.open && prev.leagueId === leagueId && prev.myTeamId === myTeam.id) return prev;
      return {
        ...initialState,
        open: true,
        leagueId,
        myTeamId: myTeam.id,
        partners: [{
          id: myTeam.id,
          name: myTeam.name,
          abbr: myTeam.abbr || myTeam.logo_abbr || (myTeam.name || "").slice(0,3).toUpperCase(),
          owner: myTeam.owner_name || "You",
          owner_id: myTeam.owner_id,
        }],
      };
    });
  }, []);

  const closeBuilder = useCallback(() => {
    setState(initialState);
    setCollapsed(false);
  }, []);

  const addPartner = useCallback((team) => {
    setState((prev) => {
      if (!prev.open) return prev;
      if (prev.partners.some((p) => p.id === team.id)) return prev;
      return {
        ...prev,
        partners: [...prev.partners, {
          id: team.id,
          name: team.name,
          abbr: team.abbr || team.logo_abbr || (team.name || "").slice(0,3).toUpperCase(),
          owner: team.owner || team.owner_name || "—",
          owner_id: team.owner_id,
        }],
      };
    });
  }, []);

  const removePartner = useCallback((teamId) => {
    setState((prev) => {
      // Cannot remove proposer (index 0)
      if (prev.partners[0]?.id === teamId) return prev;
      const remaining = prev.partners.filter((p) => p.id !== teamId);
      // Drop any assets/picks owned by or destined to that team
      const assets = prev.assets.filter(
        (a) => (a.player.ownerTeamId !== teamId) && (a.toTeamId !== teamId),
      );
      const picks = prev.picks.filter(
        (p) => (p.pick.ownerTeamId !== teamId) && (p.toTeamId !== teamId),
      );
      return { ...prev, partners: remaining, assets, picks };
    });
  }, []);

  const _defaultRecipient = (state, ownerTeamId) => {
    const others = state.partners.filter((p) => p.id !== ownerTeamId);
    return others[0]?.id || null;
  };

  const addAsset = useCallback((player) => {
    setState((prev) => {
      if (prev.assets.some((a) => a.player.id === player.id)) {
        toast.info(`${player.name} is already in the trade`);
        return prev;
      }
      // Ensure the player's owning team is one of the partners
      const ownerTeamId = player.ownerTeamId;
      let partners = prev.partners;
      if (ownerTeamId && !partners.some((p) => p.id === ownerTeamId) && player.ownerTeamName) {
        partners = [...partners, {
          id: ownerTeamId,
          name: player.ownerTeamName,
          abbr: (player.ownerTeamName || "").slice(0, 3).toUpperCase(),
          owner: "—",
        }];
      }
      const next = { ...prev, partners };
      const toTeamId = _defaultRecipient(next, ownerTeamId);
      return {
        ...next,
        assets: [...prev.assets, {
          player, retainSalary: false, retainedPercentage: 0, toTeamId,
        }],
      };
    });
  }, []);

  const removeAsset = useCallback((playerId) => {
    setState((prev) => ({ ...prev, assets: prev.assets.filter((a) => a.player.id !== playerId) }));
  }, []);

  const toggleRetain = useCallback((playerId) => {
    setState((prev) => ({
      ...prev,
      assets: prev.assets.map((a) =>
        a.player.id === playerId
          ? { ...a, retainSalary: !a.retainSalary, retainedPercentage: a.retainSalary ? 0 : 10 }
          : a,
      ),
    }));
  }, []);

  const updateRetention = useCallback((playerId, pct) => {
    setState((prev) => ({
      ...prev,
      assets: prev.assets.map((a) =>
        a.player.id === playerId ? { ...a, retainedPercentage: pct } : a,
      ),
    }));
  }, []);

  const setAssetRecipient = useCallback((playerId, toTeamId) => {
    setState((prev) => ({
      ...prev,
      assets: prev.assets.map((a) =>
        a.player.id === playerId ? { ...a, toTeamId } : a,
      ),
    }));
  }, []);

  const addPick = useCallback((pick) => {
    setState((prev) => {
      if (prev.picks.some((p) => p.pick.id === pick.id)) {
        toast.info("This pick is already in the trade");
        return prev;
      }
      const ownerTeamId = pick.ownerTeamId;
      let partners = prev.partners;
      if (ownerTeamId && !partners.some((p) => p.id === ownerTeamId) && pick.ownerTeamName) {
        partners = [...partners, {
          id: ownerTeamId,
          name: pick.ownerTeamName,
          abbr: (pick.ownerTeamName || "").slice(0,3).toUpperCase(),
          owner: "—",
        }];
      }
      const next = { ...prev, partners };
      const toTeamId = _defaultRecipient(next, ownerTeamId);
      return { ...next, picks: [...prev.picks, { pick, toTeamId }] };
    });
  }, []);

  const removePick = useCallback((pickId) => {
    setState((prev) => ({ ...prev, picks: prev.picks.filter((p) => p.pick.id !== pickId) }));
  }, []);

  const setPickRecipient = useCallback((pickId, toTeamId) => {
    setState((prev) => ({
      ...prev,
      picks: prev.picks.map((p) => p.pick.id === pickId ? { ...p, toTeamId } : p),
    }));
  }, []);

  const setMessage = useCallback((message) => {
    setState((prev) => ({ ...prev, message }));
  }, []);

  // Submit the trade. Multi-party uses /api/trades/multi; 2-party uses legacy /api/trades.
  const sendProposal = useCallback(async () => {
    if (!state.leagueId || !state.myTeamId) {
      toast.error("Trade Builder is missing league or team context");
      return false;
    }
    if (state.partners.length < 2) {
      toast.error("Add at least one partner team");
      return false;
    }
    if (state.assets.length === 0 && state.picks.length === 0) {
      toast.error("Add at least one asset to trade");
      return false;
    }

    // Pull pick upgrades from the editor (window-bridge contract)
    const pickUpgrades = (typeof window !== "undefined" && window.__getPickUpgrades?.()) || [];
    const conditions = [];

    const isMulti = state.partners.length > 2;

    if (isMulti) {
      // Build parties array
      const parties = state.partners.map((p) => {
        const sends = [];
        const receives = [];
        for (const a of state.assets) {
          const fromId = a.player.ownerTeamId;
          if (fromId === p.id) {
            sends.push({
              asset_type: "player",
              player_id: String(a.player.id),
              player_name: a.player.name,
              position: a.player.position,
              nhl_team: a.player.team,
              salary_retained_pct: a.retainSalary ? (a.retainedPercentage || 0) : 0,
              to_team_id: a.toTeamId,
            });
          }
          if (a.toTeamId === p.id) {
            receives.push({
              asset_type: "player",
              player_id: String(a.player.id),
            });
          }
        }
        for (const pp of state.picks) {
          const fromId = pp.pick.ownerTeamId;
          if (fromId === p.id) {
            sends.push({
              asset_type: "pick",
              pick_id: pp.pick.pickId || undefined,
              pick_year: Number(pp.pick.year) || undefined,
              pick_round: pp.pick.round ? String(pp.pick.round) : undefined,
              to_team_id: pp.toTeamId,
            });
          }
          if (pp.toTeamId === p.id) {
            receives.push({
              asset_type: "pick",
              pick_id: pp.pick.pickId || undefined,
              pick_year: Number(pp.pick.year) || undefined,
              pick_round: pp.pick.round ? String(pp.pick.round) : undefined,
            });
          }
        }
        return { team_id: p.id, sends, receives };
      });

      try {
        const { data } = await api.post("/trades/multi", {
          league_id: state.leagueId,
          parties,
          conditions,
          pick_upgrades: pickUpgrades,
          message: state.message || undefined,
        });
        toast.success(`${state.partners.length}-team trade proposed`, {
          description: `Awaiting ${state.partners.length - 1} acceptance(s)`,
        });
        closeBuilder();
        return true;
      } catch (e) {
        toast.error("Trade proposal failed", {
          description: e?.response?.data?.detail || e?.message || "Unknown error",
        });
        return false;
      }
    } else {
      // 2-party legacy path
      const target = state.partners.find((p) => p.id !== state.myTeamId);
      if (!target) {
        toast.error("Add a trade partner");
        return false;
      }
      const offered = [];
      const requested = [];
      for (const a of state.assets) {
        const asset = {
          asset_type: "player",
          player_id: String(a.player.id),
          player_name: a.player.name,
          position: a.player.position,
          nhl_team: a.player.team,
          salary_retained_pct: a.retainSalary ? (a.retainedPercentage || 0) : 0,
        };
        if (a.player.ownerTeamId === state.myTeamId) offered.push(asset);
        else requested.push(asset);
      }
      for (const pp of state.picks) {
        const asset = {
          asset_type: "pick",
          pick_id: pp.pick.pickId || undefined,
          pick_year: Number(pp.pick.year) || undefined,
          pick_round: pp.pick.round ? String(pp.pick.round) : undefined,
        };
        if (pp.pick.ownerTeamId === state.myTeamId) offered.push(asset);
        else requested.push(asset);
      }

      try {
        const { data } = await api.post("/trades", {
          league_id: state.leagueId,
          target_team_id: target.id,
          assets_offered: offered,
          assets_requested: requested,
          conditions,
          pick_upgrades: pickUpgrades,
          message: state.message || `Proposal to ${target.name}`,
        });
        const label = pickUpgrades.length > 0 ? "Conditional trade proposed" : "Trade proposed";
        toast.success(label, { description: `Sent to ${target.name}` });
        closeBuilder();
        return true;
      } catch (e) {
        toast.error("Trade proposal failed", {
          description: e?.response?.data?.detail || e?.message || "Unknown error",
        });
        return false;
      }
    }
  }, [state, closeBuilder]);

  const value = useMemo(() => ({
    ...state,
    collapsed,
    setCollapsed,
    openBuilder,
    closeBuilder,
    addPartner,
    removePartner,
    addAsset,
    removeAsset,
    toggleRetain,
    updateRetention,
    setAssetRecipient,
    addPick,
    removePick,
    setPickRecipient,
    setMessage,
    sendProposal,
  }), [state, collapsed, openBuilder, closeBuilder, addPartner, removePartner,
       addAsset, removeAsset, toggleRetain, updateRetention, setAssetRecipient,
       addPick, removePick, setPickRecipient, setMessage, sendProposal]);

  return (
    <TradeBuilderContext.Provider value={value}>
      {children}
    </TradeBuilderContext.Provider>
  );
}

export function useTradeBuilder() {
  const ctx = useContext(TradeBuilderContext);
  if (!ctx) throw new Error("useTradeBuilder must be used inside TradeBuilderProvider");
  return ctx;
}
