"""Original-only animation format/reader identity and numeric controller checks."""
import copy, json, os, struct, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import animation_fixture, animation, main
from common import digest, string, u
package=animation_fixture.cook()
root=Path('build/ko-07/source')
m=json.loads((root/'package.json').read_text())
def readers(out,good=True):
    results=[]
    for command in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        p=subprocess.run(command,env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
        assert (p.returncode==0)==good,(command,p.stdout,p.stderr)
        results.append(p.stdout.splitlines()[0] if good else '')
    if good: assert results[0]==results[1]==(out/'release.sha256').read_text().strip()
readers(package)
subprocess.run(['build/client/n3e-animation-check',str(package)],check=True)
# Rehash mutations so both readers reach the semantic parser rather than only hash validation.
def rehash(out,name,data):
    (out/name).write_bytes(data)
    raw=(out/'release.bin').read_bytes();at=16
    for _ in range(2):n=struct.unpack_from('<I',raw,at)[0];at+=4+n
    header=raw[:at];count=struct.unpack_from('<I',raw,at)[0];at+=4
    entries=[]
    for _ in range(count):
        n=struct.unpack_from('<I',raw,at)[0];at+=4
        key=raw[at:at+n].decode();at+=n+36
        content=(out/key).read_bytes()
        entries.append(string(key)+u(len(content))+digest(content))
    (out/'release.bin').write_bytes(header+u(count)+b''.join(entries))
with tempfile.TemporaryDirectory(dir='build') as tmp:
    out=Path(tmp)/'release'
    for offset,value in [(4,float('nan')),(4,0),(8,-.1),(16,4000)]:
        main.cook(root,out);data=bytearray((out/'animation.bin').read_bytes());struct.pack_into('<f',data,offset,value)
        rehash(out,'animation.bin',data);readers(out,False)
    for data in [b'N3A1',animation.cook(m['animation'])+b'\0']:
        main.cook(root,out);rehash(out,'animation.bin',data);readers(out,False)
    main.cook(root,out);data=bytearray((out/'animation.bin').read_bytes());struct.pack_into('<I',data,12+2*20,1)
    rehash(out,'animation.bin',data);readers(out,False)
    for mutation in ['missing','engine','marker','loop']:
        bad=copy.deepcopy(m)
        if mutation=='missing':bad['presentation'].pop('npc-death.bin')
        if mutation=='engine':bad['engine_version']=7
        if mutation=='marker':bad['animation'][2]['markers']=[2,-1]
        if mutation=='loop':bad['animation'][2]['loop_blend']=True
        (root/'package.json').write_text(json.dumps(bad))
        try:main.cook(root,out)
        except ValueError:pass
        else:raise AssertionError(mutation)
        finally:(root/'package.json').write_text(json.dumps(m,indent=2)+'\n')
# Player-only metadata must load without NPC presentation in both readers.
with tempfile.TemporaryDirectory(dir='build') as tmp:
    out=Path(tmp)/'release'
    player=copy.deepcopy(m)
    player['animation']=player['animation'][:7]
    player['presentation']={k:v for k,v in player['presentation'].items() if not k.startswith('npc-')}
    try:
        (root/'package.json').write_text(json.dumps(player))
        main.cook(root,out);readers(out)
        assert (out/'animation.bin').read_bytes()[:4]==b'N3A2'
        subprocess.run(['build/client/n3e-animation-check',str(out)],check=True)
        valid=(out/'animation.bin').read_bytes()
        for data in [valid[:-1],valid+b'\0',b'N3A1'+valid[4:],b'N3A2'+animation.cook(m['animation'])[4:]]:
            main.cook(root,out);rehash(out,'animation.bin',data);readers(out,False)
        for offset,value in [(4,float('nan')),(8,-1),(16,4000)]:
            main.cook(root,out);data=bytearray(valid);struct.pack_into('<f',data,offset,value)
            rehash(out,'animation.bin',data);readers(out,False)
        for missing in ['player-ready.bin','player-backward.bin']:
            bad=copy.deepcopy(player);bad['presentation'].pop(missing)
            (root/'package.json').write_text(json.dumps(bad))
            try:main.cook(root,out)
            except ValueError:pass
            else:raise AssertionError(missing)
    finally:(root/'package.json').write_text(json.dumps(m,indent=2)+'\n')
print('PASS player-only animation C++/Rust compatibility, transitions and malformed metadata')
print('PASS animation C++/Rust hashes, rehashed malformed metadata, producer completeness/compatibility')
