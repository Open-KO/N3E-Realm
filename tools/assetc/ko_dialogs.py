"""Bind local KO UIF dialog trees to reusable, bounded native HUD actions.

Layout/artwork is local-asset evidence; bindings and pagination adapters are n3e
presentation policy. No imported artwork is stored in this module.
"""
import copy, hashlib, json
from pathlib import Path


def append(assets, parse, tex, add, controls, sounds=None, item_icons=None, equipment_slots=None):
    spec=json.loads(Path('games/moradon/ui.json').read_text())
    if equipment_slots is not None:spec['equipment_slots']=equipment_slots  # PQ-319: the glow package's areas
    sources=[]
    def source(name):
        data=assets.get('UI_US/'+name+'.uif')
        sources.append(dict(path='UI_US/'+name+'.uif',sha256=hashlib.sha256(data).hexdigest()))
        return parse(data)
    trees={v:source(v) for v in spec['sources']}
    def emit_tree(root,panel,origin,fields=None,actions=None,skip=(),area=None,bounds=True,anchor=(0,0),selected=()):
        fields=fields or {};actions={k:(f'close:{panel}' if v=='close' else v) for k,v in (actions or {}).items()};late=[]
        ox,oy=origin
        def emit(kind,n,**kw):
            rect=[n['rect'][0]+ox,n['rect'][1]+oy,n['rect'][2]+ox,n['rect'][3]+oy]
            add(kind,anchor,rect,panel=panel,**kw)
        # Root bounds consume clicks even in unpainted gaps.
        if bounds:emit(2,root,binding='action',text='panel')
        def walk(n,control=0,states=15,field=''):
            ident=n['id'].lower();kind=n['kind']
            if ident in skip:return
            field=fields.get(ident,field)
            if kind==1:
                controls.append((control,0,int(ident in selected),int(ident in actions)))
                control=len(controls)
                if sounds is not None:sounds[control]=[n['hover_sound'],n['click_sound']]
            if kind==4 and n['texture']:
                emit(0,n,texture=tex(n['texture']),uv=n['uv'],control=control,states=states,
                     binding='meter' if field else '',text=field)
            elif kind==6:
                # Numeric count strings are replaced by the live slot labels.
                if field or (n.get('text') and not ident.isdigit()):
                    late.append((1,n,dict(binding='value' if field else '',text=field or n.get('text',''),color=n.get('color',0xffffffff),control=control,states=states,text_flags=1)))
            elif kind==1:
                hit=dict(n,rect=n['click'])
                late.append((2,hit,dict(binding='action',text=actions.get(ident,'panel'),control=control)))
            elif kind==9 and area:
                if ident=='area_char':
                    late.append((0,n,dict(binding='portrait',text='player')))
                    return
                slot=area(n)
                if slot:
                    item=slot.split(':')[0] in ('bag','gear','bank','offer','loot')
                    if item:late.append((0,n,dict(binding='item',text=slot)))
                    late.append((1,n,dict(binding='item_label' if item else 'value',text=slot)))
                    late.append((2,n,dict(binding='action',text=slot)))
            elif kind==8:
                late.append((1,n,dict(binding='value',text=field,text_flags=1)))
                return
            elif kind==14 and field:
                l,t,r,b=n['rect']
                for i in range(8):
                    row=dict(n,rect=[l,t+i*16,r,t+(i+1)*16])
                    late.append((1,row,dict(binding='value',text=field+str(i),text_flags=1)))
                    late.append((2,row,dict(binding='action',text=field+str(i))))
                return
            for child in n['children']:
                walk(child,control,1<<child['reserved'] if kind==1 and child['kind']==4 else states,field)
        walk(root)
        for kind,n,kw in late:emit(kind,n,**kw)
    def slots(prefix,types):
        return lambda n:prefix.get(n.get('area'),'')+n['id'] if n.get('area') in types and n['id'].isdigit() else None
    emit_tree(trees['ka_inventory_us'],1,[-364,11],spec['inventory_fields'],{'btn_close':'close'},
              ['area_samma','elmo_ecli666'],lambda n: 'bag:'+n['id'] if n.get('area')==2 and n['id'].isdigit() else 'gear:'+str(spec['equipment_slots'][n['id']]) if n.get('area')==1 and n['id'] in spec['equipment_slots'] else None,anchor=(1,0))
    # Character/Friends share the original tab frame. Unsupported tabs stay disabled.
    for panel,name,fields,actions in [(2,'ka_page_state_us',spec['state_fields'],{}),(5,'ka_page_friends_us',spec['friend_fields'],spec['friend_actions'])]:
        emit_tree(trees[name],panel,[0,80],fields,actions)
        emit_tree(trees['ka_various_frame_us'],panel,[0,80],actions={'btn_state':'tab:state','btn_friends':'tab:friends','btn_close':'close'},skip=['btn_knights'],bounds=False,selected=['btn_state' if panel==2 else 'btn_friends'])
    emit_tree(trees['ka_warehouse_us'],4,[-363,14],spec['warehouse_fields'],spec['warehouse_actions'],area=slots({11:'bag:',3:'bank:'},[11,3]),anchor=(1,0))
    emit_tree(trees['Ka_Transaction_us'],3,[-365,10],spec['shop_fields'],spec['shop_actions'],
              skip=spec['shop_hidden'],area=slots({11:'bag:',3:'offer:'},[11,3]),anchor=(1,0))
    party=copy.deepcopy(trees['Co_Party_us'])
    def filter_party(n):
        n['children']=[v for v in n['children'] if not any(v['id'].endswith(s)for s in ('_slow','_drop','_lasting'))]
        for v in n['children']:filter_party(v)
    filter_party(party)
    party_fields={**{'static_name_'+str(i):'member:'+str(i) for i in range(8)},**{'progress_hp_'+str(i):'member_hp:'+str(i) for i in range(8)},**{'progress_mp_'+str(i)+'_curse':'member_mp:'+str(i) for i in range(8)}}
    emit_tree(party,6,[-131,40],party_fields,area=lambda n:'member:'+n['id'][5:] if n['id'].startswith('Area_') else None,anchor=(1,0))
    emit_tree(trees['co_tradecount_us'],8,[-128,-53],{'text_title':'prompt_title','edit_count':'prompt_input'},{'btn_ok':'confirm','btn_cancel':'cancel'},anchor=(.5,.5))
    # Supplemental actions use an original UIF button, with package-authored labels.
    button=next(n for n in trees['ka_page_friends_us']['children'] if n['id']=='btn_add')
    def button_at(panel,x,y,label,action,anchor=(0,0)):
        b=copy.deepcopy(button);dx=x-b['rect'][0];dy=y-b['rect'][1]
        def move(n):
            for key in ('rect','click'):
                if key in n:n[key]=[v+(dx if i%2==0 else dy)for i,v in enumerate(n[key])]
            if n['kind']==6:n['text']=''
            for c in n['children']:move(c)
        move(b);emit_tree(b,panel,[0,0],actions={'btn_add':action},anchor=anchor)
        add(1,anchor,[x+3,y,x+70,y+17],text=label,text_flags=1,panel=panel,color=0xff101010)
    for row,buttons in enumerate(spec['menu']):
        for col,(label,action) in enumerate(buttons):button_at(0,294+col*72,55+row*20,label,action)
    for panel,buttons in spec['actions'].items():
        panel=int(panel)
        anchor=(1,0) if panel in (1,3,4,6) else (0,0)
        x=-366 if anchor[0] else 0
        y={1:590,3:596,4:596,5:546,6:434}[panel]
        for i,(label,action) in enumerate(buttons):button_at(panel,x+(i%5)*72,y+(i//5)*22,label,action,anchor)
        add(1,anchor,[x,y+48,x+360,y+80],binding='value',text='selection',panel=panel)
    # Full instructions use a data record; ordinary chat retains the original HUD.
    help_tree=copy.deepcopy(trees['Co_Help_us'])
    help_tree['children']=[n for n in help_tree['children'] if n['kind']==4 or n['id']=='btn_close']
    emit_tree(help_tree,7,[-232,-212],actions={'btn_close':'close'},anchor=(.5,.5))
    add(1,(.5,.5),[-212,-204,188,-182],text='Help',panel=7,text_flags=1)
    for i,line in enumerate(spec['help'].splitlines()):
        if line:add(1,(.5,.5),[-212,-172+i*16,228,-156+i*16],text=line,panel=7,text_flags=1)
    import ko_item_icons
    icons,icon_sources=ko_item_icons.cook(assets,tex,spec['item_icons'] if item_icons is None else item_icons)
    dropped=source('Co_DroppedItem_us')
    # Counters are generated from the same live slot bindings as the icons.
    dropped['children']=[n for n in dropped['children'] if n['kind']!=6]
    emit_tree(dropped,9,[0,0],area=lambda n:'loot:'+n['id'] if n.get('area')==6 and n['id'].isdigit() else None)
    skills=source('ka_skilltree_us')
    # Bounded base-page skills; retain original slot, label and button geometry.
    # Binary004ea6f0 uses six area7 slots and full skill-icon UVs.
    keep={'img_public','img_skill_up','img_skill_down','btn_public','btn_close','string_page',
          'string_info','string_skill_mp','string_skill_point','string_list_0','string_list_1'}
    skills['children']=[n for n in skills['children'] if n['id'].lower() in keep or (n['kind']==9 and n['id'] in ('0','1'))]
    fields={'string_list_0':'skill_name:0','string_list_1':'skill_name:1','string_page':'skill_page','string_info':'skill_info','string_skill_mp':'skill_cost','string_skill_point':'skill_requirement'}
    emit_tree(skills,10,[-364,10],fields,{'btn_close':'close','btn_public':'skill_base'},anchor=(1,0),selected=['btn_public'])
    for n in skills['children']:
        if n['kind']!=9:continue
        key='skill:'+n['id'];l,t,r,b=n['rect'];rect=[l-364,t+10,r-364,b+10]
        add(0,(1,0),rect,binding='item',text=key,panel=10)
        add(2,(1,0),rect,binding='action',text=key,panel=10)
    tooltip=source('co_iteminfo_us')
    background=next(n for n in tooltip['children'] if n['id']=='mins')
    rows=[next(n for n in tooltip['children'] if n['id']==f'string_{i}')['rect'][1::2] for i in range(30)]
    tip=dict(texture=tex(background['texture']),uv=background['uv'],rows=rows)
    return sources,icons,icon_sources,spec['portraits'],tip
