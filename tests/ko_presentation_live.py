"""Opt-in real KO presentation with the retained isolated combat/fault driver."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools/assetc'))
import main
# N3E_KO_WORK: where the KO cooks wrote (default build/; make live-ko: build/live-ko/work).
work=pathlib.Path(os.environ.get('N3E_KO_WORK','build'))
root=work/'ko-source/combat'
shutil.copytree(work/'ko-source/field',root,dirs_exist_ok=True)
manifest=json.loads((root/'package.json').read_text())
# Preserve Phase 3 authority/fault timings; replace only presentation assets.
rules=json.loads(pathlib.Path('tests/fixtures/legacy-demo/package.json').read_text())['gameplay']
for k in ['action','item','npc']:rules[k]=rules[k].replace('demo:','kotest:')
manifest['gameplay']=rules
(root/'package.json').write_text(json.dumps(manifest))
meta=json.loads(pathlib.Path('tests/fixtures/legacy-demo/scene.json').read_text());meta['instance_scale']=[1,1,1];meta['attachment_node']=0
(root/'scene.json').write_text(json.dumps(meta))
package=work/'packages/ko-presentation-combat'
print('Combat presentation release',main.cook(root,package),flush=True)
subprocess.run([sys.executable,'tests/gameplay.py'],env={**os.environ,'N3E_TEST_PACKAGE':str(package),'N3E_GRAPHICAL':'1'},check=True)
log=pathlib.Path('build/ko-gameplay/alpha-graphics.txt').read_text()
for state in [0,2,3]:assert f'POSE state={state}' in log,log
print('PASS actual player idle/attack/death/respawn and KO HUD during authoritative graphical combat')
