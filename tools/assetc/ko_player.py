"""Assemble a KO player model from the local default-looks table (RQ-003).

The package names its races in `games/<game>/character-create.json`: each
race's KO code and `looks`, the stem of its `UPC_DefaultLooks` parts (checked
against the row, so a wrong table is refused by name), and `player`, the race
whose model the package's player scenes (`player-<state>.bin`) are until each
race draws its own (RQ-007). No race is named here.

KO reads the looks row whose key is the race code, and sets each of its six
parts in part-position order (upper, lower, face, hands, feet, hair); the face
and hair files are the row's name with the face or hair number as two digits
before the extension, and an empty name sets no part (source
`GameProcCharacterCreate.cpp` `SetChr`, `PlayerMySelf.cpp` `InitFace` and
`InitHair`; the 1298 build `005fd120` returns without a row, binary,
content/character-create.md).
"""
import csv
import io
import json
import ntpath
import pathlib
import shutil
import ko_character as ko
import main

GAME = pathlib.Path('games/moradon')
SOURCE = 'Data/UPC_DefaultLooks.tbl.csv'
# UPC_DefaultLooks columns: the key, the name, the joint, the animation and the
# six part files in KO's part-position order (__TABLE_PLAYER_LOOKS).
KEY, JOINT, ANIMATION, PARTS = 0, 2, 3, slice(4, 10)
POSITIONS = ('upper', 'lower', 'face', 'hands', 'feet', 'hair')
FACE, HAIR = POSITIONS.index('face'), POSITIONS.index('hair')


def clip_indices(locomotion=False, ready=False, rest=False, combat=False):
    """(state, KO clip index) of each player clip the cook converts, in order;
    a combat clip's state is combat-<index> (PQ-317 maps them to a skeletal
    plug's clips)."""
    states = [('idle',0),('walk',1 if locomotion else 2),('attack',87),('death',8)]
    if locomotion:
        states += [('run',2),('backward',3)]
    if ready:
        states += [("ready",86)]
    if rest:states += [("sit-down",11),("sit-idle",12),("stand-up",13)]
    if combat:
        config=json.loads(pathlib.Path('games/moradon/combat-animation.json').read_text())
        indexes=sorted({i for p in config['profiles'] for i in [p['ready'],p['moving'],*p['attacks']]})
        states += [(f'combat-{i}',i)for i in indexes]
    return states


def rules(game=GAME):
    """The package's races (character-create.json, checked by ko_create)."""
    import ko_create
    r = ko_create.rules(pathlib.Path(game))
    if r is None:
        raise ValueError('%s has no %s to name its player races' % (game, ko_create.SOURCE))
    return r


def race(code=None, game=GAME):
    """The race entry {race, nation, specialties, looks} of `code`, or of the
    package's player race when `code` is None."""
    r = rules(game)
    code = r['player'] if code is None else code
    entry = next((x for x in r['races'] if x['race'] == code), None)
    if entry is None:
        raise ValueError('%s lists no race %r' % (pathlib.Path(game) / 'character-create.json', code))
    return entry


def numbered(path, number):
    """KO's face or hair file: the name with `number` as two digits before the
    extension (InitFace / InitHair's "{}{}{:02}{}" of the directory, name, number
    and extension; source PlayerMySelf.cpp)."""
    stem, ext = ntpath.splitext(path)
    return '%s%02d%s' % (stem, number, ext)


def looks(assets, entry, face=0, hair=0):
    """The race's UPC_DefaultLooks row as {row, definition, positions}: the
    definition `ko_character.convert` takes (its joint, animation and the parts
    KO sets, face `face` and hair `hair`) and the part position of each part
    it keeps. Refuses a race the table lacks and a row whose parts are not the
    race's `looks`."""
    table = assets.get(SOURCE)
    rows = list(csv.reader(io.StringIO(table.decode('utf-8-sig'))))
    row = next((r for r in rows[1:] if r and r[KEY] == str(entry['race'])), None)
    if row is None:
        raise ValueError('%s has no row for race %d' % (SOURCE, entry['race']))
    if len(row) < PARTS.stop:
        raise ValueError('%s row %d: no part columns' % (SOURCE, entry['race']))
    names = row[PARTS]
    stem = ntpath.basename(names[FACE]).lower()
    if stem != entry['looks'] + '_face.n3cpart':
        raise ValueError('%s row %d: face part %r is not looks %r' % (SOURCE, entry['race'], names[FACE], entry['looks']))
    parts, positions = [], []
    for position, name in zip(POSITIONS, names):
        if not name:
            continue  # KO sets no part for an empty name
        if position == 'face':
            name = numbered(name, face)
        elif position == 'hair':
            name = numbered(name, hair)
        parts.append(name)
        positions.append(position)
    definition = dict(name=entry['looks'], joint=row[JOINT], animation=row[ANIMATION], parts=parts,
                      collision=[], split=[-1]*4, extras=[])
    return dict(row=row, definition=definition, positions=positions)


def cook(root, out, locomotion=False, ready=False, rest=False, combat=False, race_code=None, game=GAME):
    """The player scenes of race `race_code` (default the package's player
    race), face 0 and hair 0, one per clip_indices state: out/player-<state>.bin."""
    entry = race(race_code, game)
    assets=ko.Assets(root)
    definition = looks(assets, entry)['definition']
    reports={}
    for state,index in clip_indices(locomotion,ready,rest,combat):
        target=out/state
        report=ko.convert(root,SOURCE,target,index,1.0,definition=definition)
        cooked=out/('cooked-'+state)
        main.cook(target,cooked)
        shutil.copyfile(cooked/'scene.bin',out/('player-'+state+'.bin'))
        reports[state]=report
    (out/'player-provenance.json').write_text(json.dumps(dict(race=entry['race'],looks=entry['looks'],face=0,hair=0,states=reports),indent=2)+'\n')
    return reports
