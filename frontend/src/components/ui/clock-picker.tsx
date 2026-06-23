// @ts-nocheck
/**
 * ClockPicker — shadcn-style popover dial picker.
 *
 * Drop-in replacement for `<input type="time">` that surfaces a 12-hour dial
 * (hour ring + minute ring) with AM/PM toggle. Emits an HH:MM 24-hour string
 * so existing form state plumbing works unchanged.
 *
 * Usage:
 *   <ClockPicker value={time} onChange={setTime} data-testid="..." />
 */
import { useMemo, useState } from "react";
import { Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

function pad(n) { return String(n).padStart(2, "0"); }

function parse24(value) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(value || "");
  if (!m) return { h: 9, m: 0 };
  return {
    h: Math.max(0, Math.min(23, parseInt(m[1], 10))),
    m: Math.max(0, Math.min(59, parseInt(m[2], 10))),
  };
}

function to12(h24) {
  const period = h24 >= 12 ? "PM" : "AM";
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return { h12, period };
}

function to24(h12, period) {
  if (period === "AM") return h12 === 12 ? 0 : h12;
  return h12 === 12 ? 12 : h12 + 12;
}

/**
 * A clickable polar dial. radius/inner ratio chosen so the hour ring sits
 * inside and the minute ring sits outside without overlapping.
 */
function Dial({ values, selected, onPick, radius, fontSize = 11 }) {
  const cx = 90; const cy = 90;
  return values.map((v, idx) => {
    const angle = (idx / values.length) * 2 * Math.PI - Math.PI / 2;
    const x = cx + radius * Math.cos(angle);
    const y = cy + radius * Math.sin(angle);
    const isSelected = String(v) === String(selected);
    return (
      <g key={`${v}-${idx}`} onClick={() => onPick(v)} className="cursor-pointer">
        <circle cx={x} cy={y} r="11"
          className={isSelected ? "fill-primary" : "fill-transparent hover:fill-secondary/40"}
        />
        <text x={x} y={y} dy="0.35em" textAnchor="middle"
          className={`select-none ${isSelected ? "fill-primary-foreground" : "fill-foreground"}`}
          style={{ fontSize, fontWeight: isSelected ? 700 : 500 }}
        >
          {v}
        </text>
      </g>
    );
  });
}

export function ClockPicker({
  value,
  onChange,
  className = "",
  placeholder = "HH:MM",
  disabled = false,
  "data-testid": dataTestId,
}) {
  const [open, setOpen] = useState(false);
  const parsed = useMemo(() => parse24(value), [value]);
  const { h12, period } = to12(parsed.h);

  const setH = (newH12) => {
    onChange(`${pad(to24(newH12, period))}:${pad(parsed.m)}`);
  };
  const setM = (newM) => {
    onChange(`${pad(parsed.h)}:${pad(newM)}`);
  };
  const togglePeriod = () => {
    const newPeriod = period === "AM" ? "PM" : "AM";
    onChange(`${pad(to24(h12, newPeriod))}:${pad(parsed.m)}`);
  };

  const hours = [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
  const minutes = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55];

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <div className={`relative ${className}`}>
          <Input
            readOnly
            value={value || ""}
            placeholder={placeholder}
            disabled={disabled}
            onClick={() => !disabled && setOpen(true)}
            data-testid={dataTestId}
            className="pr-9 cursor-pointer"
          />
          <Clock className="h-4 w-4 absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
        </div>
      </PopoverTrigger>
      <PopoverContent className="w-[280px] p-4" align="start" data-testid="clock-picker-popover">
        {/* Read-out + AM/PM toggle */}
        <div className="flex items-center justify-between mb-3">
          <div className="text-3xl font-mono tabular-nums" data-testid="clock-picker-readout">
            {pad(h12)}:{pad(parsed.m)}
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={togglePeriod}
            data-testid="clock-picker-period-toggle"
          >
            {period}
          </Button>
        </div>

        {/* Dial */}
        <svg viewBox="0 0 180 180" className="w-full h-auto select-none" role="img" aria-label="Clock picker dial">
          <circle cx="90" cy="90" r="86" className="fill-muted/30 stroke-border" strokeWidth="1" />
          {/* Minute ring (outer, every 5 min) */}
          <Dial values={minutes} selected={parsed.m - (parsed.m % 5)} onPick={setM} radius={75} fontSize={9} />
          {/* Hour ring (inner) */}
          <Dial values={hours} selected={h12} onPick={setH} radius={50} fontSize={12} />
          <circle cx="90" cy="90" r="3" className="fill-primary" />
        </svg>

        <div className="flex items-center justify-between mt-3">
          <span className="text-[10px] text-muted-foreground">Click hour (inner) and minute (outer)</span>
          <Button type="button" size="sm" onClick={() => setOpen(false)} data-testid="clock-picker-done">Done</Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
