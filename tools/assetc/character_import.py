#!/usr/bin/env python3
"""Reduce Blender glTF character exports to the strict `gltf.cook` subset.

Pairs with `tools/assetc/blender/export_character.py`. For each exported clip:
one mesh, skin, primitive and material; exactly POSITION/NORMAL/TEXCOORD_0/
JOINTS_0/WEIGHTS_0; no samplers or extensions; LINEAR keys; the external texture
replaced by an RGB8 PNG without ancillary chunks. The skeleton root is turned to
face -Z, the direction n3e characters walk. Returns each clip's duration, which
the package's animation metadata must match.
"""
import json
import math
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BLENDER = ROOT / ".cache/tools/blender/blender"
KEEP = {"POSITION", "NORMAL", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0"}


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz]


def texture(source, out, size=256, recolor=None, painted=False):
    """Downsample to a KO-sized RGB8 texture (point-sampled at runtime).

    `recolor=(lo, hi, hue, saturation)` moves HSL hues in [lo, hi] to `hue` and
    scales their saturation, a palette swap for gradient-atlas characters.
    """
    swap = []
    if recolor:
        lo, hi, hue, sat = recolor
        swap = ["-colorspace", "HSL", "-channel", "R", "-fx", f"(u>{lo}&&u<{hi})?{hue}:u",
                "-channel", "G", "-fx", f"(p.r>{hue - .001}&&p.r<{hue + .001})?u*{sat}:u", "+channel", "-colorspace", "sRGB"]
    # `painted` pushes a baked texture towards KO's hand-painted look: more
    # contrast and saturation, then a sharpen after downsampling.
    paint = ["-sigmoidal-contrast", "3.5x45%", "-modulate", "100,125"] if painted else []
    sharp = ["-unsharp", "0x0.8+0.8+0.02"] if painted else []
    subprocess.run(["magick", str(source), "-alpha", "off", *swap, *paint, "-resize", f"{size}x{size}", *sharp,
                    "-define", "png:exclude-chunks=all", "PNG24:" + str(out)], check=True)


def retime(g, path, factor):
    """Scale every animation key time by `factor` (0.5 plays twice as fast)."""
    import struct
    blob = bytearray((path.parent / g["buffers"][0]["uri"]).read_bytes())
    inputs = {s["input"] for s in g["animations"][0]["samplers"]}
    for index in inputs:
        accessor = g["accessors"][index]
        view = g["bufferViews"][accessor["bufferView"]]
        start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        count = accessor["count"]
        times = struct.unpack_from(f"<{count}f", blob, start)
        struct.pack_into(f"<{count}f", blob, start, *[t * factor for t in times])
        accessor["min"], accessor["max"] = [times[0] * factor], [times[-1] * factor]
    (path.parent / g["buffers"][0]["uri"]).write_bytes(bytes(blob))


def reduce(path, texture_uri, turn=math.pi, speed=1.0):
    g = json.loads(path.read_text())
    g.pop("samplers", None)
    g.pop("extensionsUsed", None)
    g.pop("extensionsRequired", None)
    g["textures"] = [{"source": 0}]
    g["images"] = [{"uri": texture_uri}]
    g["materials"] = [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}]
    if len(g["meshes"]) != 1 or len(g["meshes"][0]["primitives"]) != 1:
        raise ValueError(f"{path.name}: expected one mesh primitive")
    prim = g["meshes"][0]["primitives"][0]
    prim["attributes"] = {k: v for k, v in prim["attributes"].items() if k in KEEP}
    if set(prim["attributes"]) != KEEP:
        raise ValueError(f"{path.name}: missing skinning attributes {KEEP - set(prim['attributes'])}")
    prim["material"] = 0
    prim.pop("extensions", None)
    for accessor in g["accessors"]:
        accessor.pop("normalized", None) if not accessor.get("normalized") else None
    for node in g["nodes"]:
        node.pop("extensions", None)
        node.pop("extras", None)
    g.pop("extras", None)
    # Turn the root (the armature node) to face -Z.
    children = {c for n in g["nodes"] for c in n.get("children", [])}
    roots = [i for i in range(len(g["nodes"])) if i not in children]
    for i in roots:
        node = g["nodes"][i]
        if "mesh" in node:
            continue
        node["rotation"] = qmul([0, math.sin(turn / 2), 0, math.cos(turn / 2)], node.get("rotation", [0, 0, 0, 1]))
    duration = 0.0
    if len(g.get("animations", [])) == 1 and speed != 1.0:
        retime(g, path, 1 / speed)
    if len(g.get("animations", [])) != 1:
        raise ValueError(f"{path.name}: expected exactly one animation")
    for sampler in g["animations"][0]["samplers"]:
        sampler["interpolation"] = "LINEAR"
        duration = max(duration, g["accessors"][sampler["input"]]["max"][0])
    g["animations"][0].pop("name", None)
    path.write_text(json.dumps(g))
    return duration


def export(source, out_dir, prefix, clips, keep_rigid=(), texture_source=None, size=256, recolor=None,
           speeds=None, painted=False):
    """Run Blender for `clips` ({state: action}) and reduce every result.

    Returns {state: duration}. The texture is written once as PREFIX.png.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping = ",".join(f"{s}={a}" for s, a in clips.items())
    run = subprocess.run([str(BLENDER), "-b", "--factory-startup", "--python",
                          str(ROOT / "tools/assetc/blender/export_character.py"), "--",
                          str(source), str(out_dir), prefix, mapping, ",".join(keep_rigid)],
                         capture_output=True, text=True)
    if run.returncode or "EXPORTED" not in run.stdout:
        raise RuntimeError(run.stdout[-3000:] + run.stderr[-3000:])
    texture(texture_source, out_dir / f"{prefix}.png", size, recolor, painted)
    durations = {}
    for state in clips:
        durations[state] = reduce(out_dir / f"{prefix}-{state}.gltf", f"{prefix}.png",
                                  speed=(speeds or {}).get(state, 1.0))
    return durations


if __name__ == "__main__":
    import sys
    source, out, prefix = sys.argv[1:4]
    print(export(source, out, prefix, dict(p.split("=") for p in sys.argv[4].split(",")),
                 texture_source=sys.argv[5]))
    shutil.os.sys.exit(0)
