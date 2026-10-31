"""Independent consumers, hostile rehashed durability definitions and reuse."""
import copy,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from storage_auth_live import prepare
package=prepare();sys.path.insert(0,str(Path('tools/assetc').resolve()))
import main,storage_auth
from common import u,string,digest
m=json.loads((package/'recipe.json').read_text())['manifest']
def check(out,good=True):
    hashes=[]
    for cmd in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        p=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(out)},text=True,capture_output=True)
        assert(p.returncode==0)==good,(cmd,p.stdout,p.stderr)
        if good:hashes.append(p.stdout.splitlines()[0])
    if good:assert hashes[0]==hashes[1]
check(package)

for key,values in [('comparison',['unknown',True,1]),('minimum',[0,True,17]),('maximum',[129,False,5]),('alphabet',['','aab','ba','abc ', 'abcé']),('forbidden',[['bad','BAD'],[''],['é'],['x'*65],['a']*401])]:
    for value in values:
        p=copy.deepcopy(m['storage_auth']);p[key]=value
        try:storage_auth.cook(p)
        except (ValueError,TypeError):pass
        else:raise AssertionError((key,value))
with tempfile.TemporaryDirectory(dir='build')as td:
    out=Path(td)/'release';shutil.copytree(package,out)
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in('release.bin','release.sha256')}
    def repack(data,engine=22,protocol=15,omit=False):
        changed=dict(files);changed['storage-auth.bin']=data
        if omit:del changed['storage-auth.bin']
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):(out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['storage-auth.bin']
    for data in [b'BAD!'+original[4:],original[:-1],original+b'\0']:repack(data);check(out,False)
    for at,value in [(4,0),(4,17),(8,129),(8,5),(12,2),(16,0),(16,95)]:
        b=bytearray(original);b[at:at+4]=u(value);repack(bytes(b));check(out,False)
    for engine,protocol in [(21,15),(22,14),(23,16)]:repack(original,engine,protocol);check(out,False)
    repack(original,omit=True);check(out,False)
    source=Path(td)/'source';shutil.copytree('build/ko-completion/storage-auth/source',source)
    other=json.loads(json.dumps(m).replace('demo:','alternate:').replace('"game_id": "demo"','"game_id": "alternate"'));other['storage_auth']['minimum']=8;other['storage_auth']['comparison']='exact'
    (source/'package.json').write_text(json.dumps(other));main.cook(source,out);check(out)
print('PASS storage credential producer/readers, hostile rehashed bounds, versions and second namespace')
