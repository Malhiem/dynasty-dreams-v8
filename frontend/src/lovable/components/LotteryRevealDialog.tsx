// @ts-nocheck
/**
 * LotteryRevealDialog — Iter 228 high-delight draft order reveal.
 *
 * Picks teams in REVERSE order (last → first) with a slow, suspense-style
 * reveal: drum-roll oscillator tones via Web Audio API, blurred placeholder
 * card flips to the team logo + name, confetti burst on pick #1.
 *
 * Usage:
 *   <LotteryRevealDialog
 *     open={open}
 *     teams={[{id, name, abbr, logo}]}
 *     onClose={() => setOpen(false)}
 *     onComplete={(order) => persistOrder(order)}
 *   />
 *
 * The reveal animation runs entirely client-side. `order` is delivered to
 * `onComplete` as the FINAL draft order (index 0 = team picking 1st).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function useAudio() {
  const ctxRef = useRef(null);
  const ensure = () => {
    if (!ctxRef.current && typeof window !== "undefined") {
      const AC = window.AudioContext || (window as any).webkitAudioContext;
      if (AC) ctxRef.current = new AC();
    }
    return ctxRef.current;
  };
  const drumroll = (durationMs = 600) => {
    const ctx = ensure();
    if (!ctx) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sawtooth";
    osc.frequency.setValueAtTime(80, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(40, ctx.currentTime + durationMs / 1000);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + 0.05);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + durationMs / 1000);
    osc.connect(gain); gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + durationMs / 1000);
  };
  const reveal = (toneHz = 440) => {
    const ctx = ensure();
    if (!ctx) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = toneHz;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.22, ctx.currentTime + 0.04);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35);
    osc.connect(gain); gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.4);
  };
  return { drumroll, reveal };
}

/** Pure CSS confetti — small absolutely-positioned dots with random
 * trajectories. Mounted/unmounted around pick #1 reveal. */
function ConfettiBurst() {
  const pieces = useMemo(() =>
    Array.from({ length: 80 }, (_, i) => ({
      id: i,
      left: Math.random() * 100,
      delay: Math.random() * 0.4,
      dur: 1.6 + Math.random() * 1.4,
      hue: Math.floor(Math.random() * 360),
      size: 6 + Math.random() * 6,
    })), []);
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" data-testid="lottery-confetti">
      {pieces.map((p) => (
        <span
          key={p.id}
          className="absolute -top-2 rounded-sm"
          style={{
            left: `${p.left}%`,
            width: p.size, height: p.size * 0.4,
            background: `hsl(${p.hue} 90% 60%)`,
            animation: `lottery-fall ${p.dur}s ease-in ${p.delay}s forwards`,
          }}
        />
      ))}
      <style>{`
        @keyframes lottery-fall {
          0% { transform: translateY(0) rotate(0); opacity: 1; }
          100% { transform: translateY(420px) rotate(720deg); opacity: 0; }
        }
      `}</style>
    </div>
  );
}

