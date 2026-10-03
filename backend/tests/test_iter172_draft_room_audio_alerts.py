"""
Iter 172 — Draft Room audio alerts.

Static guards for the "next up" + "on the clock" audio cues:
  • The hook lives at /app/frontend/src/hooks/use-draft-sounds.ts and
    exports both useDraftSounds (default) and useTabTitleAlert.
  • DraftRoom.tsx wires the hook with a transition-aware useEffect
    (prev/curr picksUntilMyTurn comparison) so the chime only fires on
    the actual edge, never on every render.
  • The sound toggle is exposed in the Draft Live tile with the
    `draft-room-sounds-toggle` testid (used by Playwright smoke).
  • The hook persists the enabled flag via localStorage so a muted
    manager stays muted across reloads.
"""
from tests.source_tree import read_source
from pathlib import Path

HOOK = Path("/app/frontend/src/hooks/use-draft-sounds.ts")
DRAFT_ROOM = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")
LIVE_TILE = Path("/app/frontend/src/lovable/pages/draftroom/DraftLiveTile.tsx")


def test_hook_file_exists_and_exports_api():
    assert HOOK.exists(), "use-draft-sounds.ts hook is missing"
    src = read_source(HOOK)
    assert "export default function useDraftSounds" in src
    assert "export function useTabTitleAlert" in src
    # Public API surface used by DraftRoom.tsx.
    for symbol in ("playNextUp", "playOnTheClock", "setEnabled", "enabled"):
        assert symbol in src, symbol


def test_hook_synthesizes_two_distinct_patterns():
    src = read_source(HOOK)
    # Both tone tables should be defined as module-level constants so the
    # patterns are stable across renders.
    assert "NEXT_UP_TONES" in src
    assert "ON_CLOCK_TONES" in src
    # Distinct → at least one tone in ON_CLOCK_TONES should exceed the
    # highest tone in NEXT_UP_TONES, signaling urgency.
    assert "freq: 1318.5" in src  # E6 — on-the-clock peak
    assert "freq: 659.25" in src  # E5 — next-up start
    # On-the-clock arpeggio repeats for emphasis (≥ 6 osc nodes).
    assert src.count("freq:") >= 8


def test_hook_uses_web_audio_api_lazily():
    """Autoplay policies require a user gesture before audio plays. The
    hook must create the AudioContext lazily (not on import) and call
    resume() to satisfy Chrome / Safari."""
    src = read_source(HOOK, include_imports=False)
    assert "ensureContext" in src
    assert ".resume()" in src
    # No <audio> element / asset URL — we want zero-asset deployment.
    assert ".mp3" not in src
    assert ".wav" not in src
    assert "new Audio(" not in src


def test_hook_persists_enabled_flag():
    src = read_source(HOOK)
    assert "localStorage" in src
    assert "draftroom.sounds.enabled.v1" in src
    # Default ON so a fresh manager hears the alarm.
    assert "v === null ? true" in src or "v === null\n        ? true" in src


def test_tab_title_alert_only_flashes_when_hidden():
    src = read_source(HOOK)
    assert "document.hidden" in src
    # Restores original title on cleanup so we don't leak the prefix.
    assert "document.title = original" in src


def test_draftroom_imports_and_wires_hook():
    src = read_source(DRAFT_ROOM)
    assert "from '@/hooks/use-draft-sounds'" in src
    assert "useDraftSounds()" in src
    # Edge-detection: previous vs current picksUntilMyTurn.
    assert "prevPicksUntilRef" in src
    assert "playNextUp" in src
    assert "playOnTheClock" in src
    # Sound effect must be gated on draftStarted so hydration doesn't
    # blast the user with a chime on first mount.
    assert "draftConfig.draftStarted" in src and "playNextUp" in src
    # Tab-title flash hooked.
    assert "useTabTitleAlert" in src


def test_draftroom_transitions_only_fire_on_real_edges():
    """Guard against regressions where every render fires the chime —
    the comparison must use the ref + the new value AND ensure the new
    value differs from the previous one."""
    src = read_source(DRAFT_ROOM)
    assert "prev !== curr" in src
    assert "curr === 1 && prev > 1" in src
    assert "curr === 0 && prev > 0" in src


def test_live_tile_renders_sound_toggle():
    src = read_source(LIVE_TILE)
    assert 'data-testid="draft-room-sounds-toggle"' in src
    # When enabled, a preview button surfaces so managers can audition
    # the on-the-clock alert.
    assert 'data-testid="draft-room-sounds-preview"' in src
    # Both icons used.
    assert "<Volume2" in src
    assert "<VolumeX" in src
    # Tooltips imported (the Iter 172 regression that bit us locally).
    assert 'from "@/components/ui/tooltip"' in src


def test_live_tile_toggle_primes_audio_context_via_preview():
    """On toggle ON, we play the next-up chime inside the click handler
    so the AudioContext is unlocked under a user gesture. Otherwise the
    later "on the clock" alert never fires when the tab is hidden."""
    src = read_source(DRAFT_ROOM)
    # Toggle handler should preview NextUp on enable and surface a toast.
    assert "draftSounds.playNextUp()" in src
    assert "Draft alerts enabled" in src or "alerts enabled" in src.lower()
    assert "Draft alerts muted" in src or "alerts muted" in src.lower()


def test_no_audio_assets_were_added_to_public():
    """Iter 172 was explicitly a zero-asset feature — the tones are
    synthesized via Web Audio API. Guard against accidental .mp3/.wav
    drops into /public."""
    public = Path("/app/frontend/public")
    if not public.exists():
        return
    for ext in ("*.mp3", "*.wav", "*.ogg"):
        bad = [p for p in public.rglob(ext) if "draft" in p.name.lower() or "chime" in p.name.lower() or "alert" in p.name.lower()]
        assert not bad, f"Found stray audio assets: {bad}"
