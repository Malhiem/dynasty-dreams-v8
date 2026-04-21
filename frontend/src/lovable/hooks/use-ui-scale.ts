// @ts-nocheck
import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "dynasty-ice-ui-scale";
const DEFAULT_SCALE = 100;
const MIN_SCALE = 50;
const MAX_SCALE = 150;
const STEP = 10;

function getStoredScale(): number {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored !== null) {
    const val = parseInt(stored, 10);
    if (!isNaN(val) && val >= MIN_SCALE && val <= MAX_SCALE) return val;
  }
  return DEFAULT_SCALE;
}

export function useUiScale() {
  const [scale, setScaleState] = useState(getStoredScale);

  const setScale = useCallback((value: number) => {
    const clamped = Math.max(MIN_SCALE, Math.min(MAX_SCALE, value));
    localStorage.setItem(STORAGE_KEY, String(clamped));
    setScaleState(clamped);
    window.dispatchEvent(new Event("ui-scale-updated"));
  }, []);

  useEffect(() => {
    const handler = () => setScaleState(getStoredScale());
    window.addEventListener("ui-scale-updated", handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener("ui-scale-updated", handler);
      window.removeEventListener("storage", handler);
    };
  }, []);

  const resetScale = useCallback(() => setScale(DEFAULT_SCALE), [setScale]);

  return { scale, setScale, resetScale, MIN_SCALE, MAX_SCALE, STEP };
}
