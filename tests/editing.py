"""P4 content validation and independent C++/Rust admin golden."""
import os,json,shutil,subprocess,tempfile,sys
from pathlib import Path
from world_peer import integer,blob,real
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import main
B=Path('build/p4');B.mkdir(exist_ok=True,parents=True)
expected=blob(28,integer(1,63)+blob(2,'request-1')+blob(3,'publish')+integer(4,127)+blob(5,'a'*64)+blob(6,blob(1,'fixture:lighting.intensity')+real(2,.5))+blob(7,'golden'))
assert expected==bytes.fromhex(Path('protocol/golden-admin.hex').read_text())
for binary,lang in [('build/client/n3e-peer','cpp'),('target/debug/n3e-server','rust')]:
    subprocess.run([binary,'--golden',str(B/lang)],check=True)
    assert (B/f'{lang}-admin.bin').read_bytes()==expected
with tempfile.TemporaryDirectory(dir=B) as td:
    source=Path(td)/'source';shutil.copytree('games/demo',source);original=json.loads((source/'package.json').read_text())
    for bad in ['event','collision','visual','nan','duplicate','boolean']:
        m=json.loads(json.dumps(original));d=m['editing']['decorations'][0]
        if bad in ['event','collision']:d[bad]=1
        if bad=='visual':d['visual']='../../outside.bin'
        if bad=='nan':d['position'][0]=float('nan')
        if bad=='boolean':m['editing']['lighting']=True
        if bad=='duplicate':m['editing']['decorations'].append(dict(d))
        (source/'package.json').write_text(json.dumps(m))
        try:main.cook(source,Path(td)/'out')
        except ValueError:pass
        else:raise AssertionError('bad edit data accepted: '+bad)
# PQ-250: a zone's whole population edits a chosen subset of its spawn points.
# By path: this check shares the cooker module's name.
import importlib.util
spec=importlib.util.spec_from_file_location('assetc_editing',Path('tools/assetc/editing.py').resolve())
editing=importlib.util.module_from_spec(spec);spec.loader.exec_module(editing)
m=json.loads(json.dumps(original));m['gameplay']['spawns']=[[0,0]]*2048
try:editing.descriptors(m)
except ValueError as e:assert str(e)=='editing property bound',e
else:raise AssertionError('2,048 editable spawns accepted')
for chosen in [[5,0],[0,0],[2048],[-1],['0'],{}]:
    m['editing']['spawns']=chosen
    try:editing.descriptors(m)
    except ValueError as e:assert str(e)=='editing spawns',(chosen,e)
    else:raise AssertionError(('bad editable spawns accepted',chosen))
m['editing']['spawns']=[0,5,2047]
assert [(k.split(':',1)[1],kind,t) for k,kind,t,*_ in editing.descriptors(m) if kind in (7,8)]==[
    ('spawn.0.x',7,0),('spawn.0.z',8,0),('spawn.5.x',7,5),('spawn.5.z',8,5),('spawn.2047.x',7,2047),('spawn.2047.z',8,2047)]
m['editing']['spawns']=[]
assert not [d for d in editing.descriptors(m) if d[1] in (7,8)]
# Without the field every spawn point is editable, as before.
assert sum(d[1]==7 for d in editing.descriptors(original))==len(original['gameplay'].get('spawns',[0]))
normal=subprocess.check_output(['nm','-C','build/client/n3e-client'],text=True)
assert 'n3e::Editor::' not in normal and 'ImGui::' not in normal
print('PASS editing content exclusions, invalid assets, duplicate IDs, finite bounds, editable spawn subset, admin golden, normal UI linkage exclusion')
