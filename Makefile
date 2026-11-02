TOOLS ?= 0
GAME ?= demo
JOBS ?= 4
BUILD := build/client$(if $(filter 1,$(TOOLS)),-tools,)
.PHONY: all client server assets test graphical codegen
all: client
client:
	cmake -S . -B $(BUILD) -DN3E_TOOLS=$(if $(filter 1,$(TOOLS)),ON,OFF) -DIMGUI_DIR="$(IMGUI)" -DCMAKE_BUILD_TYPE=RelWithDebInfo
	cmake --build $(BUILD) -j $(JOBS)
server:
	cargo build --locked
assets:
	python tools/assetc/main.py games/$(GAME) build/packages/$(GAME)
.PHONY: ko-assets realm-assets
# Raw KO client tree, pinned by sha256 in UPSTREAM.md; fetched, never committed.
ko-assets:
	tools/fetch-ko-assets.sh
# The realm's package (specs/10-content.md): the Moradon bake, zone key 210, with the
# games/moradon feature set, from the pinned client tree only. Prints the package hash.
realm-assets: ko-assets
	python tools/assetc/ko_bake.py 210 --features --into=build
codegen:
	mkdir -p build/generated
	protoc -I protocol --cpp_out=build/generated protocol/wire.proto
# make test is test-fast, then test-slow: SLOW_TESTS are the scripts that take
# minutes and catch little per change (the KO bake pins: about 7 of make test's 10
# minutes on 2026-11-01). The loop's per-item gate runs test-fast and only the slow
# scripts a change touches (make test-slow SLOW_TESTS=...); its daily gate runs all of
# make test (docs/loop/LOOP.md "Gate").
SLOW_TESTS := tests/ko_bake_pin.py
.PHONY: test-fast test-slow
test:
	$(MAKE) test-fast
	$(MAKE) test-slow
test-fast:
	$(MAKE) client
	$(MAKE) server
	$(MAKE) assets
	python tools/assetc/main.py tests/fixtures/legacy-demo build/packages/legacy-demo
	python tests/player_build.py
	python tests/client_launchers.py
	build/client/n3e-hotbar-check
	build/client/n3e-input-check
	python tests/input_map.py
	python tests/pick_policy.py
	build/client/n3e-loot-visual-check
	build/client/n3e-target-marker-check
	build/client/n3e-audio-check
	build/client/n3e-effects-check
	build/client/n3e-postprocess-check
	python tests/postprocess.py
	python tests/item_heads.py
	python tests/ko_item_heads.py
	python tests/ko_fx.py
	python tests/ko_weapon_fx.py
	python tests/ko_glow_2233.py
	python tests/ko_chrplug_2145.py
	python tests/ko_armour_2145.py
	python tests/ko_hdr_2233.py
	python tests/skills.py
	build/client/n3e-nameplate-check
	build/client/n3e-chat-check
	build/client/n3e-refusal-check
	build/client/n3e-login-check
	python tests/front_end.py
	build/client/n3e-message-log-check
	python tests/check.py
	python tests/isolation_check.py
	python tests/host_network_check.py
	python tests/local_ca.py
	python tests/world_peer_check.py
	python tests/tick_scale.py
	python tests/gameplay_rules.py
	python tests/ko_character.py
	python tests/ko_attachments.py
	python tests/presentation.py
	python tests/loot_visual.py
	python tests/walking.py
	python tests/exploration.py
	build/client/n3e-lod-check
	python tests/world_lod.py
	python tests/world_chunks.py
	python tests/world_overlay.py
	python tests/render_detail.py
	python tests/movement_policy.py
	python tests/large_map.py
	python tests/camera.py
	python tests/melee.py
	python tests/damage.py
	python tests/npc.py
	python tests/npc_reference.py
	python tests/npc_looks.py
	python tests/npc_scale.py
	python tests/attachments.py
	python tests/ko_npc_looks_import.py
	python tests/ko_npc_templates.py
	python tests/life.py
	python tests/animation.py
	python tests/progression.py
	python tests/loot.py
	python tests/demo.py
	python tests/editing.py
	python tests/inventory.py
	python tests/commerce.py
	python tests/repair.py
	python tests/equipment.py
	python tests/stats.py
	python tests/wear.py
	python tests/storage.py
	python tests/storage_auth.py
	python tests/friends.py
	python tests/party.py
	python tests/party_rewards.py
	python tests/party_loot.py
	python tests/coin_loot.py
	python tests/item_drops.py
	python tests/appearance.py
	python tests/ko_terrain.py
	python tests/moradon_bridges.py
	python tests/loop_gate.py
test-slow:
	@set -e; for t in $(SLOW_TESTS); do echo "python $$t"; python $$t; done
graphical:
	python tools/assetc/main.py tests/fixtures/legacy-demo build/packages/legacy-demo
	python tests/graphical.py

.PHONY: test-multiplayer integration
# CPU regressions are included in make test; real dependencies/display are explicit.
test-multiplayer: client server
	python tests/walking.py
integration:
	python tests/multiplayer.py

.PHONY: integration-gameplay
integration-gameplay:
	python tests/gameplay.py

.PHONY: live
# Every disposable live and database suite (tests/live.py, PQ-001): Docker and a
# hardware GPU required. LIVE_SUITES=name... runs a subset; see python tests/live.py --list.
# Suites run 4 at a time (PQ-114); LIVE_JOBS=N changes that, LIVE_JOBS=1 is serial.
# The suites' graphical branches run by default (N3E_GRAPHICAL=1, PQ-116);
# LIVE_GRAPHICAL=0 is a headless developer run.
# The graphical clients render offscreen on the GPU, with no window (PQ-121);
# LIVE_DISPLAY=desktop opens them as windows on the desktop, one suite at a time.
# Every suite runs at the production 50 ms tick; LIVE_TICK_MS=25 (developer opt-in,
# PQ-115) runs the suites marked scaled at a 25 ms test tick. The gate removes it.
LIVE_GRAPHICAL ?= 1
live: client server assets
	$(MAKE) TOOLS=1 client
	N3E_GRAPHICAL=$(if $(filter 1,$(LIVE_GRAPHICAL)),1,) N3E_LIVE_DISPLAY=$(LIVE_DISPLAY) python tests/live.py $(if $(LIVE_JOBS),--jobs=$(LIVE_JOBS)) $(if $(LIVE_TICK_MS),--tick-ms=$(LIVE_TICK_MS)) $(LIVE_SUITES)

.PHONY: live-ko
# Opt-in, never a gate step or build prerequisite: the 19 suites tests/live.py
# leaves out because they need the raw KO client assets (assets/ko via tools/fetch-ko-assets.sh,
# D-118). Cooks the KO packages locally, gives each Moradon/field suite a disposable
# stack, and reports a suite whose input is missing as NOT RUN (tests/live_ko.py,
# PQ-111). Cooks only into build/live-ko/work. LIVE_KO_SUITES=name... runs a subset;
# LIVE_JOBS and LIVE_GRAPHICAL as for live. The clients render offscreen on the GPU,
# with no window (PQ-129); LIVE_DISPLAY=desktop opens them as windows, one suite at
# a time. Exit 0 only on LIVE_KO_OK; make exits 2 for both LIVE_KO_FAIL and
# LIVE_KO_INCOMPLETE, so read the last line.
live-ko: client server
	N3E_GRAPHICAL=$(if $(filter 1,$(LIVE_GRAPHICAL)),1,) N3E_LIVE_DISPLAY=$(LIVE_DISPLAY) python tests/live_ko.py $(if $(LIVE_JOBS),--jobs=$(LIVE_JOBS)) $(LIVE_KO_SUITES)
