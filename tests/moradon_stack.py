"""Which Moradon stack the opt-in moradon_*_live suites probe (PQ-111).

By default the persistent local demo that `tools/play-moradon --provision-only`
starts (Compose project n3e-moradon, state in build/moradon-demo/session.json).
`make live-ko` runs each suite through tests/ko_stack.py instead, which starts a
disposable stack of its own and names it here through N3E_MORADON_STATE,
N3E_MORADON_PROJECT and N3E_IMAGE, so no user stack or character is touched.

The package and its build provenance are under N3E_KO_WORK (default build/, where
tools/play-moradon cooks them); make live-ko cooks its own copies under
build/live-ko/work so it never replaces the package a persistent stack mounts.
"""
import json
import os
import sys
from pathlib import Path

STATE_PATH = Path(os.environ.get("N3E_MORADON_STATE", "build/moradon-demo/session.json"))
PROJECT = os.environ.get("N3E_MORADON_PROJECT", "n3e-moradon")
IMAGE = os.environ.get("N3E_IMAGE", "n3e-moradon:local")
WORK = Path(os.environ.get("N3E_KO_WORK", "build"))
PACKAGE = WORK / "packages/moradon"
PROVENANCE = WORK / "ko-moradon/provenance.json"


def state():
    """{'port', 'realm', 'release', 'zone'} of the stack under test."""
    return json.loads(STATE_PATH.read_text())


def effects_magic(provenance):
    """RQ-219: the magic of effects.bin in a Moradon feature package (default,
    classic, 1097, glow2233) cooked under the realm's current choice: N3E5
    since PQ-376 (1298's alpha-list sort records), N3E6 since RQ-206 where
    games/moradon/realm-config.json sets `world_dust` draw (RQ-203: N3E5 whose
    sort list may be empty, then the dust section). The cook's `provenance`
    (its 'effects' record) must agree: a dust record with KO's two textures and
    at least one key exactly when the file is N3E6."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/assetc"))
    import front_end_choice
    import ko_fx_bake
    dust = front_end_choice.world_dust(Path("games/moradon"))
    record = provenance["effects"].get("dust")
    if dust:
        assert record and record["textures"] == list(ko_fx_bake.DUST) and record["keys"], record
    else:
        assert record is None, record
    return b"N3E6" if dust else b"N3E5"
