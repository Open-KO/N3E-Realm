"""Blender (headless) + MPFB2: a MakeHuman-based investigator for Ashgrave.

    BLENDER_USER_RESOURCES=.cache/tools/blender-user \
    blender -b --factory-startup --python tools/assetc/blender/mpfb_investigator.py -- OUT_DIR [--preview]

Builds a male MakeHuman character with the CC0 system assets:
- the proxy741 low-poly body topology and a painted middle-aged skin;
- an elegant suit whose jacket is recoloured into a trench coat and extended with
  a fitted, flared coat skirt and belt;
- shoes, short hair, eyebrows and low-poly eyes.

It then:
1. rigs him with MPFB's hand-weighted game-engine rig;
2. lowers the arms from the A-pose to hang at his sides, applied as the rest pose;
3. decimates the clothing into a KO-like budget;
4. maps the 53 game-engine bones onto the 13-joint Ashgrave rig, so the scripted
   clips apply;
5. unwraps once and bakes every material plus a key light into one texture.

Writes OUT_DIR/investigator.json (glTF space, facing -Z, four influences, joint
rest positions) and OUT_DIR/investigator-bake.png. Content made with MPFB and its
system assets is CC0; the add-on itself is GPL and is not redistributed.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

args = sys.argv[sys.argv.index("--") + 1:]
out_dir = Path(args[0])
out_dir.mkdir(parents=True, exist_ok=True)
preview = "--preview" in args
glb = next((a.split("=", 1)[1] for a in args if a.startswith("--glb=")), None)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.mpfb")
from bl_ext.user_default.mpfb.services.assetservice import AssetService  # noqa: E402
from bl_ext.user_default.mpfb.services.humanservice import HumanService  # noqa: E402
from bl_ext.user_default.mpfb.services.targetservice import TargetService  # noqa: E402

scene = bpy.context.scene


def select_only(obj):
    for o in scene.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def asset(fragment, subdir):
    path = AssetService.find_asset_absolute_path(fragment, subdir)
    if not path:
        raise FileNotFoundError(f"{subdir}/{fragment}: install the MakeHuman system assets")
    return path


# ---- the human: a lean, weathered man in his late thirties
macro = TargetService.get_default_macro_info_dict()
macro.update(gender=1.0, age=0.62, muscle=0.55, weight=0.42, height=0.6, proportions=0.75)
macro["race"] = {"asian": 0.0, "african": 0.0, "caucasian": 1.0}
basemesh = HumanService.create_human(macro_detail_dict=macro)
rig = HumanService.add_builtin_rig(basemesh, "game_engine")
proxy = HumanService.add_mhclo_asset(asset("proxy741/proxy741.proxy", "proxymeshes"), basemesh,
                                     asset_type="Proxymeshes", subdiv_levels=0)
HumanService.set_character_skin(asset("middleage_caucasian_male/middleage_caucasian_male.mhmat", "skins"),
                                basemesh, bodyproxy=proxy, skin_type="GAMEENGINE")
parts = {}
for key, fragment, subdir, kind in [("suit", "male_elegantsuit01/male_elegantsuit01.mhclo", "clothes", "Clothes"),
                                    ("shoes", "shoes01/shoes01.mhclo", "clothes", "Clothes"),
                                    ("hair", "short02/short02.mhclo", "hair", "Hair"),
                                    ("brows", "eyebrow001/eyebrow001.mhclo", "eyebrows", "Eyebrows"),
                                    ("eyes", "low-poly/low-poly.mhclo", "eyes", "Eyes")]:
    parts[key] = HumanService.add_mhclo_asset(asset(fragment, subdir), basemesh, asset_type=kind,
                                              subdiv_levels=0, material_type="MAKESKIN")

# ---- arms down: rotate each upper arm about its shoulder until it hangs, as rest
select_only(rig)
bpy.ops.object.mode_set(mode="POSE")
for side, sx in (("l", 1), ("r", -1)):
    pb = rig.pose.bones[f"upperarm_{side}"]
    head = rig.matrix_world @ pb.head
    tail = rig.matrix_world @ pb.tail
    current = (tail - head).normalized()
    target = Vector((.12 * sx, .03, -1)).normalized()   # hanging, slightly out and forward
    q = current.rotation_difference(target)
    pivot = Matrix.Translation(pb.head) @ q.to_matrix().to_4x4() @ Matrix.Translation(-pb.head)
    pb.matrix = pivot @ pb.matrix
    bpy.context.view_layer.update()
bpy.ops.object.mode_set(mode="OBJECT")
meshes = [o for o in scene.objects if o.type == "MESH" and o is not basemesh]
for obj in meshes:
    select_only(obj)
    for mod in list(obj.modifiers):
        if mod.type == "MASK":
            bpy.ops.object.modifier_apply(modifier=mod.name)   # drop body hidden under clothes
    arm_mod = next((m for m in obj.modifiers if m.type == "ARMATURE"), None)
    if arm_mod:
        name = arm_mod.name
        bpy.ops.object.modifier_copy(modifier=name)
        bpy.ops.object.modifier_apply(modifier=name)           # bake the new rest shape
select_only(rig)
bpy.ops.object.mode_set(mode="POSE")
bpy.ops.pose.armature_apply(selected=False)
bpy.ops.object.mode_set(mode="OBJECT")
bpy.data.objects.remove(basemesh, do_unlink=True)


def bone_head(name):
    return rig.matrix_world @ rig.data.bones[name].head_local


# ---- coat: recolour the suit jacket and add a fitted, flared skirt and belt
suit = parts["suit"]
hip_z = bone_head("pelvis").z
knee_z = bone_head("calf_l").z
jacket = bpy.data.materials.new("coat_jacket")
source = suit.data.materials[0]
jacket = source.copy()
jacket.name = "coat_jacket"
nodes, links = jacket.node_tree.nodes, jacket.node_tree.links
tex = next(n for n in nodes if n.type == "TEX_IMAGE" and n.image and "normal" not in n.image.name.lower())
bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
bw = nodes.new("ShaderNodeRGBToBW")
ramp = nodes.new("ShaderNodeValToRGB")          # dark cloth -> weathered khaki, light shirt stays
ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.0, (.16, .11, .06, 1)
ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = .2, (.5, .385, .22, 1)
mix = nodes.new("ShaderNodeMix")
mix.data_type = "RGBA"
keep = nodes.new("ShaderNodeMapRange")
keep.inputs["From Min"].default_value, keep.inputs["From Max"].default_value = .28, .36
links.new(tex.outputs["Color"], bw.inputs["Color"])
links.new(bw.outputs["Val"], ramp.inputs["Fac"])
links.new(bw.outputs["Val"], keep.inputs["Value"])
links.new(keep.outputs["Result"], mix.inputs["Factor"])
links.new(ramp.outputs["Color"], mix.inputs["A"])
links.new(tex.outputs["Color"], mix.inputs["B"])
links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
suit.data.materials.append(jacket)
for poly in suit.data.polygons:
    if (suit.matrix_world @ poly.center).z > hip_z - .08:
        poly.material_index = len(suit.data.materials) - 1

coat_color = bpy.data.materials.new("coat_skirt")
coat_color.use_nodes = True
n2 = coat_color.node_tree.nodes
noise = n2.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 60
cr = n2.new("ShaderNodeValToRGB")
cr.color_ramp.elements[0].color, cr.color_ramp.elements[1].color = (.25, .19, .1, 1), (.32, .245, .135, 1)
coat_color.node_tree.links.new(noise.outputs["Fac"], cr.inputs["Fac"])
coat_color.node_tree.links.new(cr.outputs["Color"], n2["Principled BSDF"].inputs["Base Color"])
n2["Principled BSDF"].inputs["Roughness"].default_value = 1
belt_color = coat_color.copy()
belt_color.node_tree.nodes["Color Ramp"].color_ramp.elements[0].color = (.14, .1, .05, 1)
belt_color.node_tree.nodes["Color Ramp"].color_ramp.elements[1].color = (.2, .14, .08, 1)

# Measure the suit's torso cross-section just above the hip to fit the skirt top.
# Arms now hang at the hips: ignore arm- and hand-weighted vertices.
arm_groups = {grp.index for grp in suit.vertex_groups if any(k in grp.name for k in (
    "upperarm", "lowerarm", "hand", "thumb", "index", "middle", "ring", "pinky"))}
band = [suit.matrix_world @ v.co for v in suit.data.vertices
        if abs((suit.matrix_world @ v.co).z - (hip_z - .04)) < .05
        and sum(gw.weight for gw in v.groups if gw.group in arm_groups) < .15]
x_half = max(abs(p.x) for p in band) + .012
y_front = min(p.y for p in band) - .012   # MakeHuman faces -Y
y_back = max(p.y for p in band) + .012
yc, y_half = (y_front + y_back) / 2, (y_back - y_front) / 2


def shell(name, rings, mat, segments=14, open_front_below=None):
    bm = bmesh.new()
    loops = []
    for z, rx, ry, yo in rings:
        loops.append([bm.verts.new((rx * math.sin(t), yo - ry * math.cos(t), z))
                      for t in (2 * math.pi * k / segments for k in range(segments))])
    for a, c in zip(loops, loops[1:]):
        for k in range(segments):
            front = k in (0, segments - 1)
            if open_front_below is not None and front and a[k].co.z <= open_front_below:
                continue
            bm.faces.new([a[k], a[(k + 1) % segments], c[(k + 1) % segments], c[k]])
    bm.normal_update()
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    obj = bpy.data.objects.new(name, me)
    scene.collection.objects.link(obj)
    me.materials.append(mat)
    select_only(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    solid = obj.modifiers.new("solid", "SOLIDIFY")
    solid.thickness = .012
    bpy.ops.object.modifier_apply(modifier="solid")
    return obj


skirt = shell("coat_skirt", [(hip_z + .04, x_half, y_half, yc), (hip_z - .15, x_half + .02, y_half + .015, yc),
                             (knee_z + .12, x_half + .045, y_half + .04, yc + .01), (knee_z - .02, x_half + .055, y_half + .05, yc + .015)],
              coat_color, open_front_below=hip_z + .05)
belt = shell("coat_belt", [(hip_z + .1, x_half + .006, y_half + .006, yc), (hip_z + .05, x_half + .006, y_half + .006, yc)],
             belt_color)


def weigh(obj, rule):
    for bone in rig.data.bones:
        if bone.name not in obj.vertex_groups:
            obj.vertex_groups.new(name=bone.name)
    for v in obj.data.vertices:
        for group, w in rule(obj.matrix_world @ v.co).items():
            obj.vertex_groups[group].add([v.index], w, "REPLACE")
    mod = obj.modifiers.new("rig", "ARMATURE")
    mod.object = rig


def skirt_rule(p):
    t = min(1, max(0, (hip_z - p.z) / (hip_z - knee_z)))
    leg = "thigh_l" if p.x > 0 else "thigh_r"
    side = min(1, abs(p.x) / .12)
    return {"pelvis": 1 - .6 * t * side, leg: .6 * t * side}


weigh(skirt, skirt_rule)
weigh(belt, lambda p: {"pelvis": .6, "spine_01": .4})

# ---- KO-sized budget: decimate the dense MakeHuman clothing and hair
for key, ratio in (("suit", .04), ("shoes", .03), ("hair", .05)):
    obj = parts[key]
    select_only(obj)
    dec = obj.modifiers.new("dec", "DECIMATE")
    dec.ratio = ratio
    dec.use_collapse_triangulate = True
    bpy.ops.object.modifier_move_to_index(modifier="dec", index=0)
    bpy.ops.object.modifier_apply(modifier="dec")

# ---- join, one bake UV, one texture
# The body is mostly hidden under clothes now; thin what shows, like KO's ~1k bodies.
select_only(proxy)
body_dec = proxy.modifiers.new("dec", "DECIMATE")
body_dec.ratio = .75
bpy.ops.object.modifier_move_to_index(modifier="dec", index=0)
bpy.ops.object.modifier_apply(modifier="dec")
pieces = [proxy, skirt, belt] + list(parts.values())
for obj in pieces:
    uv = obj.data.uv_layers
    if uv:
        uv[0].name = "UVMap"
    else:
        uv.new(name="UVMap")
select_only(pieces[0])
for obj in pieces[1:]:
    obj.select_set(True)
bpy.ops.object.join()
char = bpy.context.active_object
char.name = "investigator"
for mod in [m for m in char.modifiers if m.type == "ARMATURE"][1:]:
    char.modifiers.remove(mod)
bake_uv = char.data.uv_layers.new(name="bake")
char.data.uv_layers.active = bake_uv
char.data.uv_layers["UVMap"].active_render = True
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.quads_convert_to_tris()
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=.006)
bpy.ops.object.mode_set(mode="OBJECT")

size = 1024
image = bpy.data.images.new("bake", size, size, alpha=False)
for m in char.data.materials:
    if not m or not m.use_nodes:
        continue
    for node in m.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image is not image:
            uvnode = m.node_tree.nodes.new("ShaderNodeUVMap")
            uvnode.uv_map = "UVMap"
            m.node_tree.links.new(uvnode.outputs["UV"], node.inputs["Vector"])
    target = m.node_tree.nodes.new("ShaderNodeTexImage")
    target.image = image
    m.node_tree.nodes.active = target
scene.render.engine = "CYCLES"
scene.cycles.samples = 64
scene.cycles.device = "CPU"
world = bpy.data.worlds.new("world")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (.35, .36, .4, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = .4
sun = bpy.data.objects.new("key", bpy.data.lights.new("key", "SUN"))
sun.data.energy = 4.6
sun.rotation_euler = (math.radians(40), math.radians(25), math.radians(200))
scene.collection.objects.link(sun)
select_only(char)
scene.render.bake.margin = 4
bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT", "COLOR"}, uv_layer="bake")
image.filepath_raw = str(out_dir / "investigator-bake.png")
image.file_format = "PNG"
image.save()

# ---- export: game-engine bones -> Ashgrave joints, glTF space facing -Z
JOINT_OF = {"Root": "hips", "pelvis": "hips", "spine_01": "spine", "spine_02": "chest", "spine_03": "chest",
            "clavicle_l": "chest", "clavicle_r": "chest", "neck_01": "head", "head": "head",
            "thigh_l": "thigh_l", "thigh_r": "thigh_r", "calf_l": "shin_l", "calf_r": "shin_r",
            "foot_l": "shin_l", "foot_r": "shin_r", "ball_l": "shin_l", "ball_r": "shin_r",
            "upperarm_l": "arm_l", "upperarm_r": "arm_r", "lowerarm_l": "fore_l", "lowerarm_r": "fore_r"}
NAMES = ["hips", "spine", "chest", "head", "arm_r", "fore_r", "arm_l", "fore_l", "thigh_r", "shin_r",
         "thigh_l", "shin_l", "coat"]
# MakeHuman's right side is -X and it faces -Y; n3e's right is +X facing -Z.
# (x, y, z)_blender -> (-x, z, y)_gltf mirrors nothing: it is a 180-degree turn.


def g(p):
    return [-p.x, p.z, p.y]


def joint_for(bone):
    if bone in JOINT_OF:
        return JOINT_OF[bone]
    side = "l" if bone.endswith("_l") else "r"
    return f"fore_{side}"          # hands and fingers ride the forearm


positions = {"hips": g(bone_head("pelvis")), "spine": g(bone_head("spine_02")), "chest": g(bone_head("spine_03")),
             "head": g(bone_head("neck_01")), "arm_r": g(bone_head("upperarm_r")), "fore_r": g(bone_head("lowerarm_r")),
             "arm_l": g(bone_head("upperarm_l")), "fore_l": g(bone_head("lowerarm_l")),
             "thigh_r": g(bone_head("thigh_r")), "shin_r": g(bone_head("calf_r")),
             "thigh_l": g(bone_head("thigh_l")), "shin_l": g(bone_head("calf_l")), "coat": g(bone_head("pelvis"))}
me = char.data
me.calc_loop_triangles()
uv = me.uv_layers["bake"].data
groups = {grp.index: grp.name for grp in char.vertex_groups}
key_index, vertices, triangles = {}, [], []
for tri in me.loop_triangles:
    corner = []
    for li in tri.loops:
        loop = me.loops[li]
        v = me.vertices[loop.vertex_index]
        n = loop.normal
        key = (loop.vertex_index, round(uv[li].uv.x, 5), round(uv[li].uv.y, 5), round(n.x, 3), round(n.y, 3), round(n.z, 3))
        if key not in key_index:
            acc = {}
            for gw in v.groups:
                name = groups.get(gw.group)
                if name in rig.data.bones and gw.weight > 1e-4:
                    joint = joint_for(name)
                    acc[joint] = acc.get(joint, 0) + gw.weight
            best = sorted(acc.items(), key=lambda kv: -kv[1])[:4] or [("hips", 1.0)]
            total = sum(w for _, w in best)
            key_index[key] = len(vertices)
            co = char.matrix_world @ v.co
            nn = (char.matrix_world.to_3x3() @ n).normalized()
            vertices.append({"p": g(co), "n": g(nn), "uv": [uv[li].uv.x, 1 - uv[li].uv.y],
                             "j": [NAMES.index(j) for j, _ in best] + [0] * (4 - len(best)),
                             "w": [w / total for _, w in best] + [0.0] * (4 - len(best))})
        corner.append(key_index[key])
    triangles.append(corner)
(out_dir / "investigator.json").write_text(json.dumps({"joints": NAMES, "positions": positions,
                                                       "vertices": vertices, "triangles": triangles}))
print("MPFB INVESTIGATOR", len(vertices), "vertices", len(triangles), "triangles")

if glb:
    # An unrigged, single-texture GLB in an A-pose for external auto-riggers
    # (arms held away from the body rig far more cleanly than arms down).
    select_only(rig)
    bpy.ops.object.mode_set(mode="POSE")
    for side, sx in (("l", 1), ("r", -1)):
        pb = rig.pose.bones[f"upperarm_{side}"]
        head = rig.matrix_world @ pb.head
        current = (rig.matrix_world @ pb.tail - head).normalized()
        q = current.rotation_difference(Vector((.72 * sx, 0, -.7)).normalized())
        pb.matrix = Matrix.Translation(pb.head) @ q.to_matrix().to_4x4() @ Matrix.Translation(-pb.head) @ pb.matrix
        bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode="OBJECT")
    select_only(char)
    bpy.ops.object.duplicate()
    posed = bpy.context.active_object
    for mod in list(posed.modifiers):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    posed.parent = None
    posed.vertex_groups.clear()
    for layer in [l for l in posed.data.uv_layers if l.name != "bake"]:
        posed.data.uv_layers.remove(layer)
    flat = bpy.data.materials.new("investigator")
    flat.use_nodes = True
    tex_node = flat.node_tree.nodes.new("ShaderNodeTexImage")
    tex_node.image = image
    flat.node_tree.links.new(tex_node.outputs["Color"], flat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    posed.data.materials.clear()
    posed.data.materials.append(flat)
    for poly in posed.data.polygons:
        poly.material_index = 0
    image.filepath_raw = str(out_dir / "investigator-bake.png")
    select_only(posed)
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_skins=False,
                              export_animations=False, export_image_format="AUTO")
    print("GLB exported", glb)
    bpy.ops.object.delete()
    select_only(rig)
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.transforms_clear()
    bpy.ops.object.mode_set(mode="OBJECT")

if preview:
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x, scene.render.resolution_y = 360, 560
    world.color = (.12, .13, .16)
    char.data.uv_layers["bake"].active_render = True
    for m in char.data.materials:
        if m and m.use_nodes:
            m.node_tree.nodes.active = next(n for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image is image)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 70
    for label, angle in (("front", 0), ("three-quarter", 35), ("side", 90)):
        a = math.radians(angle)
        cam.location = (4.2 * math.sin(a), -4.2 * math.cos(a), 1.0)
        cam.rotation_euler = (math.radians(90), 0, a)
        scene.render.filepath = str(out_dir / f"preview-{label}.png")
        bpy.ops.render.render(write_still=True)
    print("PREVIEW rendered")
