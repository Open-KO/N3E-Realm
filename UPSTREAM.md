# Pinned inputs

Everything this repository depends on that is not in this repository, and the one
third-party source vendored in it.

| Input | Pin | Where it goes |
|---|---|---|
| n3e (engine origin) | `aaefdab4182abc8f83b092dc23c29edc6f860316` | imported into this repo once, without history (specs/09-migration.md); nothing is fetched from it |
| KO client assets | see below | `assets/ko/` (git-ignored), via `tools/fetch-ko-assets.sh` |
| imgui | v1.91.9b @ `f5befd2d29e66809cd1110a152e375a7f1981f06` | `.cache/tools/imgui` via `tools/bootstrap.sh` |
| Rust toolchain | 1.85.1 (`rust-toolchain.toml`) | `.cache/tools` via `tools/bootstrap.sh` |
| minimp3 | `lieff/minimp3` @ `ea99364f61c14656440e8d77e9c233ccf3124633`, `minimp3.h` sha256 `57e437c5c1f0e8b243885d3929c8973b5e6c778451e0100ab4251d19915cb3ad`, `LICENSE` (CC0 1.0) sha256 `6a1ee543e5282cd9061881edf462e6fdab181f328da71fc2c9a6950a80e94d01` | vendored unmodified in `client/third_party/minimp3/` (the front-end music decoder, RQ-018, `specs/QUESTIONS.md` Q69) |

## KO client assets

Machine-readable lines; `tools/fetch-ko-assets.sh` parses them.

KO assets: ko-client-assets-3e4602ede3bb833f72d7837b225bfef26b3ca9a24fa9461eb4d27934c2e07553.tar.zst
KO assets URL: https://github.com/Open-KO/N3E-Realm/releases/download/content-store/ko-client-assets-3e4602ede3bb833f72d7837b225bfef26b3ca9a24fa9461eb4d27934c2e07553.tar.zst

Provenance: the `assets/Client` tree of `Open-KO/KnightOnline` @ `7d6cf81093e142c928c2ac9510512b2b182178b5`, archived with
`tar -c --sort=name --owner=0 --group=0 --numeric-owner --mtime=2026-01-01 . | zstd -19`
(deterministic; 738 MiB extracted, 279 MiB compressed). The tarball is not in git. Until
the `content-store` Release exists, set `N3E_KO_TARBALL=/path/to/the/file` for the
fetch script.
