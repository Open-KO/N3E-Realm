"""Assemble the real male Tuarek player from the local default-looks table."""
import csv
import io
import json
import pathlib
import shutil
import ko_character as ko
import main


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


# The UPC_DefaultLooks key of the player model, its KO race (the male Tuarek;
# ko_armour_2145 names the race's 2145 armour by it, PQ-319).
RACE = 2


def cook(root, out, locomotion=False, ready=False, rest=False, combat=False):
    assets=ko.Assets(root)
    source='Data/UPC_DefaultLooks.tbl.csv'
    rows=list(csv.reader(io.StringIO(assets.get(source).decode('utf-8-sig'))))
    row=next(row for row in rows[1:] if row[0]==str(RACE))
    if 'upc_ka_tu' not in row[2].lower(): raise ValueError('male Tuarek table identity')
    parts=row[4:10]
    parts[2]=parts[2].replace('_face.n3cpart','_face00.n3cpart')
    parts[5]=parts[5].replace('_hair.n3cpart','_hair00.n3cpart')
    definition=dict(name='Male Tuarek',joint=row[2],animation=row[3],parts=parts,
                    collision=[],split=[-1]*4,extras=[])
    reports={}
    for state,index in clip_indices(locomotion,ready,rest,combat):
        target=out/state
        report=ko.convert(root,source,target,index,1.0,definition=definition)
        cooked=out/('cooked-'+state)
        main.cook(target,cooked)
        shutil.copyfile(cooked/'scene.bin',out/('player-'+state+'.bin'))
        reports[state]=report
    (out/'player-provenance.json').write_text(json.dumps(dict(race=RACE,race_name='male Tuarek',face=0,hair=0,states=reports),indent=2)+'\n')
    return reports
