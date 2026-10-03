// @ts-nocheck
/**
 * Shared helpers for Rules & Schedule card components.
 * Extracted from RulesScheduleTab.tsx during iter 228c.
 */

export const fmtMoney = (n: number) => (Number(n) || 0).toLocaleString();

export const DAY_OPTIONS = [
  { value: "monday", label: "Monday" },
  { value: "tuesday", label: "Tuesday" },
  { value: "wednesday", label: "Wednesday" },
  { value: "thursday", label: "Thursday" },
  { value: "friday", label: "Friday" },
  { value: "saturday", label: "Saturday" },
  { value: "sunday", label: "Sunday" },
];

// 5-minute increments from 0 to 1440 (24 hrs)
export const LOCK_TIME_OPTIONS = (() => {
  const opts: { value: string; label: string }[] = [];
  for (let m = 0; m <= 1440; m += 5) {
    let label: string;
    if (m === 0) label = "At first match start (0 min)";
    else if (m < 60) label = `${m} min before first match`;
    else if (m % 60 === 0) label = `${m / 60} hr before first match`;
    else label = `${Math.floor(m / 60)} hr ${m % 60} min before first match`;
    opts.push({ value: String(m), label });
  }
  return opts;
})();
