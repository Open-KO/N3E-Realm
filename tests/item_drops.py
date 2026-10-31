"""N3P5 original fixtures, independently rehashed hostile policies and both readers."""
import copy,json,os,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
from item_drops_live import prepare
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import progression
from common import u,string,digest

def check(out,good=True):
    outputs=[]
    for command in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        r=subprocess.run(command,env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
        assert (r.returncode==0)==good,(command,r.stdout,r.stderr)
        outputs.append(r.stdout)
    if good:assert outputs[0].splitlines()[0]==outputs[1].splitlines()[0]
package=prepare();check(package);check(prepare(alternate=True));check(prepare(full=True))
m=json.loads((package/'recipe.json').read_text())['manifest'];policy=m['progression']
mutations=[lambda p:p['items'].update(group_bound=0),lambda p:p['items'].update(group_bound=32768),
 lambda p:p['items'].update(event_percent=256),lambda p:p['items'].update(event_unit=float('nan')),
 lambda p:p['items'].update(premium_rate=1.01),lambda p:p['items'].update(rows=[]),
 lambda p:p['items']['items'][0].update(quantity=10000),lambda p:p['items']['items'][0].update(durability=65536),
 lambda p:p['items']['items'][0].update(id='other:item/fake'),lambda p:p['items']['items'].append(p['items']['items'][0]),
 lambda p:p['items']['rows'][0].update(chance=10001),lambda p:p['items']['rows'][0].update(level_penalty=10001),
 lambda p:p['items']['rows'][1].update(slots=[0]),lambda p:p['items']['rows'][1].update(slots=[1,2]),
 lambda p:p['items']['rows'][0].update(slots=[3]),lambda p:p['items']['rows'][0].update(slots=[1]*31)]
for mutate in mutations:
    p=copy.deepcopy(policy);mutate(p)
    try:progression.cook(p,m['gameplay'],m['game_id'])
    except ValueError:pass
    else:raise AssertionError('hostile item recipe accepted')
with tempfile.TemporaryDirectory(dir='build') as tmp:
    out=Path(tmp)/'release';shutil.copytree(package,out)
    files={p.name:p.read_bytes() for p in out.iterdir() if p.name not in ('release.bin','release.sha256')}
    def repack(changed,engine=28,wire=21):
        index=b'N3R1'+u(1)+u(engine)+u(wire)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):
            (out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['progression.bin'];prefix=len((package.parent/'old/package/progression.bin').read_bytes())
    malformed=[original[:-1],original+b'\0',b'N3P4'+original[4:]]
    for offset,value in [(prefix+12,0),(prefix+12,32768),(prefix+16,256),(prefix+20,0x7fc00000),(prefix+24,0x40000000),(prefix+28,65)]:
        b=bytearray(original);struct.pack_into('<I',b,offset,value);malformed.append(bytes(b))
    # Last row is a group of zero entries; a rehashed out-of-range item reference fails.
    malformed.append(original[:-4]+u(3))
    for data in malformed:
        changed=dict(files);changed['progression.bin']=data;repack(changed);check(out,False)
    for name in ['inventory.bin','party.bin','progression.bin']:
        changed=dict(files);del changed[name];repack(changed);check(out,False)
    for engine,wire in [(27,20),(28,20),(29,22)]:repack(files,engine,wire);check(out,False)
print('PASS N3P5 base/alternate/full readers, malformed rehashed records, bounds, missing capabilities and version isolation')
