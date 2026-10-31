"""Foundation CPU regressions: identity, animation, collision, hostile source/cooked data."""

import copy, hashlib, json, math, os, pathlib, shutil, struct, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tools/assetc"))
import main as assetc
import ko


def run(*args, good=True, env=None):
    p = subprocess.run(
        list(map(str, args)), capture_output=True, text=True, env=env, timeout=30
    )
    assert (p.returncode == 0) == good, (args, p.stdout, p.stderr)
    return p.stdout


B = ROOT / "build/check"
B.mkdir(parents=True, exist_ok=True)
run("cargo", "test", "--locked")
# Fixed golden vectors independently inherited from the measured wire contract.
for binary, name in [
    ("build/client/n3e-peer", "cpp"),
    ("target/debug/n3e-server", "rust"),
]:
    run(binary, "--golden", B / name)
for mode in ["strike", "template", "present", "absent", "move", "move-mode", "action", "respawn", "life", "settlement", "private", "bag", "bag-state", "equipment", "stats", "storage", "storage-state", "storage-auth", "storage-auth-state", "friends", "friends-state", "friends-presence", "party", "party-state", "party-invitation", "party-result", "error", "discord-login", "session-login", "login-result"]:
    expected = bytes.fromhex((ROOT / f"protocol/golden-{mode}.hex").read_text())
    assert (
        (B / f"cpp-{mode}.bin").read_bytes()
        == (B / f"rust-{mode}.bin").read_bytes()
        == expected
    )
print("PASS C++/Rust protocol golden vectors")
# Codegen reproducibility for the installed protoc; Rust bindings generated twice by prost-build below.
for name in ["gen1", "gen2"]:
    (B / name).mkdir(exist_ok=True)
    run("protoc", "-I", "protocol", f"--cpp_out={B/name}", "protocol/wire.proto")
assert all(
    (B / "gen1" / p).read_bytes() == (B / "gen2" / p).read_bytes()
    for p in ["wire.pb.cc", "wire.pb.h"]
)
print("PASS C++ codegen reproducibility")
script = next((ROOT / "target/debug/build").glob("n3e-server-*/build-script-build"))
for name in ["rust-gen1", "rust-gen2"]:
    (B / name).mkdir(exist_ok=True)
    subprocess.run(
        [str(script)],
        cwd=ROOT / "server",
        env={**os.environ, "OUT_DIR": str(B / name)},
        check=True,
        capture_output=True,
    )
assert (B / "rust-gen1/n3e.rs").read_bytes() == (B / "rust-gen2/n3e.rs").read_bytes()
print("PASS Rust codegen reproducibility")
base = assetc.cook(ROOT / "tests/fixtures/legacy-demo", B / "package-a")
assert base == assetc.cook(ROOT / "tests/fixtures/legacy-demo", B / "package-b")
with tempfile.TemporaryDirectory() as td:
    src = pathlib.Path(td) / "source"
    shutil.copytree("tests/fixtures/legacy-demo", src)
    m = json.loads((src / "package.json").read_text())
    (src / "package.json").write_text(json.dumps(m, indent=4, sort_keys=True))
    assert assetc.cook(src, B / "format") == base
    m["package_version"] = "0.1.1"
    (src / "package.json").write_text(json.dumps(m))
    assert assetc.cook(src, B / "version") != base
print("PASS deterministic cooking, canonical manifest and changed identity")
cpp = run("build/client/n3e-asset-check", B / "package-a").splitlines()
rust = run(
    "target/debug/n3e-server",
    "--check-content",
    env={**os.environ, "N3E_PACKAGE": str(B / "package-a")},
).splitlines()
assert cpp[0] == rust[0] == base
for row in cpp[1:6]:
    t, *actual = map(float, row.split())
    angle = min(t, 1 - t) * math.pi / 3
    c, s = math.cos(angle), math.sin(angle)
    expected = [
        (c * 0.7 - s * 0.7) * 1.25,
        (1 + s * 0.7 + c * 0.7) * 0.8,
        0.21,
        (c * 0.5 - s * 0.4) * 1.25,
        (1 + s * 0.5 + c * 0.4) * 0.8,
        0.4,
    ]
    assert max(abs(a - b) for a, b in zip(actual, expected)) < 1e-6, (
        t,
        actual,
        expected,
    )
