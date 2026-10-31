"""Original-only UIF/alpha and hashed presentation boundary regressions."""
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools/assetc'))
from common import u,f,string
import ko_hud
import main


def reject(fn, data):
    try:fn(data)
    except (ValueError,struct.error):return
    raise AssertionError('invalid presentation accepted')

# Original UIF tree: one image, no copied UI/assets required.
def base(children=b'',count=0,ident='test'):
    return string('')+struct.pack('<hh',count,1)+children+string(ident)+struct.pack('<8i2I',0,0,32,16,0,0,32,16,0,0)+string('')*3
image=base()+string('sample.dxt')+f([0,0,1,1,0])
tree=base(u(4)+image,1)
assert ko_hud.parse(tree)['children'][0]['texture']=='sample.dxt'
list_tree=base(u(14)+base()+string('OriginalFont')+u(12)+u(0xffffffff)+u(0)+u(0),1)
assert ko_hud.parse(list_tree)['children'][0]['list_font']==[12,0xffffffff,0,0]
reject(ko_hud.parse,list_tree[:-1])
for data in [tree[:-1],tree+b'\0',string('')+struct.pack('<hh',2000,1)]:reject(ko_hud.parse,data)
# Four-bit straight alpha; channels must neither become opaque nor premultiplied.
ntf=string('')+b'NTF\x03'+struct.pack('<4i',4,4,26,0)+struct.pack('<16H',*([0x8f24]*16))
w,h,rgba=ko_hud.texture(ntf)
assert (w,h)==(4,4) and rgba[:4]==bytes([255,34,68,136])
for data in [ntf[:-1],ntf+b'\0']:reject(ko_hud.texture,data)
print('PASS original UIF tree bounds, truncation/trailing rejection and ARGB4444 straight alpha')

