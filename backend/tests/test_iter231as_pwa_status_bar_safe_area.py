"""Iter 231as — PWA status-bar safe-area fix.

User screenshot: app launched as iOS PWA (Add to Home Screen → opened
in standalone mode) drew the "WELCOME BACK, SpringfieldIsotopes" header
under the system status bar, hiding the user's clock / battery / signal
icons.

RCA: Iter 231an set `apple-mobile-web-app-status-bar-style:
black-translucent` together with `viewport-fit=cover`. The translucent
status bar makes the system overlay the app instead of reserving a
slot for itself. Without `env(safe-area-inset-top)` padding on the
body, our content drew under the chrome.

Two-line fix:
  • `index.html` — flipped the meta to `default` so iOS reserves a
    status-bar slot in standalone mode (no overlap by default).
  • `index.css` — added `padding-{top|right|bottom|left}: env(safe-
    area-inset-*)` on the body so when `viewport-fit=cover` IS active
    (e.g. iOS 15+ where the system still surfaces the home indicator
    bar) the content is inset away from every safe-area edge. The
    `env()` macro resolves to 0 in regular browser tabs, so non-PWA
    users see no change.
"""
from pathlib import Path


INDEX = Path("/app/frontend/public/index.html")
INDEX_CSS = Path("/app/frontend/src/index.css")


def test_status_bar_style_no_longer_translucent():
    src = INDEX.read_text()
    # `default` reserves a slot for the status bar in iOS standalone.
    assert '<meta name="apple-mobile-web-app-status-bar-style" content="default" />' in src
    # The old translucent value must not slip back in as the active
    # meta value (the explanatory code comment may still reference it
    # for historical context — we only forbid the live `content=`).
    assert 'content="black-translucent"' not in src


def test_body_padding_uses_safe_area_insets():
    src = INDEX_CSS.read_text()
    # All four edges respected — top is the user's immediate complaint,
    # but bottom (home indicator) + left/right (landscape notch) matter
    # too on iOS 14+.
    assert "padding-top: env(safe-area-inset-top);" in src
    assert "padding-left: env(safe-area-inset-left);" in src
    assert "padding-right: env(safe-area-inset-right);" in src
    assert "padding-bottom: env(safe-area-inset-bottom);" in src
    # `100dvh` keeps min-height honest under standalone — `100vh`
    # double-counts the safe-area slots on some iOS versions.
    assert "min-height: 100dvh;" in src
