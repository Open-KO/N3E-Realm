# Optional camera and navigation presentation (N3V1, N3V2)

A source package may add a `camera` object independently of imported player/HUD
assets. Without melee, camera packages require **engine_version 3**; protocol_version remains 1
for legacy gameplay or 2 for N3G3 movement. Without melee, releases without camera retain engine
1/1 or 2/2 and their prior defaults/input selection. Both C++ and Rust require
`camera.bin` exactly when engine is 3, validate its structure, and include it in
release identity. Optional [melee](melee.md) instead requires engine 4, where camera
data is independently optional. Older binaries reject unsupported engine versions.
No wire or database change.

The cooker writes magic `N3V1`, fourteen little-endian float32 values in the order
below, then one little-endian uint32 boolean. Exact length: 64 bytes. All values
must be finite; missing/extra keys, invalid intervals and trailing bytes fail.

| Field | Bounds | KO-02 laboratory value |
|---|---|---|
| pitch | pitch_min..pitch_max | 25° in radians |
| pitch_min | .05..1.4 radians | 10° in radians |
| pitch_max | pitch_min..1.4 radians | 70° in radians |
| distance | distance_min..distance_max | 7m |
| distance_min | .5..32m | 2m |
| distance_max | distance_min..32m | 10m |
| focus_height | 0..3m | 0m |
| focus_scale | 0..1 | .8 |
| yaw_per_pixel | .0001...05 radians/logical pixel | .006 |
| pitch_per_pixel | .0001...05 radians/logical pixel | .005 |
| zoom_per_step | .01..4m/wheel step | .7 |
| clearance | .1...5m | .2 |
| turn_rate | .1..6.3 radians/second | π/3 |
| hold_delay | 0..1 seconds | .1 |
| facing_relative | boolean; cooked 0 or 1 | true |

## KO mode-3 extension (N3V2, PQ-012)

Four more keys, all present or all absent (D-143).
Absent, the block cooks to `N3V1` as above. Present, the cooker writes magic
`N3V2`, the same fourteen floats and boolean, then a little-endian uint32 drag
axis and three float32 values. Exact length: 80 bytes. Both readers accept
`N3V1` and `N3V2`; the server checks bounds and otherwise ignores the file.

| Field | Bounds | KO package (`games/moradon/camera.json`) |
|---|---|---|
| drag_vertical | `pitch` or `distance`; cooked 0 or 1 | `distance` |
| distance_per_pixel | .0001..0.5 m/logical pixel | 0.08π/30 ≈ .0083776 |
| key_pitch_rate | 0..6.3 radians/second; 0 is off | π/4 |
| edge_yaw_rate | 0..6.3 radians/second; 0 is off | 2 |

With `distance`, vertical right-drag moves the camera away as the cursor moves
down, within distance_min..distance_max, and leaves the pitch alone (KO
`005e3e20` → `0063e2e0`). The input map's held actions `camera_pitch_up` and
`camera_pitch_down` raise and lower the pitch at key_pitch_rate, raise winning
when both are held, and stop while a text field has focus (KO Home/End,
`005c6990`). The cursor on the outermost column of the focused window turns the
camera at edge_yaw_rate, the left edge as a drag to the left; it does not
during a right-drag. That is a gap: KO still turns there on drag frames whose
cursor rests on a border column (D-143, PQ-160). The KO package overrides the copied camera block with
these values and KO's 0.02π/30 ≈ .0020944 rad yaw per pixel: KO's per-frame
drag factors at its nominal 1/30 s frame time, a fixed per-pixel rate where KO
scales by the frame time (BINARY-POLICY, "Right-drag frame-time scaling
correction"). The demo package and the KO-02 laboratory carry no extension.

Focus Y is predicted/smoothed feet Y + focus_height + focus_scale × package
movement height (or 1.6m without a movement policy). This uses the approved
synthetic body height, not animated mesh bounds. Facing-relative input uses A/D
turn and W/S travel; false uses camera-relative WASD. Held ground navigation,
right-drag yaw/pitch (or yaw/distance under N3V2), wheel zoom and the N3V2 pitch
keys and screen edges are the supported input vocabulary; Esc no
longer cancels movement (PQ-010: KO's Esc branch never touches it). These are presentation/input choices, not authoritative movement rules.

The renderer retains its 60° vertical FOV and .05m near plane. The desired zoom
distance survives obstruction. A continuous segment clips against each static
collision triangle expanded by the clearance radius (increased to enclose the
near-plane corners for wide windows). This conservative triangular prism can
retract early near corners. It cannot tunnel through a thin triangle; checks are
bounded at five clipping planes per cooked triangle, at most 65,536 triangles.
Terrain and props use the same collision triangles as KO-01 movement, with no new
collision asset or simulation change. No broad-phase performance claim is made.
Since PQ-215 (D-158) the sweep tests only the triangles within the radius plus
1 m of the segment, from the same gather as movement (an N3C2 heightfield
included). Only the prism's early corner retraction from a triangle farther away
than that is lost: 6 of 20,000 random sweeps on the local Moradon package.

Obstruction retracts immediately and restores desired distance when clear. No
camera spring interpolates through collision. A focus already overlapping geometry
fails closed at zero boom; pathological embedded spawns/oversized focus are not
repaired. The lab's supported actor positions and height do not overlap its props.
Ground picking finds the nearest triangle and only accepts a surface within the
existing 45° walking-slope bound; a nearer wall blocks picking through it. This
supplies a destination to the existing movement solver, not pathfinding.

KO-02 evidence separates
reference findings, adopted controls and original collision implementation.