with tempfile.TemporaryDirectory(dir='build') as tmp:
    root=pathlib.Path(tmp)/'source';shutil.copytree('tests/fixtures/legacy-demo',root)
    for state in ['idle','walk','attack','death']:
        shutil.copyfile('build/packages/legacy-demo/scene.bin',root/f'player-{state}.bin')
    # A synthetic transparent glyph atlas and one image record.
    prefix=b'N3H1'+u(0)+f([30,20])+u(1)+u(256)+u(128)+bytes(256*128*4)
    record=u(0)+f([0,0])+f([0,0,16,16])+u(0)+f([0,0,1,1])+string('')+string('')+u(0xffffffff)+u(0)+u(0)
    valid=prefix+u(1)+record
    (root/'hud.bin').write_bytes(valid)
    manifest=json.loads((root/'package.json').read_text())
    # Keep the imported HUD's 30 HP metadata but use a 150 HP gameplay mob.
    manifest['gameplay']['npc_health']=150
    manifest['presentation']={name:name for name in ['hud.bin','player-idle.bin','player-walk.bin','player-attack.bin','player-death.bin']}
    (root/'package.json').write_text(json.dumps(manifest))
    out=pathlib.Path(tmp)/'release'
    digest=main.cook(root,out)
    def check(good=True):
        result=subprocess.run(['build/client/n3e-asset-check',str(out)],capture_output=True,text=True)
        assert (result.returncode==0)==good,(result.stdout,result.stderr)
    check()
    result=subprocess.run(['target/debug/n3e-server','--check-content'],env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True)
    assert result.returncode==0,result.stderr
    # Optional ready clip is hashed, structurally loaded, and requires melee.
    import copy
    legacy = copy.deepcopy(manifest)
    shutil.copyfile('build/packages/legacy-demo/scene.bin',root/'player-ready.bin')
    manifest['presentation']['player-ready.bin']='player-ready.bin'
    (root/'package.json').write_text(json.dumps(manifest))
    try: main.cook(root,out)
    except ValueError: pass
    else: raise AssertionError('ready clip accepted without melee policy')
    manifest.update(engine_version=4,melee=dict(actor_radius=1,target_radius=1,reach=0,facing_dot=.7))
    (root/'package.json').write_text(json.dumps(manifest))
    main.cook(root,out);check()
    result=subprocess.run(['target/debug/n3e-server','--check-content'],env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True)
    assert result.returncode==0,result.stderr
    (out/'player-ready.bin').write_bytes(b'tampered');check(False)
    manifest=legacy
    (root/'package.json').write_text(json.dumps(manifest))
    main.cook(root,out)
    (out/'player-walk.bin').write_bytes(b'tampered')
    check(False)
    for invalid in [valid[:-1],valid+b'\0',prefix+u(2049),prefix+u(1)+u(8)+record[4:]]:
        (root/'hud.bin').write_bytes(invalid);main.cook(root,out);check(False)
    # N3H2 has a bounded acyclic control table and per-record state masks.
    h2prefix = b'N3H2' + prefix[4:]
    control = u(0)+u(2)+u(0)+u(1)
    h2 = h2prefix+u(1)+control+u(1)+record+u(1)+u(1)
    (root/'hud.bin').write_bytes(h2);main.cook(root,out);check()
    subprocess.run(['build/client/n3e-hud-check',str(out)],check=True)
    result=subprocess.run(['target/debug/n3e-server','--check-content'],env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True)
    assert result.returncode==0,result.stderr
    invalid_h2 = [h2[:-1],h2+b'\0',h2prefix+u(257)]
    for bad in [u(1)+control[4:],u(0)+u(4)+control[8:],control[:8]+u(4)+u(1),control[:12]+u(2)]:
        invalid_h2.append(h2prefix+u(1)+bad+u(1)+record+u(1)+u(1))
    for cid,mask in [(2,1),(1,0),(1,16),(0,1)]:
        invalid_h2.append(h2[:-8]+u(cid)+u(mask))
    for invalid in invalid_h2:
        (root/'hud.bin').write_bytes(invalid);main.cook(root,out);check(False)
    # N3H3 measured fixed-cell font metrics and single-line alignment flags.
    metrics=f([7])+u(14)+u(5)
    h3prefix=b'N3H3'+prefix[4:]+metrics
    textrecord=u(1)+record[4:]
    h3=h3prefix+u(1)+control+u(1)+textrecord+u(1)+u(15)+u(5)
    (root/'hud.bin').write_bytes(h3);main.cook(root,out);check()
    result=subprocess.run(['target/debug/n3e-server','--check-content'],env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True)
    assert result.returncode==0,result.stderr
    bad_h3=[h3[:-1],h3+b'\0']
    for flags in [2,4,6,7,8]:bad_h3.append(h3[:-4]+u(flags))
    for metric in [(float('nan'),14,5),(0,14,5),(17,14,5),(7,0,5),(7,21,0),(7,14,7)]:
        bad_h3.append(b'N3H3'+prefix[4:]+f([metric[0]])+u(metric[1])+u(metric[2])+h3[len(h3prefix):])
    bad_h3.append(h3prefix+u(1)+control+u(1)+record+u(1)+u(15)+u(5))
    for invalid in bad_h3:
        (root/'hud.bin').write_bytes(invalid);main.cook(root,out);check(False)
    # N3HB is the H3 layout behind a uint32 scale policy (0 fit, 1 pixel).
    for policy in (0,1):
        (root/'hud.bin').write_bytes(b'N3HB'+u(policy)+h3[4:]);main.cook(root,out);check()
    for invalid in [b'N3HB'+u(2)+h3[4:],b'N3HB'+h3[4:],b'N3HB'+u(1)+h3[4:-1]]:
        (root/'hud.bin').write_bytes(invalid);main.cook(root,out);check(False)
    from hud_import import verify
    verify(root,out,main.cook,check)
    (root/'hud.bin').write_bytes(valid)
    # Optional movement clips are a paired, hashed extension for N3G3 only.
    for name in ['player-run.bin','player-backward.bin']:
        shutil.copyfile('build/packages/legacy-demo/scene.bin',root/name)
        manifest['presentation'][name]=name
    (root/'package.json').write_text(json.dumps(manifest))
    try:main.cook(root,out)
    except ValueError:pass
    else:raise AssertionError('legacy locomotion extension accepted')
    manifest.update(engine_version=2,protocol_version=2)
    manifest['gameplay']['movement']=dict(run_speed=4.5,backward_speed=1.5,radius=.2,height=1.6,step_height=.25)
    (root/'package.json').write_text(json.dumps(manifest))
    main.cook(root,out);check()
    result=subprocess.run(['target/debug/n3e-server','--check-content'],env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True)
    assert result.returncode==0,result.stderr
    # Rehash an incomplete cooked set to reach both readers' semantic check.
    from common import string
    data=(out/'release.bin').read_bytes()
    pos=16
    for _ in range(2):
        length=struct.unpack_from('<I',data,pos)[0];pos+=4+length
    count=struct.unpack_from('<I',data,pos)[0];start=pos;pos+=4
    entries=[]
    for _ in range(count):
        begin=pos;length=struct.unpack_from('<I',data,pos)[0];pos+=4
        name=data[pos:pos+length].decode();pos+=length+4+32
        if name!='player-backward.bin':entries.append(data[begin:pos])
    (out/'release.bin').write_bytes(data[:start]+u(count-1)+b''.join(entries))
    check(False)
    result=subprocess.run(['target/debug/n3e-server','--check-content'],env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True)
    assert result.returncode!=0
    manifest['presentation'].pop('player-backward.bin')
    (root/'package.json').write_text(json.dumps(manifest))
    try:main.cook(root,out)
    except ValueError:pass
    else:raise AssertionError('unpaired locomotion accepted')
    manifest['presentation'].pop('player-death.bin')
    (root/'package.json').write_text(json.dumps(manifest))
    try:main.cook(root,out)
    except ValueError:pass
    else:raise AssertionError('incomplete set accepted')
print('PASS C++/Rust optional presentation identity, tampering and rehashed malformed HUD rejection')

subprocess.run(['build/client/n3e-pose-check'],check=True)
# Full player timelines may exceed the old 4096-key monster spike bound.
from ko_character import Reader, key
track=u(4336)+u(0)+f([30])+f([0,0,0])*4336
assert len(key(Reader(track),0)['values'])==4336
reject(lambda data:key(Reader(data),0),u(65537))
print('PASS bounded long player animation timeline')
