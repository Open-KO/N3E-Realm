"""Original-only icon lookup and hostile H5/native-reader coverage."""
import json
from common import f, string, u
import ko_item_icons


def verify(root, out, cook, check, header, field):
    assert ko_item_icons.path(12345678) == 'UI/ItemIcon_1_2345_67_8.dxt'
    assert ko_item_icons.path(12345678, 98765432) == 'UI/ItemIcon_9_8765_43_2.dxt'
    for bad in (-1, 2**32, True, '123'):
        try: ko_item_icons.path(bad)
        except ValueError: pass
        else: raise AssertionError('invalid legacy icon ID accepted')
    game=json.loads((root/'package.json').read_text())['game_id']
    item=game+':item/paint'
    class Fixture:
        def get(self,path):
            assert path=='UI/ItemIcon_9_8765_43_2.dxt'
            return b'original icon provenance fixture'
    icons, provenance=ko_item_icons.cook(Fixture(),lambda _:0,{item:dict(base=12345678,extension=98765432)})
    assert icons==[(item,0,(0,0,45/64,45/64))] and len(provenance[0]['sha256'])==64
    # header is the H4 prefix up to (but excluding) its record count.
    prefix=b'N3H5'+header[4:]
    records=u(2)+field(0,'item','bag:0')+field(1,'item_label','bag:0')
    table=ko_item_icons.encode(icons)
    valid=prefix+records+table
    def run(data,good):
        (root/'hud.bin').write_bytes(data);cook(root,out);check(good)
    run(valid,True)
    run(prefix+records+u(0),True) # No icon mapping is a supported text fallback.
    font=int.from_bytes(prefix[4:8],'little')
    bad_tables=[u(257),u(1),u(2)+table[4:]*2]
    for name,tex,uv in [(item,64,[0,0,1,1]),(item,font,[0,0,1,1]),
                        ('other:item/paint',0,[0,0,1,1]),(game+':../paint',0,[0,0,1,1]),
                        (item,0,[0,0,float('nan'),1]),(item,0,[0,0,1.1,1]),
                        (item,0,[1,0,0,1]),(item,0,[0,0,0,1])]:
        bad_tables.append(u(1)+string(name)+u(tex)+f(uv))
    for table in bad_tables:run(prefix+records+table,False)
    for data in [valid[:-1],valid+b'\0',
                 prefix+u(1)+field(1,'item','bag:0')+u(0),
                 prefix+u(1)+field(0,'item_label','bag:0')+u(0),
                 prefix+u(1)+field(0,'item','../bad')+u(0),
                 b'N3H4'+valid[4:]]:run(data,False)
    run(valid,True)
    print('PASS original H5 icon lookup/override, native table, namespace/UV/texture/duplicate/binding rejection and H4 isolation')

    # H6 independently validates preview bindings and package camera parameters.
    h6=b'N3H6'+header[4:]+u(1)+field(0,'portrait','player')+u(0)
    portrait=string('player')+f([-20,11.309932,1.15])
    valid6=h6+u(1)+portrait
    run(valid6,True)
    for data in [h6+u(0),h6+u(9),h6+u(2)+portrait*2,valid6[:-1],valid6+b'\0',
                 h6+u(1)+string('../player')+f([0,0,1]),
                 h6+u(1)+string('player')+f([float('nan'),0,1]),
                 h6+u(1)+string('player')+f([181,0,1]),
                 h6+u(1)+string('player')+f([0,81,1]),
                 h6+u(1)+string('player')+f([0,0,.5]),
                 b'N3H5'+valid6[4:]]:run(data,False)
    run(valid6,True)
    print('PASS original H6 portrait binding, bounded camera table and malformed/duplicate/missing/version rejection')

    # H7 tooltip artwork and rows are bounded separately from H6 portraits.
    prefix7=b'N3H7'+valid6[4:]
    layout=u(0)+f([0,0,1,1])+f([42,14,26])+u(2)+f([5,27,32,47])
    run(prefix7+layout,True)
    for tail in [layout[:-1],layout+b'\0',u(font)+layout[4:],layout[:4]+f([0,0,2,1])+layout[20:],
                 layout[:20]+f([0,14,26])+layout[32:],layout[:32]+u(31),layout[:36]+f([5,27,4,47])]:
        run(prefix7+tail,False)
    h8=b'N3H8'+valid6[4:]+layout
    run(h8+u(0)+u(0x8cf46161)+u(0)*3,True)
    for tail in [u(0)+u(0)*3,u(0)+u(0x8cf46161)+u(font)+u(0)*2,u(1)+string('unknown:action')+u(0)+f([0,0,1,1])+u(0)*3]:
        run(h8+tail,False)
    # Independent H9 fixture: proportional ASCII metrics and root-joint policy.
    n9=(b'N3H9'+u(0)+f([30,20])+u(2)+u(256)+u(128)+bytes(256*128*4)
        +u(512)+u(192)+bytes(512*192*4)+f([7])+u(14)+u(3)+u(0)
        +u(1)+field(1,'value','coins')+u(0)+u(0)
        +u(1)+f([0,0,1,1])+f([42,14,26])+u(1)+f([5,27])
        +u(0)+u(0x8cf46161)+u(1)*3)
    font9=u(1)+u(18)+u(7)+f([8]*95)
    tail9=f([48,.1,5,.5])+u(0xffffff)*3+font9*2+f([2])+u(0)+f([.75])+u(0)
    run(n9+tail9,True)
    for offset,value in [(0,f([0])),(0,f([float('nan')])),(4,f([2])),(12,f([-1])),
                         (28,u(0)),(32,u(33)),(36,u(0xffffffff)),(40,f([0])),
                         (40,f([float('inf')])),(812,f([0])),(816,u(1)),(824,u(63))]:
        run(n9+tail9[:offset]+value+tail9[offset+4:],False)
    run(n9+tail9[:-1],False);run(n9+tail9+b'\0',False)
    print('PASS H9 synthetic fonts, bounds, nonfinite metrics, atlas mismatch, invalid root joints and truncation rejection')
    # HA is H9 behind a uint32 scale policy: 0 fits the reference view, 1 keeps pixel size.
    for policy in (0,1):run(b'N3HA'+u(policy)+n9[4:]+tail9,True)
    for bad in (b'N3HA'+u(2)+n9[4:]+tail9,b'N3HA'+n9[4:]+tail9,b'N3HA'+u(1)+n9[4:]+tail9[:-1]):run(bad,False)
    print('PASS HA scale policy over the H9 layout; unknown or missing policy and truncation rejected')
    # HC appends a draggable panel table to HA (panels 1-15 except prompt 8 and loot 9).
    def movable(panel=11,group=1,anchor=(0,1),handle=(0,-20,80,0),bounds=(0,-140,500,0),snap=0,key='chat'):
        return u(panel)+u(group)+f(list(anchor))+f(list(handle))+f(list(bounds))+u(snap)+string(key)
    hc=b'N3HC'+u(1)+n9[4:]+tail9
    run(hc+u(0),True);run(hc+u(2)+movable()+movable(panel=12,key=''),True)
    for table in [u(1)+movable(panel=8),u(1)+movable(panel=9),u(1)+movable(panel=16),u(1)+movable(panel=0),
                  u(2)+movable()+movable(),u(2)+movable()+movable(panel=12),u(1)+movable(group=16),u(1)+movable(snap=33),
                  u(1)+movable(key='Chat'),u(1)+movable(key='x'*33),u(1)+movable(anchor=(0,2)),
                  u(1)+movable(handle=(0,-20,0,0)),u(1)+movable(handle=(0,-160,80,0)),u(1)+movable(bounds=(0,0,0,0)),
                  u(9)+movable()*9,u(1)+movable()[:-1],u(1)+movable()+b'\0',b'']:
        run(hc+table,False)
    print('PASS HC draggable panel table bounds, unique panels, one saved key per group and truncation rejection')
    # HD adds the overview map: one 'minimap' image record on panel 15 and its block.
    def image(panel=15,texture=1,binding='minimap'):
        return u(0)+f([0,0,0,0,100,20])+u(texture)+f([0,0,1,1])+string(binding)+string('')+u(0xffffffff)+u(0)+u(0)+u(0)+u(15)+u(0)+u(panel)
    one=u(1)+field(1,'value','coins')
    assert n9.count(one)==1
    def hd(record=image(),texture=1,origin=(-256,-256),params=(512,6,1/30,2,1),magic=b'N3HD',tail=b''):
        body=n9.replace(one,u(2)+field(1,'value','coins')+record)
        block=u(texture)+f(list(origin))+f(list(params))+b''.join(u(c) for c in (0xff00ff00,0xff800000,0xff00a0ff,0xffffff00,0xff0040ff))
        return magic+u(1)+body[4:]+tail9+u(0)+block+tail
    toggle=u(2)+f([0,0,0,0,100,20])+u(0)+f([0,0,1,1])+string('toggle_minimap')+string('')+u(0xffffffff)+u(0)+u(0)+u(0)+u(15)+u(0)+u(0)
    run(hd(),True)
    for bad in [hd(texture=0),hd(image(texture=0),texture=0),hd(params=(0,6,1/30,2,1)),hd(params=(512,.5,1/30,2,1)),hd(params=(512,65,1/30,2,1)),
                hd(params=(512,6,0,2,1)),hd(params=(512,6,1/30,1,2)),hd(params=(512,6,1/30,17,1)),hd(origin=(-70000,0)),
                hd(image(panel=14)),hd(image(binding='')),hd(record=toggle),hd(magic=b'N3HC'),hd(tail=b'\0'),hd()[:-1]]:
        run(bad,False)
    print('PASS HD overview map block bounds, single panel-15 image on its texture, toggle binding scope and truncation rejection')
    run(valid6,True)
    print('PASS H8 empty action table, unknown action, invalid flash texture and truncation rejection')
    print('PASS H7 tooltip artwork/row bounds, malformed metadata and retained H6 compatibility')
