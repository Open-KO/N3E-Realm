"""Compatibility entry point: production integration now exercises Phase 2."""

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name("multiplayer.py")), run_name="__main__")
