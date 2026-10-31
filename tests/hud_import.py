"""Original UIF fixture for control/subtree conversion; no reference assets."""
import struct
from unittest.mock import patch
from common import u, f, string
from ko_character import Reader
import ko_hud


def verify(root, out, cook, check):
    def node(kind, ident='', children=(), slot=0, text=''):
        data=string('')+struct.pack('<hh',len(children),1)
        data+=b''.join(u(k)+v for k,v in children)
        data+=string(ident)+struct.pack('<8i2I',0,0,32,16,0,0,32,16,0x04900000 if kind==6 else 0,slot)+string('')*3
        if kind==4: data+=string('synthetic.dxt')+f([0,0,1,1,0])
        if kind==6: data+=string('')+u(0xffffffff)+string(text)+u(0)
        if kind==1: data+=struct.pack('<4i',0,0,32,16)+string('')*2
        if kind==9: data+=u(0)
        return kind,data
    names=['btn_attack','btn_walk','btn_run','btn_sit','btn_stand','btn_invite','btn_disband']
    buttons=[]
    for name in names:
        images=[node(4,children=[node(6,text=name+str(s))],slot=s) for s in range(4)]
        buttons.append(node(1,name,images))
    class Fixture:
        def get(self,path):
            if path=='synthetic.dxt':
                return string('')+b'NTF\x03'+struct.pack('<4i',4,4,26,0)+struct.pack('<16H',*([0xffff]*16))
            return node(0,children=buttons if path.endswith('ka_cmd_us.uif') else [node(1,'btn_check_normal',[node(4,slot=s) for s in range(4)])] if path.endswith('ka_chat_us.uif') else [node(9,'0')] if path.endswith('ka_hotkey_us.uif') else [])[1]
    with patch.object(ko_hud.subprocess,'check_output',return_value=bytes(256*128*4)), patch.object(ko_hud,'font_metrics',return_value=(7,14,5)):
        ko_hud.cook(Fixture(),root/'hud.bin',150,20)
    r=Reader((root/'hud.bin').read_bytes())
    assert r.take(4)==b'N3HB' and r.take(4)==(1).to_bytes(4,'little')
    r.take(12)
    for _ in range(r.integer()):
        w,h=r.unpack('2I'); r.take(w*h*4)
    assert r.floats(1)==[7] and r.unpack('2I')==[14,5]
    controls=[r.unpack('4I') for _ in range(r.integer())]
    assert [c[1] for c in controls[:7]]==[0,2,3,0,1,0,1]
    assert controls[0][2]==2 and controls[1][2]==controls[2][2]==3
    assert controls[-1][2]==1
    seen=set()
    for _ in range(r.integer()):
        kind=r.integer();r.take(24);r.take(4+16)
        binding=r.string();text=r.string();r.take(12)
        cid,states,flags=r.unpack('3I')
        assert flags==(5 if kind==1 else 0)
        if kind==1 and text:
            assert cid in range(1,8)
            assert text.startswith(names[cid-1]) and states==1<<int(text[-1])
            seen.add((cid,states))
        if kind==2:assert states==15
        assert cid != 0 # An empty hotkey area must not inject an icon or attack hit region.
    r.end()
    assert len(seen)==28 # Every state's label inherits its owning control and state.
    # Original layout fixture: correction moves hits and all state descendants
    # together, retaining their spacing and leaving the background untouched.
    background=dict(rect=[0,0,51,348],children=[],id='background')
    buttons=[]
    for ident,x in [('btn_up',5),('btn_down',27)]:
        buttons.append(dict(id=ident,rect=[x,333,x+19,345],click=[x,333,x+19,345],
            children=[dict(rect=[x,333,x+19,345],children=[]) for _ in range(4)]))
    ko_hud.align_hotkey_buttons(dict(children=[background,*buttons]))
    assert background['rect']==[0,0,51,348]
    for button,x in zip(buttons,[6,28]):
        assert button['rect']==button['click']==[x,330,x+19,342]
        assert all(c['rect']==button['rect'] for c in button['children'])
    cook(root,out);check()
    verify_basic_overview(root,out,cook,check,node)
    verify_message_block(root,out,cook,check,node)
    verify_message_scroll(root,out,cook,check)
    # H4 adds one panel word per record. Exercise independent native rejection,
    # including a legal legacy HUD upgraded without importing proprietary bytes.
    # The importer cooks N3HB; dropping its policy word yields the equivalent H3 layout.
    src=(root/'hud.bin').read_bytes();assert src[:8]==b'N3HB'+u(1);src=b'N3H3'+src[8:];r=Reader(src);r.take(4);r.take(12)
    for _ in range(r.integer()):
        w,h=r.unpack('2I');r.take(w*h*4)
    r.take(12)
    for _ in range(r.integer()):r.take(16)
    nr=r.integer();header=r.at
    chunks=[]
    for _ in range(nr):
        begin=r.at
        r.take(4+8+16+4+16);r.string();r.string();r.take(24)
        end=r.at
        chunks.append(src[begin:end]+u(1))
    valid=b'N3H4'+src[4:header]+b''.join(chunks)
    (root/'hud.bin').write_bytes(valid);cook(root,out);check()
    (root/'hud.bin').write_bytes(valid[:-4]+u(9));cook(root,out);check(False)
    (root/'hud.bin').write_bytes(valid[:-1]);cook(root,out);check(False)
    (root/'hud.bin').write_bytes(valid);cook(root,out);check()
    def field(kind,binding,key):
        return u(kind)+f([0,0,0,0,100,20])+u(0)+f([0,0,1,1])+string(binding)+string(key)+u(0xffffffff)+u(0)+u(0)+u(0)+u(15)+u(0)+u(1)
    one=b'N3H4'+src[4:header-4]+u(1)
    for kind,binding,key,good in [(1,'value','coins',True),(1,'value','../secret',False),(1,'action','confirm',False),(2,'action','confirm',True),(2,'command','delete',False)]:
        (root/'hud.bin').write_bytes(one+field(kind,binding,key));cook(root,out);check(good)
    (root/'hud.bin').write_bytes(valid);cook(root,out);check()
    print('PASS original H4 dialog producer/native reader and panel/key/kind/truncation rejection')
    print('PASS original UIF hidden alternatives, all four state subtrees and selected checkbox cook/read')
    from hud_icons import verify as verify_icons
    verify_icons(root,out,cook,check,one[:-4],field)


