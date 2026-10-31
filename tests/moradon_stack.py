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
