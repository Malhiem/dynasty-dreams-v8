/** Persist the selected roster slot, independently of a player's primary position. */
export function lineupAssignment(player: {rosterSection?: string; rosterSlotId?: string; position?: string}) {
  const group = player.rosterSection || "bench";
  const slot = player.rosterSlotId?.replace(/\d+$/, "") || player.position || "ACT";
  const sections: Record<string, string> = {starting: slot === "D" ? "defense" : "forward", goalies: "goalie", goalies_minors: "minors"};
  const reserved: Record<string, string> = {bench: "BN", ir: "IR", minors: "MIN", goalies_minors: "MIN"};
  return {section: sections[group] || group, slot: reserved[group] || slot};
}
