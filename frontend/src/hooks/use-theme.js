import { useEffect, useState, useCallback } from "react";

const STORAGE_KEY = "dynasty-theme";

/**
 * Resolve, persist, and broadcast the active app theme.
 *
 * - Persists the user's choice in localStorage so it survives reloads.
 * - Applies `class="dark"` or `class="light"` to the <html> element which
 *   triggers the matching CSS variable block in index.css.
 * - Defaults to "dark" (the historical Dynasty Dreams aesthetic) when no
 *   choice has been made yet — we don't auto-follow `prefers-color-scheme`
 *   because the brand identity is a dark-first one.
 */
export function useTheme() {
  const [theme, setThemeState] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === "light" || saved === "dark") return saved;
    } catch { /* noop */ }
    return "dark";
  });

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(theme);
    try { localStorage.setItem(STORAGE_KEY, theme); } catch { /* noop */ }
  }, [theme]);

  const setTheme = useCallback((next) => setThemeState(next), []);
  const toggle = useCallback(
    () => setThemeState((t) => (t === "dark" ? "light" : "dark")),
    [],
  );

  return { theme, setTheme, toggle };
}
