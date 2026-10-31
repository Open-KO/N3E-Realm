"""Independent bounded UIF 1264 / NTF3 HUD conversion; local outputs only."""
import pathlib
import hashlib
import struct
import subprocess
import re
from common import count, f, u, string
from ko_character import Reader


def parse(data):
    r = Reader(data)
    total = 0
    def node(kind=0, depth=0):
        nonlocal total
        total += 1
        if depth > 24 or total > 2048:
            raise ValueError("UI tree bound")
        name = r.string()
        children_count, reserved_header = r.unpack("2h")
        if reserved_header not in (0, 1):
            raise ValueError("UI version header")
        children = [node(r.integer(), depth+1) for _ in range(count(children_count, 1024, 0))]
        ident = r.string()
        rect = r.unpack("4i")
        if any(abs(v)>16384 for v in rect) or rect[2]<rect[0] or rect[3]<rect[1]:
            raise ValueError("UI rectangle")
        # 00401880: the movable (drag) rectangle follows the region; empty = fixed.
        move = r.unpack("4i")
        style, reserved = r.unpack("2I")
        r.string(); r.string(); r.string()
        n = dict(kind=kind, id=ident, rect=rect, move=move, style=style, reserved=reserved, children=children)
        if kind == 4:
            n.update(texture=r.string(), uv=r.floats(4), fps=r.floats(1)[0])
            if any(v<0 or v>1 for v in n['uv']):
                raise ValueError("UI UV")
        elif kind == 6:
            n['font'] = r.string()
            if n['font']:
                n['font_size'], n['font_flags'] = r.unpack('2I')
            n['color'] = r.unpack('I')[0]
            n['text'] = r.string()
            count(r.integer(), 128, 0)
        elif kind == 1:
            n['click'] = r.unpack('4i')
            n['hover_sound'], n['click_sound'] = r.string(), r.string()
        elif kind in (2, 8):
            r.string()
            if kind == 8: r.string()
        elif kind == 9:
            n['area'] = r.integer()
        elif kind == 14:
            # Binary 0040b970: base tree, font name, height/color/bold/italic.
            n["font"] = r.string()
            if n["font"]: n["list_font"] = r.unpack("4I")
        elif kind not in (0, 3, 5, 7):
            raise ValueError("unsupported UI type")
        return n
    root = node()
    r.end()
    return root


