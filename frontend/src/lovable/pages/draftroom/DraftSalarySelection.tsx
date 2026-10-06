// @ts-nocheck
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";

export default function DraftSalarySelection({ draftId, player, onClose, onConfirm }) {
  const [options, setOptions] = useState(null);
  const [destination, setDestination] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setOptions(null); setDestination("");
    if (!player) return;
    api.post(`/drafts/${draftId}/salary-eligibility`, { player_ids: [player.id] }).then(({data}) => {
      if (cancelled) return;
      const result = data.players[player.id];
      setOptions(result?.destinations || {});
      setDestination(result?.destination || Object.keys(result?.destinations || {})[0] || "");
    }).catch(() => { if (!cancelled) { setOptions({}); toast.error("Could not validate selection; try again"); } });
    return () => { cancelled = true; };
  }, [draftId, player]);
  const result = options?.[destination];
  const confirm = async () => {
    setBusy(true);
    try { if (await onConfirm(player, destination)) onClose(); }
    finally { setBusy(false); }
  };
  return <Dialog open={!!player} onOpenChange={open => !open && onClose()}><DialogContent>
    <DialogHeader><DialogTitle>Draft {player?.name}</DialogTitle></DialogHeader>
    {!options ? <p>Checking salary and roster eligibility…</p> : <>
      <label>Roster destination <select aria-label="Draft roster destination" value={destination} onChange={e => setDestination(e.target.value)} className="bg-secondary rounded p-2">
        {Object.keys(options).map(s => <option key={s} value={s}>{s}</option>)}
      </select></label>
      {result && <p>Salary charge: ${Number(result.charge || 0).toLocaleString()} · {result.mode} adherence</p>}
      {result?.message && <p role="alert">{result.message}</p>}
      <Button disabled={busy || !result?.allowed} onClick={confirm} data-testid="draft-salary-confirm">{busy ? "Selecting…" : "Confirm draft selection"}</Button>
    </>}
  </DialogContent></Dialog>;
}
