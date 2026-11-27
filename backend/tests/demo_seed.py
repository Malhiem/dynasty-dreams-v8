"""Skip helper for tests that verify the full demo seed (the five demo leagues,
86 demo teams, seeded minors). The disposable test stack seeds only its own
fixtures, so those tests have nothing to check there; they still run against
an environment that loaded the demo seed."""
import pytest

DEMO_LEAGUE = "Ice Kings Head-to-Head"


def require_demo_seed(league_names):
    if DEMO_LEAGUE not in set(league_names):
        pytest.skip("demo seed not loaded in this environment")
