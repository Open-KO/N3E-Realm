"""Package boundary regression: reject bad rules and bind valid changes to identity."""

import copy
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools/assetc"))
import rules

r = json.loads(pathlib.Path("tests/fixtures/legacy-demo/package.json").read_text())["gameplay"]
base = rules.cook(r, "demo")
for key, value in [
    ("health", True),
    ("cost", r["resource"] + 1),
    ("range", float("nan")),
    ("speed", 3.1),
    ("slots", 65),
    ("item", "other:item/token"),
    ("starting_items", r["slots"] + 1),
    ("aggro_range", r["leash_range"] + 1),
    ("leash_range",64.01),
    ("cooldown_ticks", 0),
]:
    changed = copy.deepcopy(r)
    changed[key] = value
    try:
        rules.cook(changed, "demo")
    except ValueError:
        pass
    else:
        raise AssertionError(key)
changed = copy.deepcopy(r)
changed["damage"] += 1
assert rules.cook(changed, "demo") != base
changed["script"] = "arbitrary"
try:
    rules.cook(changed, "demo")
except ValueError:
    pass
else:
    raise AssertionError("unknown rule accepted")
print("PASS strict gameplay vocabulary, namespace, bounds and changed binary identity")
for key, value in [("spawns", []), ("spawns", [[0, 0]]*2049),
                   ("spawns", [[float("nan"), 0]]), ("spawns", [[0]]),
                   ("interest_cell", 0), ("interest_cell", 65), ("interest_cell", True)]:
    changed = dict(r, **{key: value})
    try:
        rules.cook(changed, "demo")
    except ValueError:
        pass
    else:
        raise AssertionError((key, value))
extended = rules.cook(dict(r, spawns=[[0, 0], [2, 3]], interest_cell=24), "demo")
# PQ-250: a zone's whole population, up to the 2,048 bound shared with both readers.
full = rules.cook(dict(r, spawns=[[i % 64, i // 64] for i in range(2048)], interest_cell=24), "demo")
assert full[:4] == b"N3G2" and len(full) == len(extended) + 2046 * 8
assert base[:4] == b"N3G1" and extended[:4] == b"N3G2" and base[4:] == extended[4:len(base)]
print("PASS bounded multi-spawn extension; legacy binary unchanged")