def verify_basic_overview(root,out,cook,check,node):
    """PQ-217: N3HE, the basic layout with a panel word per record and the overview map."""
    import ko_tiles_fixture
    basic=(root/'hud.bin').read_bytes()
    class Fixture:
        def get(self,path):
            if path=='synthetic.dxt':
                return string('')+b'NTF\x03'+struct.pack('<4i',4,4,26,0)+struct.pack('<16H',*([0xffff]*16))
            if path=='Zones/orig_map.dxt':return ko_tiles_fixture.texture(16,16)
            if path.endswith('ka_statebar_us.uif'):
                group=node(0,'group_minimap',[node(4,'img_minimap'),node(4,'frame_minimap'),
                                              node(1,'btn_zoomin',[node(4,slot=s) for s in range(4)])])
                return node(0,children=[node(4,'statebar_art'),group])[1]
            if path.endswith('ka_cmd_us.uif'):
                return node(0,children=[node(1,'btn_map',[node(4,slot=s) for s in range(4)])])[1]
            return node(0)[1]
    minimap=dict(path='Zones/orig_map.dxt',origin=[-1024.0,-1024.0],extent=2048.0)
    with patch.object(ko_hud.subprocess,'check_output',return_value=bytes(256*128*4)), patch.object(ko_hud,'font_metrics',return_value=(7,14,5)):
        report=ko_hud.cook(Fixture(),root/'hud.bin',150,20,minimap=minimap)
    assert report['minimap']==minimap and not any('minimap' in o for o in report['omitted'])
    data=(root/'hud.bin').read_bytes()
    r=Reader(data)
    assert r.take(4)==b'N3HE' and r.take(4)==(1).to_bytes(4,'little')
    r.take(12)
    for _ in range(r.integer()):
        w,h=r.unpack('2I');r.take(w*h*4)
    r.take(12)
    for _ in range(r.integer()):r.take(16)
    records=[]
    for _ in range(r.integer()):
        kind=r.integer();r.take(24);texture=r.integer();r.take(16)
        binding=r.string();r.string();r.take(24)
        records.append(dict(kind=kind,texture=texture,binding=binding,panel_at=r.at,panel=r.integer()))
    texture=r.integer();assert r.floats(2)==[-1024.0,-1024.0] and r.floats(5)[0]==2048.0
    r.take(20);r.end()
    image=[q for q in records if q['binding']=='minimap']
    toggle=[q for q in records if q['binding']=='toggle_minimap']
    assert len(image)==1 and image[0]['panel']==15 and image[0]['texture']==texture and image[0]['kind']==0
    # The overview's group (frame, inert zoom artwork) is panel 15; the command-bar
    # button that toggles it (00549210) and the rest of the HUD are panel 0.
    assert len(toggle)==1 and toggle[0]['kind']==2 and toggle[0]['panel']==0
    assert {q['panel'] for q in records}=={0,15} and sum(q['panel']==15 for q in records)>=3
    def at(record,value):
        return data[:record['panel_at']]+u(value)+data[record['panel_at']+4:]
    def run(blob,good):
        (root/'hud.bin').write_bytes(blob);cook(root,out);check(good)
    run(data,True)
    other=next(q for q in records if q['binding']=='' and q['panel']==0)
    for bad in [at(image[0],0),at(image[0],14),at(other,3),at(other,16),
                data[:-1],data+b'\0',b'N3HB'+data[4:],b'N3HD'+data[4:]]:
        run(bad,False)
    run(at(other,15),True)  # extra artwork may join the overview's panel
    run(basic,True)
    print('PASS HE basic overview map: cooked panel words (overview group 15, the rest 0), one panel-15 '
          'minimap image on the block texture; wrong panel, truncation and magic rejected')


