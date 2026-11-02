"""The reference installs a cook may read, each pinned by its installer (RQ-084).

A reference install is the player's own unpack of a KO installer, at
`build/ko-reference/<name>` (git-ignored; often a link): the installed files
under `client/` and the unpacker's `manifest.json`, which names the installer
by its SHA-256 and lists every file it installed with its SHA-256
(tools/ko-reference/unpack_installer.py, unpack_inno.py). A cook reads one only
when that manifest names the pinned installer, and each file it reads only when
the file is the one the manifest lists (`ko_character.Assets(..., manifest=)`):
as `ko_bake --client=1097` checks the 1097 install (PQ-274) and `ko_glow_2233`
the 2145 one (PQ-315). Installs are named only by their link names here; where
the links point is the maintainer's own setup.
"""
import hashlib
import json
import pathlib

REFERENCE = pathlib.PurePosixPath("build/ko-reference")
# The install's own files, as the unpackers write them.
CLIENT = "client"
MANIFEST = "manifest.json"
MAX_MANIFEST = 64 * 1024 * 1024
# By link name: the installer's SHA-256 and how to unpack it.
PINNED = {
    # KnightOnline_1097.exe, 201,059,508 bytes (PQ-221, PQ-274).
    "installer-1097": dict(
        sha256="d7571e183663be3d063af491d68d7db3dc52219f58471c9595d0b745c0b8a93b",
        unpack="python3 -I tools/ko-reference/unpack_installer.py ref/ko-bin/installer/KnightOnline_1097.exe"),
    # knightonlinesetup_1264.exe, 297,557,888 bytes (PQ-214; RQ-085: the 1097
    # front end draws 1264's English screens, specs/KO-FINDINGS.md 9.1).
    "installer-1264": dict(
        sha256="eb4e1a3508c33f381fbeeedccf95f09a746a7d6ead3ccc97616ab6b2f3ccafb5",
        unpack="python3 -I tools/ko-reference/unpack_installer.py ref/ko-bin/installer/knightonlinesetup_1264.exe"),
    # KnightOnlineSetup_v2145.exe, 774,488,528 bytes (PQ-214, PQ-227).
    "installer-2145": dict(
        sha256="7da88158e1ddb9c689c22d8e3cb1e8b2655d973ac21596d798104c81c30a1edf",
        unpack="python3 -I tools/ko-reference/unpack_inno.py ref/ko-bin/installer/KnightOnlineSetup_v2145.exe"),
}


def install_of(tree):
    """The pinned install a repository-relative tree reads (its link name), None
    for a tree outside `build/ko-reference`, or ValueError for any other tree
    inside it: a cook reads a reference install only as `<name>/client` of a
    pinned one."""
    parts = pathlib.PurePosixPath(tree).parts
    if parts[:len(REFERENCE.parts)] != REFERENCE.parts:
        return None
    rest = parts[len(REFERENCE.parts):]
    if len(rest) != 2 or rest[0] not in PINNED or rest[1] != CLIENT:
        raise ValueError("%s is not a pinned reference install: a cook reads %s/<name>/%s, <name> one of %s"
                         % (tree, REFERENCE, CLIENT, ", ".join(sorted(PINNED))))
    return rest[0]


def manifest(install, name):
    """The install directory's manifest, checked to name `name`'s pinned
    installer: dict(manifest, manifest_sha256, installer_sha256, hashes), the
    hashes by lower-case path under `client/`."""
    install = pathlib.Path(install)
    path = install / MANIFEST
    pin = PINNED[name]
    if not path.is_file():
        raise ValueError("no %s manifest at %s: run %s" % (name, path, pin["unpack"]))
    if path.stat().st_size > MAX_MANIFEST:
        raise ValueError("%s is over %d bytes" % (path, MAX_MANIFEST))
    data = path.read_bytes()
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("%s is not an unpacker's manifest (%s)" % (path, error))
    if type(value) is not dict:
        raise ValueError("%s is not an unpacker's manifest (not a JSON object)" % path)
    if value.get("sha256") != pin["sha256"]:
        raise ValueError("%s is not the pinned %s installer's unpack (run %s)" % (path, name, pin["unpack"]))
    entries = value.get("manifest")
    if type(entries) is not list or not all(
            type(e) is dict and type(e.get("path")) is str and type(e.get("sha256")) is str for e in entries):
        raise ValueError("%s is not an unpacker's manifest (no file list)" % path)
    hashes = {e["path"].replace("\\", "/").lower(): e["sha256"] for e in entries}
    return dict(manifest=str(path), manifest_sha256=hashlib.sha256(data).hexdigest(),
                installer_sha256=pin["sha256"], hashes=hashes)