def texture(data):
    r=Reader(data);r.string()
    if r.take(4)!=b'NTF\x03': raise ValueError('HUD NTF version')
    w,h,fmt,mips=r.unpack('4i')
    if fmt in (21,22):
        # A8R8G8B8 / X8R8G8B8 (the 2145 UI pack's item icons, PQ-338): 4 bytes a
        # texel, rows of width x 4 (1298 0043f090 at 0043f29b-0043f2a0, 2233
        # 00463180 at 00463459-0046345e). n3e reads them unmipmapped and at
        # most 256 x 256 only; X8 has no alpha (Direct3D samples it as 1).
        if any(n<4 or n>256 or n&(n-1) for n in (w,h)) or mips!=0:
            raise ValueError('HUD texture subset')
        raw=r.take(w*h*4);r.end()
        rgba=bytearray()
        for i in range(0,len(raw),4):
            rgba.extend((raw[i+2],raw[i+1],raw[i],raw[i+3] if fmt==21 else 255))
        return w,h,bytes(rgba)
    if any(n<4 or n>1024 or n&(n-1) for n in (w,h)) or fmt not in (25,26) or mips not in (0,1):
        raise ValueError('HUD texture subset')
    pixels=r.unpack(str(w*h)+'H')
    if mips:
        x,y=w//2,h//2
        while x>=4 and y>=4:r.take(x*y*2);x//=2;y//=2
    elif w>=512:r.take(256*256*2)
    r.end()
    rgba=bytearray()
    for p in pixels:
        if fmt==26:rgba.extend(((p>>8&15)*17,(p>>4&15)*17,(p&15)*17,(p>>12)*17))
        else:rgba.extend(((p>>10&31)*255//31,(p>>5&31)*255//31,(p&31)*255//31,255 if p&32768 else 0))
    return w,h,bytes(rgba)


def align_hotkey_buttons(root):
    """Repair the known local UIF/background registration bug, not a KO rule.

    The normal glyphs match background positions (6,330) and (28,330).
    Move the whole control, including every state image and its hit region.
    Only cook's exact input hash enables this correction.
    """
    def move(n):
        for field in ('rect', 'click'):
            if field in n:
                l,t,r,b=n[field]; n[field]=[l+1,t-3,r+1,b-3]
        for child in n['children']: move(child)
    for ident, expected in [('btn_up',[5,333,24,345]), ('btn_down',[27,333,46,345])]:
        button=next(n for n in root['children'] if n['id'].lower()==ident)
        if button['rect'] != expected or button['click'] != expected:
            raise ValueError('known hotkey layout changed')
        move(button)


def font_metrics(font):
    # This atlas is explicitly monospaced. Measure the actual rasterizer/font,
    # rather than estimating width from a fractional constant in the client.
    result=subprocess.run(['magick','-debug','annotate','-font',str(font),
        '-pointsize','12','label:M','null:'],capture_output=True,text=True,check=True)
    metrics=re.search(r'Metrics: text: M; width: [0-9.]+; height: ([0-9.]+); ascent: ([0-9.]+);[^\n]*origin: ([0-9.]+),',result.stderr)
    if not metrics: raise ValueError('font metrics unavailable')
    height,ascent=(round(float(v)) for v in metrics.groups()[:2])
    # Advance is not the ink bounding-box width. Preserve the rasterizer's
    # 26.6 advance so whole-string extents do not accumulate rounding error.
    advance=round(float(metrics.group(3))*64)/64
    top=15-ascent # The existing glyph cells have baseline y=15.
    if not (1<=advance<=16 and 1<=height<=20 and 0<=top and top+height<=20):
        raise ValueError('font metrics exceed atlas cell')
    return advance,height,top


def cook(assets, out, npc_health, level_xp, features=False, minimap=None, minimap_assets=None, npc_scale=1.0,
         item_icons=None, equipment_slots=None):
    # `item_icons`: the package's item icon map when it is not ui.json's (the
    # --glow-2233 package's own, PQ-321); the default cooks pass none.
    # `equipment_slots`: likewise the inventory window's equipment areas
    # ({area id: package slot}) when not ui.json's (that package's armour
    # slots, PQ-319).
    # Source panel layouts at the supplied client's default origins (005d23d0).
    # SetPos moves a root's top-left, so offsets subtract the root origin.
    roots={name:parse(assets.get('UI_US/'+name+'.uif'))['rect'] for name in ('ka_statebar_us','ka_hotkey_us','ka_cmd_us','ka_chat_us','ka_msgoutput_us','co_targetbar_us')}
    size=lambda name:(roots[name][2]-roots[name][0],roots[name][3]-roots[name][1])
    at=lambda name,x,y:(x-roots[name][0],y-roots[name][1])
    # Command bar ((W-w)/2, H-h) at 005d2498; chat (0, H+5-cmdH-chatH) at
    # 005d24bf then MoveOffset(0,-1); msgoutput follows chat to (chat.right,
    # chat.top) through 00544370; hotkey defaults to (statebar.left,
    # statebar.bottom) at 005d30e5; target bar is top-centre.
    chat_y=5-size('ka_cmd_us')[1]-size('ka_chat_us')[1]-1
    panels=[('ka_statebar_us',0,0,*at('ka_statebar_us',0,0),0),
            ('ka_hotkey_us',0,0,*at('ka_hotkey_us',roots['ka_statebar_us'][0],roots['ka_statebar_us'][3]),13 if features else 0),
            ('ka_cmd_us',.5,1,*at('ka_cmd_us',-(size('ka_cmd_us')[0]//2),-size('ka_cmd_us')[1]),0),
            ('ka_chat_us',0,1,*at('ka_chat_us',0,chat_y),11 if features else 0),
            ('ka_msgoutput_us',0,1,*at('ka_msgoutput_us',size('ka_chat_us')[0],chat_y),12 if features else 0),
            ('co_targetbar_us',.5,0,*at('co_targetbar_us',-(size('co_targetbar_us')[0]//2),0),0)]
    textures=[]; ids={};records=[];controls=[];sounds={}
    def tex(path, source=None):
        # `source`: the overview map's own client data when the map is not the
        # HUD's (minimap_assets, PQ-274).
        key=path.replace('\\','/').lower()
        # A source with a `namespace` (the 2145 UI pack, PQ-338) keeps its
        # textures apart from the client's files of the same name.
        if getattr(source,'namespace',None):key=source.namespace+':'+key
        if key not in ids:
            ids[key]=len(textures)
            if key.startswith('misc/recastobject/') or key.startswith('zones/'):
                import ko_tiles
                textures.append(ko_tiles.texture((source or assets).get(path)))
            else:textures.append(texture((source or assets).get(path)))
        return ids[key]
    panel_id=0
    def add(kind, anchor, rect, texture=0, uv=(0,0,1,1), binding='', text='', color=0xffffffff, target=0, align=0, control=0, states=15, text_flags=0,panel=None):
        records.append((kind,anchor,rect,texture,uv,binding,text,color,target,align,control,states,text_flags,panel_id if panel is None else panel))
    movables=[]
    for filename,ax,ay,ox,oy,panel_id in panels:
        target=int(filename=='co_targetbar_us')
        source=assets.get('UI_US/'+filename+'.uif')
        root=parse(source)
        if filename=='ka_hotkey_us' and hashlib.sha256(source).hexdigest() == '2ce4ffcd08eb7dfe07f72c3c45b3a5b7f9654109cd1848158947cf5e5e3aefef':
            # Local-asset correction; binary 00403fc0 loads the mismatched rects unchanged.
            align_hotkey_buttons(root)
        hotbar_slots=[];hotbar_counts=[]
        # PQ-408 (D-211): the message window's `scroll` child (006d5b3c) is a
        # scroll bar: buttons by reserved 0 (up) and 1 (down) (0040d000,
        # 0040d090), and a track bar whose image reserved 1 is the thumb
        # (00410240). They become the message line's scroll records.
        roles={}
        if filename=='ka_msgoutput_us':
            for child in root['children']:
                if child['kind']==5 and child['id'].lower()=='scroll':
                    for part in child['children']:
                        if part['kind']==1 and part['reserved'] in (0,1):
                            roles[id(part)]=('message_up','message_down')[part['reserved']]
                        if part['kind']==7:
                            roles[id(part)]='message_track'
                            for image in part['children']:
                                if image['kind']==4 and image['reserved']==1:roles[id(image)]='message_thumb'
        def walk(n, progress='', control=0, states=15):
            nonlocal panel_id
            ident=n['id'].lower()
            if ident=='group_minimap' and minimap:
                # The state bar's overview map group (00561d70) on toggled panel 15.
                outer=panel_id;panel_id=15
                for child in n['children']:walk(child,progress,control,states)
                panel_id=outer
                return
            if ident=='img_minimap' and minimap:
                # The zone overview fills Img_MiniMap (00562b60, Zones column 8).
                rect=[n['rect'][0]+ox,n['rect'][1]+oy,n['rect'][2]+ox,n['rect'][3]+oy]
                add(0,(ax,ay),rect,tex(minimap['path'],minimap_assets),(0,0,1,1),'minimap')
                return
            if ident in ('group_minimap','progress_hp_slow','progress_hp_drop','progress_hp_lasting','text_version','string_fps','systemtime'):
                return
            rect=[n['rect'][0]+ox,n['rect'][1]+oy,n['rect'][2]+ox,n['rect'][3]+oy]
            kind=n['kind']
            if kind==1:
                # Binary: 00548980 hides Stand; 00549730 selects Invite for an
                # ungrouped player. Sitting/party/clan membership are not yet supported.
                visibility = {'btn_stand':1, 'btn_disband':1, 'btn_knights':1,
                              'btn_walk':2, 'btn_run':3}.get(ident, 0)
                action = {'btn_map':'toggle_minimap'} .get(ident) if minimap else None
                action = action or roles.get(id(n)) or {'btn_exit':'exit', 'btn_inventory':'inventory',
                          'btn_chat':'chat', 'btn_attack':'strike',
                          'btn_walk':'walk', 'btn_run':'run'}.get(ident, 'unavailable')
                if features:
                    visibility={'btn_sit':4,'btn_stand':5}.get(ident,visibility)
                    action={'btn_sit':'rest','btn_stand':'rest','btn_skill':'skills','btn_character':'equipment','btn_invite':'party','btn_control':'features'}.get(ident,action)
                # 00403bc0 selects normal/down/on/disabled image by runtime state.
                # 005429b0 initializes chat filter checkboxes to down (selected).
                selection = 1 if ident.startswith('btn_check_') else 2 if ident=='btn_attack' else 3 if ident in ('btn_walk','btn_run') else 0
                # Unsupported actions retain the existing unavailable feedback;
                # lack of n3e gameplay support is not a KO disabled-state rule.
                enabled = 1
                if states != 15:
                    raise ValueError('nested button inside state artwork')
                controls.append((control, visibility, selection, enabled))
                control = len(controls)
                sounds[control] = [n['hover_sound'],n['click_sound']]
            if kind==3:
                progress={'progress_hp':'health','progress_msp':'resource','progress_expp':'xp','progress_expc':'xp','pro_target':'target_health'}.get(ident,'')
            if kind==7 and roles.get(id(n))=='message_track':
                add(2,(ax,ay),rect,binding='message_track',target=target,control=control)
            if kind==4:
                if n['texture']:
                    add(0,(ax,ay),rect,tex(n['texture']),n['uv'],roles.get(id(n)) or (progress if n['reserved']==1 else ''),target=target,control=control,states=states)
            if kind==6:
                single=bool(n['style'] & 0x00100000)
                text_flags=(1 | (2 if n['style'] & 0x02000000 else 4 if n['style'] & 0x04000000 else 0)) if single else 0
                binding={'text_hp':'health_text','text_msp':'resource_text','text_expp':'xp_text','text_position':'position',
                         'text_target':'target_name','text_message':'combat','text_chat':'chat','edit_chat':'chat_input','text0':'chat'}.get(ident,'')
                text=n.get('text','')
                if filename=='ka_hotkey_us' and ident.isdigit():
                    # Binary 004de550 hides tooltip/count controls before rendering.
                    # Leave empty until a package supplies actual hover/count state.
                    text=''
                    if features and int(ident)<8:
                        hotbar_counts.append((rect,'count:hotbar:'+ident,n.get('color',0xffffffff),2 if n['style']&0x00800000 else 1 if n['style']&0x00400000 else 0,text_flags));binding='';text=''
                if binding or text:
                    add(1,(ax,ay),rect,binding=binding,text=text,color=n.get('color',0xffffffff),target=target,align=2 if n['style']&0x00800000 else 1 if n['style']&0x00400000 else 0,control=control,states=states,text_flags=text_flags)
            if features and filename=='ka_hotkey_us' and kind==9 and n['area']==8:
                key='hotbar:'+ident
                hotbar_slots.append((rect,key))
            if kind==8:
                add(1,(ax,ay),rect,binding='chat_input',control=control,states=states)
                add(2,(ax,ay),rect,binding='chat',control=control)
            # Zoom buttons have no handler in this build (inert): artwork only.
            if kind==1 and not (minimap and ident in ('btn_zoomin','btn_zoomout')):
                click=n['click'];click=[click[0]+ox,click[1]+oy,click[2]+ox,click[3]+oy]
                add(2,(ax,ay),click,binding='action' if features and filename=='ka_hotkey_us' else action,text=('hotbar_prev' if ident=='btn_up' else 'hotbar_next') if features and filename=='ka_hotkey_us' else '',target=target,control=control)
            # Missing state images stay absent, matching 00403bc0's null checks.
            for child in n['children']:
                child_states = states
                if kind==1 and child['kind']==4:
                    slot = child['reserved']
                    if slot > 3:
                        raise ValueError('button image state')
                    child_states = 1 << slot
                walk(child,progress,control,child_states)
        walk(root)
        # Draggable panels (non-empty UIF movable rect). Chat and msgoutput move
        # as a rigid pair (00544370/0052a4c0); only chat and hotkey positions
        # are saved (00645ea0); the hotkey snaps to side edges within 10 px
        # (004ddc20).
        move=root['move']
        if features and move[2]>move[0] and move[3]>move[1]:
            group,key,snap={'ka_chat_us':(1,'chat',0),'ka_msgoutput_us':(1,'',0),'ka_hotkey_us':(2,'hotkey',10)}[filename]
            shift=lambda r:[r[0]+ox,r[1]+oy,r[2]+ox,r[3]+oy]
            movables.append((panel_id,group,(ax,ay),shift(move),shift(root['rect']),snap,key))
        for rect,key in hotbar_slots:
            add(0,(ax,ay),rect,binding='item',text=key)
            add(2,(ax,ay),rect,binding='action',text=key)
        for rect,key,color,align,flags in hotbar_counts:add(1,(ax,ay),rect,binding='value',text=key,color=color,align=align,text_flags=flags)
    dialogs=[];icons=[];icon_sources=[];portraits={}
    if features:
        import ko_dialogs
        dialogs,icons,icon_sources,portraits,tooltip=ko_dialogs.append(assets,parse,tex,add,controls,sounds,item_icons,
                                                                      equipment_slots)
        # The party window is draggable but not saved (no Wnd_Party in the exe);
        # ko_dialogs places Co_Party at (W-w, 40) on panel 6.
        party=parse(assets.get('UI_US/Co_Party_us.uif'));pw=party['rect'][2]-party['rect'][0]
        shift=lambda r:[r[0]-party['rect'][0]-pw,r[1]-party['rect'][1]+40,r[2]-party['rect'][0]-pw,r[3]-party['rect'][1]+40]
        movables.append((6,3,(1,0),shift(party['move']),shift(party['rect']),0,''))
    action_icons=[];cooldown_frames=[]
    if features:
        for item,skill in [('demo:item/potion',490011),('demo:item/mana_potion',490016),('demo:skill/tiny_healing',204001),('demo:skill/light_strike',204002)]:
            action_icons.append((item,tex(f'UI/skillicon_{skill%100:02}_{skill//100}.dxt'),(0,0,1,1)))
        for i in range(3):
            ix=tex(f'Misc/RecastObject/64shot000{i}.dxt')
            w,h,pixels=textures[ix];pixels=bytearray(pixels)
            for j in range(3,len(pixels),4):pixels[j]=round(pixels[j]*100/255)
            textures[ix]=(w,h,bytes(pixels));cooldown_frames.append(ix)
    # Local font substitute for Windows UI strings; source HUD artwork is unchanged.
    font=pathlib.Path('/usr/share/fonts/liberation/LiberationMono-Regular.ttf')
    args=['magick','-size','256x128','xc:none','-font',str(font),'-pointsize','12','-fill','white']
    for code in range(32,127):
        x=(code-32)%16*16;y=(code-32)//16*20
        char=chr(code)
        if char == chr(92): char = chr(92)*2
        args += ['-annotate',f'+{x}+{y+15}',char]
    raw=subprocess.check_output(args+['-depth','8','rgba:-'])
    if len(raw)!=256*128*4:raise ValueError('font raster size')
    font_index=len(textures);textures.append((256,128,raw))
    names=b'';name_report=None
    if features:
        import ko_nameplates
        # PQ-288: the NPC name height at the package NPC's drawn size.
        names,name_report=ko_nameplates.cook(assets,textures,npc_scale)
    # KnightOnLine.exe draws UI at authored pixel size in every viewport mode and only
    # re-anchors panels (SetPos 00401660, SetPosCenter 00401690, fonts 00429700), so
    # every imported HUD declares the pixel scale policy (1): N3HA over the feature
    # layout, N3HB over the basic one.
    # N3HE (PQ-217) is the basic N3HB layout with a panel word per record and the
    # same overview map block as N3HD, for a zone package without feature dialogs.
    data=(b'N3HD' if minimap and features else b'N3HE' if minimap else b'N3HC' if features else b'N3HB')+u(1)+u(font_index)+f([npc_health,level_xp])+u(count(len(textures),64 if features else 16))
    for w,h,pixels in textures:data+=u(w)+u(h)+pixels
    metrics=font_metrics(font)
    data+=f([metrics[0]])+u(metrics[1])+u(metrics[2])
    data+=u(count(len(controls),512 if features else 256,0))
    for c in controls:
        data+=b''.join(u(v) for v in c)
    data+=u(len(records))
    for kind,anchor,rect,texture_index,uv,binding,text,color,target,align,control,states,text_flags,panel in records:
        data+=u(kind)+f(anchor)+f(rect)+u(texture_index)+f(uv)+string(binding)+string(text)+u(color)+u(target)+u(align)+u(control)+u(states)+u(text_flags)
        if features or minimap:data+=u(panel)
    if features:
        import ko_item_icons
        data+=ko_item_icons.encode(icons)
        data+=u(count(len(portraits),8,0))
        for key,view in portraits.items():
            if not key or len(key)>64 or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in key):raise ValueError("portrait key")
            yaw,pitch,framing=(view[k] for k in ("yaw","pitch","framing"))
            if not (-180<=yaw<=180 and -80<=pitch<=80 and 1<=framing<=4):raise ValueError("portrait view")
            data+=string(key)+f([yaw,pitch,framing])
    if features:
        data+=u(tooltip['texture'])+f(tooltip['uv'])+f([42,14,26])+u(len(tooltip['rows']))
        for row in tooltip['rows']:data+=f(row)
    if features:
        data+=ko_item_icons.encode(action_icons)+u(0x8cf46161)+b''.join(u(i) for i in cooldown_frames)
        data+=names
        data+=u(count(len(movables),8,0))
        for panel,group,anchor,handle,bounds,snap,key in movables:
            data+=u(panel)+u(group)+f(anchor)+f(handle)+f(bounds)+u(snap)+string(key)
    if minimap:
        # 00563ed0/00563240/005daba0: zoom 6, arrow height/30, 2/1 px markers;
        # colours self, hostile NPC, other NPC, party, other player.
        data+=u(tex(minimap['path'],minimap_assets))+f(minimap['origin'])+f([minimap['extent'],6,1/30,2,1])
        data+=b''.join(u(c) for c in (0xff00ff00,0xff800000,0xff00a0ff,0xffffff00,0xff0040ff))
    # PQ-407 (D-210): the message output window's log. 0052aa10 cuts
    # text_message into (height / line height) single-line rows; n3e's combat
    # status, item and reward lines take the last three, the messages the rest.
    # 1298 writes a refusal there in 0xffffff00 from the server (005c5da8,
    # 005c5df2) and from the client (005c7aa4, 005c7b41); both kinds take it.
    message_rows=0;message_scroll=False
    message=[r for r in records if r[0]==1 and r[5]=='combat']
    if message:
        if len(message)!=1:raise ValueError('HUD message line count')
        left,top,right,bottom=message[0][2]
        message_rows=max(1,min(16,(bottom-top)//metrics[1]-3))
        data+=b'N3HM'+u(message_rows)+u(0xffffff00)+u(0xffffff00)
        # PQ-408 (D-211): 0052acd0 keeps 255 records and drops wrapped lines
        # past 100; the scroll bar steps 1 (0040cf00), the track bar pages 2
        # (00410120) and a held button repeats after 0.5 s (00403c80, 006a35e0).
        scroll=[r[5] for r in records if r[5] in ('message_up','message_down','message_track','message_thumb')]
        if scroll:
            if sorted(scroll)!=['message_down','message_thumb','message_track','message_up']:raise ValueError('HUD message scroll bar')
            data+=b'N3HS'+u(255)+u(100)+u(1)+u(2)+f([0.5])
            message_scroll=True
    out.write_bytes(data)
    return dict(minimap=minimap,message_rows=message_rows,message_scroll=message_scroll,movable_panels=[dict(panel=m[0],group=m[1],anchor=m[2],handle=m[3],bounds=m[4],snap=m[5],key=m[6]) for m in movables],sounds=sounds,dialogs=dialogs,item_icons=icon_sources,nameplates=name_report,panels=[p[0] for p in panels],quad_records=len(records),controls=len(controls),textures=len(textures),
                font_metrics=dict(advance=metrics[0],height=metrics[1],top=metrics[2]),font_substitute=str(font),font_sha256=hashlib.sha256(font.read_bytes()).hexdigest(),omitted=([] if minimap else ['minimap (no imported zone overview)'])+['lagging HP overlay layers','debug/system strings'])