def verify_message_block(root,out,cook,check,node):
    """PQ-407 (D-210): the message output window's log rows and colours (N3HM)."""
    basic=(root/'hud.bin').read_bytes()
    def text_message(rect):
        data=string('')+struct.pack('<hh',0,1)+string('text_message')
        data+=struct.pack('<8i2I',*rect,0,0,0,0,0,0)+string('')*3
        data+=string('')+u(0xffffffff)+string('')+u(0)
        return 6,data
    class Fixture:
        def get(self,path):
            if path=='synthetic.dxt':
                return string('')+b'NTF\x03'+struct.pack('<4i',4,4,26,0)+struct.pack('<16H',*([0xffff]*16))
            if path.endswith('ka_msgoutput_us.uif'):
                root_node=string('')+struct.pack('<hh',1,1)+u(6)+text_message([4,1,298,122])[1]
                return root_node+string('')+struct.pack('<8i2I',0,0,323,145,0,0,0,0,0,0)+string('')*3
            return node(0)[1]
    with patch.object(ko_hud.subprocess,'check_output',return_value=bytes(256*128*4)), patch.object(ko_hud,'font_metrics',return_value=(7,14,5)):
        report=ko_hud.cook(Fixture(),root/'hud.bin',150,20)
    data=(root/'hud.bin').read_bytes()
    # 0052aa10: 121 / 14 = 8 rows in text_message, less n3e's three status rows.
    assert report['message_rows']==5 and data.endswith(b'N3HM'+u(5)+u(0xffff_ff00)+u(0xffff_ff00)), report['message_rows']
    def run(blob,good):
        (root/'hud.bin').write_bytes(blob);cook(root,out);check(good)
    run(data,True)
    body=data[:-16]
    for rows,tag,tail,good in [(1,b'N3HM',b'',True),(16,b'N3HM',b'',True),(0,b'N3HM',b'',False),(17,b'N3HM',b'',False),
                               (5,b'N3HX',b'',False),(5,b'N3HM',b'\0',False),(5,b'N3HM',u(0),False)]:
        run(body+tag+u(rows)+u(0xffff_ff00)+u(0xff00_00ff)+tail,good)
    run(data[:-1],False)
    # A block needs the line it colours: the basic fixture has no text_message.
    run(basic+b'N3HM'+u(5)+u(0xffff_ff00)*2,False)
    run(basic,True)
    print('PASS N3HM message block: rows from text_message by the line height less three status rows, '
          'yellow for both kinds; row bounds, tag, trailing data, truncation and a HUD without a message line rejected')


