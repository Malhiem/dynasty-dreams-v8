// @ts-nocheck
import { useRef, useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ChevronUp, ChevronDown } from "lucide-react";

/**
 * SmartNumberInput — number field with press-and-hold acceleration.
 *
 * Click once: increments/decrements by `step`.
 * Hold the button: after 400ms starts repeating; after 2s switches to
 * `fastStep`; after 4s to `turboStep`. Designed for big-money inputs like
 * salary cap where ±1 is useless and the user wants ±$100k → ±$500k → ±$1M.
 *
 * Usage:
 *   <SmartNumberInput
 *     value={cap}
 *     onChange={setCap}
 *     min={0}
 *     max={200_000_000}
 *     step={100_000}
 *     fastStep={500_000}
 *     turboStep={1_000_000}
 *     prefix="$"
 *     format={(n) => n.toLocaleString()}
 *   />
 */
export default function SmartNumberInput({
  value,
  onChange,
  min = 0,
  max = Number.MAX_SAFE_INTEGER,
  step = 1,
  fastStep = null,
  turboStep = null,
  prefix = "",
  format,
  className = "",
  inputClassName = "",
  disabled = false,
  testId,
}) {
  const intervalRef = useRef(null);
  const timeoutsRef = useRef([]);
  const stepRef = useRef(step);
  const startedAtRef = useRef(0);

  const clamp = (n) => Math.max(min, Math.min(max, n));

  const tick = useCallback(
    (dir) => {
      onChange((cur) => {
        const base = Number(cur) || 0;
        const next = base + dir * stepRef.current;
        return clamp(next);
      });
    },
    [onChange],
  );

  const clearAll = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    for (const t of timeoutsRef.current) clearTimeout(t);
    timeoutsRef.current = [];
    stepRef.current = step;
  };

  const startHold = (dir) => {
    if (disabled) return;
    startedAtRef.current = Date.now();
    stepRef.current = step;
    // First tick: immediate (handles a simple click)
    tick(dir);
    // After 400ms begin repeating
    const t1 = setTimeout(() => {
      intervalRef.current = setInterval(() => tick(dir), 90);
      // After 2s of holding, switch to fastStep
      if (fastStep) {
        const t2 = setTimeout(() => {
          stepRef.current = fastStep;
          // After 4s of holding, switch to turboStep
          if (turboStep) {
            const t3 = setTimeout(() => {
              stepRef.current = turboStep;
            }, 2000);
            timeoutsRef.current.push(t3);
          }
        }, 1600);
        timeoutsRef.current.push(t2);
      }
    }, 400);
    timeoutsRef.current.push(t1);
  };

  const display = format ? format(Number(value) || 0) : String(value ?? "");

  return (
    <div className={`flex items-center gap-1 ${className}`} data-testid={testId}>
      <div className="relative flex-1">
        {prefix && (
          <span className="absolute inset-y-0 left-3 flex items-center text-muted-foreground text-sm pointer-events-none">
            {prefix}
          </span>
        )}
        <Input
          type="text"
          inputMode="numeric"
          value={display}
          onChange={(e) => {
            // Strip non-digits to keep it controllable
            const raw = e.target.value.replace(/[^0-9-]/g, "");
            const num = raw === "" || raw === "-" ? 0 : parseInt(raw, 10);
            if (!Number.isNaN(num)) onChange(clamp(num));
          }}
          disabled={disabled}
          className={`${prefix ? "pl-7" : ""} pr-1 ${inputClassName}`}
          data-testid={testId ? `${testId}-input` : undefined}
        />
      </div>
      <div className="flex flex-col">
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-5 w-7 rounded-b-none border-b-0"
          onMouseDown={() => startHold(1)}
          onMouseUp={clearAll}
          onMouseLeave={clearAll}
          onTouchStart={(e) => {
            e.preventDefault();
            startHold(1);
          }}
          onTouchEnd={clearAll}
          disabled={disabled || Number(value) >= max}
          aria-label="Increase"
          data-testid={testId ? `${testId}-up` : undefined}
        >
          <ChevronUp className="h-3 w-3" />
        </Button>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-5 w-7 rounded-t-none"
          onMouseDown={() => startHold(-1)}
          onMouseUp={clearAll}
          onMouseLeave={clearAll}
          onTouchStart={(e) => {
            e.preventDefault();
            startHold(-1);
          }}
          onTouchEnd={clearAll}
          disabled={disabled || Number(value) <= min}
          aria-label="Decrease"
          data-testid={testId ? `${testId}-down` : undefined}
        >
          <ChevronDown className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}