for c, r in zip(cpp[6:], rust[1:]):
    _, x, z, y = c.split()
    _, rx, rz, ry = r.split()
    expected = 0.2 * float(x) + 0.1 * float(z) - 0.6
    assert abs(float(y) - expected) < 1e-6 and abs(float(ry) - expected) < 1e-6
print("PASS five analytic skin/attachment poses and C++/Rust heightfield contacts")
# Invalid source cases, each in an independent complete package.
cases = {
    "cycle": lambda g: g["nodes"][1]["children"].append(0),
    "index": lambda g: g["meshes"][0]["primitives"][0].update(indices=999),
    "huge-accessor": lambda g: g["accessors"][0].update(count=1000000000),
    "traversal": lambda g: g["buffers"][0].update(uri="../outside.bin"),
    "nan": lambda g: g["nodes"][0].update(translation=[float("nan"), 0, 0]),
    "missing": lambda g: g["buffers"][0].update(uri="absent.bin"),
    "unsupported": lambda g: g.update(extensionsRequired=["unknown"]),
    "key-order": lambda g: g["animations"][0]["samplers"][0].update(
        interpolation="CUBICSPLINE"
    ),
}
for name, mutate in cases.items():
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / "source"
        shutil.copytree("tests/fixtures/legacy-demo", src)
        p = src / "fixture.gltf"
        g = json.loads(p.read_text())
        mutate(g)
        p.write_text(json.dumps(g))
        try:
            assetc.cook(src, pathlib.Path(td) / "out")
        except (ValueError, KeyError, IndexError, OSError):
            pass
        else:
            raise AssertionError(name)
print("PASS malformed source/dependency rejection", ",".join(cases))
# Corruption must fail both runtime readers before either process can admit a peer.
for file in ["scene.bin", "collision.bin", "release.bin"]:
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "package"
        shutil.copytree(B / "package-a", p)
        b = bytearray((p / file).read_bytes())
        b[0] ^= 128
        (p / file).write_bytes(b)
        run("build/client/n3e-asset-check", p, good=False)
        run(
            "target/debug/n3e-server",
            "--check-content",
            good=False,
            env={**os.environ, "N3E_PACKAGE": str(p)},
        )
print("PASS client/server reject corrupted package data")
# Original synthetic legacy layout; no third-party asset is copied or required.
mesh = (
    struct.pack("<i", 0)
    + struct.pack("<6i", 0, 0, 3, 3, 3, 3)
    + b"".join(
        struct.pack("<8f", *v)
        for v in [
            [0, 0, 1, 0, 0, -1, 0, 0],
            [2, 0, 1, 0, 0, -1, 1, 0],
            [0, 3, 1, 0, 0, -1, 0, 1],
        ]
    )
    + struct.pack("<3Hi", 0, 1, 2, 0)
)
p = B / "original.n3pmesh"
p.write_bytes(mesh)
converted = ko.import_mesh(p, 0.5)
assert converted["vertices"][1][:3] == [1, 0, -0.5] and converted["indices"] == [
    0,
    2,
    1,
]
for bad in [mesh[:-1], mesh + b"variant", mesh[:4] + struct.pack("<i", 1) + mesh[8:]]:
    p.write_bytes(bad)
    try:
        ko.import_mesh(p, 0.5)
    except ValueError:
        pass
    else:
        raise AssertionError("KO invalid accepted")
p.write_bytes(mesh)
print(
    "PASS synthetic KO static reflection/unit calibration, malformed/unsupported rejection"
)
print(run(sys.executable, "tests/asset_features.py").strip())
print("PASS CPU foundation suite")
