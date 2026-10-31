"""Bounded cast-time direct recovery and resistance-based spell damage."""
from common import u, f, string
import re

def identity(value):
    if not isinstance(value,str) or len(value)>96 or not re.fullmatch('[a-z][a-z0-9_-]*:[a-z][a-z0-9_/-]*',value):raise ValueError('skill identity')
    return string(value)

PLANES=('3d','xz')

def reach(value):
    """PQ-465 (D-232): the package's range rule over each skill's range:
    `start` is added with both actors' radii to the 3-D limit at a cast's
    acceptance, `hold` to the limit the target stays below from the release to
    the impact, measured on `plane` (3-D, or the ground plane x/z)."""
    if type(value) is not dict or set(value)!={'start','hold','plane'} or value['plane'] not in PLANES:raise ValueError('skill reach')
    for key in ('start','hold'):
        if type(value[key]) not in (int,float) or not 0<=value[key]<=50:raise ValueError('skill reach')
    return f([value['start'],value['hold']])+u(PLANES.index(value['plane']))

MAX_NOTICE=96

def notice(value):
    """PQ-466 (D-234): the line the client posts, and sends nothing, when a
    skill's target is beyond the start limit: 1-96 printable ASCII bytes, with
    at most one `%s` (the skill's label, as 1298's 00583780 formats text 0xfa9
    with the row's name) and no other `%`."""
    if (type(value) is not str or not 1<=len(value)<=MAX_NOTICE or not all(' '<=c<='~' for c in value)
            or value.replace('%s','',1).count('%')):raise ValueError('skill notice')
    return string(value)

def failed(value):
    """PQ-469 (D-235): the line the client posts, and its colour (ARGB, alpha
    not 0), when the server refuses a skill it sent `out_of_range`, as 1298's
    fail receive 00586fa0 posts text 0xfa4 formatted with the row's name in
    0xffff3b3b on Ebenezer's -103. The text is bounded as the notice is."""
    if (type(value) is not dict or set(value)!={'text','color'} or type(value['color']) is not int
            or not 0x01000000<=value['color']<=0xffffffff):raise ValueError('skill failed line')
    try:return notice(value['text'])+u(value['color'])
    except ValueError:raise ValueError('skill failed line') from None

TARGETS=('any','player','npc')

def refusals(value):
    """PQ-479 (D-243): the lines the client posts, each in its colour, when the
    server refuses at its acceptance a skill the client sent with `status`,
    on a target that was a player or an NPC in the client's view (`target`;
    `any` for either), as 1298 posts its own refusal text before it sends a
    cast (0057f7f0 from 005819e0) or text 0xfa2 on Ebenezer's -100 for a
    casting phase (00586fa0). 1-8 lines, one per status; `out_of_range` has
    the failed line instead. Each text is bounded as the notice is."""
    if type(value) is not list or not 1<=len(value)<=8:raise ValueError('skill refusal lines')
    out=u(len(value));seen=set()
    for line in value:
        if (type(line) is not dict or set(line)!={'status','target','text','color'} or type(line['status']) is not str
                or not re.fullmatch('[a-z][a-z_]{0,31}',line['status']) or line['status']=='out_of_range'
                or line['status'] in seen or line['target'] not in TARGETS):raise ValueError('skill refusal line')
        seen.add(line['status'])
        try:out+=string(line['status'])+u(TARGETS.index(line['target']))+failed(dict(text=line['text'],color=line['color']))
        except ValueError:raise ValueError('skill refusal line') from None
    return out

def cook(config):
    """N3K2; N3K3 (PQ-466) when the policy has a `notice` (after the reach);
    N3K4 (PQ-469) when it also has a `failed` line (after the notice); N3K5
    (PQ-479) when it also has `refusals` (after the failed line)."""
    if set(config)-{'notice','failed','refusals'}!={'archetype','label','reach','skills'} or not 1<=len(config['skills'])<=32:raise ValueError('skill policy')
    if 'failed' in config and 'notice' not in config:raise ValueError('skill failed line needs a notice')
    if 'refusals' in config and 'failed' not in config:raise ValueError('skill refusal lines need a failed line')
    magic=b'N3K5' if 'refusals' in config else b'N3K4' if 'failed' in config else b'N3K3' if 'notice' in config else b'N3K2'
    out=magic+identity(config['archetype'])+string(config['label'])+reach(config['reach'])
    if 'notice' in config:out+=notice(config['notice'])
    if 'failed' in config:out+=failed(config['failed'])
    if 'refusals' in config:out+=refusals(config['refusals'])
    out+=u(len(config['skills']))
    seen=set()
    for s in config['skills']:
        if set(s)!={'id','label','class','level','cost','cast_ms','cooldown_ms','range','target','amount','survival','attribute','resistance','weapons','animation','cast_effect','cast_joints','target_effect','target_joint'}:raise ValueError('skill fields')
        if s['class']!=config['archetype'] or s['id'] in seen or not 1<=len(s['label'])<=80:raise ValueError('skill duplicate/label')
        seen.add(s['id']);out+=identity(s['id'])+string(s['label'])+identity(s['class'])
        bounds={'level':(1,100),'cost':(0,100000),'cast_ms':(50,10000),'cooldown_ms':(0,60000),'target':(1,2),'amount':(1,5000),'survival':(0,100),'attribute':(0,4),'resistance':(0,200),'animation':(0,31)}
        for key,(low,high) in bounds.items():
            if type(s[key]) is not int or not low<=s[key]<=high:raise ValueError('skill bounds')
            out+=u(s[key])
        if not 0<s['range']<=50 or not 0<=len(s['weapons'])<=64 or not 1<=len(s['cast_joints'])<=2 or len(set(s['cast_joints']))!=len(s['cast_joints']):raise ValueError('skill range/attachment')
        out+=f([s['range']])+u(len(s['weapons']))+b''.join(identity(x) for x in s['weapons'])
        for key in ('cast_effect','target_effect'):out+=string(s[key])
        out+=u(len(s['cast_joints']))
        for joint in s['cast_joints']+[s['target_joint']]:
            if type(joint)is not int or not -1<=joint<128:raise ValueError('skill joint')
            out+=u(joint+1)
    return out
