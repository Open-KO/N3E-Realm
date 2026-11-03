#!/usr/bin/env python3
"""The realm's local package, build/packages/moradon, kept to the tree that tests it.

  python tools/assetc/realm_assets.py           bake it again only when its inputs changed
  python tools/assetc/realm_assets.py --always  bake it (make realm-assets)

The bake is `make realm-assets`'s, `tools/assetc/ko_bake.py 210 --features
--into=build`, from the player's own KO data. tests/npc_reference.py checks that
package with this tree's readers, so a package baked by an older cooker (a
front-end.bin at N3FE 12 after RQ-109 moved the cook to 13) failed `make
test-fast` until someone baked it again by hand. `make test-fast` runs this first
instead: the package is baked again when the stamp beside it,
build/packages/moradon.inputs, does not hold the hash of what the bake reads
from the tree, and the package's own release.sha256 as that bake wrote it. The
inputs are every file under tools/assetc and games that git tracks or would add
(untracked but not ignored; working-tree bytes, so an uncommitted change
counts), UPSTREAM.md (the pinned KO client tree) and the 1264 install's
manifest (games/moradon/front-ends.json, RQ-085). The KO data itself is pinned
there and never rehashed (about 280 MB). A package rewritten since by another
bake (a plain `ko_bake.py 210`, say) no longer matches its release hash and is
baked again.

Without the KO client tree (tools/fetch-ko-assets.sh) or the unpacked 1264
install, the default run bakes nothing and leaves the package as it is: its
checks then skip or fail as they did before. `--always` (make realm-assets)
instead fails, naming what is missing, so a stale package is never published as
the realm's. A bake that fails exits with its status and leaves the stamp
unwritten, so the next run bakes again.
"""
import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE = pathlib.Path("build/packages/moradon")
STAMP = pathlib.Path("build/packages/moradon.inputs")
BAKE = ["tools/assetc/ko_bake.py", "210", "--features", "--into=build"]
CLIENT = pathlib.Path("assets/ko")
INSTALL_1264 = pathlib.Path("build/ko-reference/installer-1264/manifest.json")
TRACKED = ["tools/assetc", "games", "UPSTREAM.md"]


def inputs():
    """The hash of the bake's command and the tree files it reads."""
    names = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *TRACKED],
                           cwd=ROOT, check=True, capture_output=True).stdout.split(b"\0")
    h = hashlib.sha256(b"\0".join(a.encode() for a in BAKE) + b"\n")
    for name in sorted(set(n for n in names if n)):
        path = ROOT / name.decode()
        if path.is_file():  # a tracked file deleted in the working tree is not read
            h.update(name + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    h.update(b"installer-1264\0" + hashlib.sha256((ROOT / INSTALL_1264).read_bytes()).digest())
    return h.hexdigest()


def release():
    """The package's release hash, or None without one."""
    path = ROOT / PACKAGE / "release.sha256"
    return path.read_text().strip() if path.is_file() else None


def main(argv):
    if argv[1:] not in ([], ["--always"]):
        raise SystemExit(__doc__)
    missing = [str(p) for p in (CLIENT, INSTALL_1264) if not (ROOT / p).exists()]
    if missing and argv[1:]:
        print("realm-assets: FAIL cannot bake %s: no %s (the client tree: make ko-assets; the 1264 install: "
              "python3 -I tools/ko-reference/unpack_installer.py <knightonlinesetup_1264.exe>)"
              % (PACKAGE, " or ".join(missing)))
        return 2
    if missing:
        print("realm-assets: %s kept as it is: no %s to bake it from" % (PACKAGE, " or ".join(missing)))
        return 0
    stamp = inputs()
    current = (ROOT / STAMP).read_text().split() if (ROOT / STAMP).is_file() else None
    if argv[1:] == [] and current == [stamp, release()]:
        print("realm-assets: %s is current (inputs %s)" % (PACKAGE, stamp[:12]))
        return 0
    why = ("asked" if argv[1:] else "no stamp" if current is None
           else "its inputs changed" if current[:1] != [stamp] else "the package changed since")
    print("realm-assets: baking %s (%s): python %s" % (PACKAGE, why, " ".join(BAKE)), flush=True)
    (ROOT / STAMP).unlink(missing_ok=True)
    code = subprocess.run([sys.executable, *BAKE], cwd=ROOT).returncode
    if code:
        print("realm-assets: FAIL the bake exited %d" % code)
        return code
    (ROOT / STAMP).write_text("%s %s\n" % (stamp, release()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
