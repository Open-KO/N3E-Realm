"""Opt-in test of a local KO field stack; uses a separate probe account.

Probes the persistent tools/play-ko-field stack (project n3e-ko-field, port 7778)
unless tests/ko_stack.py names a disposable one through N3E_FIELD_PROJECT and
N3E_FIELD_PORT (make live-ko, PQ-111)."""
import json
import os
import pathlib
import secrets
import subprocess
import time
from world_peer import Peer, first

project=os.environ.get("N3E_FIELD_PROJECT","n3e-ko-field")
port=int(os.environ.get("N3E_FIELD_PORT","7778"))
account="probe"+secrets.token_hex(4)
password=secrets.token_urlsafe(24)
subprocess.run(["docker","compose","-p",project,"exec","-T","server","n3e-server","account-create",account],input=password+"\n",text=True,check=True)
p=Peer(port,account,password,content=pathlib.Path(os.environ.get("N3E_KO_WORK","build"),"packages/ko-field/release.sha256").read_text().strip(),game="kotest")
p.select(p.create("Probe"))
npcs={i:e for i,e in p.entities.items() if first(e,9)}
assert len(npcs)==4, p.entities
target=min(npcs,key=lambda i: first(npcs[i],3)**2+first(npcs[i],5)**2)
original=set(npcs)
start=time.monotonic()
while time.monotonic()-start<12:
    me=p.entities[p.id]; e=p.entities[target]
    dx,dz=first(e,3)-first(me,3),first(e,5)-first(me,5)
    d=(dx*dx+dz*dz)**.5
    if d<.8: break
    p.move(dx/max(d,1),dz/max(d,1));p.pump(.05)
else: raise AssertionError("approach timeout")
assert p.action(target)=="hit"
p.pump(.6)
assert all(first(p.entities[i],7)==30 for i in original-{target}),p.entities
assert p.action(target)=="hit"
p.pump(.6)
assert p.action(target)=="hit"
p.pump(.4)
assert first(p.inventory,2)==2 and first(p.inventory,4)==10,p.inventory
# Stale dead entity cannot grant another reward; another mob is out of range.
assert p.action(target)=="target_dead"
far=max(original-{target},key=lambda i:first(npcs[i],3)**2+first(npcs[i],5)**2)
assert p.action(far)=="out_of_range"
p.pump(10.2)
current={i for i,e in p.entities.items() if first(e,9)}
assert len(current)==4 and len(current-original)==1 and target not in current
assert first(p.inventory,2)==2
p.logout()
print("PASS four independent mobs, approach, damage isolation, reward once, stale/dead/range rejection and fresh respawn ID")
