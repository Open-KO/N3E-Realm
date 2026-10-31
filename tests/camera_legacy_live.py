"""Opt-in retained play/HUD replay against an existing local legacy field package.

The replay is tests/play_replay_live.py's, which `make live` runs on the demo
package; here it runs on the KO field package `make live-ko` cooks (PQ-129).
"""

import os
from pathlib import Path
from play_replay_live import replay

package = Path(os.environ.get("N3E_TEST_PACKAGE", Path(os.environ.get("N3E_KO_WORK", "build"), "packages/ko-field")))
played = replay(package, "build/ko-02/legacy")
print("PASS legacy package right drag/release, zoom, click travel, HUD/chat and target replay:", played)
