"""The player client's release archive (specs/06-cd.md "build", spec 04).

  python tools/package_client.py BUILD_DIR OUT.tar.zst

Writes `n3e-client` (`n3e-client.exe` on Windows) at the archive's top level, which
is where the Launcher runs it from (client/<version>/). The Windows client is one
static .exe (vcpkg triplet x64-windows-static). The Linux client carries the shared
libraries a stock distribution lacks (SDL3, protobuf and abseil), found through
its RUNPATH $ORIGIN; everything else (glibc, libstdc++, OpenSSL 3, libGL) is the
system's. Prints the archive's sha256 and size for the manifest.
"""
import hashlib
import io
import re
import subprocess
import sys
import tarfile
from pathlib import Path

BUNDLED = re.compile(r"^lib(SDL3|protobuf|absl_|utf8_)")


def bundled_libraries(binary):
    """The non-stock shared objects `binary` loads, as (name, path)."""
    out = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, check=True).stdout
    libraries = []
    for line in out.splitlines():
        m = re.match(r"\s*(\S+) => (/\S+)", line)
        if m and BUNDLED.match(m.group(1)):
            libraries.append((m.group(1), Path(m.group(2)).resolve()))
        elif "not found" in line:
            raise SystemExit(f"package_client: {binary} needs {line.strip()}")
    return libraries


def main():
    if len(sys.argv) != 3 or not sys.argv[2].endswith(".tar.zst"):
        raise SystemExit(__doc__)
    build, target = Path(sys.argv[1]), Path(sys.argv[2])
    windows = (build / "n3e-client.exe").is_file()
    exe = build / ("n3e-client.exe" if windows else "n3e-client")
    if not exe.is_file():
        raise SystemExit(f"package_client: no {exe}")
    entries = [(exe.name, exe.read_bytes(), 0o755)]
    if not windows:
        dynamic = subprocess.run(["readelf", "-d", str(exe)], capture_output=True, text=True, check=True).stdout
        if "$ORIGIN" not in dynamic:
            raise SystemExit(f"package_client: {exe} has no RUNPATH $ORIGIN for its bundled libraries")
        entries += [(name, path.read_bytes(), 0o644) for name, path in bundled_libraries(exe)]
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:zst") as tar:
        for name, data, mode in entries:
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            tar.addfile(info, io.BytesIO(data))
    data = raw.getvalue()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    for name, _, _ in entries:
        print(f"  {name}")
    print(f"{target} sha256={hashlib.sha256(data).hexdigest()} size={len(data)}")


main()
