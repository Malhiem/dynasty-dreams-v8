"""Iter 231an — PWA shell (manifest + install banner) + mobile-friendly
Commissioner Settings tabs.

User asked for:
  "A one-tap 'Save to Home Screen' PWA banner the next time chriszarek
   opens the app on mobile. Adding a manifest.json + iOS/Android install
   hint would turn DynastyDreams into a true app-shell experience."

  "Also, please make the pages in League Administration more mobile
   friendly. Currently a lot of side scrolling across the sub-menu,
   perhaps a drop down may make it easier for mobile."

This locks in the artefacts:
  • `public/manifest.json` declares standalone display + theme + icons
  • `index.html` carries the PWA meta tags + apple-touch-icon
  • `PWAInstallBanner.tsx` covers both Android (`beforeinstallprompt`)
    and iOS Safari (manual Share → Add to Home Screen hint)
  • `CommissionerSettings.tsx` swaps the 13-item horizontal-scrolling
    tab strip for a `<Select>` dropdown on mobile (controlled state
    keeps desktop tabs + the dropdown in sync)
"""
import json
from pathlib import Path


FRONTEND = Path("/app/frontend")
PUBLIC = FRONTEND / "public"
SRC = FRONTEND / "src"

MANIFEST = PUBLIC / "manifest.json"
INDEX = PUBLIC / "index.html"
BANNER = SRC / "components" / "PWAInstallBanner.tsx"
APP_JS = SRC / "App.js"
COMMISSIONER = SRC / "lovable" / "pages" / "CommissionerSettings.tsx"


def test_manifest_declares_standalone_pwa():
    data = json.loads(MANIFEST.read_text())
    assert data["name"] == "DynastyDreams Fantasy Hockey"
    assert data["short_name"] == "DynastyDreams"
    # `standalone` strips the browser chrome so the app feels native.
    assert data["display"] == "standalone"
    # Theme + background match the DynastyDreams dark surface so
    # there's no white flash on launch.
    assert data["theme_color"] == "#0B0B0F"
    assert data["background_color"] == "#0B0B0F"
    # Both icon sizes Chrome / iOS reference, plus `maskable` so
    # adaptive Android launcher icons render correctly.
    sizes = sorted(i["sizes"] for i in data["icons"])
    assert sizes == ["192x192", "512x512"]
    for icon in data["icons"]:
        assert "maskable" in icon["purpose"]
    # App shortcuts surface the three highest-frequency actions
    # directly in the launcher long-press menu.
    shortcut_urls = {s["url"] for s in data["shortcuts"]}
    assert shortcut_urls == {"/draft-room", "/lineups", "/trades"}


def test_manifest_icons_exist_on_disk():
    for name in ("icon-192.png", "icon-512.png", "apple-touch-icon.png"):
        assert (PUBLIC / name).exists(), f"missing {name}"


def test_index_html_carries_pwa_meta():
    src = INDEX.read_text()
    # Manifest link.
    assert '<link rel="manifest" href="/manifest.json" />' in src
    # iOS-specific tags so Add to Home Screen produces a real icon
    # and the status bar matches the app surface.
    assert '<meta name="apple-mobile-web-app-capable" content="yes" />' in src
    assert 'apple-mobile-web-app-status-bar-style' in src
    assert 'apple-mobile-web-app-title' in src
    # `viewport-fit=cover` lets the app draw under the iOS notch /
    # Android cutout when launched in standalone mode.
    assert "viewport-fit=cover" in src
    # Theme colour switched from the inherited #000000 default to
    # the DynastyDreams dark surface so the address bar tints match.
    assert 'name="theme-color" content="#0B0B0F"' in src


def test_install_banner_handles_both_android_and_ios():
    src = BANNER.read_text()
    # Android: capture the `beforeinstallprompt` event and surface a
    # tappable "Install app" button.
    assert "beforeinstallprompt" in src
    assert "promptEvent.prompt()" in src
    # iOS: detect Mobile Safari without standalone mode and show the
    # manual Share → Add to Home Screen hint.
    assert "isIos" in src
    assert "Add to Home Screen" in src
    # Dismissal persists with a 30-day cool-down so we don't nag.
    assert "PWA_BANNER_DISMISSED_AT" in src
    assert "30 * 24 * 60 * 60 * 1000" in src
    # Banner is mobile-only; desktop browsers expose install via the
    # omnibox already.
    assert 'md:hidden' in src
    # data-testids on every interactive element for Playwright.
    for tid in (
        "pwa-install-banner",
        "pwa-install-banner-dismiss",
        "pwa-install-banner-install",
    ):
        assert f'"{tid}"' in src


def test_app_mounts_install_banner_inside_router():
    src = APP_JS.read_text()
    assert 'import PWAInstallBanner from "@/components/PWAInstallBanner"' in src
    # Mounted right after ImpersonationBanner so it lives above every
    # route's content but below the impersonation chrome.
    assert "<ImpersonationBanner />\n        <PWAInstallBanner />" in src


def test_commissioner_settings_tabs_collapse_to_dropdown_on_mobile():
    src = COMMISSIONER.read_text()
    # Single source of truth for the tab strip.
    assert "const COMMISSIONER_TABS" in src
    # Controlled active tab so the Select + TabsList stay in sync.
    assert 'useState<string>("league-setup")' in src
    assert "<Tabs value={activeTab} onValueChange={setActiveTab}" in src
    # Desktop tab strip is hidden below md.
    assert 'className="hidden md:flex flex-wrap h-auto bg-secondary border border-border"' in src
    # Mobile dropdown — wrapped in md:hidden so it disappears on desktop.
    assert '<div className="md:hidden">' in src
    assert 'data-testid="commissioner-settings-mobile-tab-select"' in src
    # Each option carries a testid so QA can drive the dropdown.
    assert 'data-testid={`commissioner-settings-mobile-tab-${value}`}' in src
    # Health-card jump now updates state directly (no more brittle
    # DOM-click) — the fallback remains for legacy callers.
    assert "if (typeof tab === \"string\") setActiveTab(tab);" in src


def test_commissioner_tabs_config_lists_every_section():
    """Locks in the 12 sub-sections so a future PR doesn't silently
    drop the dropdown's coverage."""
    src = COMMISSIONER.read_text()
    for tab in (
        "league-setup",
        "player-pool",
        "rosters",
        "divisions",
        "rules-schedule",
        "salary-cap-contracts",
        "scoring",
        "draft",
        "tanking",
        "roster-monitor",
        "admin",
        "audit-log",
    ):
        assert f'value: "{tab}"' in src, f"missing tab entry: {tab}"
