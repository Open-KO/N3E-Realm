"""KO NPC models from the operator's NPC_Looks table (PQ-254, D-167).

Converts each looks key a zone's N3N3 templates use (`<game>:looks/<sPid>`,
tools/assetc/ko_npc.py) into one entry of the per-template presentation of
PQ-253 (tools/assetc/npc_looks.py): four N3S1 clips (idle, walk, attack,
death) built from the row's character files by tools/assetc/ko_character.py,
and the row's name flag. Reads the player's own client data
(`Data/NPC_Looks.tbl.csv` and the files it names); writes only under build/.
Nothing it reads or writes is committed.

How the client uses a looks row (client `KnightOnLine.exe`, headless audit
project; record: docs/implementation/evidence/pq-254-ko-npc-looks-import.md):

* `006113b0` loads `Data\\NPC_Looks.tbl` through `00616b80`, which reads the
  rows only when the row size under `006364e0`'s offset rule is 0x150 (binary,
  PQ-170). Under that rule the installer's 38 columns (one u32, sixteen
  strings of 16 bytes, eighteen i32, three bytes) put column 3 at `+0x14`,
  column 4 at `+0x24`, columns 5-10 at `+0x34`..`+0x84`, column 16 at `+0xe4`,
  column 17 at `+0xf4`, column 35 at `+0x148` and column 36 at `+0x14c`
  (binary rule + local-asset column types). The CSV this module reads is the
  operator's decoded copy of the same table; its header must carry those 38
  column types.
* `0045dda0` (NPC slot `+0x20`, from NPC-in `005cd620` at `005cdd7f`): when
  the column 16 string is empty (`+0xec`, its length: inference from the MSVC
  string layout) it sets the skeleton from column 3 (`0041b260`) and the clip
  table from column 4 (`0041bd30`), and passes column 17 to `0041cb80`
  when that is not empty (an effect plug load: inference, not read); otherwise it calls the character object's (`+0x50`)
  slot `+8` with column 16 and slot `+0x24` with the actor's position. The
  column 16 values are `.n3chr` character files (local-asset), so that slot
  is the character load (inference; the source name is LoadFromFile).
  Column 35 = 0 clears actor `+0x45b` on both paths; the turn `00457910`
  does nothing while it is 0 (binary; `004579d0` also reads it, not traced):
  such an NPC never turns.
* NPC-in then calls the actor's slot `+0x2c` (`0045cd90`) six times with
  position i and row `+0x34 + 16 i`, so columns 5-10 (`005cdfd5`-`005ce035`,
  binary). A non-empty name goes to `0041b6d0` (positions 0 and 1 also test
  actor `+0x278`, an item branch not traced for NPCs), which replaces part i of the
  character object only when i is below its part count and the name differs,
  by the part's slot `+8` (binary; the slot being the part's load is
  inference). An empty name at positions 2 and 5 calls NPC slots `+0x28` and
  `+0x24`, which are a bare `RET` (`004465e0`); at 0, 1, 3, 4 it looks the
  actor's race (100 for NPCs, `005cdb58`) up in the table at `[00818758]` and
  sets nothing when no row matches (binary; that table being UPC_DefaultLooks,
  whose ids are 1-4 and 11-13, is inference + local-asset). So an empty
  column leaves that part as it was. On the row path the part vector has ten
  slots: the actor constructor `004554e0` calls `0041b4d0(10)` on the character
  object (`004555b8`), which creates one part per slot (binary). Neither `0045dda0` nor that loop reads
  columns 11-15 (binary for those two functions).
* Clips (binary): the stand clip `0045bfe0` returns 0 for an NPC (race 100 or
  `+0x4a8` set) nine times in ten and 12 + rand() % 4 otherwise; the move
  `0045a950` plays 1 (walk), 2 (run) or 3 (backward) from its jump table
  `0045aca4`; the NPC tick `004647a0` picks run when its speed `+0x33c` is
  at least 2 x 1.5 (`006a4124`) x `+0x168` x `+0x90` and walk below it
  (`00464c33`-`00464c88`); the attack clip `0045bf70` is 4 + rand() % 2; the
  death handler `005cf620` calls `0045acc0` with mode 2 (`005cf906`), which
  plays 10 for an NPC (`0045ad3d`-`0045ad5e`).

n3e takes clip 0 (idle), 2 (walk: its NPCs move only while chasing at the
template's run speed bySpeed2 or returning at twice it; KO's walk below the
size threshold is not carried), 4 (attack) and 10 (death); the worm's
0, 2, 4, 10 are these. Not carried (reported per row): column 17 effects,
an .n3chr's own effect and collision names, the stand clip's talk variants,
attack clip 5, column 35's fixed facing; a state whose clip the table lacks
is reported with the clip it takes.

A clip that starts and ends on one frame (the shop and smith attack clips)
converts as that frame's pose held (ko_character.convert, PQ-273, D-169).
A clip index at or past the table's count (PQ-268, D-178, `clip_plan`): KO's
clip starts leave the clip already playing, so on a table without clips
every state is the joints at frame 0 held (the guard stones, crystals and
bind point that name chr\\default.n3anim) and on a table whose only carried
clip is 0 (one or two clips) the missing states take clip 0; a table that
has the walk clip but lacks another is refused.
Each row converts or fails closed with a named reason (a missing or unreadable
file, an unsupported format, a clip the table lacks); `cook` refuses a zone
with any failed key, so no template is left without its model.
"""
import csv
import io
import shutil

