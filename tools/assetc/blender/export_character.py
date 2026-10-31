"""Blender (headless) half of the character pipeline: one clip per glTF.

    blender -b --factory-startup --python tools/assetc/blender/export_character.py -- \
        SOURCE.glb OUT_DIR PREFIX 'state=Action,state=Action,...' [keep_rigid_mesh,...]

Imports a rigged source (for example a CC0 KayKit character), keeps only the
skinned body meshes plus any named rigid parts (re-skinned to their parent bone),
joins them into one mesh with one material, limits influences to four, and exports
`OUT_DIR/PREFIX-STATE.gltf` for every state with exactly that action active.
`tools/assetc/character_import.py` then reduces each export to the strict
`gltf.cook` subset. Nothing here is package-specific.
"""
import json
import sys
from pathlib import Path

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
source, out_dir, prefix, mapping = args[0], Path(args[1]), args[2], args[3]
keep_rigid = set(filter(None, args[4].split(","))) if len(args) > 4 else set()
clips = [pair.split("=", 1) for pair in mapping.split(",")]
out_dir.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=source)
armature = next(o for o in bpy.data.objects if o.type == "ARMATURE")

# Keep skinned meshes and requested rigid parts; drop weapons, helpers and props.
keep = []
for o in list(bpy.data.objects):
    if o.type != "MESH":
        continue
    rigid = o.parent is armature and o.parent_bone and not o.vertex_groups
    if o.vertex_groups or (rigid and o.name in keep_rigid):
        keep.append(o)
    else:
        bpy.data.objects.remove(o, do_unlink=True)
for o in keep:
    if not o.vertex_groups:
        # A part rigidly parented to a bone becomes skinned to that bone.
        bone = o.parent_bone
        world = o.matrix_world.copy()
        o.parent = armature
        o.parent_type = "OBJECT"
        o.matrix_world = world
        group = o.vertex_groups.new(name=bone)
        group.add(range(len(o.data.vertices)), 1.0, "REPLACE")
        mod = o.modifiers.new("Armature", "ARMATURE")
        mod.object = armature

# One texture: faces using another material (glowing eyes) sample the
# brightest-red texel instead, then every face uses the first textured material.
textured = next(m for o in keep for m in o.data.materials if m and m.use_nodes and any(
    n.type == "TEX_IMAGE" for n in m.node_tree.nodes))
image = next(n.image for n in textured.node_tree.nodes if n.type == "TEX_IMAGE")
w, h = image.size
px = list(image.pixels)
best = max(range(w * h), key=lambda i: px[4 * i] - (px[4 * i + 1] + px[4 * i + 2]) / 2)
glow_uv = ((best % w + .5) / w, (best // w + .5) / h)
for o in keep:
    uv = o.data.uv_layers.active.data
    for poly in o.data.polygons:
        material = o.data.materials[poly.material_index] if o.data.materials else None
        if material is not textured:
            for li in poly.loop_indices:
                uv[li].uv = glow_uv
    o.data.materials.clear()
    o.data.materials.append(textured)

bpy.ops.object.select_all(action="DESELECT")
for o in keep:
    o.select_set(True)
bpy.context.view_layer.objects.active = keep[0]
if len(keep) > 1:
    bpy.ops.object.join()
body = bpy.context.view_layer.objects.active
body.name = prefix + "_body"
bpy.ops.object.vertex_group_limit_total(limit=4)
bpy.ops.object.vertex_group_normalize_all(lock_active=False)
for extra in list(body.data.uv_layers)[1:]:
    body.data.uv_layers.remove(extra)
for attr in [a.name for a in body.data.color_attributes]:
    body.data.color_attributes.remove(body.data.color_attributes[attr])

props = {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
report = {"source": source, "texture": image.filepath or image.name, "clips": {}}
for state, action_name in clips:
    # "*" selects a file's only action (for one-clip-per-file sources such as Meshy).
    action = bpy.data.actions[0] if action_name == "*" else bpy.data.actions[action_name]
    armature.animation_data_create()
    armature.animation_data.action = action
    if hasattr(armature.animation_data, "action_slot") and getattr(action, "slots", None):
        armature.animation_data.action_slot = action.slots[0]
    start, end = int(action.frame_range[0]), int(action.frame_range[1])
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = start, max(end, start + 1)
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    body.select_set(True)
    options = dict(filepath=str(out_dir / f"{prefix}-{state}.gltf"), export_format="GLTF_SEPARATE",
                   use_selection=True, export_animation_mode="ACTIVE_ACTIONS", export_force_sampling=True,
                   export_frame_step=1, export_optimize_animation_size=False, export_anim_slide_to_zero=True,
                   export_image_format="NONE", export_tangents=False, export_morph=False, export_lights=False,
                   export_cameras=False, export_extras=False, export_yup=True, export_skins=True,
                   export_all_influences=False, export_def_bones=False, export_vertex_color="NONE",
                   export_reset_pose_bones=True)
    bpy.ops.export_scene.gltf(**{k: v for k, v in options.items() if k in props or k == "filepath"})
    report["clips"][state] = {"action": action_name, "frames": [start, end], "fps": bpy.context.scene.render.fps}
(out_dir / f"{prefix}-export.json").write_text(json.dumps(report, indent=2))
print("EXPORTED", prefix, len(clips), "clips; joints", len(armature.data.bones), "tris",
      sum(len(p.vertices) - 2 for p in body.data.polygons))
