import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import registerServiceWorker from "@/lib/registerServiceWorker";

// ── Apply persisted theme BEFORE first paint to avoid a FOUC.
// Reads the same key + falls back to "dark" the way `useTheme` does.
(() => {
  try {
    const saved = localStorage.getItem("dynasty-theme");
    const theme = saved === "light" || saved === "dark" ? saved : "dark";
    document.documentElement.classList.add(theme);
  } catch {
    document.documentElement.classList.add("dark");
  }
})();

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// Iter 231av — Register the offline-first service worker after first
// render. The helper is a no-op in `NODE_ENV=development` so CRA hot
// reload + HMR keep working.
registerServiceWorker();
