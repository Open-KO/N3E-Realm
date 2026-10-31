"""N3N2 reference NPC policy: cooker bounds, cross-language golden, and both readers.

The golden bytes are also parsed by the Rust unit test
`npc_ai::tests::reference_policy_golden_matches_cooker`. The reader checks use the
local-asset Moradon package when it has been built; without it they are skipped
explicitly, never counted as passing.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path("tools/assetc").resolve()))
# After tools/assetc: tests/npc.py would shadow the cooker's npc module.
sys.path.append(str(Path("tests").resolve()))
import npc
from common import u, string, digest

policy = {
    "model": "reference_melee_v2", "scan_ticks": 10, "acquire_ticks": 10, "stuck_ticks": 40,
    "chase_ticks": 200, "return_ticks": 200, "recovery_ticks": 20, "acquisition": "passive",
    "renew_on_hit": True, "return_heal": False, "retaliate_returning": True,
    "return_speed_percent": 200, "regen_interval_ticks": 200, "regen_divisor": 20, "spawn_tries": 500,
    "slots": [{"area": [-8, -8, 7, 8], "respawn_ticks": 600}, {"area": [-12, -12, 9, 10], "respawn_ticks": 400}],
}
golden = bytes.fromhex(Path("tests/fixtures/npc-reference.hex").read_text().strip())
assert npc.cook(policy, [[0, 0], [1, 1]]) == golden, "cooker drifted from the committed golden"


def rejects(value, spawns=None):
    try:
        npc.cook(value, spawns)
    except ValueError:
        return
    raise AssertionError(("accepted", value))


rejects(policy, [[0, 0]])  # one slot per spawn point
# PQ-250: one slot per spawn up to the shared 2,048 bound.
assert npc.cook(dict(copy.deepcopy(policy), slots=[policy["slots"][0]] * 2048), [[0, 0]] * 2048)
rejects(dict(copy.deepcopy(policy), slots=[policy["slots"][0]] * 2049), [[0, 0]] * 2049)
for key, bad in [("acquisition", "hostile"), ("renew_on_hit", 1), ("return_speed_percent", 99),
                 ("return_speed_percent", 301), ("regen_interval_ticks", 12001), ("regen_divisor", 0),
                 ("spawn_tries", 0), ("spawn_tries", 501), ("chase_ticks", 0), ("slots", []),
                 ("slots", [policy["slots"][0]] * 2049)]:
    rejects(dict(copy.deepcopy(policy), **{key: bad}))
for area in [[1, -1, 1, 1], [-1, 1, 1, 1], [-1, -1, -1, 1], [-1, -1, 1, -1], [-257, 0, 0, 0], [0, 0, 1.5, 0], [0, 0, 1]]:
    bad = copy.deepcopy(policy)
    bad["slots"][0]["area"] = area
    rejects(bad)
for slot in [{"area": [0, 0, 0, 0], "respawn_ticks": 0}, {"area": [0, 0, 0, 0], "respawn_ticks": 12001},
             {"area": [0, 0, 0, 0]}, {"area": [0, 0, 0, 0], "respawn_ticks": 1, "extra": 1}]:
    bad = copy.deepcopy(policy)
    bad["slots"][0] = slot
    rejects(bad)
rejects({k: v for k, v in policy.items() if k != "spawn_tries"})
rejects(dict(policy, extra=1))
# The N3N1 vocabulary is unchanged and cannot carry reference fields.
legacy = {k: policy[k] for k in npc.FIELDS}
assert npc.cook(dict(legacy, model="hostile_melee_v1")).startswith(b"N3N1")
rejects(dict(legacy, model="hostile_melee_v1", acquisition="passive"))
print("PASS N3N2 cooker bounds and cross-language golden")

# N3N3 (PQ-249): the template table. Same golden as the Rust unit test
# npc_ai::tests::template_policy_golden_matches_cooker.
templated = {k: v for k, v in policy.items() if k != "acquisition"}
templated["model"] = "reference_templates_v3"
templated["templates"] = [
    {"name": "demo:creature/worm", "looks": "demo:looks/worm", "acquisition": "passive", "health": 7, "level": 1,
     "xp": 10, "damage": 2, "attack": 18, "defense": 40, "accuracy": 50, "evasion": 100, "attack_ticks": 40,
     "speed": 3, "attack_range": 1, "search_range": 3, "tracing_range": 40},
    {"name": "demo:creature/bandit", "looks": "demo:looks/bandit", "acquisition": "aggressive", "health": 90, "level": 5,
     "xp": 40, "damage": 9, "attack": 60, "defense": 10, "accuracy": 80, "evasion": 60, "attack_ticks": 30,
     "speed": 2.5, "attack_range": 1.5, "search_range": 6, "tracing_range": 20},
]
templated["slots"] = [dict(policy["slots"][0], template="demo:creature/bandit"),
                      dict(policy["slots"][1], template="demo:creature/worm")]
template_golden = bytes.fromhex(Path("tests/fixtures/npc-templates.hex").read_text().strip())
assert npc.cook(templated, [[0, 0], [1, 1]], "demo") == template_golden, "N3N3 cooker drifted from the committed golden"


def rejects_templated(change, game="demo"):
    bad = copy.deepcopy(templated)
    change(bad)
    try:
        npc.cook(bad, [[0, 0], [1, 1]], game)
    except ValueError:
        return
    raise AssertionError(("accepted", bad))


rejects_templated(lambda b: b.update(acquisition="passive"))  # acquisition lives in each template
rejects_templated(lambda b: b.update(templates=[]))
rejects_templated(lambda b: b.update(templates=b["templates"] * 129))  # 258 > 256
rejects_templated(lambda b: b["templates"][1].update(name="demo:creature/worm"))
rejects_templated(lambda b: b["slots"][0].update(template="demo:creature/missing"))
rejects_templated(lambda b: b["slots"][0].pop("template"))
rejects_templated(lambda b: b["templates"][0].update(search_range=41))
rejects_templated(lambda b: b["templates"][0].update(acquisition="hostile"))
rejects_templated(lambda b: b["templates"][0].pop("looks"))
rejects_templated(lambda b: b["templates"][0].update(extra=1))
rejects_templated(lambda b: b["templates"][0].update(name="other:creature/worm"))
for key, value in [("health", 0), ("health", 2000001), ("level", 0), ("level", 256), ("xp", -1), ("xp", 50000001),
                   ("damage", -1), ("damage", 100001), ("attack", 10001), ("defense", 32768), ("accuracy", 32768),
                   ("evasion", 32768), ("accuracy", -1), ("attack_ticks", 0),
                   ("attack_ticks", 1201), ("speed", -0.5), ("speed", 12.5), ("attack_range", 0), ("attack_range", 65),
                   ("tracing_range", 65), ("health", 1.5), ("speed", float("nan"))]:
    rejects_templated(lambda b, k=key, v=value: b["templates"][0].update({k: v}))
rejects_templated(lambda b: b["templates"][0].update(search_range=65, tracing_range=64))
# PQ-251 (D-164): the reference rows' bounds (tools/assetc/ko_npc.py) cook.
top = copy.deepcopy(templated)
top["templates"][0].update(health=2000000, level=255, speed=0, attack_range=64, search_range=64, tracing_range=64)
top["templates"][1].update(speed=12, attack_range=0.05, search_range=0.05)
# PQ-252 (D-165): the rows' combat columns, 0 and the largest (iExp 39,438,375).
top["templates"][0].update(xp=50000000, damage=100000, attack=10000, defense=32767, accuracy=32767, evasion=32767)
top["templates"][1].update(xp=0, damage=0, attack=0, defense=0, accuracy=0, evasion=0)
assert npc.cook(top, [[0, 0], [1, 1]], "demo")
print("PASS N3N3 cooker bounds, template vocabulary and cross-language golden")

# N3N4 (PQ-272, D-179): a template's drawn scale in percent (KO sSize). Same
# golden as the Rust unit test npc_ai::tests::scaled_template_golden_matches_cooker.
scaled = copy.deepcopy(templated)
scaled["templates"][0]["scale"] = 55  # the bandit keeps no key: 100
scaled_golden = bytes.fromhex(Path("tests/fixtures/npc-templates-scaled.hex").read_text().strip())
scaled_bytes = npc.cook(scaled, [[0, 0], [1, 1]], "demo")
assert scaled_bytes == scaled_golden, "N3N4 cooker drifted from the committed golden"
plain = npc.cook(templated, [[0, 0], [1, 1]], "demo")
# N3N4 is N3N3 with u32 scale after each template's tracing range.
assert scaled_bytes[:8] == b"N3N4" + u(4) and len(scaled_bytes) == len(plain) + 8
assert npc.scaled(scaled) and not npc.scaled(templated)
for value in (0, 1001, -1, 1.5, True, "100", None):
    rejects_templated(lambda b, v=value: b["templates"][0].update(scale=v))
for value in (1, 1000):
    edge = copy.deepcopy(scaled)
    edge["templates"][1]["scale"] = value
    assert npc.cook(edge, [[0, 0], [1, 1]], "demo")[:4] == b"N3N4"
print("PASS N3N4 cooker: scale 1-1000 per template (100 without the key), N3N3 byte for byte without any, "
      "cross-language golden")

# Both readers on the synthetic engine 37 package of tests/npc_templates_live.py
# (no KO data): the package loads, and forged template tables fail closed.
from npc_templates_live import prepare as templates_package  # noqa: E402

synthetic = templates_package()
with tempfile.TemporaryDirectory(dir="build") as tmp:
    out = Path(tmp) / "release"
    shutil.copytree(synthetic, out)
    files = {p.name: p.read_bytes() for p in out.iterdir() if p.name not in ("release.bin", "release.sha256")}
    m = json.loads((out / "recipe.json").read_text())["manifest"]
    assert (m["engine_version"], m["protocol_version"]) == (37, 30)

    def repack_synthetic(changed, engine=37, protocol=30):
        index = (b"N3R1" + u(1) + u(engine) + u(protocol) + string(m["game_id"])
                 + string(m["package_version"]) + u(len(changed)))
        for name, data in sorted(changed.items()):
            (out / name).write_bytes(data)
            index += string(name) + u(len(data)) + digest(data)
        (out / "release.bin").write_bytes(index)
        (out / "release.sha256").write_text(digest(index).hex() + "\n")

    def readers(good):
        lines = []
        for cmd in [["build/client/n3e-asset-check", str(out)], ["target/debug/n3e-server", "--check-content"]]:
            p = subprocess.run(cmd, env={**os.environ, "N3E_PACKAGE": str(out)}, capture_output=True, text=True)
            assert (p.returncode == 0) == good, (cmd, p.stdout[-400:], p.stderr[-400:])
            lines += p.stdout.splitlines()
        return lines

    original = files["npc.bin"]
    repack_synthetic(files)
    # PQ-465 (D-232): the server adds the package's melee radii (1 m each) to
    # the synthetic skill policy's start limit; its reach has no margins.
    shown = [line for line in readers(True) if line.startswith("skills reach ")]
    assert shown == ["skills reach start=0 hold=0 plane=3d radii=2"], shown
    # Offsets: magic, model, six timers, three flags, four limits, then the count.
    count_at = 8 + 6 * 4 + 3 * 4 + 4 * 4
    first_template = count_at + 4
    name_length = struct.unpack_from("<I", original, first_template)[0]
    looks_at = first_template + 4 + name_length
    looks_length = struct.unpack_from("<I", original, looks_at)[0]
    numbers_at = looks_at + 4 + looks_length  # health, level, xp, damage, attack, defense, accuracy, evasion, ticks, acquisition
    floats_at = numbers_at + 10 * 4  # speed, attack, search, tracing ranges
    forged = [original[:-1], original + b"\0", b"N3N2" + original[4:], original[:-4] + u(2)]
    for offset, value in [(count_at, 0), (count_at, 257), (numbers_at, 0), (numbers_at, 2000001),
                          (numbers_at + 4, 0), (numbers_at + 4, 256), (numbers_at + 8, 50000001),
                          (numbers_at + 12, 100001), (numbers_at + 16, 10001), (numbers_at + 20, 32768),
                          (numbers_at + 24, 32768), (numbers_at + 28, 32768), (numbers_at + 32, 0),
                          (numbers_at + 36, 2)]:
        data = bytearray(original)
        struct.pack_into("<I", data, offset, value)
        forged.append(bytes(data))
    for offset, value in [(floats_at, -0.5), (floats_at, 12.5), (floats_at + 4, 64.5), (floats_at + 8, 13.0),
                          (floats_at + 12, 65.0)]:
        data = bytearray(original)
        struct.pack_into("<f", data, offset, value)
        forged.append(bytes(data))
    # PQ-251 (D-164): both readers take the reference rows' bounds: health
    # 2,000,000, level 255, speed 0 and 64 m ranges.
    lifted = bytearray(original)
    struct.pack_into("<II", lifted, numbers_at, 2000000, 255)
    struct.pack_into("<ffff", lifted, floats_at, 0.0, 64.0, 64.0, 64.0)
    repack_synthetic(dict(files, **{"npc.bin": bytes(lifted)}))
    readers(True)
    # PQ-252 (D-165): xp, damage, attack, defense, accuracy, evasion at the
    # rows' 0 and at the template maxima.
    for numbers in [(0, 0, 0, 0, 0, 0), (50000000, 100000, 10000, 32767, 32767, 32767)]:
        lifted = bytearray(original)
        struct.pack_into("<6I", lifted, numbers_at + 8, *numbers)
        repack_synthetic(dict(files, **{"npc.bin": bytes(lifted)}))
        readers(True)
    # A name outside the package namespace (same length).
    name = original[first_template + 4:first_template + 4 + name_length]
    forged.append(original.replace(name, b"oops" + name[4:], 1))
    for number, data in enumerate(forged):
        repack_synthetic(dict(files, **{"npc.bin": data}))
        try:
            readers(False)
        except AssertionError as error:
            raise AssertionError(("forged N3N3 npc.bin accepted", number)) from error
    # N3N3 needs engine 37 / wire 30.
    repack_synthetic(files, 36, 29)
    readers(False)
print("PASS N3N3 both readers accept the synthetic engine 37 package and the reference bounds (health 2,000,000, "
      "level 255, speed 0, 64 m ranges; XP, damage, attack, defence, hit rate and evasion from 0 to 50,000,000, "
      "100,000, 10,000 and 32,767) and reject forged template tables and engine 36")

package = Path("build/packages/moradon")
if not (package / "npc.bin").is_file() or (package / "npc.bin").read_bytes()[:4] != b"N3N2":
    print("SKIP N3N2 reader checks: build the local Moradon package (tools/assetc/ko_bake.py 210 --features)")
    sys.exit(0)


def check(out, good=True):
    results = []
    for cmd in [["build/client/n3e-asset-check", str(out)], ["target/debug/n3e-server", "--check-content"]]:
        p = subprocess.run(cmd, env={**os.environ, "N3E_PACKAGE": str(out)}, capture_output=True, text=True)
        assert (p.returncode == 0) == good, (cmd, p.stdout[-400:], p.stderr[-400:])
        if good:
            results.append(p.stdout.splitlines())
    if good:
        # Both readers bind the same release identity.
        assert set(results[0]) & set(results[1]), "readers disagree on the release"


check(package)
# PQ-465 (D-232): Moradon's skill reach and its melee radii, as the server loads them.
reach = subprocess.run(["target/debug/n3e-server", "--check-content"], env={**os.environ, "N3E_PACKAGE": str(package)},
                       capture_output=True, text=True, check=True).stdout.splitlines()
assert [line for line in reach if line.startswith("skills reach ")] == [
    "skills reach start=2 hold=15 plane=xz radii=2"], reach
with tempfile.TemporaryDirectory(dir="build") as tmp:
    out = Path(tmp) / "release"
    shutil.copytree(package, out)
    files = {p.name: p.read_bytes() for p in out.iterdir() if p.name not in ("release.bin", "release.sha256")}
    m = json.loads((out / "recipe.json").read_text())["manifest"]

    def repack(changed, engine=36, protocol=29):
        # Forged but correctly rehashed release: only the named files differ.
        index = (b"N3R1" + u(1) + u(engine) + u(protocol) + string(m["game_id"])
                 + string(m["package_version"]) + u(len(changed)))
        for name, data in sorted(changed.items()):
            (out / name).write_bytes(data)
            index += string(name) + u(len(data)) + digest(data)
        (out / "release.bin").write_bytes(index)
        (out / "release.sha256").write_text(digest(index).hex() + "\n")

    original = files["npc.bin"]
    repack(files)
    check(out)
    slots = struct.unpack_from("<I", original, 8 + 6 * 4 + 8 * 4)[0]
    assert slots == len(m["gameplay"]["spawns"]) == 10
    tail = 8 + 6 * 4 + 8 * 4 + 4
    forged = [original[:-1], original + b"\0", b"N3N1" + original[4:]]
    for offset, value in [(8 + 6 * 4, 2), (8 + 6 * 4 + 4, 2), (8 + 6 * 4 + 16, 99), (8 + 6 * 4 + 20, 12001),
                          (8 + 6 * 4 + 24, 0), (8 + 6 * 4 + 28, 501), (tail, 1), (tail + 16, 0),
                          (tail + 16, 12001), (8 + 6 * 4 + 32, 9)]:
        data = bytearray(original)
        struct.pack_into("<I", data, offset, value)
        forged.append(bytes(data))
    # A slot respawn shorter than corpse removal is rejected against the life policy.
    data = bytearray(original)
    struct.pack_into("<I", data, tail + 16, 1)
    forged.append(bytes(data))
    for number, data in enumerate(forged):
        repack(dict(files, **{"npc.bin": data}))
        try:
            check(out, False)
        except AssertionError as error:
            raise AssertionError(("forged npc.bin accepted", number)) from error
    repack(files, 35, 28)
    check(out, False)
print("PASS N3N2 both readers accept the Moradon reference package and reject forged layouts, bounds, slot counts and engine 35")
