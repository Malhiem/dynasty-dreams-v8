// Iter 230k — Frontend ESLint flat-config (v9).
//
// PURPOSE
// -------
// Lock in the iter 228-230 megafile decomposition wins by hard-capping
// new `.tsx` files at 500 lines (non-blank, non-comment). Future PRs
// that silently re-grow these surfaces will fail lint.
//
// SCOPE
// -----
// THIS CONFIG ENFORCES ONE RULE ONLY: `max-lines` for `.tsx` files.
// All correctness rules (syntax, unused-vars, hooks, etc.) are handled
// by the platform linter that runs in this workspace.
//
// LEGACY FILES (RATCHET PATTERN)
// ------------------------------
// 37 .tsx files currently exceed the 500-line cap. Rather than
// disabling the rule wholesale for them, every legacy file has its
// own per-file ceiling set to its CURRENT line count. Net effect: each
// file can only get smaller, never larger. As contributors trim them
// below 500, simply delete that file's entry from `LEGACY_TSX_CEILINGS`
// and the global 500-line cap takes over automatically.
//
// USAGE
// -----
//   cd frontend && yarn lint              # check all .tsx files for size

import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

const LEGACY_TSX_CEILINGS = {
  "src/components/ui/sidebar.tsx": 638,
  "src/lovable/components/admin/SchedulesTab.tsx": 735,
  "src/lovable/components/dashboard/PlayerCardModal.tsx": 1157,
  "src/lovable/components/dashboard/PlayerRoster.tsx": 1158,
  "src/lovable/components/dashboard/TeamDraftPicks.tsx": 699,
  "src/lovable/components/dashboard/player-roster/sub-components.tsx": 1335,
  "src/lovable/components/trade/PickUpgradeEditor.tsx": 629,
  "src/lovable/components/trade/TradeBuilder.tsx": 708,
  "src/lovable/pages/Analytics.tsx": 791,
  "src/lovable/pages/Chat.tsx": 529,
  "src/lovable/pages/CommissionerSettings.tsx": 675,
  "src/lovable/pages/DepthChart.tsx": 942,
  "src/lovable/pages/DraftBoard.tsx": 936,
  "src/lovable/pages/DraftHistory.tsx": 565,
  "src/lovable/pages/DraftLottery.tsx": 677,
  "src/lovable/pages/DraftRoom.tsx": 816,
  "src/lovable/pages/LeagueHistory.tsx": 1393,
  "src/lovable/pages/Matchup.tsx": 547,
  "src/lovable/pages/PlayerPool.tsx": 540,
  "src/lovable/pages/PlayoffBracket.tsx": 711,
  "src/lovable/pages/SalaryCap.tsx": 1013,
  "src/lovable/pages/Scoring.tsx": 627,
  "src/lovable/pages/Standings.tsx": 924,
  "src/lovable/pages/Team.tsx": 915,
  "src/lovable/pages/Transactions.tsx": 1136,
  "src/lovable/pages/TrophyRoom.tsx": 533,
  "src/lovable/pages/Waivers.tsx": 1000,
  "src/lovable/pages/admin/components/AdminActionsPanel.tsx": 624,
  "src/lovable/pages/commissioner/ExpansionDraftSettingsCard.tsx": 522,
  "src/lovable/pages/commissioner/OpsConsole.tsx": 743,
  "src/lovable/pages/commissioner/PlayoffsScheduleCards.tsx": 1128,
  "src/lovable/pages/commissioner/RostersTab.tsx": 867,
  "src/lovable/pages/commissioner/TransactionsConfigCards.tsx": 1274,
  "src/lovable/pages/commissioner/data/commissionerData.tsx": 905,
  "src/lovable/pages/commissioner/tabs/DraftTab.tsx": 1208,
  "src/lovable/pages/draftroom/DraftChatPanel.tsx": 518,
  "src/lovable/pages/site-admin/OperationsConsole.tsx": 584,
};

// Build one ESLint config block per legacy file with its own `max-lines`
// ceiling. Each block uses the file path as the only entry in `files`
// so the rule does not bleed into siblings.
const legacyOverrides = Object.entries(LEGACY_TSX_CEILINGS).map(([file, max]) => ({
  files: [file],
  rules: {
    "max-lines": ["error", { max, skipBlankLines: true, skipComments: true }],
  },
}));

export default [
  // TypeScript parser for .ts/.tsx so `max-lines` can actually scan them.
  // Plugins are REGISTERED but their rules are OFF — we register them
  // so that inline `eslint-disable react-hooks/exhaustive-deps` and
  // `eslint-disable @typescript-eslint/no-unused-vars` directives
  // scattered throughout the codebase resolve to known rule names
  // (otherwise ESLint v9 errors on "rule definition not found"). The
  // platform linter owns enforcement of those rules.
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "@typescript-eslint": tseslint.plugin,
    },
    linterOptions: {
      // Other configs may add inline `eslint-disable` directives that
      // appear "unused" against our minimal rule set. Don't punish them.
      reportUnusedDisableDirectives: "off",
    },
  },

  // ── Global 500-line cap for all .tsx files ─────────────────────────────
  // Counts code lines only (no blanks, no comments). New components that
  // approach this number should be decomposed into smaller pieces
  // BEFORE merging.
  {
    files: ["src/**/*.tsx"],
    rules: {
      "max-lines": [
        "error",
        { max: 500, skipBlankLines: true, skipComments: true },
      ],
    },
  },

  // ── Per-file legacy ceilings (ratchet pattern) ─────────────────────────
  // Spread last so they win over the global 500-line cap.
  ...legacyOverrides,

  // ── Ignore non-source paths ───────────────────────────────────────────
  {
    ignores: [
      "build/**",
      "node_modules/**",
      "public/**",
      "**/*.test.tsx",
      "**/*.test.ts",
      // Generated / vendored
      "src/components/ui/**/*.test.tsx",
    ],
  },
];
