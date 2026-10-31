"""Moradon starter skills: local tables, binary-confirmed semantics, original clips."""
import csv,io,json,shutil
from pathlib import Path
import ko_character,main

# PQ-466 (D-234): 1298's skill start (KnightOnLine.exe 005819e0) checks the
# range through 00583780, which, out of range, loads text 0xfa9 (4009) from the
# Data\Texts table (00615080; the table at 008186e8, PQ-361), formats it with
# the row's +0x18 string (0067429f) and posts it through 005d7250 in 0xffffff00
# before returning 0 (no cast). The policy's `notice` is that text from the
# player's Texts_us.tbl, never committed; the local row has no format field.
TOO_FAR=4009
# PQ-469 (D-235): Ebenezer refuses a skill out of range (004c1dbe from the
# magic packet 004630a6) with phase 4 and -103 (0046e707). 1298's fail receive
# 00586fa0 then, for the caster, loads text 0xfa4 (4004) (0058738c), formats it
# with the row's +0x18 string (0067429f, 005873d2) and posts it through 005d7250
# in 0xffff3b3b (00587438). The policy's `failed` line is that text from the
# player's Texts_us.tbl, never committed, in that colour.
FAILED=4004
FAILED_COLOR=0xffff3b3b
# PQ-479 (D-243): what 1298 shows for the server's other refusals of a skill
# at its acceptance (KO's casting phase, which 1298's cast start 00583f20 sends
# for a row with a cast time, 005845a2). 1298's usable check 0057f7f0 (from
# the skill start 005819e0 at 005829e2, before any packet) refuses the class
# (row +0x64, text 0xfa3 at 0057f8bc), the MP (player +0x808 below row +0x68,
# 0057fae6; text 0xbbc for a mage or priest, 0057fb01-0057fb1b) and the need
# item kind (row +0x70 not 0 or 9 and neither hand's kind / 10, 0057fe54;
# text 0xfa5 at 0057fe8d), each posted through 005d7250 in 0xffffff00. It has
# no level test, so a low level reaches Ebenezer's admission 00464b43, which
# answers a casting phase -100 (00464cc8-00464cd2), as it answers a dead NPC
# target (00464d78); 1298's fail receive posts text 0xfa2 for -100 in
# 0xffff3b3b (0058752a-00587544). The row's NeedSkill 2040 is a priest's, so
# the MP text is 3004. Each text is the player's Texts_us.tbl row, never
# committed.
REFUSALS=(('wrong_class','any',4003,0xffffff00),('insufficient_resource','any',3004,0xffffff00),
          ('weapon_required','any',4005,0xffffff00),('level_required','any',4002,0xffff3b3b),
          ('target_dead','npc',4002,0xffff3b3b))

def cook(assets,root,manifest):
    spec=json.loads(Path('games/moradon/skills.json').read_text())
    rows={int(r[0]):r for r in csv.reader(io.StringIO(assets.get('Data/Skill_Magic_Main_us.tbl.csv').decode('utf-8-sig'))) if r[0].isdigit()}
    type3={int(r[0]):r for r in csv.reader(io.StringIO(assets.get('Data/skill_magic_3.tbl.csv').decode('utf-8-sig'))) if r[0].isdigit()}
    looks=next(r for r in csv.reader(io.StringIO(assets.get('Data/UPC_DefaultLooks.tbl.csv').decode('utf-8-sig'))) if r[0]=='2')
    parts=looks[4:10];parts[2]=parts[2].replace('_face.n3cpart','_face00.n3cpart');parts[5]=parts[5].replace('_hair.n3cpart','_hair00.n3cpart')
    definition=dict(name='Male Tuarek',joint=looks[2],animation=looks[3],parts=parts,collision=[],split=[-1]*4,extras=[])
    texts={r[0]:r for r in csv.reader(io.StringIO(assets.get('Data/Texts_us.tbl.csv').decode('utf-8-sig'))) if r and r[0].isdigit()}
    notice=texts.get(str(TOO_FAR))
    if notice is None or len(notice)<2:raise ValueError('1298 Texts_us.tbl has no text %d'%TOO_FAR)
    spec['notice']=notice[1]
    failed=texts.get(str(FAILED))
    if failed is None or len(failed)<2:raise ValueError('1298 Texts_us.tbl has no text %d'%FAILED)
    spec['failed']=dict(text=failed[1],color=FAILED_COLOR)
    spec['refusals']=[]
    for status,target,number,color in REFUSALS:
        line=texts.get(str(number))
        if line is None or len(line)<2:raise ValueError('1298 Texts_us.tbl has no text %d'%number)
        spec['refusals'].append(dict(status=status,target=target,text=line[1],color=color))
    report=[]
    for index,s in enumerate(spec['skills']):
        source_id=s.pop('source_skill');row=rows[source_id];direct=type3[source_id]
        if [int(x)for x in direct[1:]]!=[0,1,s['amount']*(1 if s['target']==1 else -1),0,0,0 if s['target']==1 else 4]:raise ValueError('starter direct spell mismatch')
        expected={4:s['animation'],14:2 if s['target']==1 else 7,15:s['level'],16:2040,17:s['cost'],18:0,19:9,20:0,21:s['cast_ms']//100,22:s['cooldown_ms']//100,25:s['survival'],26:3,27:0,28:int(s['range'])}
        if any(int(row[k])!=v for k,v in expected.items()):raise ValueError('starter skill table mismatch')
        target=root/'skills'/str(index);clip=ko_character.convert(assets.root,'Data/UPC_DefaultLooks.tbl.csv',target,s['animation'],1.,definition=definition)
        main.cook(target,target/'cooked');shutil.copyfile(target/'cooked/scene.bin',root/f'player-skill-{index}.bin')
        report.append(dict(source_id=source_id,animation=clip,table=row))
        s['animation']=index
    manifest['skills']=spec;manifest['engine_version']=35;manifest['protocol_version']=28
    return dict(skills=report,notice=dict(text=TOO_FAR,value=notice[1]),failed=dict(text=FAILED,value=failed[1],color='%08x'%FAILED_COLOR),
                refusals=[dict(status=r['status'],target=r['target'],text=n,value=r['text'],color='%08x'%r['color'])
                          for (_,_,n,_),r in zip(REFUSALS,spec['refusals'])],sources=assets.sources.copy())
