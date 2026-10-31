"""Blender (headless): render characters side by side under identical settings.

    blender -b --factory-startup --python tools/assetc/blender/compare_characters.py -- \
        OUT_DIR LABEL=path.gltf [LABEL=path.gltf ...]

Each glTF (n3e characters face -Z, glTF +Y up) is imported, scaled to the same
1.8 m height, and rendered front / three-quarter / side with flat texture
shading (roughly how the game draws baked character textures). Prints triangles,
texture size, surface area and texel density (texels per metre) as JSON. Local
comparison only: renders of reference characters stay in build/ and are never
committed or fed to generators.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
out_dir = Path(args[0])
out_dir.mkdir(parents=True, exist_ok=True)
items = [a.split("=", 1) for a in args[1:]]
stats = {}
for label, path in items:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in scene.objects if o.type == "MESH"]
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    zs, tris, area, uv_area, tex = [], 0, 0.0, 0.0, None
    for o in meshes:
        me = o.evaluated_get(deps).to_mesh()
        me.calc_loop_triangles()
        tris += len(me.loop_triangles)
        uv = me.uv_layers.active.data if me.uv_layers else None
        for t in me.loop_triangles:
            a, b, c = (o.matrix_world @ me.vertices[i].co for i in t.vertices)
            area += (b - a).cross(c - a).length / 2
            if uv:
                p, q, r = (Vector((*uv[li].uv, 0)) for li in t.loops)
                uv_area += (q - p).cross(r - p).length / 2
        zs += [(o.matrix_world @ v.co).z for v in me.vertices]
        for m in o.data.materials:
            for n in (m.node_tree.nodes if m and m.use_nodes else []):
                if n.type == "TEX_IMAGE" and n.image:
                    tex = n.image.size[:]
    height = max(zs) - min(zs)
    texels = tex[0] * tex[1] * uv_area if tex else 0
    stats[label] = {"triangles": tris, "texture": tex, "height_m": round(height, 3),
                    "surface_m2_at_1_8m": round(area * (1.8 / height) ** 2, 3),
                    "texels_per_m": round(math.sqrt(texels / (area * (1.8 / height) ** 2)), 1) if texels else None}
    root = bpy.data.objects.new("root", None)
    scene.collection.objects.link(root)
    for o in scene.objects:
        if o.parent is None and o is not root:
            o.parent = root
    root.scale = [1.8 / height] * 3
    root.location.z = -min(zs) * 1.8 / height
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x, scene.render.resolution_y = 300, 480
    scene.world = bpy.data.worlds.new("w")
    scene.world.color = (.12, .13, .16)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 70
    for view, angle in (("front", 0), ("three-quarter", 35), ("side", 90)):
        # glTF -Z (the facing) imports as Blender +Y.
        a = math.radians(angle)
        cam.location = (4.4 * math.sin(a), 4.4 * math.cos(a), 1.0)
        cam.rotation_euler = (math.radians(90), 0, math.radians(180) - a)
        scene.render.filepath = str(out_dir / f"{label}-{view}.png")
        bpy.ops.render.render(write_still=True)
print("COMPARE", json.dumps(stats))
