"""Blender (headless): a Synty POLYGON character mapped onto the Ashgrave rig.

    blender -b --factory-startup --python tools/assetc/blender/synty_investigator.py -- \
        CHARACTERS_FBX OUT_DIR [--body=Character_Male_Face_01] [--hair=Character_Hair_Male_01] \
        [--paint=1] [--preview=TEXTURE]

Takes one rigged body and its hair from a Synty POLYGON `Characters.fbx` (the
free Starter Pack's male by default). It then:
1. lowers the arms from Synty's T-pose so they hang, applied as the rest pose;
2. binds the rigid hair to the head;
3. maps the 49 Synty bones onto the 13-joint Ashgrave rig, so the scripted clips
   apply;
4. keeps Synty's own UVs, which sample its flat-colour palette texture. The
   Starter Pack body is a bare mannequin on one swatch, so `--paint` moves each
   face onto a palette swatch by region (coat, shirt, trousers, shoes, skin, hair).

Writes OUT_DIR/investigator.json in the same form as `mpfb_investigator.py`
(glTF space, facing -Z, four influences, joint rest positions). Synty sources
are licensed per team and are never committed.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

args = sys.argv[sys.argv.index("--") + 1:]
fbx, out_dir = Path(args[0]), Path(args[1])
out_dir.mkdir(parents=True, exist_ok=True)
opt = dict(a[2:].split("=", 1) for a in args[2:] if a.startswith("--") and "=" in a)
body_name = opt.get("body", "Character_Male_Face_01")
hair_name = opt.get("hair", "Character_Hair_Male_01")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(fbx))
scene = bpy.context.scene
rig = next(o for o in scene.objects if o.type == "ARMATURE")
body = scene.objects[body_name]
hair = scene.objects.get(hair_name) if hair_name else None
for o in [o for o in scene.objects if o.type == "MESH" and o not in (body, hair)]:
    bpy.data.objects.remove(o, do_unlink=True)


def select_only(obj):
    for o in scene.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def bone_head(name):
    return rig.matrix_world @ rig.data.bones[name].head_local


# ---- hair: rigid in the source (no weights), so it follows the head
if hair:
    hair_world = hair.matrix_world.copy()
    hair.parent = None
    hair.matrix_world = hair_world
    group = hair.vertex_groups.new(name="Head")
    group.add([v.index for v in hair.data.vertices], 1.0, "REPLACE")
    hair.modifiers.new("rig", "ARMATURE").object = rig

# ---- arms down: rotate each upper arm about its shoulder until it hangs, as rest.
# Directions are measured head to head, because FBX bone tails are arbitrary.
select_only(rig)
bpy.ops.object.mode_set(mode="POSE")
to_rig = rig.matrix_world.inverted().to_3x3()
for side, sx in (("L", 1), ("R", -1)):
    pb = rig.pose.bones[f"Shoulder_{side}"]
    elbow = rig.pose.bones[f"Elbow_{side}"]
    current = (elbow.head - pb.head).normalized()
    target = (to_rig @ Vector((.12 * sx, .03, -1))).normalized()   # hanging, slightly out and forward
    q = current.rotation_difference(target)
    pb.matrix = Matrix.Translation(pb.head) @ q.to_matrix().to_4x4() @ Matrix.Translation(-pb.head) @ pb.matrix
    bpy.context.view_layer.update()
bpy.ops.object.mode_set(mode="OBJECT")
pieces = [o for o in (body, hair) if o]
for obj in pieces:
    select_only(obj)
    arm_mod = next(m for m in obj.modifiers if m.type == "ARMATURE")
    name = arm_mod.name
    bpy.ops.object.modifier_copy(modifier=name)
    bpy.ops.object.modifier_apply(modifier=name)                 # bake the new rest shape
select_only(rig)
bpy.ops.object.mode_set(mode="POSE")
bpy.ops.pose.armature_apply(selected=False)
bpy.ops.object.mode_set(mode="OBJECT")

# ---- one mesh, triangulated, on the source UVs
for obj in pieces:
    obj.data.uv_layers[0].name = "UVMap"
select_only(body)
if hair:
    hair.select_set(True)
bpy.ops.object.join()
char = bpy.context.active_object
for mod in [m for m in char.modifiers if m.type == "ARMATURE"][1:]:
    char.modifiers.remove(mod)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.quads_convert_to_tris()
bpy.ops.object.mode_set(mode="OBJECT")

# ---- paint: the Starter Pack's base body samples one blue swatch (hair a darker
# one, eyes black). With --paint, each face is moved onto a Synty palette swatch
# by region, dressing the body as the investigator; the source palette is kept.
SWATCH = {"skin": (20, 835), "coat": (52, 680), "coat_dark": (52, 760), "shirt": (74, 632),
          "trousers": (85, 745), "shoes": (65, 807), "hair": (455, 595)}
if "paint" in opt:
    me = char.data
    uvs = me.uv_layers["UVMap"].data
    names = {grp.index: grp.name for grp in char.vertex_groups}
    hip = bone_head("Hips").z
    neck = bone_head("Neck").z
    chest = bone_head("Spine_03").z
    for poly in me.polygons:
        v0 = [uvs[li].uv.copy() for li in poly.loop_indices]
        if max(1 - uv.y for uv in v0) > .98 and min(uv.x for uv in v0) < .02:
            continue                                            # eyes keep their black
        weight = {}
        for vi in poly.vertices:
            for gw in me.vertices[vi].groups:
                weight[names[gw.group]] = weight.get(names[gw.group], 0) + gw.weight
        bone = max(weight, key=weight.get)
        c = char.matrix_world @ poly.center
        nrm = (char.matrix_world.to_3x3() @ poly.normal).normalized()
        front = nrm.y < -.35
        if min(1 - uv.y for uv in v0) > .685:
            part = "hair"
        elif bone in ("Head", "Eyes", "Eyebrows") or (bone == "Neck" and c.z > neck - .02):
            part = "skin"
        elif bone.startswith(("Hand_", "Thumb", "IndexFinger", "Finger")):
            part = "skin"
        elif bone.startswith(("Ankle", "Ball", "Toes")):
            part = "shoes"
        elif bone.startswith(("UpperLeg", "LowerLeg")) or (bone in ("Hips", "Root") and c.z < hip - .06):
            part = "trousers"
        elif abs(c.z - (hip + .02)) < .035:
            part = "coat_dark"                                  # belt
        elif front and c.z > chest - .1 and all(
                abs((char.matrix_world @ me.vertices[vi].co).x) < .02 + .1 * max(0, (char.matrix_world @ me.vertices[vi].co).z - chest + .1) / (neck - chest + .1)
                for vi in poly.vertices):
            # Open coat over a shirt collar (the coarse body cannot carry a tie).
            part = "shirt"
        else:
            part = "coat"
        x, y = SWATCH[part]
        for li in poly.loop_indices:
            uvs[li].uv = ((x + .5) / 1024, 1 - (y + .5) / 1024)

# ---- export: Synty bones -> Ashgrave joints, glTF space facing -Z
JOINT_OF = {"Root": "hips", "Hips": "hips", "Spine_01": "spine", "Spine_02": "chest", "Spine_03": "chest",
            "Clavicle_L": "chest", "Clavicle_R": "chest", "Neck": "head", "Head": "head", "Eyes": "head",
            "Eyebrows": "head", "UpperLeg_L": "thigh_l", "UpperLeg_R": "thigh_r",
            "Shoulder_L": "arm_l", "Shoulder_R": "arm_r", "Elbow_L": "fore_l", "Elbow_R": "fore_r"}
NAMES = ["hips", "spine", "chest", "head", "arm_r", "fore_r", "arm_l", "fore_l", "thigh_r", "shin_r",
         "thigh_l", "shin_l", "coat"]


def g(p):
    # Synty (as imported) faces -Y with its right at -X; n3e's right is +X facing -Z.
    return [-p.x, p.z, p.y]


def joint_for(bone):
    if bone in JOINT_OF:
        return JOINT_OF[bone]
    b = rig.data.bones[bone]
    while b.parent and b.name not in JOINT_OF:
        b = b.parent                # fingers ride the hand, feet the shin
        if b.name.startswith(("Hand_", "LowerLeg_")):
            return ("fore_" if b.name.startswith("Hand_") else "shin_") + b.name[-1].lower()
    return JOINT_OF.get(b.name, "hips")


positions = {"hips": g(bone_head("Hips")), "spine": g(bone_head("Spine_02")), "chest": g(bone_head("Spine_03")),
             "head": g(bone_head("Neck")), "arm_r": g(bone_head("Shoulder_R")), "fore_r": g(bone_head("Elbow_R")),
             "arm_l": g(bone_head("Shoulder_L")), "fore_l": g(bone_head("Elbow_L")),
             "thigh_r": g(bone_head("UpperLeg_R")), "shin_r": g(bone_head("LowerLeg_R")),
             "thigh_l": g(bone_head("UpperLeg_L")), "shin_l": g(bone_head("LowerLeg_L")), "coat": g(bone_head("Hips"))}
me = char.data
me.calc_loop_triangles()
uv = me.uv_layers["UVMap"].data
groups = {grp.index: grp.name for grp in char.vertex_groups}
to_world = char.matrix_world
to_world_n = to_world.to_3x3().inverted().transposed()
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
            vertices.append({"p": g(to_world @ v.co), "n": g((to_world_n @ n).normalized()),
                             "uv": [uv[li].uv.x, 1 - uv[li].uv.y],
                             "j": [NAMES.index(j) for j, _ in best] + [0] * (4 - len(best)),
                             "w": [w / total for _, w in best] + [0.0] * (4 - len(best))})
        corner.append(key_index[key])
    triangles.append(corner)
(out_dir / "investigator.json").write_text(json.dumps({"joints": NAMES, "positions": positions,
                                                       "vertices": vertices, "triangles": triangles}))
top = max(v["p"][1] for v in vertices)
print("SYNTY INVESTIGATOR", len(vertices), "vertices", len(triangles), "triangles", f"height {top:.3f} m")

if "preview" in opt:
    image = bpy.data.images.load(opt["preview"])
    mat = bpy.data.materials.new("preview")
    mat.use_nodes = True
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.interpolation = "Closest"
    mat.node_tree.links.new(tex.outputs["Color"], mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    me.materials.clear()
    me.materials.append(mat)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x, scene.render.resolution_y = 360, 560
    scene.world = bpy.data.worlds.new("world")
    scene.world.color = (.12, .13, .16)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 70
    for label, angle in (("front", 0), ("three-quarter", 35), ("side", 90)):
        a = math.radians(angle)
        cam.location = (4.2 * math.sin(a), -4.2 * math.cos(a), .95)
        cam.rotation_euler = (math.radians(90), 0, a)
        scene.render.filepath = str(out_dir / f"preview-{label}.png")
        bpy.ops.render.render(write_still=True)
    print("PREVIEW rendered")