import ko_character
import main
import npc_looks

SOURCE = "Data/NPC_Looks.tbl.csv"
# Column types of the installer's NPC_Looks.tbl (PQ-170: the 0x150-byte row).
TYPES = ["UInt32"] + ["String"] * 16 + ["Int32"] * 18 + ["Byte"] * 3
JOINT, ANIMATION, PART0, CHARACTER, EFFECTS, FACING, NAME = 2, 3, 4, 15, 16, 34, 35
PARTS = 6  # NPC-in sets positions 0-5 from columns 5-10 (005cdfd5)
CLIPS = (("idle", 0), ("walk", 2), ("attack", 4), ("death", 10))
MAX_ID = 32767  # NPC-in sign-extends the record's resource ID (MOVSX at 005cd68f), so a larger ID never matches a row


def table(data):
    """{resource id: row} from the decoded CSV; refuses another layout."""
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    if not rows or [h.split(" - ", 1)[-1].strip() for h in rows[0]] != TYPES:
        raise ValueError("NPC_Looks header is not the 38-column layout")
    out = {}
    for row in rows[1:]:
        if not row:
            continue
        if len(row) != len(TYPES) or not row[0].isdigit() or not 0 <= int(row[0]) <= MAX_ID:
            raise ValueError("NPC_Looks row %r malformed" % row[:1])
        if int(row[0]) in out:
            raise ValueError("NPC_Looks resource id %s repeated" % row[0])
        if row[NAME] not in ("0", "1") or not row[FACING].lstrip("-").isdigit():
            raise ValueError("NPC_Looks resource id %s flag columns" % row[0])
        out[int(row[0])] = row
    return out