def verify_message_scroll(root,out,cook,check):
    """PQ-408 (D-211): the message window's scroll bar records and limits (N3HS)."""
    basic=(root/'hud.bin').read_bytes()
    def gnode(kind,ident='',children=(),rect=(0,0,32,16),reserved=0,style=0):
        data=string('')+struct.pack('<hh',len(children),1)+b''.join(u(k)+v for k,v in children)
        data+=string(ident)+struct.pack('<8i2I',*rect,0,0,0,0,style,reserved)+string('')*3
        if kind==4:data+=string('synthetic.dxt')+f([0,0,1,1,0])
        if kind==6:data+=string('')+u(0xffffffff)+string('')+u(0)
        if kind==1:data+=struct.pack('<4i',*rect)+string('')*2
        return kind,data
    def window(thumb=(300,19,318,37),with_thumb=True):
        track=[gnode(4,rect=(300,19,318,103),reserved=0)]+([gnode(4,rect=thumb,reserved=1)] if with_thumb else [])
        scroll=gnode(5,'scroll',[gnode(1,children=[gnode(4,rect=(300,2,318,20))],rect=(300,2,318,20),reserved=0,style=0x10000),
                                 gnode(1,children=[gnode(4,rect=(300,104,318,122))],rect=(300,104,318,122),reserved=1,style=0x10000),
                                 gnode(7,children=track,rect=(300,19,318,103),style=0x20000)],rect=(300,2,319,121),style=0x20000)
        return gnode(0,children=[gnode(6,'text_message',rect=(4,1,298,122)),scroll],rect=(0,0,323,145))[1]
    def cooked(uif):
        class Fixture:
            def get(self,path):
                if path=='synthetic.dxt':
                    return string('')+b'NTF\x03'+struct.pack('<4i',4,4,26,0)+struct.pack('<16H',*([0xffff]*16))
                if path.endswith('ka_msgoutput_us.uif'):return uif
                return gnode(0)[1]
        with patch.object(ko_hud.subprocess,'check_output',return_value=bytes(256*128*4)), patch.object(ko_hud,'font_metrics',return_value=(7,14,5)):
            report=ko_hud.cook(Fixture(),root/'hud.bin',150,20)
        return report,(root/'hud.bin').read_bytes()
    report,data=cooked(window())
    block=b'N3HS'+u(255)+u(100)+u(1)+u(2)+f([0.5])
    assert report['message_scroll'] and data.endswith(b'N3HM'+u(5)+u(0xffff_ff00)*2+block), report
    # The records: the buttons' click regions, the track's and the thumb image.
    r=Reader(data);r.take(4+4+4+8)
    for _ in range(r.integer()):
        w,h=r.unpack('2I');r.take(w*h*4)
    r.take(12)
    for _ in range(r.integer()):r.take(16)
    bound={}
    for _ in range(r.integer()):
        kind=r.integer();r.take(8);rect=r.floats(4);r.take(4+16)
        binding=r.string();r.string();r.take(12+12)
        if binding.startswith('message_'):bound.setdefault(binding,[]).append((kind,rect))
    # The message window sits at (chat width, ...): only the rectangles' sizes and order matter here.
    assert sorted(bound)==['message_down','message_thumb','message_track','message_up'] and all(len(v)==1 for v in bound.values()), bound
    (kt,track),(kh,thumb)=bound['message_track'][0],bound['message_thumb'][0]
    assert kt==2 and kh==0 and bound['message_up'][0][0]==bound['message_down'][0][0]==2
    assert track[3]-track[1]==84 and thumb[3]-thumb[1]==18 and thumb[1]==track[1], (track,thumb)
    def run(blob,good):
        (root/'hud.bin').write_bytes(blob);cook(root,out);check(good)
    run(data,True)
    body=data[:-len(block)]
    run(body,False)  # scroll records without their block
    for records,lines,step,page,repeat,good in [(1024,5,64,64,10,True),(1,4096,1,1,0.01,True),(0,100,1,2,.5,False),
                                                (1025,100,1,2,.5,False),(255,4,1,2,.5,False),(255,4097,1,2,.5,False),
                                                (255,100,0,2,.5,False),(255,100,65,2,.5,False),(255,100,1,0,.5,False),
                                                (255,100,1,65,.5,False),(255,100,1,2,0,False),(255,100,1,2,10.5,False)]:
        run(body+b'N3HS'+u(records)+u(lines)+u(step)+u(page)+f([repeat]),good)
    run(body+b'N3HX'+block[4:],False)
    run(data+b'\0',False)
    run(data[:-1],False)
    # The thumb must lie in the track and be shorter than it.
    run(cooked(window(thumb=(300,10,318,30)))[1],False)
    run(cooked(window(thumb=(300,19,318,103)))[1],False)
    run(cooked(window(thumb=(300,85,318,103)))[1],True)
    try:
        cooked(window(with_thumb=False));raise AssertionError('a scroll bar without a thumb cooked')
    except ValueError as e:assert str(e)=='HUD message scroll bar',e
    run(basic,True)
    print('PASS N3HS message scroll: the scroll child\'s buttons, track and thumb bound, 255 records, 100 lines, '
          'steps 1 and 2, 0.5 s; limits, tag, trailing data, truncation, a block-less scroll bar, a thumb outside or '
          'filling the track and a scroll bar without a thumb rejected')
