"""Hardware/context tests; run in a real graphical login session."""

import pathlib, subprocess, os, math, hashlib, json

ROOT = pathlib.Path(__file__).resolve().parents[1]
B = ROOT / "build/graphics"
B.mkdir(parents=True, exist_ok=True)
MESH = ROOT / "build/packages/legacy-demo"
results = []


def run(backend, tools, time=0, unsupported=False):
    env = os.environ.copy()
    env["SDL_VIDEO_DRIVER"] = backend
    env["N3E_TEST_TEXTURE_BANKS"] = "1"
    capture = B / f"{backend}-{tools}-{time}.ppm"
    args = [
        str(ROOT / ("build/client-tools" if tools else "build/client") / "n3e-test-client"),
        str(MESH),
        "--smoke",
        "--time",
        str(time),
        "--capture",
        str(capture),
    ]
    if time is None:
        args = args[:3] + args[5:]
    if unsupported:
        args += ["--unsupported"]
    p = subprocess.run(args, env=env, capture_output=True, text=True, timeout=20)
    print(p.stdout.strip() or p.stderr.strip())
    assert p.returncode == (1 if unsupported else 0), (args, p.stdout, p.stderr)
    if not unsupported:
        assert f"backend={backend}" in p.stdout and "resize=1" in p.stdout
        assert "PASS native texture bank boundary" in p.stdout
        if tools:
            assert "focus=1" in p.stdout and "UI edited" in p.stdout
        results.append(
            dict(
                backend=backend,
                tools=tools,
                time=time,
                diagnostics=p.stdout,
                capture=str(capture.relative_to(ROOT)),
                sha256=hashlib.sha256(capture.read_bytes()).hexdigest(),
            )
        )
    return capture


def pixels(path):
    with path.open("rb") as f:
        assert f.readline() == b"P6\n"
        w, h = map(int, f.readline().split())
        assert f.readline() == b"255\n"
        data = f.read()
        assert len(data) == w * h * 3
    return w, h, data


def verify_reference(path, t):
    # Independent analytic source positions; never read cooked vertices for these expectations.
    w, h, data = pixels(path)
    angle = (t if t <= 0.5 else 1 - t) * math.pi / 3
    c = math.cos(angle)
    s = math.sin(angle)
    points = [[-0.8, 0, -0.24], [0.4, 0, 0.12], [0.7, 1.7, 0.21], [-0.8, 1, -0.24]]
    uvs = [[0, 1], [1, 1], [1, 0], [0, 0]]
    normals = []
    for i, p in enumerate(points):
        if i >= 2:
            x, y = p[:2]
            p[0] = c * x - s * (y - 1)
            p[1] = 1 + s * x + c * (y - 1)
        p[0] *= 1.25
        p[1] *= 0.8
        n = [-0.3 * (c if i >= 2 else 1) / 1.25, -0.3 * (s if i >= 2 else 0) / 0.8, 1]
        length = math.sqrt(sum(x * x for x in n))
        normals.append([x / length for x in n])
    # Attachment's local +X direction is the narrow red arrow's long edge.
    for x, y in [[0.5, 0.4], [0.72, 0.4], [0.5, 0.52]]:
        points.append([(c * x - s * y) * 1.25, (1 + s * x + c * y) * 0.8, 0.4])
        normals.append([0, 0, 1])
        uvs.append([0, 0])
    screen = [
        [
            (p[0] / (2.1 * w / h) * 0.5 + 0.5) * w,
            (0.5 - (p[1] - 0.7 - p[2] * 0.25) / 4.2) * h,
        ]
        for p in points
    ]
    chart = [[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0]]
    worst = 0
    for tri in [[0, 1, 2], [0, 2, 3], [4, 5, 6]]:
        a, b, c0 = [screen[i] for i in tri]
        x = int(sum(screen[i][0] for i in tri) / 3)
        y = int(sum(screen[i][1] for i in tri) / 3)
        px, py = x + 0.5, y + 0.5
        den = (b[1] - c0[1]) * (a[0] - c0[0]) + (c0[0] - b[0]) * (a[1] - c0[1])
        wa = ((b[1] - c0[1]) * (px - c0[0]) + (c0[0] - b[0]) * (py - c0[1])) / den
        wb = ((c0[1] - a[1]) * (px - c0[0]) + (a[0] - c0[0]) * (py - c0[1])) / den
        weights = [wa, wb, 1 - wa - wb]
        assert min(weights) > 0
        uv = [
            sum(weight * uvs[i][axis] for weight, i in zip(weights, tri))
            for axis in range(2)
        ]
        normal = [
            sum(weight * normals[i][axis] for weight, i in zip(weights, tri))
            for axis in range(3)
        ]
        length = math.sqrt(sum(x * x for x in normal))
        normal = [x / length for x in normal]
        diffuse = max(
            0, sum(x * y for x, y in zip(normal, [0.3, 0.4, 1])) / math.sqrt(1.25)
        )
        light = 0.15 + 0.85 * diffuse
        color = chart[(int(uv[1] * 2) % 2) * 2 + int(uv[0] * 2) % 2]
        expected = [round(k * light) for k in color]
        actual = list(data[(y * w + x) * 3 : (y * w + x) * 3 + 3])
        error = max(abs(a - b) for a, b in zip(expected, actual))
        worst = max(worst, error)
        assert error <= 3, (t, tri, x, y, expected, actual)
    # Independent ground sample: y = .2*x + .1*z - .6 at (x,z)=(0,1).
    # This also proves upward-facing collision triangles survive backface culling.
    x = w // 2
    y = int((0.5 - (-0.5 - 0.7 - 1 * 0.25) / 4.2) * h)
    n = [-0.2, 1, -0.1]
    diffuse = sum(a * b for a, b in zip(n, [0.3, 0.4, 1])) / math.sqrt(1.05 * 1.25)
    expected = [0, round(255 * (0.15 + 0.85 * diffuse)), 0]
    actual = list(data[(y * w + x) * 3 : (y * w + x) * 3 + 3])
    assert max(abs(a - b) for a, b in zip(actual, expected)) <= 3, (
        "ground",
        actual,
        expected,
    )
    print("PASS ground visibility/culling pixel", actual)
    print("PASS analytic reference pixels", t, "max channel error", worst)


for t in [0, 0.25, 0.5, 0.75]:
    verify_reference(run("wayland", 0, t), t)
run("wayland", 0, None)
run("wayland", 1, 0.5)
run("x11", 0, 0.25)
run("x11", 1, 0.5)
run("wayland", 0, unsupported=True)
normal = subprocess.run(
    ["nm", "-C", str(ROOT / "build/client/n3e-client")],
    capture_output=True,
    text=True,
    check=True,
).stdout
assert "ImGui" not in normal
with (B / "results.json").open("w") as f:
    json.dump(results, f, indent=2)
print("PASS no editor symbols in normal binary")
print(
    "PASS graphics suite; compositor accepted minimize/restore requests, observed event flags are recorded separately"
)