def definition(row, assets):
    """(ko_character definition, omitted features) for one looks row, built as
    0045dda0 and NPC-in build the actor."""
    omitted = []
    if row[CHARACTER]:
        chr_name = row[CHARACTER]
        ch = ko_character.character(assets.get(chr_name), strict=False)
        parts = list(ch["parts"])
        for i in range(PARTS):
            if row[PART0 + i] and i < len(parts):
                parts[i] = row[PART0 + i]
        if any(ch["collision"]):
            omitted.append("character collision %s" % ",".join(n for n in ch["collision"] if n))
        if any(ch["extras"]):
            omitted.append("character extras %s" % ",".join(n for n in ch["extras"] if n))
        joint, animation, name = ch["joint"], ch["animation"], ch["name"]
    else:
        parts = [row[PART0 + i] for i in range(PARTS) if row[PART0 + i]]
        joint, animation, name = row[JOINT], row[ANIMATION], row[1]
        if row[EFFECTS]:
            omitted.append("effects %s" % row[EFFECTS])
    if not parts:
        raise ValueError("no parts")
    if int(row[FACING]) == 0:
        omitted.append("fixed facing (column 35 = 0)")
    return dict(name=name, joint=joint, animation=animation, parts=parts,
                collision=[], split=[-1] * 4, extras=[]), omitted


def clip_plan(count):
    """(state, clip index) for CLIPS on a clip table of `count` clips, and the
    note for the report (PQ-268, D-178; record:
    docs/implementation/evidence/pq-268-ko-npc-looks-without-clips.md).

    KO's clip starts 0041be40, 0041c160 and 0041c000 start nothing for an
    index at or past the table's count and leave the clip already playing as
    it is (binary). A table without clips never starts one, so the NPC shows
    its joints at frame 0 in every state: index None, the rest pose
    (ko_character.REST_CLIP). A table whose only carried clip is the stand
    clip 0 (one or two clips) keeps clip 0 playing in every state n3e
    carries, so a missing index takes clip 0. A table that also has a carried
    clip past 0 but lacks another (3 to 10 clips) is refused: the clip KO
    keeps there depends on the state before (none in the operator's table,
    local-asset)."""
    missing = [(state, index) for state, index in CLIPS if index >= count]
    if not missing:
        return list(CLIPS), None
    if count == 0:
        return [(state, None) for state, _ in CLIPS], "no clips: every state the joints at frame 0"
    if any(0 < index < count for _, index in CLIPS):
        state, index = missing[0]
        raise ValueError("%s clip %d past the table's %d clips, which has the walk clip: the clip KO keeps "
                         "playing depends on the state before" % (state, index, count))
    return ([(state, 0 if index >= count else index) for state, index in CLIPS],
            "%s past the table's %d clips: the idle clip 0" % (
                ", ".join("%s clip %d" % m for m in missing), count))


def resource(key, game):
    prefix = game + ":looks/"
    tail = key[len(prefix):] if key.startswith(prefix) else ""
    if not tail.isdigit() or str(int(tail)) != tail or int(tail) > MAX_ID:
        raise ValueError("looks key %s is not %s<resource id>" % (key, prefix))
    return int(tail)


def convert_row(assets_root, rows, pid, work, meters=1.0):
    """Converts one looks row into four N3S1 clips under `work`; returns
    (clip metadata list, files, report). Raises ValueError with the reason."""
    if pid not in rows:
        raise ValueError("no NPC_Looks row")
    row = rows[pid]
    assets = ko_character.Assets(assets_root)
    assets.last = SOURCE
    try:
        spec, omitted = definition(row, assets)
        count = len(ko_character.animations(assets.get(spec["animation"]), empty=True))
    except (ValueError, OSError, UnicodeError) as error:
        raise ValueError("%s: %s" % (assets.last, error)) from None
    try:
        plan, note = clip_plan(count)
    except ValueError as error:
        raise ValueError("%s: %s" % (spec["animation"], error)) from None
    if note:
        omitted.append(note)
    clips, files, sources = [], [], {}
    for (state, wanted), (_, index) in zip(CLIPS, plan):
        target = work / state
        if target.exists():
            shutil.rmtree(target)
        try:
            report = ko_character.convert(assets_root, SOURCE, target, index, meters, definition=spec,
                                          player=False, assets=assets)
        except (ValueError, OSError, UnicodeError) as error:
            raise ValueError("%s clip %d, %s: %s" % (state, wanted, assets.last, error)) from None
        main.cook(target, target / "cooked", materials=True)
        clip = ko_character.animation_metadata(report)
        if state in ("attack", "death"):
            clip["loop_blend"] = False
        clips.append(clip)
        files.append(target / "cooked" / "scene.bin")
        sources.update(report["sources"])
    return clips, files, dict(definition=spec, omitted=omitted, sources=sources,
                              vertices=report["render_vertices"], joints=report["joint_count"],
                              clips=dict(plan))


