"""Iter 231ap — Harden `PWAInstallBanner` against the "Script error."
overlay that surfaced when chriszarek tapped Install.

The dev overlay's red "Uncaught runtime errors: Script error." is what
`window.onerror` reports when ANY listener throws and the source isn't
same-origin with proper CORS. Two failure paths exist in the banner:

  1. `localStorage` access on Safari Private mode + sandboxed
     iframes throws a `SecurityError` on the very first read.
  2. `BeforeInstallPromptEvent.prompt()` throws `InvalidStateError` if
     called more than once on the same event — which happens trivially
     under a double-tap.

This iteration wraps every browser-surface call in try/catch and
disables the install button while a prompt is in-flight, so the
banner never propagates an exception to the global handler.
"""
from pathlib import Path


BANNER = Path("/app/frontend/src/components/PWAInstallBanner.tsx")


def test_storage_access_is_guarded():
    src = BANNER.read_text()
    # Every localStorage / matchMedia / navigator access goes through
    # a safe wrapper. The wrappers themselves must catch.
    for helper in ("safeMatchMedia", "safeLocalStorageGet", "safeLocalStorageSet"):
        assert f"function {helper}" in src, f"missing helper {helper}"
    # No direct `localStorage.getItem(` outside the safe helper.
    # (The helper is the only call site that does so.)
    raw_calls = src.count("localStorage.getItem")
    assert raw_calls == 1, f"expected 1 raw localStorage.getItem call (inside safeLocalStorageGet), got {raw_calls}"
    raw_sets = src.count("localStorage.setItem")
    assert raw_sets == 1, f"expected 1 raw localStorage.setItem call (inside safeLocalStorageSet), got {raw_sets}"


def test_install_button_disables_to_defeat_double_tap():
    src = BANNER.read_text()
    # `installing` flag prevents the InvalidStateError that
    # `BeforeInstallPromptEvent.prompt()` throws on the 2nd call.
    assert "const [installing, setInstalling]" in src
    assert "if (!promptEvent || installing) return;" in src
    assert "setInstalling(true);" in src
    assert "setInstalling(false);" in src
    # The button itself is `disabled={installing}` + shows a pending
    # label so the user gets feedback.
    assert "disabled={installing}" in src
    assert "Opening…" in src


def test_install_swallows_errors_so_dev_overlay_stays_quiet():
    src = BANNER.read_text()
    # The `prompt()` call site has try / catch / finally. The catch
    # block sets the dismissal cookie so we don't keep nagging if
    # something is broken in the user's environment.
    assert "await promptEvent.prompt();" in src
    # Catch block exists right under the try in `install`.
    install_block = src.split("const install = async () =>")[1].split("};")[0]
    assert "try {" in install_block
    assert "} catch {" in install_block
    assert "} finally {" in install_block
    # All of `safeLocalStorageSet` is fire-and-forget — verify we
    # actually use it (not the raw API) in the catch.
    assert "safeLocalStorageSet(DISMISS_KEY" in install_block


def test_useeffect_body_is_fully_guarded():
    src = BANNER.read_text()
    effect_block = src.split("useEffect(() => {")[1].split("}, []);")[0]
    # Every browser-surface call inside the effect is in a try/catch
    # so a single failure (SecurityError, matchMedia stub, etc.) never
    # propagates to React's render path.
    assert effect_block.count("try {") >= 3
    assert effect_block.count("} catch {") >= 3
