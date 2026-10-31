// Package input map, keyboard targeting and continuous movement (PQ-009); the
// cancel action's window order (PQ-010).
// Usage: n3e-input-check [cooked-package ko|demo]
#include "render/hotbar.h"
#include "render/input_map.h"
#include "render/nameplates.h"
#include "render/orbit.h"
#include "render/pick_attack.h"
#include "render/targeting.h"
#include "render/window_stack.h"
#include <filesystem>
#include <iostream>
#include <stdexcept>
using n3e::input::Action;
using n3e::input::Map;
static void check(bool value, const char *what) {
  if (!value) throw std::runtime_error(std::string("input map regression: ") + what);
}
static std::vector<Action> press(const Map &m, SDL_Scancode k, uint32_t mods = 0, bool typing = false) {
  return m.pressed(k, mods, typing);
}
static bool only(const std::vector<Action> &v, Action a) { return v.size() == 1 && v[0] == a; }
// Ctrl+left press picks and attacks (005e16f0); a left double click attacks the
// current target (005e1490), whatever the modifiers. Neither is a key.
static void mouse_layout(const Map &m) {
  using namespace n3e::input;
  check(only(m.clicked(left_click, ctrl), Action::attack_pick) && m.clicked(left_click, 0).empty() &&
        only(m.clicked(left_click, ctrl | shift), Action::attack_pick), "Ctrl+click attack pick, plain click none");
  check(only(m.clicked(left_double, 0), Action::attack_target) && only(m.clicked(left_double, ctrl), Action::attack_target),
        "double click attacks the target");
  check(press(m, SDL_SCANCODE_UNKNOWN).empty() && press(m, SDL_SCANCODE_UNKNOWN, ctrl).empty(), "mouse bindings never fire from a key");
  check(m.labels(Action::attack_pick) == "Ctrl+Click" && m.labels(Action::attack_target) == "Double-click" &&
        m.label(Action::attack_pick).empty(), "mouse labels");
}
static n3e::Entity *add(n3e::WorldState &w, uint64_t id, float x, float z, bool npc, uint32_t health) {
  auto *e = w.world.add_entities();
  e->set_id(id); e->set_x(x); e->set_z(z); e->set_npc(npc); e->set_health(health);
  return e;
}
// The KO table (games/moradon/input.json) as cooked: every binding the binary
// handler 005c6990 reads, and none it lacks.
static void ko_layout(const Map &m) {
  using namespace n3e::input;
  const uint32_t lshift = left_shift | shift;
  check(m.packaged, "KO map packaged");
  for (int i = 0; i < 8; ++i) {
    check(only(press(m, SDL_Scancode(SDL_SCANCODE_1 + i)), Action(int(Action::hotbar_use_1) + i)), "1-8 hotbar slot");
    check(press(m, SDL_Scancode(SDL_SCANCODE_1 + i), 0, true).empty(), "hotbar slot blocked while typing");
    check(only(press(m, SDL_Scancode(SDL_SCANCODE_F1 + i), 0, true), Action(int(Action::hotbar_page_1) + i)), "F1-F8 page, also while typing");
    check(press(m, SDL_Scancode(SDL_SCANCODE_F1 + i), alt).empty(), "F1-F8 need Alt up");
  }
  check(only(press(m, SDL_SCANCODE_PAGEUP), Action::hotbar_page_prev) && only(press(m, SDL_SCANCODE_PAGEDOWN), Action::hotbar_page_next), "PgUp/PgDn pages");
  check(only(press(m, SDL_SCANCODE_T), Action::run_toggle), "T walk/run");
  check(only(press(m, SDL_SCANCODE_E), Action::auto_move), "E continuous move");
  check(only(press(m, SDL_SCANCODE_R), Action::attack_toggle), "R auto-attack");
  check(only(press(m, SDL_SCANCODE_Z), Action::target_enemy) && only(press(m, SDL_SCANCODE_X), Action::target_party) &&
        only(press(m, SDL_SCANCODE_B), Action::target_npc), "Z/X/B targets");
  check(only(press(m, SDL_SCANCODE_C), Action::rest_toggle) && only(press(m, SDL_SCANCODE_C, lshift), Action::hide_hud), "C sit, left Shift+C hide");
  check(only(press(m, SDL_SCANCODE_U), Action::character) && only(press(m, SDL_SCANCODE_H), Action::command_list) &&
        only(press(m, SDL_SCANCODE_O), Action::names_toggle) && only(press(m, SDL_SCANCODE_F10), Action::help), "U/H/O/F10");
  check(only(press(m, SDL_SCANCODE_I), Action::inventory) && only(press(m, SDL_SCANCODE_K), Action::skills) &&
        only(press(m, SDL_SCANCODE_M), Action::minimap), "I/K/M windows");
  check(only(press(m, SDL_SCANCODE_F9, 0, true), Action::camera_mode) && press(m, SDL_SCANCODE_F10, 0, true).empty(), "F9 while typing, F10 not");
  check(only(press(m, SDL_SCANCODE_9), Action::chat_size) && only(press(m, SDL_SCANCODE_0), Action::message_size), "9/0 window size");
  check(only(press(m, SDL_SCANCODE_KP_MINUS, 0, true), Action::screenshot), "numpad minus screenshot");
  for (auto k : {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_ENTER}) {
    auto v = press(m, k);
    check(v.size() == 2 && v[0] == Action::respawn && v[1] == Action::chat, "Enter: death prompt first, then chat");
  }
  for (auto k : {SDL_SCANCODE_F, SDL_SCANCODE_V, SDL_SCANCODE_TAB, SDL_SCANCODE_SPACE, SDL_SCANCODE_F11, SDL_SCANCODE_F12})
    check(press(m, k).empty(), "no gameplay handler for F, V, Tab, Space; F11/F12 engine-reserved");
  bool state[SDL_SCANCODE_COUNT] = {};
  for (auto [action, keys] : {std::pair{Action::move_forward, std::pair{SDL_SCANCODE_W, SDL_SCANCODE_UP}},
                              std::pair{Action::move_backward, std::pair{SDL_SCANCODE_S, SDL_SCANCODE_DOWN}},
                              std::pair{Action::turn_left, std::pair{SDL_SCANCODE_A, SDL_SCANCODE_LEFT}},
                              std::pair{Action::turn_right, std::pair{SDL_SCANCODE_D, SDL_SCANCODE_RIGHT}}}) {
    check(!m.down(action, state, 0), "nothing held");
    state[keys.first] = true; check(m.down(action, state, 0), "letter key held"); state[keys.first] = false;
    state[keys.second] = true; check(m.down(action, state, 0), "arrow alias held"); state[keys.second] = false;
    check(press(m, keys.first).empty(), "held actions never fire on a press");
  }
  state[SDL_SCANCODE_Q] = true; check(m.down(Action::turbo, state, 0), "Q turbo held");
  // PQ-012: Home raises and End lowers the camera while held (005c6990 reads
  // DIK 0xc7/0xcf every frame); they never fire as presses.
  state[SDL_SCANCODE_HOME] = true;
  check(m.down(Action::camera_pitch_up, state, 0) && !m.down(Action::camera_pitch_down, state, 0), "Home pitch up held");
  state[SDL_SCANCODE_HOME] = false; state[SDL_SCANCODE_END] = true;
  check(m.down(Action::camera_pitch_down, state, 0) && !m.down(Action::camera_pitch_up, state, 0), "End pitch down held");
  state[SDL_SCANCODE_END] = false;
  check(press(m, SDL_SCANCODE_HOME).empty() && press(m, SDL_SCANCODE_END).empty(), "pitch keys are held actions");
  check(m.label(Action::respawn) == "Enter" && m.label(Action::loot_nearest).empty(), "labels");
  // Esc (005c6990 +0x270, outside the text-focus block): cancel. While typing
  // the text field or prompt keeps Esc (window-local), so no typing flag.
  check(only(press(m, SDL_SCANCODE_ESCAPE), Action::cancel) && press(m, SDL_SCANCODE_ESCAPE, 0, true).empty(), "Esc cancel");
  check(m.label(Action::cancel) == "Esc", "Esc label");
  mouse_layout(m);
}
static void demo_layout(const Map &m) {
  check(m.packaged, "demo map packaged");
  check(only(press(m, SDL_SCANCODE_T), Action::run_toggle) && only(press(m, SDL_SCANCODE_E), Action::auto_move) &&
        only(press(m, SDL_SCANCODE_Z), Action::target_enemy) && only(press(m, SDL_SCANCODE_X), Action::target_party), "demo shares the KO layout");
  check(only(press(m, SDL_SCANCODE_F), Action::loot_nearest), "demo F collects loot");
  check(only(press(m, SDL_SCANCODE_LEFTBRACKET), Action::window_page_prev), "demo window paging");
  check(press(m, SDL_SCANCODE_H).empty() && press(m, SDL_SCANCODE_TAB).empty(), "demo leaves KO-only keys unbound");
  check(!m.key(Action::camera_pitch_up) && !m.key(Action::camera_pitch_down), "demo leaves Home/End pitch unbound");
  check(only(press(m, SDL_SCANCODE_ESCAPE), Action::cancel), "demo Esc cancel");
  mouse_layout(m);
}
int main(int argc, char **argv) {
  try {
    if (argc == 3) {
      auto release = n3e::load_release(argv[1]);
      check(release.input.has_value(), "cooked package has an input table");
      auto m = Map::from(release);
      std::string arg = argv[2];
      // ko-key320: the KO table as the bake writes it for Zones.tbl key 320
      // (PQ-173), otherwise the KO layout.
      bool key320 = arg == "ko-key320";
      std::string layout = key320 ? "ko" : arg;
      if (layout == "ko") ko_layout(m);
      else if (layout == "demo") demo_layout(m);
      else throw std::runtime_error("layout ko|ko-key320|demo");
      // PQ-014: the package's name display. KO: shown at start (006d42e4 = 1),
      // O hides self (0046b5a0) and other players (0046ea90), never NPCs
      // (00459820). The demo table has no names policy: all shown, all hidden.
      using P = n3e::NameDisplayPolicy;
      NameDisplay names{release.names};
      check(names.shown && names.visible(false, true) && names.visible(false, false) && names.visible(true, false),
            "every name shown at start");
      names.toggle();
      if (layout == "ko")
        check(release.names.hides == (P::self | P::players) && !names.visible(false, true) && !names.visible(false, false) &&
                  names.visible(true, false), "KO: O hides self and other players, NPC names stay");
      else
        check(release.names.hides == P::all && !names.visible(false, true) && !names.visible(false, false) &&
                  !names.visible(true, false), "demo default: the toggle hides every class");
      names.toggle();
      check(names.shown && names.visible(false, true) && names.visible(false, false), "a second press shows them again");
      // PQ-169: KO's other-player label lifetime (00470900: below 10.0 from the
      // local player's position, above 20.0 freed, party members exempt). The
      // demo has none: every other player keeps a label.
      if (layout == "ko") {
        const auto &life = release.names.lifetime;
        check(life && life->from == n3e::NameLifetimePolicy::self && life->acquire == 10 && life->release == 20 &&
                  life->exempt == n3e::NameLifetimePolicy::party, "KO: label lifetime 10/20 m from the local player, party exempt");
      } else
        check(!release.names.lifetime, "demo: no label lifetime");
      // PQ-166: KO's party marker (other-player +0x7dc) keeps a party member's
      // name under O and beyond the 48 m limit (0046ea90; Moradon's Zones.tbl
      // row 210 column 23 is 1) and draws it 0xffffff00 (0046e840).
      if (layout == "ko") {
        const auto &party = release.names.party;
        // Key 320's column 23 is 0: no party skip of the limit there.
        check(party && party->while_hidden && party->beyond_distance == !key320 && party->color == 0xffff00u,
              "KO: party names kept under O, beyond 48 m (not in key 320), yellow");
        NameDisplay hidden{release.names};
        hidden.toggle();
        check(hidden.visible(false, false, true) && !hidden.visible(false, false) && !hidden.visible(false, true, true),
              "KO: O keeps party members' names only");
      } else
        check(!release.names.party, "demo: no party names policy");
      // PQ-173: other players' camera limit by zone. KO 0046ea90 compares with
      // 33.0 (006a4250) instead of 48.0 (006a40dc) in zone key 0x140; self
      // (0046b5a0) and NPCs (00459820) keep 48.0. Moradon (key 210) and the
      // demo carry no per-class limit: the style's distance applies to all.
      {
        const auto &limits = release.names.distance;
        if (key320)
          check(!limits[0] && limits[1] == 33.f && !limits[2], "KO key 320: other players 33 m, self and NPCs the style's");
        else
          check(!limits[0] && !limits[1] && !limits[2], "no per-class camera limit");
        n3e::NameplateStyle style{};
        style.distance = 48;
        for (auto &font : style.fonts) { font.height = 18; font.advances.fill(8); }
        auto drawn = [&](bool npc, bool self, float camera, bool party = false) {
          bool beyond = party && release.names.party && release.names.party->beyond_distance;
          return nameplate(style, 1, "Wi", npc, self, {0, 0, 0}, {0, 0, camera}, {320, 200, 10}, 640, 480, beyond,
                           std::nullopt, name_distance(style, release.names, npc, self)).has_value();
        };
        check(drawn(false, false, 32.9f) && drawn(true, false, 47.9f) && drawn(false, true, 47.9f) && !drawn(false, false, 48),
              "players inside 33 m, NPCs and self inside 48 m");
        check(drawn(false, false, 40) == !key320 && drawn(false, false, 33) == !key320,
              "a player at 33-40 m drawn only outside key 320");
        if (layout == "ko")
          check(drawn(false, false, 60, true) == !key320, "a party member beyond the limit only where column 23 is not 0");
      }
      // PQ-174: KO's NPC label lifetime (00470900 NPC loop: below 10.0 of the
      // local player's position built, 10.0 <= d < 20.0 freed, 20.0 or farther
      // kept; dead NPCs freed). The Moradon worm's looks row (700) has column
      // 36 = 0, so no NPC is exempt from the band (named at any range). The demo has none.
      if (layout == "ko") {
        const auto &npcs = release.names.npc_lifetime;
        check(npcs && npcs->range.from == n3e::NameLifetimePolicy::self && npcs->range.acquire == 10 &&
                  npcs->range.release == 20 && npcs->range.band && !npcs->always && npcs->drop_dead,
              "KO: NPC label band 10/20 m from the local player, no looks flag, dropped when dead");
        NpcNameLifetime life{npcs};
        check(life.update(1, 15, false) == NameLifetime::none && life.update(1, 9, false) == NameLifetime::acquired &&
                  life.update(1, 25, false) == NameLifetime::none && life.update(1, 12, false) == NameLifetime::released,
              "KO: NPC label made below 10 m, kept beyond 20 m, freed in the band");
      } else
        check(!release.names.npc_lifetime, "demo: no NPC label lifetime");
      // PQ-177: KO's NPC info line (00465070: "ID(%d) : TYPE(%d)", 006d44f0, in
      // 0xff00ff00; TYPE 0 until opcode 0x5d). PQ-186: TYPE shows the state the
      // server reports for a traced NPC, else the KO table's fallback `{state:0}`
      // (the engine's default for a bare `{state}` is empty). The demo has none.
      if (layout == "ko") {
        const auto &info = release.names.npc_info;
        check(info && info->color == 0x00ff00u && info->text == "ID({id}) : TYPE({state:0})" &&
                  n3e::npc_info_line(*info, 7) == "ID(7) : TYPE(0)" &&
                  n3e::npc_info_line(*info, 7, "chase") == "ID(7) : TYPE(chase)" &&
                  n3e::npc_info_line(*info, 7, "") == "ID(7) : TYPE(0)" &&
                  n3e::npc_info_line({0, "{id} {state}"}, 7) == "7 " &&
                  n3e::npc_info_line({0, "{id} {state:n/a}"}, 7) == "7 n/a" &&
                  n3e::npc_info_line({0, "{id} {state:n/a}"}, 7, "idle") == "7 idle" &&
                  n3e::npc_info_text_valid("{id}{state:0123456789abcdef}") &&
                  !n3e::npc_info_text_valid("{id}{state:0123456789abcdefg}") &&
                  !n3e::npc_info_text_valid("{id}{state:}") && !n3e::npc_info_text_valid("{state:{id}}") &&
                  !n3e::npc_info_text_valid("{id}{state:0}{state}"),
              "KO: the green ID(n) : TYPE(state) NPC info line");
      } else
        check(!release.names.npc_info, "demo: no NPC info line");
      // PQ-178: KO's chat handler 005cac80 colours an operator's line
      // 0xffcd9bff (005cb2f5) unless its type is 7. The demo has no style.
      if (layout == "ko")
        check(release.names.operator_chat == 0xcd9bffu, "KO: the operator chat colour");
      else
        check(!release.names.operator_chat, "demo: no operator chat colour");
      // PQ-146: the package's pick policy (KO 0041c300 and 0041c7d0 values)
      // and the boxes its actor models give in the idle pose and the final
      // dying pose (printed; the demo rig has two joints on one vertical line).
      check(release.pick.min_extent == .5f && release.pick.pad == .25f && release.pick.mesh_lod == 1, "package pick policy");
      std::cout << "PICK_POLICY box=" << (release.pick.joints ? "joints" : "vertices") << "\n";
      for (auto [idle, death] : {std::pair{"npc-idle.bin", "npc-death.bin"}, std::pair{"player-idle.bin", "player-death.bin"}}) {
        if (!std::filesystem::exists(release.root / idle)) continue;
        auto a = n3e::load_scene(release, idle), d = n3e::load_scene(release, death);
        float end = 0;
        for (const auto &t : d.tracks) end = std::max(end, t.keys.back().time);
        auto stand = n3e::targeting::model_box(a, a.sample(0), release.pick);
        auto lie = n3e::targeting::model_box(d, d.sample(end), release.pick);
        std::cout << "PICK_BOX " << idle << " lo " << stand.lo[0] << ' ' << stand.lo[1] << ' ' << stand.lo[2] << " hi " << stand.hi[0]
                  << ' ' << stand.hi[1] << ' ' << stand.hi[2] << " dead hi_y " << lie.hi[1] << "\n";
        for (int k = 0; k < 3; ++k) check(stand.hi[k] - stand.lo[k] >= .5f && lie.hi[k] - lie.lo[k] >= .5f, "boxes at least the minimum extent");
      }
      std::cout << "PASS " << arg << " input map from " << argv[1] << "\n";
      return 0;
    }
    // A release without a table keeps the pre-PQ-009 layout.
    n3e::Release legacy_release{};
    auto legacy = Map::from(legacy_release);
    check(!legacy.packaged, "legacy fallback");
    check(only(press(legacy, SDL_SCANCODE_V), Action::run_toggle) && only(press(legacy, SDL_SCANCODE_TAB), Action::target_cycle) &&
          only(press(legacy, SDL_SCANCODE_E), Action::respawn) && only(press(legacy, SDL_SCANCODE_F), Action::loot_nearest), "legacy keys");
    auto one = press(legacy, SDL_SCANCODE_1);
    check(one.size() == 2 && one[0] == Action::hotbar_use_1 && one[1] == Action::attack_toggle, "legacy 1: hotbar first, then attack");
    check(legacy.labels(Action::attack_toggle) == "R/Space/1", "joined labels");
    check(legacy.clicked(n3e::input::left_click, n3e::input::ctrl).empty() && legacy.clicked(n3e::input::left_double, 0).empty(),
          "legacy layout has no mouse bindings");
    check(only(press(legacy, SDL_SCANCODE_ESCAPE), Action::cancel), "legacy Esc cancel");
    // Parsing fails closed.
    n3e::Release bad{};
    for (auto b : {n3e::InputBinding{"fly", "T"}, n3e::InputBinding{"run_toggle", "F13"}, n3e::InputBinding{"run_toggle", "F12"},
                   n3e::InputBinding{"run_toggle", "F11"}, n3e::InputBinding{"run_toggle", "Grave"},
                   n3e::InputBinding{"run_toggle", "T", 1, 1}, n3e::InputBinding{"run_toggle", "T", 16, 0},
                   n3e::InputBinding{"move_forward", "MouseLeft"}, n3e::InputBinding{"attack_pick", "MouseLeft", 0, 0, 1}}) {
      bad.input = std::vector{b};
      bool refused = false;
      try { Map::from(bad); } catch (const std::runtime_error &) { refused = true; }
      check(refused, "unknown, reserved, contradictory or mouse-held/typing binding refused");
    }
    // Modifiers: required and forbidden sets.
    n3e::Release mods{};
    mods.input = std::vector{n3e::InputBinding{"hide_hud", "C", n3e::input::left_shift, 0}, n3e::InputBinding{"rest_toggle", "C", 0, n3e::input::left_shift}};
    auto m = Map::from(mods);
    check(only(press(m, SDL_SCANCODE_C), Action::rest_toggle), "plain C");
    check(only(press(m, SDL_SCANCODE_C, n3e::input::modifiers(SDL_KMOD_LSHIFT)), Action::hide_hud), "left Shift+C");
    check(only(press(m, SDL_SCANCODE_C, n3e::input::modifiers(SDL_KMOD_RSHIFT)), Action::rest_toggle), "right Shift is not left Shift");

    // Targeting: Z nearest living NPC (keeps target when none), X nearest party
    // member, B nearest NPC actor, dying included, corpses not (PQ-199).
    n3e::WorldState w{};
    w.world.set_self(1);
    add(w, 1, 0, 0, false, 10);
    add(w, 2, 9, 0, true, 5);
    add(w, 3, 0, 4, true, 5);
    add(w, 4, 2, 0, true, 0);   // slain NPC
    add(w, 5, 3, 0, false, 10);  // another player, in the party
    add(w, 6, 1, 0, false, 10);  // a player outside the party
    check(n3e::targeting::enemy(w) == 3, "Z nearest living NPC");
    check(n3e::targeting::npc(w, {}) == 4, "B nearest NPC actor, a dying NPC included");
    // Once its death presentation has finished it is a corpse (KO: the corpse
    // map, 00470b25), which B (004711b0, NPC map only) never sees; the next
    // nearest NPC, living or dying, is selected instead.
    check(n3e::targeting::npc(w, {4}) == 3, "B skips a corpse");
    check(n3e::targeting::npc(w, {4, 3}) == 2, "B skips every corpse");
    check(n3e::targeting::npc(w, {4, 3, 2}) == 0, "B with only corpses selects nothing");
    check(n3e::targeting::npc(w, {5, 6, 99}) == 4, "the corpse set never adds players or departed actors");
    check(n3e::targeting::party_member(w) == 0, "X without a party");
    auto *member = w.party.add_members(); member->set_entity(5);
    auto *self_member = w.party.add_members(); self_member->set_entity(1);
    check(n3e::targeting::party_member(w) == 5, "X nearest member, never self");
    add(w, 7, 0, -4, true, 5);
    check(n3e::targeting::enemy(w) == 3, "equal distance: lower ID");
    n3e::WorldState empty{};
    empty.world.set_self(1);
    add(empty, 1, 0, 0, false, 10);
    check(!n3e::targeting::enemy(empty) && !n3e::targeting::npc(empty, {}), "nothing to select");

    // PQ-011 pick set (00472ab0) and PQ-146 pick geometry (004724c0): every
    // other player and NPC, slain NPCs and party members included, never the
    // local player; the cursor ray against each drawn actor's box, nearest the
    // eye first; with several hits the drawn mesh decides at LOD 0-1 and the
    // box at LOD 2-3 (0041c7d0, with the D-138 ray correction).
    {
      n3e::WorldState p{};
      p.world.set_self(1);
      add(p, 1, 0, 0, false, 10);
      using namespace n3e::targeting;
      using n3e::V;
      // A standing actor's box and a closed box-shaped mesh inside it (a
      // stand-in body), both in world space as the viewer records them.
      n3e::PickPolicy ko{true, .5f, .25f, 1};
      auto body = [](PickFrame &f, V at, float half, float top) {
        auto &b = f.buffers[0];
        MeshRange m{0, b.size(), 36, 8};
        auto c = box_corners({at[0] - half, at[1], at[2] - half}, {at[0] + half, at[1] + top, at[2] + half});
        for (auto i : box_triangles) b.insert(b.end(), {c[i][0], c[i][1], c[i][2], 0, 0, 0, 0, 0});
        return m;
      };
      auto actor = [&](PickFrame &f, uint64_t id, V at, int lod = 0, float mesh_half = .2f) {
        Box box{{-.3f, 0, -.3f}, {.3f, 1.8f, .3f}};
        f.volumes.push_back({id, at, lod, place(box, at, 0), body(f, at, mesh_half, 1.6f)});
      };
      // Camera 10 m back on +z, looking down -z, 60 degrees, 800x600.
      n3e::CameraConfig config;
      Orbit o(config);
      o.eye = {0, 1, 10};
      o.right = {1, 0, 0};
      o.up = {0, 1, 0};
      o.back = {0, 0, 1};
      auto at_pixel = [&](V world) { auto q = o.project(world, 800, 600); return o.ray(q[0], q[1], 800, 600); };
      {
        PickFrame f;
        actor(f, 1, {0, 0, 0});
        check(!pick(p, f, o.eye, at_pixel({0, 1, 0}), 1), "the local player is never picked");
      }
      add(p, 2, 3, 0, true, 0);     // slain NPC, dying
      add(p, 3, 0, 3, false, 10);   // another player
      add(p, 4, 6, 0, true, 5);     // living NPC
      auto *party = p.party.add_members(); party->set_entity(3);
      for (uint64_t id : {2, 3, 4}) {
        PickFrame f;
        actor(f, id, {0, 0, 0});
        check(pick(p, f, o.eye, at_pixel({0, 1, 0}), 1) == id, "dying NPC, party member and living NPC are pickable");
      }
      {
        // PQ-199: a corpse (death presentation finished; KO's corpse map) is
        // not in the actor pick (004724c0 reads the NPC and player maps only):
        // the ray passes it and reaches the actor behind, or nothing.
        PickFrame f;
        actor(f, 2, {0, 0, 0});
        actor(f, 4, {0, 0, -3});
        f.corpses = {2};
        check(pick(p, f, o.eye, at_pixel({0, 1, 0}), 1) == 4, "a corpse does not occlude the actor behind it");
        f.volumes.pop_back();
        check(!pick(p, f, o.eye, at_pixel({0, 1, 0}), 1), "a click on a lone corpse picks no actor");
        f.corpses.clear();
        check(pick(p, f, o.eye, at_pixel({0, 1, 0}), 1) == 2, "the same NPC while dying is picked");
      }
      {
        // One box hit wins at once, whatever its mesh (004729a5).
        PickFrame f;
        f.volumes.push_back({4, {0, 0, 0}, 0, place({{-.3f, 0, -.3f}, {.3f, 1.8f, .3f}}, {0, 0, 0}, 0), {}});
        check(pick(p, f, o.eye, at_pixel({.25f, 1, 0}), 1) == 4, "a single box hit needs no mesh");
        // Just outside the box but within PQ-011's old 45 px of the chest point.
        auto q = o.project({.3f, .35f, 0}, 800, 600), chest = o.project({0, .35f, 0}, 800, 600);
        check(q[0] + 3 - chest[0] < 45, "the probe lies within the old proxy radius");
        check(!pick(p, f, o.eye, o.ray(q[0] + 3, q[1], 800, 600), 1), "a cursor just outside the box picks nothing");
        check(pick(p, f, o.eye, o.ray(q[0] - 1, q[1], 800, 600), 1) == 4, "just inside the box picks the actor");
        // Nothing behind the camera, and no pick from inside a box (front faces only).
        PickFrame behind;
        behind.volumes.push_back({4, {0, 0, 20}, 0, place({{-.3f, 0, -.3f}, {.3f, 1.8f, .3f}}, {0, 0, 20}, 0), {}});
        check(!pick(p, behind, o.eye, o.ray(400, 300, 800, 600), 1), "nothing behind the camera");
        PickFrame around;
        around.volumes.push_back({4, {0, 0, 10}, 0, place({{-.3f, 0, -.3f}, {.3f, 1.8f, .3f}}, {0, 0, 10}, 0), {}});
        check(!pick(p, around, o.eye, o.ray(400, 300, 800, 600), 1), "the eye inside a box does not pick it");
        // An actor that left the world since the frame was drawn.
        PickFrame gone;
        actor(gone, 99, {0, 0, 0});
        check(!pick(p, gone, o.eye, at_pixel({0, 1, 0}), 1), "a departed actor is not picked");
      }
      {
        // Two actors on the ray: the nearer one occludes the farther one.
        PickFrame f;
        actor(f, 4, {0, 0, -3});
        actor(f, 2, {0, 0, 0});
        check(pick(p, f, o.eye, at_pixel({0, 1, 0}), 1) == 2, "the nearer of two hit actors wins");
        // The volumes' order does not matter: distance from the eye does (00472250).
        std::swap(f.volumes[0], f.volumes[1]);
        check(pick(p, f, o.eye, at_pixel({0, 1, 0}), 1) == 2, "camera-distance order, not draw order");
        // The ray crosses both boxes but only the farther actor's mesh: KO's
        // tie-break tests the meshes; n3e tests them in world space (D-138).
        auto probe = o.ray(o.project({.2f, 1, 0}, 800, 600)[0], 300, 800, 600);
        check(ray_box(o.eye, probe, f.volumes[0].box) && ray_box(o.eye, probe, f.volumes[1].box), "the probe crosses both boxes");
        PickFrame g;
        actor(g, 2, {0, 0, 0}, 0, .1f);   // nearer, thin body
        actor(g, 4, {0, 0, -3}, 0, .3f);  // farther, wide body under the probe
        check(pick(p, g, o.eye, probe, 1) == 4, "with several boxes hit, the nearer actor whose mesh is hit wins");
        PickFrame h;
        actor(h, 2, {0, 0, 0}, 0, .1f);
        actor(h, 4, {0, 0, -3}, 0, .05f);
        check(!pick(p, h, o.eye, probe, 1) , "boxes hit but no mesh: nothing");
        // LOD 2-3 skips the mesh: its box hit stands (0041c7d0 box branch).
        PickFrame far;
        actor(far, 2, {0, 0, 0}, 0, .1f);
        actor(far, 4, {0, 0, -3}, 2, .05f);
        check(pick(p, far, o.eye, probe, 1) == 4, "a coarse-LOD actor is accepted on its box");
        PickFrame coarse;
        actor(coarse, 2, {0, 0, 0}, 3, .1f);
        actor(coarse, 4, {0, 0, -3}, 0, .3f);
        check(pick(p, coarse, o.eye, probe, 1) == 2, "the nearer coarse-LOD actor wins on its box");
        check(pick(p, coarse, o.eye, probe, 3) == 4, "mesh_lod 3 tests every LOD's mesh");
        PickFrame hidden;
        actor(hidden, 2, {0, 0, 0}, -1);
        check(!pick(p, hidden, o.eye, at_pixel({0, 1, 0}), 1), "an actor not drawn at LOD 0-3 is skipped");
        // A mesh range outside its buffer never hits.
        PickFrame bad;
        actor(bad, 2, {0, 0, 0});
        actor(bad, 4, {0, 0, -3});
        bad.volumes[0].mesh.vertices = 1000;
        check(pick(p, bad, o.eye, at_pixel({0, 1, 0}), 1) == 4, "a bad mesh range is no hit");
      }
      {
        // The box: joint positions, each axis shorter than 0.5 grown by 0.25 on
        // each side (0041c300); turned and placed as the model is drawn.
        auto b = bounds({{-.1f, 0, 0}, {.1f, 1.7f, .2f}}, ko);
        check(std::abs(b.lo[0] + .35f) < 1e-6f && std::abs(b.hi[0] - .35f) < 1e-6f && b.lo[1] == 0 && b.hi[1] == 1.7f &&
              std::abs(b.lo[2] + .25f) < 1e-6f && std::abs(b.hi[2] - .45f) < 1e-6f, "short axes grow by the padding");
        auto none = bounds({{-.1f, 0, 0}, {.1f, 1.7f, .2f}}, n3e::PickPolicy{});
        check(none.lo[0] == -.1f && none.hi[0] == .1f, "no policy: no padding");
        n3e::Scene s{};
        s.scale = {1, 1, 1};
        s.nodes = {{-1, {0, 0, 0}, {1, 1, 1}, {0, 0, 0, 1}}, {0, {.1f, 1.7f, .05f}, {1, 1, 1}, {0, 0, 0, 1}}};
        s.joints = {{0, {}}, {1, {}}};
        auto m = model_box(s, s.nodes, ko);
        check(m.hi[1] == 1.7f && std::abs(m.hi[0] - .35f) < 1e-6f && std::abs(m.lo[0] + .25f) < 1e-6f, "a model box from its joints");
        s.scale = {2, 2, 2};
        check(model_box(s, s.nodes, ko).hi[1] == 3.4f, "the model scale applies");
        // The vertex policy (engine default) bounds the skinned mesh instead:
        // one triangle weighted to the root joint, taller than the joints.
        s.scale = {1, 1, 1};
        n3e::M identity{1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1};
        s.joints = {{0, identity}, {1, identity}};
        for (n3e::V v : {n3e::V{-.4f, 0, 0}, n3e::V{.4f, 0, 0}, n3e::V{0, 2, .1f}})
          s.vertices.push_back({v, {0, 0, 1}, {0, 0}, {0, 0, 0, 0}, {1, 0, 0, 0}});
        s.indices = {0, 1, 2};
        auto mesh = model_box(s, s.nodes, n3e::PickPolicy{});
        check(mesh.lo[0] == -.4f && mesh.hi[0] == .4f && mesh.hi[1] == 2 && mesh.lo[2] == 0 && mesh.hi[2] == .1f,
              "vertex policy: the skinned mesh's bounds, no padding");
        check(model_box(s, s.nodes, ko).hi[1] == 1.7f, "joint policy: the joints, not the mesh");
        // A long, thin box along z turned a quarter turn lies along x.
        Box thin{{-.1f, 0, -1}, {.1f, 1, 1}};
        V side = o.ray(o.project({.8f, .5f, 0}, 800, 600)[0], o.project({.8f, .5f, 0}, 800, 600)[1], 800, 600);
        check(!ray_box(o.eye, side, place(thin, {0, 0, 0}, 0)) && ray_box(o.eye, side, place(thin, {0, 0, 0}, 1.5707963f)),
              "the box turns with the actor");
        // KO's triangle test: front faces only, t >= 0.
        check(ray_triangle({0, 0, 1}, {0, 0, -1}, {-1, -1, 0}, {1, -1, 0}, {0, 1, 0}), "front face hit");
        check(!ray_triangle({0, 0, 1}, {0, 0, -1}, {-1, -1, 0}, {0, 1, 0}, {1, -1, 0}), "back face culled");
        check(!ray_triangle({0, 0, -1}, {0, 0, -1}, {-1, -1, 0}, {1, -1, 0}, {0, 1, 0}), "behind the origin: no hit");
      }
      // Attack predicate (00468750): attackable and within reach on the ground
      // plane; height does not count. Decisions of 005e16f0 and 005e1490.
      using namespace n3e::targeting;
      check(attackable(p.world.entities(3)) && !attackable(p.world.entities(1)) && !attackable(p.world.entities(2)),
            "living NPCs are attackable; slain NPCs and players are not");
      check(can_attack(true, {0, 0, 0}, {0, 9, 1}, 1) && !can_attack(true, {0, 0, 0}, {0, 0, 1.01f}, 1) &&
            !can_attack(false, {0, 0, 0}, {0, 0, .5f}, 1), "predicate: planar reach, inclusive, hostile only");
      check(ctrl_click(false, true) == Click::none && ctrl_click(true, true) == Click::attack &&
            ctrl_click(true, false) == Click::approach, "Ctrl+click: attack in reach, else approach");
      check(double_click(false, true, {}, {}, 1) == Click::none && double_click(true, true, {}, {0, 0, .5f}, 1) == Click::attack &&
            double_click(true, false, {}, {0, 0, 3}, 1) == Click::approach &&
            double_click(true, false, {}, {0, 0, .5f}, 1) == Click::none &&
            double_click(true, false, {}, {0, .9f, .9f}, 1) == Click::approach, "double click: attack, approach beyond 3-D reach, else nothing");
      // Double click (00640140): second left release within 500 ms and under 6 px.
      DoubleClick d;
      check(!d.release(1000, 10, 10) && d.release(1499, 15.9f, 4.1f), "second release in time and place");
      check(d.release(1600, 15, 5), "a third quick release counts again");
      check(!d.release(2100, 15, 5) && !d.release(2200, 21, 5) && !d.release(2300, 21, 11), "late or 6 px away: no double click");
    }
    // E: continuous movement.
    n3e::targeting::AutoMove a;
    check(!a.toggle(true, true, false) && !a.active, "E refused with a move key held");
    check(!a.toggle(true, false, true) && !a.active, "E refused with the left button held");
    check(!a.toggle(false, false, false) && !a.active, "E refused while dead");
    check(a.toggle(true, false, false) && a.active, "E starts");
    a.update(true, false); check(a.active, "turning or nothing keeps it");
    a.update(true, true); check(!a.active, "a forward/back key ends it");
    a.toggle(true, false, false); check(a.active, "E restarts");
    check(a.toggle(true, false, false) && !a.active, "second E stops");
    a.toggle(true, false, false); a.update(false, false); check(!a.active, "death ends it");

    // Hotbar pages: F1-F8 select, PgUp/PgDn step and clamp.
    Hotbar bar;
    bar.select_page(5); check(bar.page == 5, "F6 selects page 6");
    bar.select_page(8); check(bar.page == 5, "out-of-range page ignored");
    bar.select_page(7); bar.change_page(true); check(bar.page == 7, "PgDn clamps at page 8");
    bar.select_page(0); bar.change_page(false); check(bar.page == 0, "PgUp clamps at page 1");
    // Cancel closes the most recently opened dialog first, one per press
    // (00579260 front of the z-list; 00648a40 one focused window per key).
    using n3e::windows::Window;
    n3e::windows::Stack stack;
    n3e::windows::Open open{};
    check(!stack.top(), "no window open");
    open[size_t(Window::character)] = true; stack.sync(open);
    open[size_t(Window::inventory)] = true; stack.sync(open);
    check(stack.top() == Window::inventory, "the later window is in front, not the enum order");
    open[size_t(Window::inventory)] = false; stack.sync(open);
    check(stack.top() == Window::character && stack.order.size() == 1, "one window per press");
    open[size_t(Window::inventory)] = true; stack.sync(open);
    open[size_t(Window::character)] = false; stack.sync(open);
    open[size_t(Window::character)] = true; stack.sync(open);
    check(stack.top() == Window::character, "a reopened window comes to the front");
    // n3e's generic stack: windows opened in one frame enter by kind. KO probably
    // never shows the shop with the inventory (00579260, shared style bit 0x80;
    // fidelity gap PQ-142), so this orders a state of n3e's own layout.
    open = {}; open[size_t(Window::inventory)] = open[size_t(Window::shop)] = true;
    n3e::windows::Stack together; together.sync(open);
    check(together.top() == Window::shop && together.order.size() == 2, "a shop opened with the inventory is in front");
    open = {}; stack.sync(open);
    check(!stack.top() && stack.order.empty(), "all closed");
    // PQ-014: a release without a names policy shows every name; a policy that
    // starts hidden keeps unlisted classes visible.
    {
      using P = n3e::NameDisplayPolicy;
      check(NameDisplay{}.visible(true, false) && NameDisplay{}.visible(false, true), "default: names shown");
      NameDisplay hidden{P{false, P::npcs}};
      check(!hidden.visible(true, false) && hidden.visible(false, true) && hidden.visible(false, false), "hidden at start, NPCs only");
      hidden.toggle(); check(hidden.visible(true, false), "toggle shows them");
    }
    std::cout << "PASS legacy fallback, fail-closed parsing, modifiers, Z/X/B targeting, E continuous move, hotbar pages, cancel window order, "
                 "pick set and geometry, attack predicate, Ctrl+click and double-click decisions, name display toggle\n";
  } catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
  }
}