def convert(assets_root, keys, root, game, work, meters=1.0):
    """Converts every looks key. Returns (entries, failures, report): entries
    are npc_looks policy entries (clip sources under `root`), ordered by
    resource ID so entry 0 is the lowest (KO's fallback node, PQ-253);
    failures map a key to its reason."""
    assets = ko_character.Assets(assets_root)
    rows = table(assets.get(SOURCE))
    entries, failures, report = [], {}, {}
    for key in sorted(set(keys), key=lambda k: resource(k, game)):
        pid = resource(key, game)
        try:
            clips, files, record = convert_row(assets_root, rows, pid, work / str(pid), meters)
        except ValueError as error:
            failures[key] = str(error)
            continue
        out = []
        for (state, _), clip, path in zip(CLIPS, clips, files):
            source = "npc-looks-src/%d-%s.bin" % (pid, state)
            (root / source).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, root / source)
            out.append(dict(source=source, **clip))
        entries.append(dict(key=key, name_always=rows[pid][NAME] == "1", clips=out))
        report[key] = record
    return entries, failures, report


def cook(assets_root, templates, root, game, work, meters=1.0):
    """The npc_looks policy for a package's templates; refuses when any looks
    key fails, naming every failed key and its reason."""
    entries, failures, report = convert(assets_root, [t["looks"] for t in templates], root, game, work, meters)
    if failures:
        raise ValueError("NPC looks not converted: " + "; ".join("%s: %s" % kv for kv in sorted(failures.items())))
    return entries, report


def main_cli(argv):
    """Converts a zone's looks keys and prints one line per key (no KO data is
    written outside build/)."""
    import argparse
    import json
    import pathlib
    import sys

    import ko_npc
    import ko_tables
    parser = argparse.ArgumentParser(description=main_cli.__doc__)
    parser.add_argument("zone", type=int)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path("assets/ko"))
    parser.add_argument("--export", default=str(ko_tables.EXPORT))
    parser.add_argument("--game", default="ko")
    parser.add_argument("--out", type=pathlib.Path, default=None)
    args = parser.parse_args(argv)
    out = args.out or pathlib.Path("build/ko-npc-looks/zone-%d" % args.zone)
    tables = {name: ko_tables.load(name, args.export) for name in ko_tables.TABLES}
    if any(t is None for t in tables.values()):
        print("REFUSED the K_MONSTER, K_NPC and K_NPCPOS exports are missing under %s" % args.export, file=sys.stderr)
        return 2
    templates, _ = ko_npc.zone_templates(tables, args.zone, args.game)
    entries, failures, report = convert(args.root, [t["looks"] for t in templates], out / "root", args.game,
                                        out / "work")
    for entry in entries:
        record = report[entry["key"]]
        print("OK %s vertices %d joints %d%s" % (entry["key"], record["vertices"], record["joints"],
                                                 "; omitted " + "; ".join(record["omitted"]) if record["omitted"] else ""))
    for key, reason in sorted(failures.items(), key=lambda kv: resource(kv[0], args.game)):
        print("FAILED %s: %s" % (key, reason))
    print("zone %d: %d of %d looks converted" % (args.zone, len(entries), len(entries) + len(failures)))
    (out / "report.json").write_text(json.dumps(dict(entries=entries, failures=failures, report=report),
                                                indent=1, sort_keys=True, default=str))
    return 0 if not failures else 1


if __name__ == "__main__":
    import sys
    sys.exit(main_cli(sys.argv[1:]))