export function LotteryRevealDialog({ open, teams, onClose, onComplete }) {
  // `order` is the reveal sequence (last pick first). teams[order[0]] is the
  // last overall pick; teams[order[n-1]] is the #1 overall pick.
  const [order, setOrder] = useState([]);
  const [revealedCount, setRevealedCount] = useState(0);
  const [running, setRunning] = useState(false);
  const [showConfetti, setShowConfetti] = useState(false);
  const audio = useAudio();
  const timersRef = useRef([]);

  useEffect(() => {
    if (!open) {
      setOrder([]);
      setRevealedCount(0);
      setRunning(false);
      setShowConfetti(false);
      timersRef.current.forEach((t) => clearTimeout(t));
      timersRef.current = [];
    } else if (teams?.length) {
      setOrder(shuffle(teams));
    }
  }, [open, teams]);

  const start = () => {
    if (running || !order.length) return;
    setRunning(true);
    setRevealedCount(0);
    // Schedule reveals: tick every 1.4s, faster early, slower for #1.
    const cumulative = [];
    let t = 0;
    for (let i = 0; i < order.length; i++) {
      const remaining = order.length - i;
      // top-3 picks are big drama: 2.2s; otherwise 1.2s
      const gap = remaining <= 3 ? 2200 : 1200;
      t += gap;
      cumulative.push(t);
    }
    cumulative.forEach((delay, idx) => {
      timersRef.current.push(setTimeout(() => {
        audio.drumroll(300);
        timersRef.current.push(setTimeout(() => {
          audio.reveal(440 + idx * 25);
          setRevealedCount((c) => c + 1);
          if (idx === order.length - 1) {
            // Final pick (= #1 overall) → confetti
            setShowConfetti(true);
            setTimeout(() => setShowConfetti(false), 4000);
          }
        }, 300));
      }, delay));
    });
  };

  const skip = () => {
    timersRef.current.forEach((t) => clearTimeout(t));
    timersRef.current = [];
    setRevealedCount(order.length);
    setShowConfetti(true);
    setTimeout(() => setShowConfetti(false), 3000);
  };

  const finish = () => {
    // Reverse so order[0] = team picking 1st overall.
    const finalOrder = [...order].reverse();
    onComplete?.(finalOrder);
    onClose?.();
  };

  const allRevealed = revealedCount >= order.length && order.length > 0;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose?.(); }}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden relative" data-testid="lottery-reveal-dialog">
        {showConfetti && <ConfettiBurst />}
        <DialogHeader>
          <DialogTitle>Draft Order Lottery</DialogTitle>
          <DialogDescription>
            Teams reveal in REVERSE order — last pick first, building suspense for the #1 overall.
          </DialogDescription>
        </DialogHeader>

        {!running && !allRevealed && (
          <div className="text-center py-6 space-y-3" data-testid="lottery-pre-start">
            <p className="text-sm text-muted-foreground">
              {order.length} team{order.length === 1 ? "" : "s"} ready. Click Begin to start the reveal.
            </p>
            <Button onClick={start} size="lg" data-testid="lottery-start-btn">
              Begin the lottery
            </Button>
          </div>
        )}

        {(running || allRevealed) && (
          <ul className="space-y-1.5 max-h-[400px] overflow-y-auto pr-2" data-testid="lottery-reveals">
            {order.map((team, idx) => {
              const pickNum = order.length - idx; // last in list = #1
              const isRevealed = idx < revealedCount;
              const isFirstPick = pickNum === 1 && isRevealed;
              return (
                <li
                  key={team.id || idx}
                  className={`flex items-center gap-3 px-3 py-2 rounded-md border transition-all duration-500 ${
                    isFirstPick
                      ? "bg-gradient-to-r from-amber-500/20 to-orange-500/20 border-amber-500/60 scale-[1.02]"
                      : isRevealed
                        ? "bg-secondary/40 border-border"
                        : "bg-muted/30 border-border opacity-50"
                  }`}
                  data-testid={`lottery-pick-${pickNum}`}
                >
                  <span className={`text-2xl font-mono font-bold w-10 text-right ${
                    isFirstPick ? "text-amber-400" : "text-muted-foreground"
                  }`}>
                    #{pickNum}
                  </span>
                  <div className="flex-1">
                    {isRevealed ? (
                      <span className={`font-semibold ${isFirstPick ? "text-amber-200" : ""}`}>
                        {team.name || team.team_name || "—"}
                      </span>
                    ) : (
                      <span className="text-muted-foreground italic blur-sm select-none">
                        Hidden team
                      </span>
                    )}
                  </div>
                  {isFirstPick && (
                    <span className="text-xs uppercase tracking-wider font-bold text-amber-300">
                      🏆 #1 Overall
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        <div className="flex items-center justify-between pt-3 border-t border-border">
          {running && !allRevealed && (
            <Button variant="outline" size="sm" onClick={skip} data-testid="lottery-skip-btn">
              Skip animation
            </Button>
          )}
          <div className="ml-auto flex gap-2">
            <Button variant="outline" onClick={onClose} data-testid="lottery-close-btn">
              {allRevealed ? "Discard" : "Cancel"}
            </Button>
            {allRevealed && (
              <Button onClick={finish} data-testid="lottery-finish-btn">
                Lock in this order
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
