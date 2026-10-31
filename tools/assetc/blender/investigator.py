"""Blender (headless): a KO-style low-poly investigator for Ashgrave.

    blender -b --factory-startup --python tools/assetc/blender/investigator.py -- OUT_DIR

Builds an organic low-poly body with the skin modifier on a stick skeleton
(realistic proportions), a flared open trench coat, collar, tie, hair and face
details; weights it to the Ashgrave investigator rig (automatic weights for the
body, explicit weights for the rigid and cloth pieces); unwraps it; and bakes
colour, cloth grain, a key light and ambient occlusion into one texture, the
painted-with-light look of KO-era characters. Writes OUT_DIR/investigator.json
(glTF-space vertices, normals, UVs, four joint influences, triangles) and
OUT_DIR/investigator-bake.png. The animation clips stay in tools/assetc/ashgrave.py.

Blender is Z-up and the character faces +Y here; glTF/n3e is Y-up facing -Z:
(x, y, z)_blender -> (x, z, -y)_gltf.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

out_dir = Path(sys.argv[sys.argv.index("--") + 1])
out_dir.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# The Ashgrave investigator rig, glTF space (y up), joint -> (parent, position).
JOINTS = [("hips", None, (0, .98, 0)), ("spine", "hips", (0, 1.12, 0)), ("chest", "spine", (0, 1.38, 0)),
          ("head", "chest", (0, 1.68, 0)), ("arm_r", "chest", (.23, 1.58, 0)), ("fore_r", "arm_r", (.23, 1.28, 0)),
          ("arm_l", "chest", (-.23, 1.58, 0)), ("fore_l", "arm_l", (-.23, 1.28, 0)),
          ("thigh_r", "hips", (.1, .96, 0)), ("shin_r", "thigh_r", (.1, .52, 0)),
          ("thigh_l", "hips", (-.1, .96, 0)), ("shin_l", "thigh_l", (-.1, .52, 0)), ("coat", "hips", (0, .98, 0))]
NAMES = [j[0] for j in JOINTS]
TAILS = {"hips": (0, 1.12, 0), "spine": (0, 1.38, 0), "chest": (0, 1.66, 0), "head": (0, 1.92, 0),
         "arm_r": (.23, 1.28, 0), "fore_r": (.24, .98, .01), "arm_l": (-.23, 1.28, 0), "fore_l": (-.24, .98, .01),
         "thigh_r": (.1, .52, 0), "shin_r": (.11, .1, 0), "thigh_l": (-.1, .52, 0), "shin_l": (-.11, .1, 0),
         "coat": (0, .6, .12)}


def b(p):
    """glTF (x, y, z) -> Blender (x, -z, y)."""
    return Vector((p[0], -p[2], p[1]))


def material(name, color, grain=.12, scale=40.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nodes, links = m.node_tree.nodes, m.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 1.0
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 6
    ramp = nodes.new("ShaderNodeValToRGB")
    lo = [max(0, c * (1 - grain)) for c in color] + [1]
    hi = [min(1, c * (1 + grain)) for c in color] + [1]
    ramp.color_ramp.elements[0].color, ramp.color_ramp.elements[1].color = lo, hi
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return m


MATS = {name: material(name, color, grain, scale) for name, color, grain, scale in [
    ("coat", (.36, .27, .15), .18, 30), ("coat_dark", (.22, .16, .09), .15, 30), ("suit", (.045, .045, .055), .25, 50),
    ("shirt", (.72, .70, .64), .08, 60), ("tie", (.38, .03, .04), .1, 60), ("skin", (.62, .40, .30), .08, 20),
    ("hair", (.20, .13, .07), .35, 80), ("shoe", (.03, .025, .02), .2, 40), ("eye", (.02, .02, .02), 0, 10)]}
ORDER = list(MATS)


def new_object(name, mesh):
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    return obj


def select_only(obj):
    for o in scene.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


# ---- body: skin modifier over a stick skeleton (x, y, z Blender; radius x, y)
points = {
    "pelvis": ((0, 0, .97), (.16, .11)), "waist": ((0, .005, 1.12), (.135, .095)), "chest": ((0, .01, 1.36), (.18, .115)),
    "neck": ((0, 0, 1.6), (.055, .055)), "jaw": ((0, .015, 1.68), (.085, .095)), "head": ((0, .005, 1.79), (.098, .108)),
    "crown": ((0, -.005, 1.9), (.07, .08)),
}
edges = [("pelvis", "waist"), ("waist", "chest"), ("chest", "neck"), ("neck", "jaw"), ("jaw", "head"), ("head", "crown")]
for side, s in (("r", 1), ("l", -1)):
    points.update({
        f"shoulder_{side}": ((.2 * s, 0, 1.53), (.07, .07)), f"elbow_{side}": ((.25 * s, 0, 1.25), (.052, .052)),
        f"wrist_{side}": ((.265 * s, -.015, .99), (.038, .033)), f"hand_{side}": ((.275 * s, -.025, .89), (.045, .024)),
        f"hip_{side}": ((.1 * s, 0, .92), (.09, .095)), f"knee_{side}": ((.11 * s, .01, .52), (.066, .068)),
        f"ankle_{side}": ((.11 * s, -.005, .11), (.05, .052)), f"toe_{side}": ((.11 * s, .15, .04), (.052, .034)),
    })
    edges += [("chest", f"shoulder_{side}"), (f"shoulder_{side}", f"elbow_{side}"), (f"elbow_{side}", f"wrist_{side}"),
              (f"wrist_{side}", f"hand_{side}"), ("pelvis", f"hip_{side}"), (f"hip_{side}", f"knee_{side}"),
              (f"knee_{side}", f"ankle_{side}"), (f"ankle_{side}", f"toe_{side}")]
names = list(points)
mesh = bpy.data.meshes.new("body")
mesh.from_pydata([points[n][0] for n in names], [(names.index(a), names.index(c)) for a, c in edges], [])
body = new_object("body", mesh)
skin = body.modifiers.new("skin", "SKIN")
skin.branch_smoothing = .4
for i, n in enumerate(names):
    body.data.skin_vertices[""].data[i].radius = points[n][1]
body.data.skin_vertices[""].data[0].use_root = True
sub = body.modifiers.new("sub", "SUBSURF")
sub.levels = 1
select_only(body)
bpy.ops.object.modifier_apply(modifier="skin")
bpy.ops.object.modifier_apply(modifier="sub")
dec = body.modifiers.new("dec", "DECIMATE")
dec.ratio = .62
bpy.ops.object.modifier_apply(modifier="dec")


def region(center):
    x, y, z = center
    if z > 1.6 and abs(x) < .13:
        return "skin"
    if z < .97 and abs(x) > .2:
        return "skin"      # hands
    if abs(x) > .16 and z > .97:
        return "coat"      # sleeves
    if z < .13:
        return "shoe"
    if z < .95:
        return "suit"      # trousers
    if y > .06 and abs(x) < .075 and z > 1.12:
        return "shirt"
    return "suit"


for name in ORDER:
    body.data.materials.append(MATS[name])
for poly in body.data.polygons:
    poly.material_index = ORDER.index(region(poly.center))


def shell(name, rings, segments=12, open_front=None, mat="coat"):
    """A tapered tube; rings = [(z, rx, ry, y_offset)], optional front slit below z."""
    bm = bmesh.new()
    loops = []
    for z, rx, ry, yo in rings:
        loops.append([bm.verts.new((rx * math.sin(t), yo + ry * math.cos(t), z))
                      for t in (2 * math.pi * k / segments for k in range(segments))])
    for a, c in zip(loops, loops[1:]):
        for k in range(segments):
            quad = [a[k], a[(k + 1) % segments], c[(k + 1) % segments], c[k]]
            center_y = sum(v.co.y for v in quad) / 4
            front = k in (0, segments - 1)   # the quad straddling +Y (the front)
            if open_front is not None and front and max(v.co.z for v in quad) <= open_front and center_y > 0:
                continue
            bm.faces.new(quad)
    bm.normal_update()
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    obj = new_object(name, me)
    me.materials.append(MATS[mat])
    select_only(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    solid = obj.modifiers.new("solid", "SOLIDIFY")
    solid.thickness = .012
    bpy.ops.object.modifier_apply(modifier="solid")
    return obj


coat = shell("coat", [(1.55, .205, .135, 0), (1.36, .215, .14, .005), (1.12, .185, .13, .005),
                      (.9, .225, .165, 0), (.62, .26, .2, -.01), (.5, .28, .21, -.015)], open_front=1.56)
collar = shell("collar", [(1.62, .085, .08, -.01), (1.56, .12, .1, -.005), (1.51, .17, .125, 0)],
               segments=10, mat="coat_dark")

belt = shell("belt", [(1.13, .192, .136, .006), (1.08, .19, .135, .006)], mat="coat_dark", open_front=1.2)
flaps = []
for s_ in (1, -1):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(.2 * s_, .09, .96), rotation=(0, 0, .45 * s_), scale=(.1, .014, .045))
    flap = bpy.context.active_object
    flap.data.materials.append(MATS["coat_dark"])
    flaps.append(flap)
bm = bmesh.new()
for z0, z1, w0, w1 in [(1.52, 1.36, .018, .026), (1.36, 1.2, .026, .02)]:
    y = .125
    q = [bm.verts.new((-w0, y, z0)), bm.verts.new((w0, y, z0)), bm.verts.new((w1, y, z1)), bm.verts.new((-w1, y, z1))]
    bm.faces.new(q)
tie_me = bpy.data.meshes.new("tie")
bm.to_mesh(tie_me)
tie = new_object("tie", tie_me)
tie_me.materials.append(MATS["tie"])

bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=.118, location=(0, -.018, 1.8))
hair = bpy.context.active_object
hair.scale = (1.02, 1.08, .92)
bm = bmesh.new()
bm.from_mesh(hair.data)
# Keep the top, back and sides; open the face and the lower front.
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -.075 or (v.co.y > .045 and v.co.z < .045)], context="VERTS")
bm.to_mesh(hair.data)
hair.data.materials.append(MATS["hair"])
bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=.022, depth=.05, location=(0, .107, 1.76), rotation=(-math.pi / 2, 0, 0))
nose = bpy.context.active_object
nose.data.materials.append(MATS["skin"])
features = []
for s in (1, -1):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(.036 * s, .098, 1.79), scale=(.018, .006, .008))
    eye = bpy.context.active_object
    eye.data.materials.append(MATS["eye"])
    bpy.ops.mesh.primitive_cube_add(size=1, location=(.037 * s, .1, 1.812), rotation=(0, -.25 * s, 0), scale=(.026, .006, .006))
    brow = bpy.context.active_object
    brow.data.materials.append(MATS["hair"])
    features += [eye, brow]

# ---- armature matching the n3e rig
arm_data = bpy.data.armatures.new("rig")
rig = new_object("rig", arm_data)
select_only(rig)
bpy.ops.object.mode_set(mode="EDIT")
bones = {}
for name, parent, pos in JOINTS:
    bone = arm_data.edit_bones.new(name)
    bone.head, bone.tail = b(pos), b(TAILS[name])
    if parent:
        bone.parent = bones[parent]
    bones[name] = bone
bpy.ops.object.mode_set(mode="OBJECT")

# Body: automatic (heat) weights. Rigid pieces: explicit weights.
select_only(body)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
# The coat bone is for the coat skirt only.
if "coat" in body.vertex_groups:
    body.vertex_groups.remove(body.vertex_groups["coat"])


def weigh(obj, rule):
    for n in NAMES:
        obj.vertex_groups.new(name=n)
    for v in obj.data.vertices:
        for n, w in rule(obj.matrix_world @ v.co).items():
            if w > 0:
                obj.vertex_groups[n].add([v.index], w, "REPLACE")
    mod = obj.modifiers.new("rig", "ARMATURE")
    mod.object = rig


def coat_rule(p):
    x, y, z = p
    if z > 1.3:
        return {"chest": 1}
    if z > 1.05:
        t = (z - 1.05) / .25
        return {"chest": t, "spine": 1 - t}
    if z > .9:
        return {"hips": 1}
    leg = "thigh_r" if x > 0 else "thigh_l"
    t = min(1, (.9 - z) / .38)
    side = min(1, abs(x) / .12)
    return {"hips": 1 - t, leg: t * .55 * side, "coat": t * (1 - .55 * side)}


weigh(coat, coat_rule)
weigh(collar, lambda p: {"chest": 1} if p[2] < 1.58 else {"chest": .5, "head": .5})
weigh(tie, lambda p: {"chest": 1})
weigh(belt, lambda p: {"spine": .5, "hips": .5})
for flap in flaps:
    weigh(flap, lambda p: {"hips": .6, ("thigh_r" if p[0] > 0 else "thigh_l"): .4})
for piece in [hair, nose] + features:
    weigh(piece, lambda p: {"head": 1})

# ---- one mesh, one UV map, one baked texture
select_only(body)
for piece in [coat, collar, tie, belt, hair, nose] + features + flaps:
    piece.select_set(True)
bpy.ops.object.join()
char = bpy.context.active_object
char.name = "investigator"
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.quads_convert_to_tris()
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=.02)
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.shade_smooth()

size = 256
image = bpy.data.images.new("bake", size, size, alpha=False)
for m in char.data.materials:
    node = m.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    m.node_tree.nodes.active = node
scene.render.engine = "CYCLES"
scene.cycles.samples = 48
scene.cycles.device = "CPU"
world = bpy.data.worlds.new("world")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (.35, .36, .4, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = .55
sun = bpy.data.objects.new("key", bpy.data.lights.new("key", "SUN"))
sun.data.energy = 3.4
sun.rotation_euler = (math.radians(40), math.radians(-25), math.radians(20))
scene.collection.objects.link(sun)
select_only(char)
bake = scene.render.bake
bake.margin = 4
bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT", "COLOR"})
image.filepath_raw = str(out_dir / "investigator-bake.png")
image.file_format = "PNG"
image.save()

# ---- export glTF-space data for the n3e rig
depsgraph = bpy.context.evaluated_depsgraph_get()
me = char.data
me.calc_loop_triangles()
uv = me.uv_layers.active.data
group_names = {g.index: g.name for g in char.vertex_groups}
key_index, vertices, triangles = {}, [], []
for tri in me.loop_triangles:
    corner = []
    for loop_index in tri.loops:
        loop = me.loops[loop_index]
        v = me.vertices[loop.vertex_index]
        n = loop.normal if hasattr(loop, "normal") else v.normal
        key = (loop.vertex_index, round(uv[loop_index].uv.x, 5), round(uv[loop_index].uv.y, 5),
               round(n.x, 3), round(n.y, 3), round(n.z, 3))
        if key not in key_index:
            influences = sorted(((g.weight, group_names[g.group]) for g in v.groups
                                 if g.weight > 1e-4 and group_names[g.group] in NAMES), reverse=True)[:4]
            if not influences:
                influences = [(1.0, "hips")]
            total = sum(w for w, _ in influences)
            joints = [NAMES.index(name) for _, name in influences] + [0] * (4 - len(influences))
            weights = [w / total for w, _ in influences] + [0.0] * (4 - len(influences))
            co = v.co
            key_index[key] = len(vertices)
            vertices.append({"p": [co.x, co.z, -co.y], "n": [n.x, n.z, -n.y],
                             "uv": [uv[loop_index].uv.x, 1 - uv[loop_index].uv.y], "j": joints, "w": weights})
        corner.append(key_index[key])
    # Blender faces are CCW from outside; the axis change keeps handedness.
    triangles.append(corner)
(out_dir / "investigator.json").write_text(json.dumps({"joints": NAMES, "vertices": vertices, "triangles": triangles}))
print("INVESTIGATOR", len(vertices), "vertices", len(triangles), "triangles")

# ---- optional turnaround preview (flat-lit texture, as the game shades it)
if "--preview" in sys.argv:
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x, scene.render.resolution_y = 360, 560
    scene.render.film_transparent = False
    world.color = (.12, .13, .16)
    for m in char.data.materials:
        m.node_tree.nodes.active = next(n for n in m.node_tree.nodes if n.type == "TEX_IMAGE")
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 70
    for label, angle in (("front", 0), ("three-quarter", 35), ("side", 90)):
        a = math.radians(angle)
        cam.location = (4.2 * math.sin(a), 4.2 * math.cos(a), 1.05)
        cam.rotation_euler = (math.radians(90), 0, math.radians(180) - a)
        scene.render.filepath = str(out_dir / f"preview-{label}.png")
        bpy.ops.render.render(write_still=True)
    print("PREVIEW rendered")
