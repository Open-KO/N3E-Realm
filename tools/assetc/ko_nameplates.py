"""Offline nameplate atlas/metrics and model bounds, from the audited KO path.

Liberation Sans is an explicit local substitute for Windows Arial. No runtime
font installation, proprietary font download, or game IDs in the engine.
"""
import hashlib
import json
import pathlib
import re
import subprocess
from common import f, u
import ko_character as character


def atlas(path, pixels):
    args=['magick','-debug','annotate','-size','512x192','xc:none','-font',str(path),
          '-pointsize',str(pixels),'-fill','white']
    for code in range(33,127):
        x=(code-32)%16*32+2;y=(code-32)//16*32+22
        char=chr(code)
        if char=='\\':char='\\\\'
        args+=['-annotate',f'+{x}+{y}',char]
    result=subprocess.run(args+['-depth','8','rgba:-'],capture_output=True,check=True)
    metrics={}
    pattern=r'Metrics: text: (.*?); width: [^;]+; height: ([0-9.]+); ascent: ([0-9.]+);[^\n]*origin: ([0-9.]+),'
    for char,height,ascent,advance in re.findall(pattern,result.stderr.decode()):
        metrics[char]=(round(float(height)),22-round(float(ascent)),round(float(advance)*64)/64)
    # Whitespace has no rasterization callback, so measure it between two glyphs.
    space=subprocess.run(['magick','-debug','annotate','-font',str(path),'-pointsize',str(pixels),
                          'label:x x','null:'],capture_output=True,text=True,check=True)
    matches=re.findall(pattern,space.stderr)
    if not matches or len(result.stdout)!=512*192*4:raise ValueError('nameplate font raster/metrics')
    space_advance=round(float(matches[-1][3])*64)/64-2*metrics['x'][2]
    height,top,_=metrics['M']
    advances=[space_advance]+[metrics[chr(code)][2] for code in range(33,127)]
    if not (0<=top and 1<=height and top+height<=32 and all(0<x<=28 for x in advances)):
        raise ValueError('nameplate glyph bounds')
    return (512,192,result.stdout), (height,top,advances)


def cook(assets,textures,npc_scale=1.0):
    """`npc_scale`: the package NPC's drawn size factor (PQ-288). KO's NPC name
    callback 00459820 places the name at y + h x s x 1.1 (h actor +0x17c, s the
    scale +0x90 that NPC-in sets, 005cdd82); a package whose one NPC set is
    drawn at s without a scale on the wire (the Moradon worm) folds s into the
    NPC profile's height here. 1 leaves the style byte for byte as before."""
    if type(npc_scale) not in (int,float) or not 0.01<=npc_scale<=10:raise ValueError('nameplate npc scale')
    source=pathlib.Path('games/moradon/nameplates.json')
    config=json.loads(source.read_text())
    fonts=[];sources=[]
    for name in config['fonts']:
        path=pathlib.Path(name);texture,metrics=atlas(path,config['font_pixels'])
        fonts.append((len(textures),metrics));textures.append(texture)
        sources.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    profiles=[]
    for name in config['skeletons']:
        # PQ-301: the padded joint box top (0041c300 at frame 0, character
        # +0x12c), which 00459820 reads as actor +0x17c; not the box's Y span.
        _,height=character.joint_bounds(character.skeleton(assets.get(name)))
        # The NPC profile (the second skeleton) at the NPC's drawn size.
        if len(profiles)==1:height*=npc_scale
        profiles.append((height,0))
    data=f([config['distance'],config['height_padding'],config['pixel_gap'],config['seated_height_fraction']])
    data+=b''.join(u(c) for c in config['colors'])
    for texture,(height,top,advances) in fonts:data+=u(texture)+u(height)+u(top)+f(advances)
    for height,root in profiles:data+=f([height])+u(root)
    return data,dict(definition=str(source),definition_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                     font_substitutes=sources,profiles=profiles,npc_scale=npc_scale,font_pixels=config['font_pixels'],
                     limits=['ASCII glyphs','one player and one NPC model','foreground colors retain prior neutral presentation','not Windows GDI raster equivalence'])
