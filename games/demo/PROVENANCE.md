# Demo profile, KO-11 revision 1

This is original n3e content, not a matched historical KO release. The selected
ordinary unarmed character / hostile melee scenario follows
KO-PROFILE, accepted KO-01–10 and
KO-REWARDS. `package.json` owns all
numeric choices; the engine contains no demo IDs or asset paths for dispatch.

| Data | Selected values and origin |
|---|---|
| Movement | Walk/run/backward 1.5/4.5/1.5 m/s; binary ordinary values with accepted adopted-unit deviation D-024. Synthetic radius .2, height 1.6, step .25m. |
| Camera | 25° initial, 10–70° pitch, 7m initial/2–10m zoom, .8×height focus; KO-02 traces. Pixel sensitivities .006/.005, wheel .7, clearance .2, facing-relative controls and .1s hold are accepted adaptations D-025. |
| Basic attack | Zero resource, 20-tick interval; synthetic 1m actor/target radii, no reach, .7 facing dot. D-026 distinguishes client observation from stronger n3e server range checks. |
| Damage | `contested_melee_v1`; player attack/defense/accuracy/evasion 36/20/50/100, NPC 18/40/50/100. Synthetic KO-04 stats, binary-derived fixed formula, adapted RNG D-027. |
| Character | 100 HP, 20 resource. Original playable balance, fixed at all ten levels. No spending, equipment, stat growth or level-up heal. |
| NPC | 60 HP, speed 3, attack range 1, aggro 3, home leash 8m. Two spawns (-5,-5)/(5,-5). KO-06 small HP; original demo aggro/balance. One ordinary hostile template, no table-ID claim. |
| AI | Scan/acquire/stuck/chase/return/recovery 10/10/40/400/200/40 ticks, from accepted KO-05 lab. Binary farthest-first acquisition and retaliation; deadlines/heal/teleport are adaptations D-028. |
| Life | 60-tick player delay, 40-tick corpse, 120-tick NPC respawn; accepted synthetic KO-06 defaults D-029/030. Player death is durable; no protection or penalty. |
| Progression | Original ten-level thresholds [0,20,50,90,140,200,270,350,440,540], level-1 NPC/base XP 10, exact 50m eligibility. D-032/033. |
| Loot | One guaranteed token, owner exclusive, 3m claim, 120s DB-clock TTL, eight-item capacity starting empty. Capacity is original demo balance; no item disposal UI. Full bag does not stop XP. D-034. |
| Legacy fields | Fixed damage 10/NPC 6, cost-independent resource regen 20 ticks, `respawn_ticks` 60, `reward_xp` 10, `level_xp` 20 and generic range 1.1 remain required compatibility fields. Opt-in damage, life and progression policies take precedence; level_xp remains the explicit conversion divisor. |
| Terrain | Original flat 48×48m heightfield, no imported terrain; shared collision, player spawn (0,0), 32m interest cells. |
| Presentation | Original closed-box two-joint figure, diagnostic four-colour atlas, eleven clips, .2s blends and 1s clip duration. Synthetic markers at .5s for attacks. Figures deliberately do not depict Tuarek/worm anatomy. |
| HUD | Original bitmap alphabet from `client/render/hud.h`, generated panels, supported bindings only. No font download or image tool is needed. |

Regenerate distributable source visuals with
`python tools/assetc/demo_presentation.py`; `tests/demo.py` compares every generated
source byte. The generator changes only original demo visual source files. Its
legacy input is preserved unchanged under `tests/fixtures/legacy-demo`.

Optional `python tools/assetc/demo_variants.py --ko` reads only already-local
`assets/ko`: male Tuarek race 2 face/hair 00, worm clips and Karus
HUD. Source hashes, selected clips and conversion metadata are written to ignored
`build/ko-11/demo-ko/provenance.json`. All authoritative policy files and collision
must be byte-identical to demo; animation timings/artwork are cosmetic overrides.
Reference revisions/hashes and uncertainty are recorded in KO-PROFILE. No reference
checkout is modified; no proprietary asset is distributed or downloaded.

The original `demo-alt` fixture uses namespace `alternate`, blue/red-swapped actor
textures, 3m/s running, 160 HP, 5m camera and 15 base XP. It is a small package
boundary check with the same executable hashes, not original Phase 5 delivery.
