#include "harness/harness.h"
#include "feature_ui.h"
#include "hotbar.h"
#include "panel_state.h"
#include "skills_ui.h"
#include "portrait.h"
#include "appearance.h"
#include "equipment_glow.h"
#include "attached_characters.h"
#include "loot_ui.h"
#include "item_wait.h"
#include "loot_visual.h"
#include "target_marker.h"
#include "network/chat.h"
#include "network/inventory.h"
#include "network/storage.h"
#include "network/friends.h"
#include "network/party.h"
#include "animation.h"
#include "combat_pose.h"
#include "melee.h"
#include "skill_reach.h"
#include "pick_attack.h"
#include "input_map.h"
#include "targeting.h"
#include "window_stack.h"
#include <deque>
#include <set>
#define GL_GLEXT_PROTOTYPES
#include "assets/assets.h"
#include "assets/world_lod.h"
#include "assets/world_stream.h"
#include "assets/character_lod.h"
#include "hud.h"
#include "motion.h"
#include "remote_motion.h"
#include "navigation.h"
#include "network/world.h"
#include "platform/gl_load.h"
#include "play.h"
#include "network/discord_login.h"
#include "presentation.h"
#include <GL/gl.h>
#include <SDL3/SDL.h>
#include "native_textures.h"
#include "terrain_overlay.h"
#if N3E_HARNESS
#include "texture_bank_check.h"
#endif
#include "effects_gl.h"
#include "postprocess.h"
#include "options.h"
#include "presentation_events.h"
#include "local_release.h"
#include "melee_presentation.h"
#include "audio_device.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <charconv>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <limits>
#include <stdexcept>
#include <vector>
#if TOOLS
#include <imgui.h>
#include "tools/editor.h"
#include <imgui_impl_opengl3.h>
#include <imgui_impl_sdl3.h>
#endif
// Blend factors by the package's index (tools/assetc/gltf.py BLEND_FACTORS,
// D3DBLEND 1-10 in order): N3SM runs and N3D3 appearance states (PQ-348).
static const GLenum part_blend_factors[] = {GL_ZERO, GL_ONE, GL_SRC_COLOR, GL_ONE_MINUS_SRC_COLOR, GL_SRC_ALPHA,
                                            GL_ONE_MINUS_SRC_ALPHA, GL_DST_ALPHA, GL_ONE_MINUS_DST_ALPHA,
                                            GL_DST_COLOR, GL_ONE_MINUS_DST_COLOR};
GLuint shader(GLenum type, const char *src) {
  auto s = glCreateShader(type);
  glShaderSource(s, 1, &src, nullptr);
  glCompileShader(s);
  int ok;
  glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
  if (!ok) {
    char b[4096];
    glGetShaderInfoLog(s, sizeof b, nullptr, b);
    throw std::runtime_error(b);
  }
  return s;
}
#if N3E_HARNESS
// Replay captures: the drawn frame as a binary PPM.
void capture(const std::string &name, int w, int h) {
  std::vector<unsigned char> p(w * h * 3);
  glPixelStorei(GL_PACK_ALIGNMENT, 1);
  glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE, p.data());
  std::ofstream f(name, std::ios::binary);
  f << "P6\n" << w << " " << h << "\n255\n";
  for (int y = h - 1; y >= 0; --y)
    f.write((char *)p.data() + y * w * 3, w * 3);
}
#endif
int viewer(const n3e::Release &release, int argc, char **argv) {
  try {
#if N3E_HARNESS
#include "harness/state.inc"
#else
    // The player client has no replay, smoke or capture mode (PQ-006). These are
    // the modes shared code still tests; as constants they fold away.
    constexpr bool smoke = false, bad = false, play_smoke = false;
    constexpr bool controls_smoke = false, melee_smoke = false;
    constexpr int world_smoke = 0;
    constexpr float fixed = -1;
#endif
    bool walking_to = false;
    uint32_t move_mode = 0;
    bool running = release.movement.has_value();
    n3e::V destination{};
    Orbit orbit(release.camera);
    bool orbit_drag = false;
    PlayerMotion motion;
    PlayerMotion camera_motion;
    HeldGround held_ground;
    held_ground.delay = release.camera.hold_delay;
    float cursor_x = 0, cursor_y = 0;
    bool window_focused = true;
    uint64_t message_frame_ns = 0;  // PQ-408: the last HUD frame, for the scroll bar's hold
    bool turbo_armed=false;
    uint64_t turbo_self=0, turbo_session=0, turbo_generation=0;
    n3e::V movement_intent{};
    float heading = 0;
    std::string endpoint, ca;
    std::optional<n3e::login::RealmConfig> realm_config;
    int fixed_width = 0, fixed_height = 0;
    bool fullscreen = false;
    for (int i = 2; i < argc; ++i) {
      std::string a = argv[i];
      if (a == "--fixed-window" && i + 1 < argc) {
        std::string size = argv[++i];
        auto split = size.find('x');
        auto dimension = [](std::string_view value) {
          int n = 0;
          auto [end, error] = std::from_chars(value.data(), value.data()+value.size(), n);
          if (error != std::errc{} || end != value.data()+value.size() || n < 64 || n > 8192)
            throw std::runtime_error("fixed window dimensions must be 64..8192");
          return n;
        };
        if (split == std::string::npos) throw std::runtime_error("fixed window expects WIDTHxHEIGHT");
        fixed_width = dimension(std::string_view(size).substr(0, split));
        fixed_height = dimension(std::string_view(size).substr(split+1));
      }
      else if (a == "--fullscreen")
        fullscreen = true;
      else if (a == "--connect" && i + 1 < argc)
        endpoint = argv[++i];
      else if (a == "--realm" && i + 1 < argc) {
        // Spec 04: the Launcher's realm config; host, port and the Discord
        // application replace --connect (spec 02 login).
        realm_config = n3e::login::read_realm(argv[++i]);
        endpoint = realm_config->endpoint();
      }
      else if (a == "--ca" && i + 1 < argc)
        ca = argv[++i];
#if N3E_HARNESS
      else if (a == "--auto-login")
        auto_login = true;
      else if (a == "--play-smoke" && i + 1 < argc) {
        play_smoke = true;
        world_smoke = std::stoi(argv[++i]);
      } else if (a == "--life-smoke" && i + 1 < argc) {
        life_smoke = true;
        world_smoke = std::stoi(argv[++i]);
      } else if (a == "--npc-observe" && i + 1 < argc) {
        npc_observe = true;
        world_smoke = std::stoi(argv[++i]);
      } else if (a == "--melee-smoke" && i + 1 < argc) {
        melee_smoke = true;
        world_smoke = std::stoi(argv[++i]);
      } else if (a == "--movement-smoke" && i + 1 < argc) {
        movement_smoke = true;
        world_smoke = std::stoi(argv[++i]);
      } else if (a == "--camera-smoke" && i + 1 < argc) {
        camera_smoke = controls_smoke = true;
        world_smoke = std::stoi(argv[++i]);
      } else if (a == "--controls-smoke" && i + 1 < argc) {
        controls_smoke = true;
        world_smoke = std::stoi(argv[++i]);
      } else if (a == "--world-smoke" && i + 1 < argc)
        world_smoke = std::stoi(argv[++i]);
      else if (a == "--smoke")
        smoke = true;
      else if (a == "--unsupported")
        bad = true;
      else if (a == "--time" && i + 1 < argc)
        fixed = std::stof(argv[++i]);
      else if (a == "--capture" && i + 1 < argc)
        capture_path = argv[++i];
#endif
      else
        throw std::runtime_error("argument " + a);
    }
#if N3E_HARNESS
    if (movement_smoke)
      running = false; // The scripted walk/run sequence starts in walk mode.
#endif
    auto scene = n3e::load_scene(release);
    std::optional<n3e::WorldMesh> world_asset;
    // N3W2 streams its chunks (PQ-232): only the header and chunk table are
    // read here; the stream starts once the world textures are known.
    std::optional<n3e::WorldTable> world_table;
    std::unique_ptr<n3e::WorldStream> world_stream;
    bool world_limited_noticed = false;
    if (release.world) {
      auto loading = SDL_GetTicksNS();
#if N3E_HARNESS
      // N3E_TEST_WORLD_WHOLE: every N3W2 chunk loaded and uploaded at start,
      // the all-resident draw the streamed captures are compared against.
      const bool whole = !release.world_chunked || std::getenv("N3E_TEST_WORLD_WHOLE");
#else
      const bool whole = !release.world_chunked;
#endif
      if (whole) world_asset = n3e::load_world(release);
      else world_asset = n3e::load_world_index(release, world_table.emplace());
      size_t vertices = 0, indices = 0;
      for (const auto &chunk : world_asset->chunks) {
        vertices += chunk.vertices.size() / n3e::WORLD_FLOATS;
        indices += chunk.indices.size();
      }
      std::cout << "WORLD_LOAD chunks=" << world_asset->chunks.size() << " vertices=" << vertices
                << " indices=" << indices << " ms=" << (SDL_GetTicksNS() - loading) / 1000000
                << (whole ? "" : " streamed") << "\n";
    }
    n3e::Scene marker_ground;
    if(release.target_marker)
      marker_ground.collision=n3e::target_marker_ground(scene.collision,release.world_chunked,
                                                        release.world_chunked||!world_asset?nullptr:&*world_asset);
    std::vector<n3e::Scene> player_scenes;
    std::vector<float> player_durations;
    std::map<uint64_t, PlayerPose> poses;
    std::map<uint64_t, CombatPose> combat_poses;
    std::vector<n3e::Clip> player_clips;
    std::map<uint64_t, AnimationPlayer> animations;
    std::map<uint64_t, size_t> entity_looks; // PQ-253: the looks entry each NPC was last drawn with
    std::map<uint64_t, LayeredAnimation> layers;
    uint64_t animation_session = 0;
    std::vector<n3e::Scene> npc_scenes;
    if (release.presentation) {
      for (const auto *name :
           {"player-idle.bin", "player-walk.bin", "player-attack.bin",
            "player-death.bin", "player-run.bin", "player-backward.bin",
            "player-ready.bin", "player-sit-down.bin", "player-sit-idle.bin", "player-stand-up.bin"}) {
        if(!release.rest&&(std::string(name)=="player-sit-down.bin"||std::string(name)=="player-sit-idle.bin"||std::string(name)=="player-stand-up.bin"))continue;
        if (std::string(name) == "player-ready.bin" && !release.ready_pose)
          continue;
        if (!release.locomotion && (std::string(name) == "player-run.bin" ||
                                    std::string(name) == "player-backward.bin"))
          continue;
        if (std::string(name) == "player-ready.bin") {
          // Stable state indices even for a package without extra locomotion
          // clips.
          while (player_scenes.size() < 6) {
            player_scenes.push_back(player_scenes.front());
            player_durations.push_back(player_durations.front());
          }
        }
        player_scenes.push_back(n3e::load_scene(release, name));
        if (player_scenes.back().texture != player_scenes.front().texture ||
            player_scenes.back().width != player_scenes.front().width ||
            player_scenes.back().height != player_scenes.front().height)
          throw std::runtime_error("player clips must share a texture atlas");
        float duration = .001f;
        for (const auto &track : player_scenes.back().tracks)
          duration = std::max(duration, track.keys.back().time);
        player_durations.push_back(duration);
      }
    }
    if (release.animation) {
      if (release.animation->size() >= 11) for (const char *name :
           {"npc-idle.bin", "npc-walk.bin", "npc-attack.bin", "npc-death.bin"})
        npc_scenes.push_back(n3e::load_scene(release, name));
      for (const auto *set : {&player_scenes, &npc_scenes})
        for (size_t i = 0; i < set->size(); ++i) {
          if (!set->front().compatible((*set)[i]))
            throw std::runtime_error("incompatible animation skeleton/mesh");
          float duration = 0;
          for (const auto &track : (*set)[i].tracks)
            duration = std::max(duration, track.keys.back().time);
          auto &clip = (*release.animation)[i + (set == &npc_scenes ? (release.rest?10:7) : 0)];
          if (std::abs(duration - clip.duration) > .001f)
            throw std::runtime_error("animation duration mismatch");
        }
      if (!npc_scenes.empty() && scene.texture != npc_scenes.front().texture)
        throw std::runtime_error("NPC texture atlas");
      for (size_t i = 0; i < player_durations.size(); ++i)
        player_durations[i] =
            (*release.animation)[i].duration + (*release.animation)[i].blend;
    }
    // Per-template NPC presentation (PQ-253, D-166): one model per looks entry,
    // parsed once at start (load_release has already hashed each file) and
    // shared by every NPC with that looks key; KO's resource managers create an
    // object only when the name's lookup finds none (0041d740, 0041e540), so
    // they share one per file name (an inference). Entry i's four scenes share
    // the first one's atlas and mesh.
    std::vector<std::vector<n3e::Scene>> looks_scenes;
    std::map<std::string, size_t> looks_index;
    const auto looks_started = std::chrono::steady_clock::now();
    uint64_t looks_texture_bytes = 0;
    for (size_t i = 0; i < release.npc_looks.size(); ++i) {
      looks_scenes.push_back(n3e::load_npc_looks(release, i));
      looks_texture_bytes += looks_scenes.back()[0].texture.size();
      looks_index.emplace(release.npc_looks[i].key, i);
    }
    const auto looks_load_ms =
        std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - looks_started).count();
    // N3AT attached characters (PQ-328, D-186): one model per entry, parsed
    // once at start, on a joint the player skeleton has.
    std::vector<std::vector<n3e::Scene>> attachment_scenes;
    if (release.attachments)
      for (size_t i = 0; i < release.attachments->entries.size(); ++i) {
        attachment_scenes.push_back(n3e::load_attachment(release, i));
        if (release.attachments->entries[i].joint >= player_scenes.front().joints.size())
          throw std::runtime_error("attachment joint");
      }
    if(release.animation)player_clips.assign(release.animation->begin(),release.animation->begin()+player_scenes.size());
    if(release.combat_animation){
      for(auto node:release.combat_animation->upper_nodes)
        if(node>=player_scenes.front().nodes.size()||std::none_of(player_scenes.front().joints.begin(),player_scenes.front().joints.end(),[&](const auto&j){return j.node==node;}))throw std::runtime_error("combat mask is not a skeleton joint");
      for(size_t i=0;i<release.combat_animation->clips.size();++i){
        auto scene=n3e::load_scene(release,"combat-"+std::to_string(i)+".bin");
        const auto&clip=release.combat_animation->clips[i];float duration=0;
        // PQ-420 (D-217): a ranged cast's clip plays over the cast time.
        if(clip.stretch!=1)for(auto&t:scene.tracks)for(auto&k:t.keys)k.time*=clip.stretch;
        for(const auto&t:scene.tracks)duration=std::max(duration,t.keys.back().time);
        if(!player_scenes.front().compatible(scene)||std::abs(duration-clip.duration)>.001f)throw std::runtime_error("combat animation geometry/duration");
        player_scenes.push_back(std::move(scene));player_clips.push_back(clip);player_durations.push_back(clip.duration+clip.blend);
      }
#if N3E_HARNESS
      for(size_t i=0;i<release.combat_animation->profiles.size();++i)
        if(const auto&profile=release.combat_animation->profiles[i];profile.ranged.cast_ms){
          const auto&clip=release.combat_animation->clips[profile.attacks[0]];
          std::cout<<"RANGED_CAST profile="<<i+1<<" clip="<<profile.attacks[0]<<" cast_ms="<<profile.ranged.cast_ms<<" duration="<<clip.duration
                   <<" stretch="<<clip.stretch<<" blend="<<clip.blend<<" marker="<<clip.markers[0]<<std::endl;
        }
#endif
    }
    // PQ-317: the first combat-animation clip's index among the player's clips.
    const size_t combat_base=player_scenes.size()-(release.combat_animation?release.combat_animation->clips.size():0);
    std::optional<n3e::RenderDetail> detail;
    if(release.render_detail) detail=n3e::load_render_detail(release,player_scenes.front());
    // PQ-211: KO's Option.Ini WeaponEffect.EffectVisible (0064b9b0, default on)
    // switches equipped-item effects; read once at start, as KO reads it.
    const auto client_options=ClientOptions::load();
    n3e::AppearanceEffects appearance_effects;
    if(detail&&release.effects&&client_options.weapon_effects)appearance_effects.build(*release.effects,player_scenes.front());
    // PQ-315: the 2233 client's equipment glow (N3E3), a 2233/2145 addition the
    // 1298 client does not have; Option.ini [Addition2233] EquipmentGlow=0 turns
    // it off. Only a package cooked with it carries any.
    n3e::EquipmentGlow equipment_glow;
#if N3E_HARNESS
    // N3E_TEST_EQUIPMENT_GLOW_CAPTURES=t,t...: with --capture, one capture
    // each time the controlled character has been drawn for t seconds, so a
    // glow is captured at a known phase of its clock (on or off alike).
    std::vector<double> glow_capture_at;double glow_self_first=-1;
    // PQ-320: this frame's glowing ranges as screen boxes (entity, self, key,
    // x0, y0, x1, y1), printed with each glow capture so a suite can find each
    // player's item in it.
    struct GlowBox{uint64_t entity;bool self;uint32_t key;float x0,y0,x1,y1;};
    std::vector<GlowBox> glow_boxes;
    if(const char*at=std::getenv("N3E_TEST_EQUIPMENT_GLOW_CAPTURES"))
      for(std::string rest=at;!rest.empty();){auto comma=rest.find(',');glow_capture_at.push_back(std::stod(rest.substr(0,comma)));
        rest=comma==std::string::npos?"":rest.substr(comma+1);}
    std::sort(glow_capture_at.begin(),glow_capture_at.end(),std::greater<>());
    // PQ-333 (a showcase framing, test client only): N3E_TEST_CAMERA="t yaw
    // pitch distance;..." holds the orbit at the last entry whose t (seconds the
    // controlled character has been drawn, the glow capture clock) has passed,
    // the first before then; N3E_TEST_SHOWCASE_TARGET=t presses the package's
    // nearest-enemy key (KO's Z) once at t, as a player would;
    // N3E_TEST_SHOWCASE_ATTACK=t presses the attack toggle (KO's R) once at t
    // (PQ-347). N3E_TEST_SHOWCASE_SKILL="t index;..." uses the package's
    // skill `index` (0-based) once at each t, as a double click on it in the
    // skill window does, and N3E_TEST_SHOWCASE_SELECT="t id" selects entity
    // `id` once at t, as a click on it does (PQ-466). An entry "t index
    // unchecked" sends the skill without the client's start-limit hint, as a
    // client that skips it would, so the server's own refusal shows (PQ-469).
    struct ShowcaseView{double at;float yaw,pitch,distance;};
    std::vector<ShowcaseView> showcase_views;double showcase_target_at=-1,showcase_attack_at=-1;
    struct ShowcaseSkill{double at;unsigned index;bool unchecked;};
    std::vector<ShowcaseSkill> showcase_skills;
    if(const char*uses=std::getenv("N3E_TEST_SHOWCASE_SKILL"))
      for(std::string rest=uses;!rest.empty();){auto semi=rest.find(';');std::istringstream in(rest.substr(0,semi));double at;unsigned index;std::string mode,extra;
        if(!(in>>at>>index)||((in>>mode)&&mode!="unchecked")||(in>>extra)||!std::isfinite(at)||at<0||at>3600||!release.skills||index>=release.skills->entries.size())
          throw std::runtime_error("N3E_TEST_SHOWCASE_SKILL expects t index [unchecked];... for the package's skills");
        showcase_skills.push_back({at,index,mode=="unchecked"});rest=semi==std::string::npos?"":rest.substr(semi+1);}
    double showcase_select_at=-1;uint64_t showcase_select=0;
    if(const char*at=std::getenv("N3E_TEST_SHOWCASE_SELECT")){std::istringstream in(at);std::string rest;
      if(!(in>>showcase_select_at>>showcase_select)||(in>>rest)||!std::isfinite(showcase_select_at)||showcase_select_at<0||showcase_select_at>3600||!showcase_select)
        throw std::runtime_error("N3E_TEST_SHOWCASE_SELECT expects t id");}
    if(const char*views=std::getenv("N3E_TEST_CAMERA"))
      for(std::string rest=views;!rest.empty();){auto semi=rest.find(';');std::istringstream in(rest.substr(0,semi));ShowcaseView v{};
        if(!(in>>v.at>>v.yaw>>v.pitch>>v.distance)||!std::isfinite(v.at)||!std::isfinite(v.yaw)||!std::isfinite(v.pitch)||!(v.distance>0&&v.distance<100))
          throw std::runtime_error("N3E_TEST_CAMERA expects t yaw pitch distance;...");
        showcase_views.push_back(v);rest=semi==std::string::npos?"":rest.substr(semi+1);}
    if(const char*at=std::getenv("N3E_TEST_SHOWCASE_TARGET")){std::istringstream in(at);std::string rest;
      if(!(in>>showcase_target_at)||(in>>rest)||!std::isfinite(showcase_target_at)||showcase_target_at<0||showcase_target_at>3600)
        throw std::runtime_error("N3E_TEST_SHOWCASE_TARGET expects seconds from 0 to 3600");}
    if(const char*at=std::getenv("N3E_TEST_SHOWCASE_ATTACK")){std::istringstream in(at);std::string rest;
      if(!(in>>showcase_attack_at)||(in>>rest)||!std::isfinite(showcase_attack_at)||showcase_attack_at<0||showcase_attack_at>3600)
        throw std::runtime_error("N3E_TEST_SHOWCASE_ATTACK expects seconds from 0 to 3600");}
#endif
    // PQ-348 (D-191): an N3D3 appearance key draws with its part's render
    // state, as KO's 004196a0 draws each part through 00412570.
    bool part_states=true;
#if N3E_HARNESS
    // N3E_TEST_PART_STATES=1 reports each key's state when first drawn and,
    // with each glow capture, the screen corners of a small state range (a
    // synthetic part); =ignore also draws every key as N3D2 does (a
    // comparison capture for the suites, never a package switch); =compare
    // draws the frame after each glow capture as N3D2 does and the one after
    // that with the states again, capturing both (<capture>.ignored.ppm,
    // <capture>.again.ppm), so a suite compares one scene a frame apart.
    const char*part_state_test=std::getenv("N3E_TEST_PART_STATES");
    if(part_state_test&&std::string(part_state_test)=="ignore")part_states=false;
    const bool part_state_compare=part_state_test&&std::string(part_state_test)=="compare";
    const bool part_states_default=part_states;
    struct PartStateFollow{std::string base;double at=0;int left=0;};
    PartStateFollow part_state_follow;
    std::set<std::pair<uint64_t,uint32_t>> part_state_seen;
    struct PartCorners{uint64_t entity;bool self;uint32_t key;std::vector<std::array<float,2>> corners;};
    std::vector<PartCorners> part_corners;
#endif
    if(detail&&release.effects&&!release.effects->glow.empty()){
      if(client_options.equipment_glow)equipment_glow.build(*release.effects);
      std::cout<<"equipment glow: "<<release.effects->glow.size()<<" record(s), a 2233/2145 addition (N3E3), "
               <<(client_options.equipment_glow?"on; Option.ini [Addition2233] EquipmentGlow=0 turns it off":"off by Option.ini [Addition2233] EquipmentGlow=0")<<std::endl;
    }
    // PQ-328: the 2233 client's attached characters (N3AT), a 2233/2145
    // addition; Option.ini [Effect] Wing=0 (2233's own key) hides the
    // optional ones, as 2233 hides CPlayerWing slot 0.
    n3e::AttachedCharacters attached;
    std::map<std::pair<uint64_t,size_t>,AnimationPlayer> attached_animations;
    std::map<std::pair<uint64_t,size_t>,n3e::AttachedCharacters::PlugState> attached_plugs;  // PQ-317
#if N3E_HARNESS
    // N3E_TEST_ATTACHMENT_CAPTURES=t,t...: with --capture, one capture each
    // time the controlled character has been drawn with any attachment for t
    // seconds (AttachedCharacters::Clock::drawn), so a pulse or a skeletal
    // plug's clip is captured at a known phase (option on or off).
    std::vector<double> attachment_capture_at;double attachment_self_drawn=-1;
    // This frame's attachments as screen boxes, printed with each capture.
    struct AttachedBox{uint64_t entity;bool self;size_t entry;float x0,y0,x1,y1;};
    std::vector<AttachedBox> attached_boxes;
    // PQ-359: and the wearers' drawn appearance keys (GlowBox), lit or not, so
    // a suite can set an attachment beside its wearer's parts.
    std::vector<GlowBox> attached_part_boxes;
    if(const char*at=std::getenv("N3E_TEST_ATTACHMENT_CAPTURES"))
      for(std::string rest=at;!rest.empty();){auto comma=rest.find(',');attachment_capture_at.push_back(std::stod(rest.substr(0,comma)));
        rest=comma==std::string::npos?"":rest.substr(comma+1);}
    std::sort(attachment_capture_at.begin(),attachment_capture_at.end(),std::greater<>());
    // PQ-355: either capture clock set; the camera then never edge-yaws, and
    // each capture prints the camera it drew (CAPTURE_CAMERA), so a suite can
    // require the same view in every client run it compares.
    const bool scene_captures=!glow_capture_at.empty()||!attachment_capture_at.empty();
#endif
    if(detail&&release.attachments){
      attached.build(*release.attachments);
      std::cout<<"attached characters: "<<release.attachments->entries.size()<<" entr"<<(release.attachments->entries.size()==1?"y":"ies")
               <<", a 2233/2145 addition (N3AT); optional ones "
               <<(client_options.wing?"shown; Option.ini [Effect] Wing=0 hides them":"hidden by Option.ini [Effect] Wing=0")<<std::endl;
    }
    std::map<uint64_t,std::vector<n3e::character_lod::AttachmentState>> attachment_states;
    std::unique_ptr<n3e::WorldClient> network;
    if (!endpoint.empty())
      network =
          std::make_unique<n3e::WorldClient>(release, scene, endpoint, ca);
    // Spec 02: with a realm config naming a Discord application the login screen
    // is "Log in with Discord"; ENTER starts it, ESC cancels the browser wait.
    std::unique_ptr<n3e::login::Flow> discord_flow;
    bool discord_start = false, discord_cancel = false;
    if (realm_config && !realm_config->discord_client_id.empty()) {
      bool launch = true;
#if N3E_HARNESS
      // A suite plays the browser itself from the printed address.
      launch = !std::getenv("N3E_TEST_NO_BROWSER");
#endif
      discord_flow = std::make_unique<n3e::login::Flow>(*realm_config, launch);
    }
    n3e::WorldState world;
    // PQ-406 (D-209): the world notices (chat, whisper, rest and admin refusals)
    // already copied to the HUD's message line.
    uint64_t notices_seen = 0;
    // Spec 03: operator notices already shown; the last one, for a HUD without a
    // message line, and a level-2 notice's centre banner until it lapses.
    uint64_t operator_notices_seen = 0;
    std::string operator_line, banner;
    std::chrono::steady_clock::time_point banner_until{};
#if N3E_HARNESS
    // PQ-355: the camera a scene capture drew, printed after its capture line.
    auto capture_camera=[&](double at){
      char line[256];std::snprintf(line,sizeof line,"CAPTURE_CAMERA at=%g yaw=%.5f pitch=%.5f distance=%.4f self=%.3f,%.3f,%.3f",
                                   at,orbit.yaw,orbit.pitch,orbit.distance,world.predicted[0],world.predicted[1],world.predicted[2]);
      std::cout<<line<<std::endl;};
#endif
    n3e::MeleeIntent melee;
    n3e::targeting::DoubleClick left_double;  // PQ-011
    std::optional<uint64_t> click_actor;      // this left press's pick, for its bindings
    // Actor pick geometry (PQ-146, D-138): the last drawn frame's actors (box,
    // LOD, triangles) and the model boxes, built once per model from its joints
    // or vertices as the package's pick policy says (KO builds the box when the
    // skeleton loads, 0041b000, and again in the final dying pose at state 5,
    // 0045a2c0).
    n3e::targeting::PickFrame pick_frame;
    using PickBox = n3e::targeting::Box;
    auto last_frame = [](const n3e::Scene &s) {
      float t = 0;
      for (const auto &track : s.tracks) t = std::max(t, track.keys.back().time);
      return t;
    };
    std::optional<PickBox> player_box, player_dead_box, npc_box, npc_dead_box;
    if (!player_scenes.empty()) {
      player_box = n3e::targeting::model_box(player_scenes[0], player_scenes[0].sample(0), release.pick);
      if (player_scenes.size() > 3)
        player_dead_box = n3e::targeting::model_box(player_scenes[3], player_scenes[3].sample(last_frame(player_scenes[3])), release.pick);
    }
    if (npc_scenes.size() > 3) {
      npc_box = n3e::targeting::model_box(npc_scenes[0], npc_scenes[0].sample(0), release.pick);
      npc_dead_box = n3e::targeting::model_box(npc_scenes[3], npc_scenes[3].sample(last_frame(npc_scenes[3])), release.pick);
    }
    PickBox legacy_box = n3e::targeting::model_box(scene, scene.sample(0), release.pick);
    // Each looks model's own boxes, standing and in its final death pose (KO
    // rebuilds the actor's box after 0041b260's load, 0041b378 -> 0041b000).
    std::vector<std::pair<PickBox, PickBox>> looks_boxes;
    for (const auto &clips : looks_scenes)
      looks_boxes.emplace_back(n3e::targeting::model_box(clips[0], clips[0].sample(0), release.pick),
                               n3e::targeting::model_box(clips[0], clips[3].sample(last_frame(clips[3])), release.pick));
    n3e::ManualAttackInput manual_attack_input;
    bool friends_open=false;unsigned friend_page=0;uint64_t friend_seq=0,friend_query=0,friend_refresh=0;n3e::FriendRequest friend_retry;
    bool features_open=false;
    FeatureUI feature_ui;
    Hotbar hotbar;
    PanelState panel_state;int panel_width=0,panel_height=0;
    struct InventoryRightPress {std::string key;uint64_t self,session,revision;unsigned bag_page,hotbar_page;};
    std::optional<InventoryRightPress> inventory_right_press;
    bool uif_dialogs=false,uif_pickup=false;
    bool party_open=false,party_block=false;uint64_t party_seq=0,party_invitation=0,party_group=0;
    bool bank_open=false; n3e::StorageRequest storage_retry;
    unsigned bank_secret=0;std::string bank_old,bank_new;n3e::StorageAuthRequest bank_auth_retry;std::string bank_prompt;
    unsigned character_page=2;
    bool bag_open=false, shop_open=false, equipment_open=false; unsigned bag_page=0; uint64_t bag_seq=0;
    auto nearest_storage=[&]()->const n3e::StorageService* {
      if(!release.storage)return nullptr;
      const n3e::StorageService *best=nullptr;float distance=1e30f;
      for(const auto &v:release.storage->services){float d=v.position[0]*v.position[0]+v.position[2]*v.position[2];
        for(const auto &e:world.world.entities())if(e.id()==world.world.self())d=std::pow(e.x()-v.position[0],2)+std::pow(e.z()-v.position[2],2);
        if(d<distance){distance=d;best=&v;}
      }return best;
    };
    auto nearest_shop=[&]()->const n3e::Shop* {
      if(!release.commerce)return nullptr;
      const n3e::Shop *selected=nullptr;float nearest=std::numeric_limits<float>::max();
      for(const auto &shop:release.commerce->shops) {float d=std::hypot(world.predicted[0]-shop.position[0],world.predicted[2]-shop.position[2]);if(d<nearest){nearest=d;selected=&shop;}}
      return selected;
    };
    auto feature_buttons=[&](){
      std::vector<std::pair<std::string,std::string>> buttons;
      if(release.inventory)buttons.push_back({"inventory","Inventory [I]"});
      if(release.equipment)buttons.push_back({"equipment","Character"});
      if(release.commerce)buttons.push_back({"shop","Shop / repair"});
      if(release.storage)buttons.push_back({"bank","Warehouse"});
      if(release.storage_auth)buttons.push_back({"unlock","Unlock bank"});
      if(release.friends)buttons.push_back({"friends","Friends"});
      if(release.party)buttons.push_back({"party","Party"});
      if(release.inventory)buttons.push_back({"features","Help"});
      return buttons;
    };
    n3e::BagRequest bag_retry;
    LootUI loot_ui;
    uint64_t loot_retry_at=0;
    uint64_t target = 0, action_seq = 0, respawn_seq = 0, claim_seq = 0, last_self = 0;
    n3e::SkillFailures skill_failures;  // PQ-469 (D-235)
#if N3E_HARNESS
    std::vector<n3e::MessageLine> skill_failed_drawn;  // failed lines posted, not yet seen drawn
#endif
    int entry = 0; // account, password, selection, create-name, playing, chat
    std::string text_entry, account, password;

    float duration = 1;
    for (const auto &track : scene.tracks)
      duration = std::max(duration, track.keys.back().time);
    if (!SDL_Init(SDL_INIT_VIDEO))
      throw std::runtime_error(SDL_GetError());
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, bad ? 99 : 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK,
                        SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 24);
    auto *w = SDL_CreateWindow(network ? "n3e - Test field" : "n3e foundation",
                               fixed_width ? fixed_width : network ? 1280 : 800,
                               fixed_height ? fixed_height : network ? 800 : 600,
                               SDL_WINDOW_OPENGL | (fixed_width ? 0 : SDL_WINDOW_RESIZABLE));
    if (!w)
      throw std::runtime_error(SDL_GetError());
    if (fixed_width &&
        (!SDL_SetWindowMinimumSize(w, fixed_width, fixed_height) ||
         !SDL_SetWindowMaximumSize(w, fixed_width, fixed_height)))
      throw std::runtime_error(SDL_GetError());
    if (fullscreen) {
      // An exclusive display mode of exactly the fixed size: the whole frame,
      // world and HUD together, is scaled to the monitor (Wayland emulates the
      // mode through compositor scaling), never the HUD alone.
      if (!fixed_width)
        throw std::runtime_error("--fullscreen requires --fixed-window");
      SDL_DisplayMode mode;
      if (!SDL_GetClosestFullscreenDisplayMode(SDL_GetDisplayForWindow(w), fixed_width, fixed_height, 0, false, &mode) ||
          mode.w != fixed_width || mode.h != fixed_height)
        throw std::runtime_error("no " + std::to_string(fixed_width) + "x" + std::to_string(fixed_height) + " fullscreen display mode");
      if (!SDL_SetWindowFullscreenMode(w, &mode) || !SDL_SetWindowFullscreen(w, true) || !SDL_SyncWindow(w))
        throw std::runtime_error(SDL_GetError());
      std::cout << "fullscreen mode=" << mode.w << "x" << mode.h << "@" << mode.refresh_rate << "\n";
    }
    auto ctx = SDL_GL_CreateContext(w);
    if (!ctx)
      throw std::runtime_error(SDL_GetError());
    load_gl();
    const bool vsync = SDL_GL_SetSwapInterval(1);
    // glGetString returns null on error (PQ-123); never stream or copy a null pointer.
    const auto gl_text = [](GLenum name) { return reinterpret_cast<const char *>(glGetString(name)); };
    const auto shown = [](const char *text) { return text ? text : "(null)"; };
    const char *backend = SDL_GetCurrentVideoDriver();
    std::cout << "backend=" << shown(backend)
              << " vendor=" << shown(gl_text(GL_VENDOR))
              << " renderer=" << shown(gl_text(GL_RENDERER))
              << " version=" << shown(gl_text(GL_VERSION)) << " tools=" << TOOLS
              << "\n";
#if N3E_HARNESS
    // SDL's offscreen video driver, which tests/live.py selects for its graphical
    // clients (PQ-121), renders on the GPU into an EGL pbuffer with no display and
    // no window, so a swap never waits for a vertical blank. Its swaps are paced
    // to a 60 Hz display instead (after SDL_GL_SwapWindow below): a test client
    // keeps a windowed client's frame cadence and never spins uncapped. Only the
    // test client does this: a player never runs this driver (it shows nothing).
    const bool offscreen = backend && std::strcmp(backend, "offscreen") == 0;
    constexpr uint64_t offscreen_vblank_ns = 1000000000ull / 60;
    const uint64_t offscreen_origin = SDL_GetTicksNS();
    if (offscreen)
      std::cout << "offscreen swaps paced to 60 Hz\n";
    // Test runs that must exercise the GPU (tests/live.py under N3E_GRAPHICAL=1,
    // PQ-116) refuse a software rasteriser instead of passing on one, and refuse a
    // renderer they cannot identify.
    if (const char *need = std::getenv("N3E_REQUIRE_HARDWARE_GL"); need && std::string(need) == "1") {
      const char *name = gl_text(GL_RENDERER);
      if (!name)
        throw std::runtime_error("GL_RENDERER unavailable; renderer refused (N3E_REQUIRE_HARDWARE_GL=1)");
      const std::string renderer = name;
      for (const char *soft : {"llvmpipe", "softpipe", "swrast", "Software Rasterizer"})
        if (renderer.find(soft) != std::string::npos)
          throw std::runtime_error("software renderer " + renderer + " refused (N3E_REQUIRE_HARDWARE_GL=1)");
    }
#endif
    // Right-drag orbit runs only while the window is in relative mouse mode: the
    // checks below cancel orbit_drag when it is not. SDL's offscreen driver has no
    // relative mode (SDL_SetWindowRelativeMouseMode fails, "That operation is not
    // supported"; PQ-239), so there the test client keeps the mode it asked for
    // itself and the replays' scripted right drags turn the camera as on a desktop
    // (PQ-129). Only the test client on the offscreen driver; every other window,
    // and always the player's, keeps SDL's answer.
#if N3E_HARNESS
    bool offscreen_relative = false;
#endif
    const auto set_relative_mouse = [&](bool on) {
      const bool granted = SDL_SetWindowRelativeMouseMode(w, on);
#if N3E_HARNESS
      offscreen_relative = offscreen && on && !granted;
#else
      (void)granted;
#endif
    };
    const auto relative_mouse = [&] {
#if N3E_HARNESS
      if (offscreen_relative)
        return true;
#endif
      return SDL_GetWindowRelativeMouseMode(w);
    };
    const char *vs = R"(#version 330 core
layout(location=0) in vec3 pos;layout(location=1) in vec3 normal;layout(location=2) in vec2 uv;layout(location=3) in vec2 uv2;layout(location=4) in vec2 slots;
uniform vec2 camera;uniform float offset;uniform float aspect;out vec2 texcoord;out vec2 texcoord2;flat out vec2 cells;out vec3 n;out vec3 worldpos;
uniform float farplane;uniform float nearplane;uniform float projection;uniform vec2 foglimits;out float fogamount;uniform float gameplay;uniform float gui;uniform vec3 eye;uniform vec3 rightward;uniform vec3 upward;uniform vec3 backward;
void main(){vec3 p=pos+vec3(offset,0,0)-vec3(camera,0);gl_Position=vec4(p.x/(2.1*aspect),(p.y-.7-p.z*.25)/2.1,-p.z*.1,1);if(gameplay>0.5){vec3 d=pos-eye;float z=dot(d,backward);gl_Position=vec4(dot(d,rightward)*projection/aspect,dot(d,upward)*projection,-(farplane+nearplane)/(farplane-nearplane)*z-(2*nearplane*farplane)/(farplane-nearplane),-z);}if(gui>0.5)gl_Position=vec4(pos.xy,gui>1.5?pos.z:0,1);texcoord=uv;texcoord2=uv2;cells=slots;n=normal;worldpos=pos;fogamount=foglimits.y>0?clamp((length(pos-eye)-foglimits.x)/(foglimits.y-foglimits.x),0,1):0;})";
    const char *fs = R"(#version 330 core
in float fogamount;uniform vec3 fogcolor;uniform float nofog;in vec2 texcoord;in vec2 texcoord2;flat in vec2 cells;in vec3 n;in vec3 worldpos;uniform sampler2D chart;uniform sampler2DArray worldchart;uniform sampler2DArray native0,native1,native2,native3,native4,native5,native6,native7;uniform float marker;uniform float native_detail;uniform float light;uniform float gui;uniform float world;uniform vec4 grid;uniform vec4 partstate;uniform vec4 glow;uniform float wearer;uniform vec2 sequence;out vec4 color;
uniform float overlay;uniform sampler2DArray overlaymaps;uniform vec4 overlaygrid;uniform vec4 overlaycell;uniform vec2 overlaypatch;uniform int overlaylayers[16];
vec4 cellsample(vec2 uv,float slot){
 // Texture IDs are categorical: the flat varying must not be interpolated.
 // Independent mip chains; each part selects repeat or mirrored repeat.
 if(native_detail<.5)return texture(worldchart,vec3(uv,slot));
 int bank=int(slot)/2048;vec3 q=vec3(uv,mod(slot,2048.));vec2 dx=dFdx(uv),dy=dFdy(uv);
 if(bank==0)return textureGrad(native0,q,dx,dy);if(bank==1)return textureGrad(native1,q,dx,dy);
 if(bank==2)return textureGrad(native2,q,dx,dy);if(bank==3)return textureGrad(native3,q,dx,dy);
 if(bank==4)return textureGrad(native4,q,dx,dy);if(bank==5)return textureGrad(native5,q,dx,dy);
 if(bank==6)return textureGrad(native6,q,dx,dy);return textureGrad(native7,q,dx,dy);}
// n3e's light on a character's equipped parts (the world branch). PQ-359: an
// N3AT model (wearer set) takes it too, so a skeletal plug or a cospre
// attachment is lit as its wearer's parts are (1298 004196a0 lights parts and
// plugs alike; 2233 00435440 draws a plug's inner parts as any parts).
float partshade(vec3 n){return .35+light*max(dot(normalize(n),normalize(vec3(.35,.85,.4))),0);}

void main(){if(marker>0.5){vec4 a=texture(chart,texcoord);color=vec4(a.rgb*(.35+light*max(dot(normalize(n),normalize(vec3(.35,.85,.4))),0)),a.a);color.rgb=mix(color.rgb,fogcolor,fogamount);return;}if(gui>0.5){color=(gui>2.5?cellsample(texcoord,cells.x):texture(chart,texcoord))*vec4(n,1);if(gui>1.5&&color.a<0.5)discard;return;}
// A map's terrain tile carries two layers the reference adds together
// (D3DTOP_ADD); its partial tiles are black where they contribute nothing.
// Object parts point the second layer at a transparent slot and cut out on
// alpha, which is what the reference's alpha test does for foliage.
// PQ-348 (D-191): an N3D3 appearance key's range sets partstate x and y as a
// looks run does (x set, y the alpha reference) and z when it blends (N3D3 has
// no unlit flag); its alpha goes to the blend, and the glow scales its colour
// only (2233 0042cf30 sets the colour op, never the alpha op). A key that does
// not blend writes alpha 1, as every N3D2 key does.
// PQ-388 (D-203): an N3W5 single-layer unlit vertex (second slot -1) is its
// first layer's texel alone: 1298's colour-map tile ends its cascade at a
// stage with COLORARG1 TEXTURE and a null texture, before the light.
// PQ-394 (D-212): a part's texture sequence (sequence x set) draws its current
// frame's slot (sequence y) in place of the first-layer slot.
// PQ-387 (D-204): an N3WO map over a near terrain patch around the eye, as
// 1298's last near-patch pass (005a2640 at 005a2c62) draws it: the block's map
// at its tile's inset cell (005a0410's UVs), texel x the light (stage 0
// MODULATE of TEXTURE and DIFFUSE), alpha the texel's, blended by the caller;
// alpha 0 is dropped as the device's GREATER-0 test drops it. Gradients come
// from the continuous position, so a tile seam keeps its mip level.
if(world>0.5&&overlay>0.5){
 float rx=(worldpos.x-overlaygrid.x)/overlaygrid.z-overlaypatch.x,rz=(overlaygrid.y-worldpos.z)/overlaygrid.z-overlaypatch.y;
 float B=overlaycell.x,C=overlaycell.y,I=overlaycell.z,S=overlaycell.w,span=C-2.*I;
 vec2 k=vec2(span/S,-span/S),gx=vec2(dFdx(rx),dFdx(rz))*k,gy=vec2(dFdy(rx),dFdy(rz))*k;
 float tx=clamp(floor(rx),0.,overlaygrid.w-1.),tz=clamp(floor(rz),0.,overlaygrid.w-1.);
 int layer=overlaylayers[int(tz/B)*int(overlaygrid.w/B+.5)+int(tx/B)];
 vec2 uv=vec2((mod(tx,B)*C+I+span*(rx-tx))/S,((B-mod(tz,B))*C-I-span*(rz-tz))/S);
 vec4 t=textureGrad(overlaymaps,vec3(uv,float(max(layer,0))),gx,gy);
 if(layer<0||floor(t.a*255.+.5)<=0.)discard;
 color=vec4(t.rgb*partshade(n),t.a);color.rgb=mix(color.rgb,fogcolor,fogamount*(1.0-nofog));return;}
if(world>0.5){vec4 a=cellsample(texcoord,sequence.x>.5?sequence.y:cells.x);bool single=cells.y<-.5;
 if(partstate.x>0.5){if(floor(a.a*255.+.5)<=partstate.y*255.)discard;}else if(a.a<0.5)discard;
 vec3 lit=single?a.rgb:min(vec3(1),a.rgb+cellsample(texcoord2,cells.y).rgb);
 // PQ-315: an equipment glow adds its emissive to the light, clamped as
 // Direct3D clamps the vertex colour, then scales the product (MODULATE2X).
 vec3 shade=vec3(partshade(n));
 // PQ-379 (D-201): a world alpha part with KO's RF_NOTUSELIGHT (0x40) is
 // unlit, as 0043dd80 turns lighting off for it (partstate w).
 if(partstate.w>0.5||single)shade=vec3(1);
 if(glow.w>0.)shade=min(vec3(1),shade+glow.rgb)*glow.w;
 color=vec4(lit*shade,partstate.x>0.5&&partstate.z>0.5?a.a:1.);color.rgb=mix(color.rgb,fogcolor,fogamount*(1.0-nofog));return;}
// An N3MM looks run (PQ-265): x set, y the alpha reference (drawn only where
// the 8-bit texture alpha is above it, as KO's GREATER alpha test), z unlit
// (the texture's own colour); the alpha goes to the blend.
if(partstate.x>0.5){vec4 a=texture(chart,texcoord);if(floor(a.a*255.+.5)<=partstate.y*255.)discard;
 vec3 lit=vec3(wearer>0.5?partshade(n):.15+light*max(dot(normalize(n),normalize(vec3(.3,.4,1))),0));
 // PQ-328: an attachment's lit run adds its emissive and modulate as the glow does.
 if(glow.w>0.)lit=min(vec3(1),(partstate.z>0.5?vec3(1):lit)+glow.rgb)*glow.w;else if(partstate.z>0.5)lit=vec3(1);
 color=vec4(a.rgb*lit,a.a);
 color.rgb=mix(color.rgb,fogcolor,fogamount);return;}
vec3 base=texture(chart,texcoord).rgb;
if(texcoord.x<-.5){
 if(texcoord.x<-2.5)base=vec3(.64,.47,.31);
 else if(texcoord.x<-1.5)base=vec3(.18,.32,.48);
 else {float noise=fract(sin(dot(floor(worldpos.xz*9),vec2(12.9898,78.233)))*43758.5453);
 base=mix(vec3(.19,.28,.09),vec3(.29,.36,.14),noise);
 if(abs(worldpos.x)<1.3||abs(worldpos.z)<1.3)base=mix(vec3(.38,.30,.19),vec3(.46,.39,.25),noise);
 if(abs(worldpos.x)>23.7||abs(worldpos.z)>23.7)base=vec3(.27,.25,.19);
 }}
color=vec4(base*(.3+light*max(dot(normalize(n),normalize(vec3(.3,.8,1))),0)),1);
if(texcoord.x>=0){vec3 lit=vec3(wearer>0.5?partshade(n):.15+light*max(dot(normalize(n),normalize(vec3(.3,.4,1))),0));
 // PQ-328: an attachment's lit indices add the emissive, clamped, then the modulate.
 if(glow.w>0.)lit=min(vec3(1),lit+glow.rgb)*glow.w;
 color=vec4(base*lit,1);}
color.rgb=mix(color.rgb,fogcolor,fogamount);
})";
    auto v = shader(GL_VERTEX_SHADER, vs), s = shader(GL_FRAGMENT_SHADER, fs),
         p = glCreateProgram();
    glAttachShader(p, v);
    glAttachShader(p, s);
    glLinkProgram(p);
    int ok;
    glGetProgramiv(p, GL_LINK_STATUS, &ok);
    if (!ok)
      throw std::runtime_error("link failed");
    glDeleteShader(v);
    glDeleteShader(s);
    glUseProgram(p);
    glUniform1i(glGetUniformLocation(p, "worldchart"), 1);
    glUniform1i(glGetUniformLocation(p, "overlaymaps"), 9);
    GLuint vao, vbo, texture;
    glGenVertexArrays(1, &vao);
    glBindVertexArray(vao);
    glGenBuffers(1, &vbo);
    glBindBuffer(GL_ARRAY_BUFFER, vbo);
    for (int a = 0; a < 3; ++a) {
      glEnableVertexAttribArray(a);
      glVertexAttribPointer(a, a == 2 ? 2 : 3, GL_FLOAT, GL_FALSE,
                            8 * sizeof(float),
                            (void *)(uintptr_t)((a == 0   ? 0
                                                 : a == 1 ? 3
                                                          : 6) *
                                                sizeof(float)));
    }
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB8, scene.width, scene.height, 0,
                 GL_RGB, GL_UNSIGNED_BYTE, scene.texture.data());
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    for(unsigned i=0;i<8;++i)glUniform1i(glGetUniformLocation(p,("native"+std::to_string(i)).c_str()),1+i);
    NativeTextures native_textures;
    // An N3W2 world's textures (N3WT, PQ-233): its own banks, never render
    // detail's world subset.
    NativeTextures world_banks;
    GLuint detail_vao=0,detail_vbo=0;
    if(detail) {
      native_textures.upload(detail->textures);

      if(!release.world_chunked)
      for(auto &chunk:world_asset->chunks)
      for(size_t i=0;i<chunk.vertices.size();i+=n3e::WORLD_FLOATS)
        for(size_t j=10;j<12;++j) {
          auto slot=size_t(chunk.vertices[i+j]);
          if(slot>=detail->world_textures)throw std::runtime_error("world native texture slot");
          chunk.vertices[i+j]=native_textures.slots.at(slot);
        }
      glGenVertexArrays(1,&detail_vao);glBindVertexArray(detail_vao);
      glGenBuffers(1,&detail_vbo);glBindBuffer(GL_ARRAY_BUFFER,detail_vbo);
      const int offsets[5]={0,3,6,8,10}, widths[5]={3,3,2,2,2};
      for(int a=0;a<5;++a){glEnableVertexAttribArray(a);glVertexAttribPointer(a,widths[a],GL_FLOAT,GL_FALSE,12*sizeof(float),(void*)(uintptr_t)(offsets[a]*sizeof(float)));}
    }
    if(release.world_chunked) {
      auto loading = SDL_GetTicksNS();
      auto textures = n3e::load_world_textures(release);
      GLint layer_cap = 0, size_cap = 0;
#if N3E_HARNESS
      // Lower array layer and texture size limits than the GPU's, so bank
      // splitting and both refusals can be exercised on any GPU.
      if (const char *cap = std::getenv("N3E_TEST_WORLD_TEXTURE_LAYERS")) layer_cap = std::stoi(cap);
      if (const char *cap = std::getenv("N3E_TEST_WORLD_TEXTURE_SIZE")) size_cap = std::stoi(cap);
#endif
      world_banks.upload_world(textures, layer_cap, size_cap);
      // Chunks loaded at start (the test client's all-resident path); streamed
      // chunks are remapped by the stream.
      for(auto &chunk:world_asset->chunks)
        for(size_t i=0;i<chunk.vertices.size();i+=n3e::WORLD_FLOATS)
          for(size_t j=10;j<12;++j) {
            // D-203: a single-layer unlit vertex keeps its marker.
            if(j==11 && chunk.vertices[i+j]==n3e::WORLD_UNLIT_VERTEX)continue;
            auto slot=size_t(chunk.vertices[i+j]);
            if(slot>=world_banks.slots.size())throw std::runtime_error("world native texture slot");
            chunk.vertices[i+j]=world_banks.slots[slot];
          }
      // D-212: a texture sequence's frames name world textures too.
      for(auto &chunk:world_asset->chunks)
        for(auto &part:chunk.parts)
          if(part.sequence)
            for(auto &slot:part.sequence->slots) {
              if(size_t(slot)>=world_banks.slots.size())throw std::runtime_error("world native texture slot");
              slot=world_banks.slots[size_t(slot)];
            }
      std::cout << "WORLD_TEXTURES textures=" << textures.chains.size() << " banks=" << world_banks.banks.size()
                << " pixels=" << textures.pixels << " ms=" << (SDL_GetTicksNS() - loading) / 1000000 << "\n";
    }
    // One vertex array, vertex buffer and index buffer per world chunk (N3W1
    // is one chunk): each chunk draws from its own buffers (PQ-231).
    struct ChunkBuffers { GLuint vao = 0, vbo = 0, ebo = 0; };
    std::vector<ChunkBuffers> world_buffers;
    // PQ-379 (D-201): the world pass's alpha parts this frame (chunk, part,
    // the level's indices and the sort key), drawn in the effect pass.
    // D-212: `slot` is the frame a sequence part draws (-1: its vertices' own).
    struct WorldAlphaDraw { size_t chunk, part; uint32_t first, count; float key; float slot = -1; };
    std::vector<WorldAlphaDraw> world_alpha;
    // D-212 (PQ-394): the time of the last world pass, for texture sequences.
    uint64_t sequence_last_ns=0;
#if N3E_HARNESS
    // A fixed sequence frame time, and a per-frame log of the sequence parts drawn.
    const char *sequence_fixed=std::getenv("N3E_TEST_SEQUENCE_SECONDS");
    const bool sequence_log=std::getenv("N3E_TEST_SEQUENCE_LOG")!=nullptr;
#endif
    std::vector<float> world_alpha_keys;
    GLuint world_texture = 0;
    GLuint world_samplers[2] = {};
    // A chunk's buffers; its host vertices are freed, its indices kept for
    // progressive refinement.
    auto upload_chunk = [&](size_t c) {
      auto &chunk = world_asset->chunks[c];
      auto &b = world_buffers[c];
      glGenVertexArrays(1, &b.vao);
      glBindVertexArray(b.vao);
      glGenBuffers(1, &b.vbo);
      glBindBuffer(GL_ARRAY_BUFFER, b.vbo);
      glBufferData(GL_ARRAY_BUFFER, chunk.vertices.size() * 4,
                   chunk.vertices.data(), GL_STATIC_DRAW);
      glGenBuffers(1, &b.ebo);
      glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, b.ebo);
      glBufferData(GL_ELEMENT_ARRAY_BUFFER, chunk.indices.size() * 4,
                   chunk.indices.data(), GL_DYNAMIC_DRAW);
      const int offsets[5] = {0, 3, 6, 8, 10}, widths[5] = {3, 3, 2, 2, 2};
      for (int a = 0; a < 5; ++a) {
        glEnableVertexAttribArray(a);
        glVertexAttribPointer(
            a, widths[a], GL_FLOAT, GL_FALSE, n3e::WORLD_FLOATS * sizeof(float),
            (void *)(uintptr_t)(offsets[a] * sizeof(float)));
      }
      chunk.vertices.clear();
      chunk.vertices.shrink_to_fit();
    };
    auto free_chunk = [&](size_t c) {
      auto &b = world_buffers[c];
      glDeleteBuffers(1, &b.vbo);
      glDeleteBuffers(1, &b.ebo);
      glDeleteVertexArrays(1, &b.vao);
      b = {};
      auto &chunk = world_asset->chunks[c];
      n3e::WorldChunk empty;
      empty.x = chunk.x; empty.z = chunk.z; empty.bounded = chunk.bounded;
      empty.lo = chunk.lo; empty.hi = chunk.hi; empty.resident = false;
      chunk = std::move(empty);
    };
    if (world_asset) {
      // The world never moves and is never posed, so each chunk is uploaded
      // once (whole worlds at start, streamed chunks as they arrive) instead
      // of being rebuilt and re-sent every frame like entity geometry.
      size_t triangles = 0;
      world_buffers.resize(world_asset->chunks.size());
      for (size_t c = 0; c < world_asset->chunks.size(); ++c) {
        if (!world_asset->chunks[c].resident) continue;
        triangles += world_asset->chunks[c].indices.size() / 3;
        upload_chunk(c);
      }
      if (world_table) {
        // N3W2 slots name the world's own textures (PQ-233).
        std::vector<float> slot_map = world_banks.slots;
        world_stream = std::make_unique<n3e::WorldStream>(std::move(*world_table), world_asset->terrain, std::move(slot_map));
      }
      glGenTextures(1, &world_texture);
      glActiveTexture(GL_TEXTURE1);
      glBindTexture(GL_TEXTURE_2D_ARRAY, world_texture);
      const auto &w = *world_asset;
      if (!detail && !release.world_chunked) {
      const unsigned inner = w.cell - 2 * w.pad;
      const unsigned columns = w.width / w.cell;
      const unsigned layers = columns * (w.height / w.cell);
      GLint limit = 0;
      glGetIntegerv(GL_MAX_ARRAY_TEXTURE_LAYERS, &limit);
      if (layers > unsigned(limit))
        throw std::runtime_error("world exceeds GPU texture array layer limit");
      std::vector<unsigned char> pixels(size_t(inner) * inner * layers * 4);
      for (unsigned layer = 0; layer < layers; ++layer)
        for (unsigned y = 0; y < inner; ++y) {
          size_t src = ((layer / columns * w.cell + w.pad + y) * w.width
                        + layer % columns * w.cell + w.pad) * 4;
          size_t dst = (size_t(layer) * inner * inner + y * inner) * 4;
          std::copy_n(w.texture.data() + src, inner * 4, pixels.data() + dst);
        }
      glTexImage3D(GL_TEXTURE_2D_ARRAY, 0, GL_RGBA8, inner, inner, layers,
                   0, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
      glGenerateMipmap(GL_TEXTURE_2D_ARRAY);
      }
      glGenSamplers(2, world_samplers);
      for (int i=0; i<2; ++i) {
        glSamplerParameteri(world_samplers[i], GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
        glSamplerParameteri(world_samplers[i], GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glSamplerParameteri(world_samplers[i], GL_TEXTURE_WRAP_S, i ? GL_MIRRORED_REPEAT : GL_REPEAT);
        glSamplerParameteri(world_samplers[i], GL_TEXTURE_WRAP_T, i ? GL_MIRRORED_REPEAT : GL_REPEAT);
      }
      glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
      glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_WRAP_S, GL_REPEAT);
      glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_WRAP_T, GL_REPEAT);
      glUniform1i(glGetUniformLocation(p, "worldchart"), 1);
      glActiveTexture(GL_TEXTURE0);
      if (release.world_chunked)
        std::cout << "world textures=" << world_banks.slots.size() << " triangles=" << triangles << "\n";
      else
        std::cout << "world atlas=" << world_asset->width << "x"
                  << world_asset->height
                  << " triangles=" << triangles << "\n";
      // Free the host atlas; the texture owns it from here.
      world_asset->texture.clear();
      world_asset->texture.shrink_to_fit();
    }
    // PQ-387 (D-204): the N3WO maps over the near terrain, checked against the
    // world's terrain policy; the window's maps go to the GPU as the eye moves.
    std::optional<TerrainOverlay> terrain_overlay;
    if (world_asset && release.world_overlay) {
      terrain_overlay.emplace();
      terrain_overlay->create(n3e::load_world_overlay(release, world_asset->terrain));
      std::cout << "world overlay maps=" << terrain_overlay->overlay.maps.size()
                << " layers=" << terrain_overlay->overlay.layers() << "\n";
    }
    GLuint loot_texture=0;
    std::vector<float> loot_mesh;
    if(release.loot_model){
      auto model=n3e::load_scene(release,"loot-model.bin");loot_mesh=model.skin(model.nodes);
      glGenTextures(1,&loot_texture);glBindTexture(GL_TEXTURE_2D,loot_texture);
      glTexImage2D(GL_TEXTURE_2D,0,GL_RGB8,model.width,model.height,0,GL_RGB,GL_UNSIGNED_BYTE,model.texture.data());
      glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_REPEAT);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_REPEAT);
    }
    std::vector<GLuint> marker_textures;
    if(release.target_marker)for(const auto&part:release.target_marker->parts){
      GLuint t;glGenTextures(1,&t);marker_textures.push_back(t);glBindTexture(GL_TEXTURE_2D,t);
      glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,part.width,part.height,0,GL_RGBA,GL_UNSIGNED_BYTE,part.texture.data());
      glGenerateMipmap(GL_TEXTURE_2D);
      glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_REPEAT);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_REPEAT);
    }
    n3e::EffectPlayer effect_player;
    PresentationEvents presentation_events;
    LocalRelease local_release;
    MeleePresentation melee_presentation;
    SkillsUI skills_ui;
    std::map<unsigned,n3e::Scene> skill_scenes;
    if(release.skills)for(const auto&skill:release.skills->entries){
      auto [it,added]=skill_scenes.try_emplace(skill.animation);
      if(added){it->second=n3e::load_scene(release,"player-skill-"+std::to_string(skill.animation)+".bin");if(!player_scenes.front().compatible(it->second))throw std::runtime_error("skill skeleton mismatch");}
    }
    AudioDevice audio;
    if(release.audio){audio.mixer.spatial=release.audio->spatial;audio.open();}
    uint64_t audio_claim=0,audio_claim_responses=0,audio_session=0;
    std::string audio_claim_key;
    std::vector<n3e::PresentationEvent> local_casts;
    auto sound=[&](const std::string&key){if(release.audio)audio.mixer.play(*release.audio,key,SDL_GetTicks()/1000.);};
    EffectsView effect_view;
    if(release.effects){effect_view.upload(*release.effects);glBindVertexArray(vao);glBindBuffer(GL_ARRAY_BUFFER,vbo);glUseProgram(p);}
    // PQ-316 (D-185): the 2233 client's screen bloom and tone map
    // (postprocess.bin), a 2233/2145 addition the 1298 client does not have;
    // off unless Option.ini [Addition2233] HDR=1. Without it, or when the
    // driver refuses a pass, the scene draws straight to the window as before.
    PostProcessView postprocess;
    uint64_t postprocess_last=0;
    if(release.postprocess){
      std::string why;
      const bool on=client_options.hdr&&postprocess.create(*release.postprocess,why);
      glBindVertexArray(vao);glBindBuffer(GL_ARRAY_BUFFER,vbo);glUseProgram(p);
      std::cout<<"HDR bloom: a 2233/2145 addition (N3PF), "
               <<(on?std::string("on; Option.ini [Addition2233] HDR=0 turns it off")
                    :client_options.hdr?"off: "+why:std::string("off; Option.ini [Addition2233] HDR=1 turns it on"))<<std::endl;
    }
#if N3E_HARNESS
    // PQ-316 harness: N3E_TEST_POSTPROCESS=1 prints each frame's measured and
    // adapted luminance; N3E_TEST_POSTPROCESS_STAGES=FRAME,FRAME... writes
    // every stage of those frames' chains (PREFIX.stage-FRAME-NAME.ppm, with
    // --capture's path as the prefix) and reads their measurement synchronously;
    // N3E_TEST_POSTPROCESS_FRAMES=N keeps a --smoke run open for N frames;
    // N3E_TEST_POSTPROCESS_PATTERN replaces the scene with a known picture:
    // phases "FRAME@BACKGROUND;X,Y,W,H=R,G,B;...|FRAME@...", BACKGROUND
    // "R,G,B" or "stripes" (one-pixel white and black columns), rectangles
    // from the top-left, each phase from its first frame on.
    const bool postprocess_test=std::getenv("N3E_TEST_POSTPROCESS")!=nullptr;
    std::set<int> postprocess_stages;
    if(const char*at=std::getenv("N3E_TEST_POSTPROCESS_STAGES"))
      for(std::string rest=at;!rest.empty();){auto comma=rest.find(',');postprocess_stages.insert(std::stoi(rest.substr(0,comma)));
        rest=comma==std::string::npos?"":rest.substr(comma+1);}
    if(const char*n=std::getenv("N3E_TEST_POSTPROCESS_FRAMES"))smoke_quit=std::max(smoke_quit,std::clamp(std::atoi(n),1,100000));
    struct PatternRect{int x,y,w,h;std::array<float,3> rgb;};
    struct PatternPhase{int frame;bool stripes;std::array<float,3> background;std::vector<PatternRect> rects;};
    std::vector<PatternPhase> pattern;
    if(const char*spec=std::getenv("N3E_TEST_POSTPROCESS_PATTERN")){
      auto split=[](const std::string&text,char c){std::vector<std::string> out;size_t a=0;for(size_t b;(b=text.find(c,a))!=std::string::npos;a=b+1)out.push_back(text.substr(a,b-a));out.push_back(text.substr(a));return out;};
      auto rgb=[&](const std::string&text){auto v=split(text,',');if(v.size()!=3)throw std::runtime_error("pattern colour");return std::array<float,3>{std::stof(v[0])/255,std::stof(v[1])/255,std::stof(v[2])/255};};
      for(const auto&phase:split(spec,'|')){
        auto parts=split(phase,';');auto at=parts[0].find('@');if(at==std::string::npos)throw std::runtime_error("pattern phase");
        PatternPhase ph{std::stoi(parts[0].substr(0,at)),parts[0].substr(at+1)=="stripes",{},{}};
        if(!ph.stripes)ph.background=rgb(parts[0].substr(at+1));
        for(size_t i=1;i<parts.size();++i){auto eq=parts[i].find('=');auto box=split(parts[i].substr(0,eq),',');
          if(eq==std::string::npos||box.size()!=4)throw std::runtime_error("pattern rectangle");
          ph.rects.push_back({std::stoi(box[0]),std::stoi(box[1]),std::stoi(box[2]),std::stoi(box[3]),rgb(parts[i].substr(eq+1))});}
        pattern.push_back(ph);
      }
    }
    if(postprocess.ready&&postprocess_test){const auto&s=postprocess.settings;
      std::cout<<"POSTPROCESS_SETTINGS threshold="<<s.threshold<<" bloom="<<s.bloom<<" exposure="<<s.exposure<<" saturation="<<s.saturation
               <<" lift="<<s.lift<<" adapt_rate="<<s.adapt_rate<<" blur_variance="<<s.blur_variance<<std::endl;}
#endif
    GLuint player_texture = 0;
    std::unique_ptr<HudView> hud;
    if (release.presentation) {
      const auto &t = player_scenes[0];
      glGenTextures(1, &player_texture);
      glBindTexture(GL_TEXTURE_2D, player_texture);
      glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB8, t.width, t.height, 0, GL_RGB,
                   GL_UNSIGNED_BYTE, t.texture.data());
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
      hud = std::make_unique<HudView>(n3e::load_hud(release));
      hud->thresholds = release.thresholds;
      hud->operator_chat = release.names.operator_chat;
      uif_dialogs=hud->data.dialogs;
      uif_pickup=std::any_of(hud->data.records.begin(),hud->data.records.end(),[](const auto&r){return r.panel==9;});
    }
    // One texture per looks atlas; the CPU copy is dropped once uploaded, so a
    // looks costs its atlas once on the GPU and its mesh once in memory.
    const auto looks_upload_started = std::chrono::steady_clock::now();
    std::vector<GLuint> looks_textures(looks_scenes.size());
    if (!looks_textures.empty()) glGenTextures(GLsizei(looks_textures.size()), looks_textures.data());
    for (size_t i = 0; i < looks_scenes.size(); ++i) {
      auto &t = looks_scenes[i][0];
      glBindTexture(GL_TEXTURE_2D, looks_textures[i]);
      // An N3MM atlas keeps its alpha for the run's alpha test and blend (PQ-265).
      glTexImage2D(GL_TEXTURE_2D, 0, t.channels == 4 ? GL_RGBA8 : GL_RGB8, t.width, t.height, 0,
                   t.channels == 4 ? GL_RGBA : GL_RGB, GL_UNSIGNED_BYTE, t.texture.data());
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
      std::vector<unsigned char>().swap(t.texture);
    }
    std::vector<GLuint> attachment_textures(attachment_scenes.size());
    if (!attachment_textures.empty()) glGenTextures(GLsizei(attachment_textures.size()), attachment_textures.data());
    for (size_t i = 0; i < attachment_scenes.size(); ++i) {
      auto &t = attachment_scenes[i][0];
      glBindTexture(GL_TEXTURE_2D, attachment_textures[i]);
      glTexImage2D(GL_TEXTURE_2D, 0, t.channels == 4 ? GL_RGBA8 : GL_RGB8, t.width, t.height, 0,
                   t.channels == 4 ? GL_RGBA : GL_RGB, GL_UNSIGNED_BYTE, t.texture.data());
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
      std::vector<unsigned char>().swap(t.texture);
    }
#if N3E_HARNESS
    for (size_t i = 0; i < looks_scenes.size(); ++i)
      if (!looks_scenes[i][0].runs.empty()) {
        std::cout << "NPC_LOOKS_RUNS looks=" << i << " key=" << release.npc_looks[i].key << " runs=";
        for (const auto &run : looks_scenes[i][0].runs)
          std::cout << (&run == &looks_scenes[i][0].runs.front() ? "" : ";") << run.first << "+" << run.count << ":"
                    << run.flags << ":" << run.source << "/" << run.destination;
        std::cout << "\n";
      }
    for (size_t i = 0; i < looks_boxes.size(); ++i) {
      const auto &[stand, dead] = looks_boxes[i];
      std::cout << "NPC_LOOKS_BOX looks=" << i << " key=" << release.npc_looks[i].key << " size=" << stand.hi[0] - stand.lo[0]
                << "," << stand.hi[1] - stand.lo[1] << "," << stand.hi[2] - stand.lo[2] << " dead_height="
                << dead.hi[1] - dead.lo[1] << " name_always=" << release.npc_looks[i].name_always << "\n";
    }
#endif
    if (!looks_scenes.empty())
      std::cout << "NPC_LOOKS_LOAD looks=" << looks_scenes.size() << " texture_bytes=" << looks_texture_bytes
                << " load_ms=" << looks_load_ms << " upload_ms="
                << std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - looks_upload_started).count()
                << "\n";
    glEnable(GL_DEPTH_TEST);
    glEnable(GL_CULL_FACE);
    glFrontFace(GL_CCW);
#if TOOLS
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGui::GetIO().IniFilename = nullptr;
#if N3E_HARNESS
    if (smoke)
      ImGui::GetIO().ConfigInputTrickleEventQueue = false;
#endif
    ImGui_ImplSDL3_InitForOpenGL(w, ctx);
    ImGui_ImplOpenGL3_Init("#version 330");
#endif
    bool run = true;
    int exit_code = 0;
    float offset = 0, light = .85, cx = 0, cy = 0;
#if TOOLS
    n3e::Editor editor;
#endif
    int frame = 0;
    auto start = SDL_GetTicks();
    auto input_last = start;
    auto fps_start = SDL_GetTicksNS();
    unsigned fps_frames = 0;
    std::string fps_label = "FPS --";
    if (network)
      SDL_StartTextInput(w);
    ItemWait item_wait;
    auto item_command=[&](){
      n3e::Envelope message;
      const auto storage=n3e::parse_storage(text_entry);
      if(storage.kind!=n3e::StorageCommand::none){
        const auto *service=nearest_storage();auto kind=storage.kind;
        if(!service||kind==n3e::StorageCommand::invalid||(kind==n3e::StorageCommand::retry&&storage_retry.request().empty())){text_entry="/bank; /deposit BAG BANK QTY; /withdraw BANK BAG QTY";return true;}
        auto *q=message.mutable_storage_request();
        if(kind==n3e::StorageCommand::retry)*q=storage_retry;
        else{
          q->set_request(std::to_string(world.world.session())+"-bank-"+std::to_string(++bag_seq));q->set_service(service->id);q->set_bag_revision(world.bag.revision());q->set_storage_revision(world.storage.revision());
          q->set_operation(kind==n3e::StorageCommand::open?0:kind==n3e::StorageCommand::deposit?1:kind==n3e::StorageCommand::withdraw?2:kind==n3e::StorageCommand::move?3:kind==n3e::StorageCommand::putcoins?4:5);
          q->set_quantity(storage.quantity);
          if(q->operation()>=1&&q->operation()<=3){const auto &slots=q->operation()==1?world.bag.slots():world.storage.slots();
            if(storage.source>=unsigned(slots.size())||!slots[storage.source].instance()){text_entry="Choose an occupied source slot";return true;}
            q->set_source(storage.source);q->set_destination(storage.destination);q->set_instance(slots[storage.source].instance());
          }
        }
        // Opening can charge a fee, so it needs the same exact retry identity.
        if(!item_wait.begin(message,world,SDL_GetTicks()/1000.)){text_entry="Wait for the current item operation";return true;}
        storage_retry=*q;
        network->send(message);party_open=friends_open=false;bank_open=true;bag_open=true;shop_open=false;equipment_open=false;entry=4;text_entry.clear();return true;
      }
      const auto bag=n3e::parse_bag(text_entry);
      if(bag.kind!=n3e::BagCommand::none) {
        const auto *shop=nearest_shop();
        bool commerce=bag.kind==n3e::BagCommand::buy||bag.kind==n3e::BagCommand::sell;
        bool gear=bag.kind==n3e::BagCommand::equip||bag.kind==n3e::BagCommand::unequip||bag.kind==n3e::BagCommand::gearswap;
        bool gear_source=bag.kind==n3e::BagCommand::repairgear||bag.kind==n3e::BagCommand::unequip||bag.kind==n3e::BagCommand::gearswap;
        bool gear_dest=bag.kind==n3e::BagCommand::equip||bag.kind==n3e::BagCommand::gearswap;
        const auto &records=gear_source?world.bag.equipment():world.bag.slots();
        bool use=bag.kind==n3e::BagCommand::use;
        bool repair=bag.kind==n3e::BagCommand::repair||bag.kind==n3e::BagCommand::repairgear;
        if((use&&(release.consumables.empty()||bag.source>=unsigned(records.size())||!records[bag.source].instance()))||
           (bag.kind==n3e::BagCommand::equipment&&!release.equipment)||
           (gear&&(!release.equipment||bag.source>=unsigned(records.size())||!records[bag.source].instance()||bag.destination>=unsigned(gear_dest?world.bag.equipment_size():world.bag.slots_size())))||
           !release.inventory || bag.kind==n3e::BagCommand::invalid ||
           ((commerce||bag.kind==n3e::BagCommand::shop)&&!shop) ||
           (repair&&(!release.commerce||!release.commerce->repair||bag.source>=unsigned(records.size())||!records[bag.source].instance())) ||
           (commerce&&(bag.source>=unsigned(world.bag.slots_size())||(bag.kind==n3e::BagCommand::buy&&bag.destination>=shop->items.size())||(bag.kind==n3e::BagCommand::sell&&!world.bag.slots(bag.source).instance()))) ||
           (bag.kind==n3e::BagCommand::retry && bag_retry.request().empty()) ||
           (bag.kind==n3e::BagCommand::swap && (bag.source>=unsigned(world.bag.slots_size()) || bag.destination>=world.bag.capacity() || !world.bag.slots(bag.source).instance()))) {
          text_entry=gear?"/equip BAG EQUIPMENT; /unequip EQUIPMENT BAG":repair?"/repair SLOT":commerce?"/buy OFFER SLOT QTY":"/swap SOURCE DESTINATION"; return true;
        }
        auto *q=message.mutable_bag_request();
        if(bag.kind==n3e::BagCommand::shop){shop_open=true;bank_open=false;}
        if(bag.kind==n3e::BagCommand::equipment||gear||gear_source){if(!uif_dialogs)equipment_open=true;bank_open=false;}
        if(bag.kind==n3e::BagCommand::swap||commerce||repair||gear||use) {
          q->set_operation(use?9:gear?(bag.kind==n3e::BagCommand::equip?5:bag.kind==n3e::BagCommand::unequip?6:7):repair?(gear_source?8:4):commerce?(bag.kind==n3e::BagCommand::buy?2:3):1); q->set_request(std::to_string(world.world.session())+"-"+std::to_string(++bag_seq));
          q->set_expected_revision(world.bag.revision()); q->set_source(bag.source); if(!commerce&&!repair)q->set_destination(bag.destination);
          if(repair)q->set_item(records[bag.source].item());
          if(commerce){q->set_service(shop->id);q->set_item(bag.kind==n3e::BagCommand::buy?shop->items[bag.destination]:world.bag.slots(bag.source).item());q->set_quantity(bag.quantity);shop_open=true;}
          q->set_instance(records[bag.source].instance());
        } else if(bag.kind==n3e::BagCommand::retry) *q=bag_retry;
        if(q->operation()){
          if(!item_wait.begin(message,world,SDL_GetTicks()/1000.)){text_entry="Wait for the current item operation";return true;}
          bag_retry=*q;
        }
        if(use&&hud&&hud->data.hotbar){
          hotbar.begin(records[bag.source].item(),q->request(),release,SDL_GetTicks()/1000.);
          if(local_casts.empty()){n3e::PresentationEvent e;e.set_kind(3);e.set_key(records[bag.source].item());e.set_tick(world.world.tick());e.set_actor(world.world.self());e.set_target(world.world.self());e.set_target_x(world.predicted[0]);e.set_target_y(world.predicted[1]);e.set_target_z(world.predicted[2]);local_casts.push_back(e);}
        }
        network->send(message); if(!uif_dialogs)party_open=friends_open=false;if(!use&&q->operation()!=9)bag_open=true; entry=4; text_entry.clear(); return true;
      }
      return false;
    };
    auto skill_use=[&](const n3e::Skill&skill,bool hint=true){
      if(!network||!world.connected)return;
      // PQ-481 (D-245): the recipient as 1298's skill start 005819e0 picks
      // it (n3e::skill_recipient). An NPC skill with no target, or (hinted)
      // on a target the client does not see, sees dead (PQ-479) or sees is
      // not an NPC, is held back with no packet and no line; a player or
      // self skill goes to a player target whatever its health, else to the
      // caster. The client has no level test: 1298 has none before it sends
      // (005819e0, 0057f7f0), and its skill tree keeps a skill above the
      // player's level off the hotbar instead (Hotbar::bind_skill). The
      // server refuses `level_required` itself, and the policy's refusal
      // line for it posts (D-243).
      const auto chosen=n3e::skill_recipient(skill.target,hint,world.world.entities(),world.world.self(),target);
      if(chosen.hold!=n3e::SkillHold::none){
#if N3E_HARNESS
        std::cout<<"SKILL_HELD skill="<<skill.id<<" target="<<target<<" reason="<<n3e::skill_hold_name(chosen.hold)<<std::endl;
#endif
        return;
      }
      const uint64_t recipient=chosen.id;
      // PQ-466 (D-234): beyond the start limit (D-232) the client sends
      // nothing and posts the package's notice, as 1298's 00583780 posts
      // text 0xfa9; a hint only, the server checks the limit itself.
      if(hint&&recipient!=world.world.self())
        for(const auto&e:world.world.entities())if(e.id()==recipient){
          const float limit=n3e::skill_start_limit(skill,release.skills->reach,release.melee?release.melee->actor_radius+release.melee->target_radius:0.f);
          const n3e::V at{e.x(),e.y(),e.z()};
          if(!n3e::skill_too_far(world.predicted,at,limit))break;
          const auto text=n3e::skill_notice(release.skills->notice,skill.label);
          if(hud&&!text.empty())hud->post_notice(text);
#if N3E_HARNESS
          std::cout<<"SKILL_TOO_FAR skill="<<skill.id<<" target="<<recipient<<" distance="
                   <<std::sqrt(std::pow(at[0]-world.predicted[0],2.f)+std::pow(at[1]-world.predicted[1],2.f)+std::pow(at[2]-world.predicted[2],2.f))
                   <<" limit="<<limit<<" notice='"<<text<<"'"<<std::endl;
#endif
          return;
        }
      n3e::Envelope message;auto*a=message.mutable_action();a->set_session(world.world.session());a->set_seq(++action_seq);a->set_target(recipient);a->set_action(skill.id);
      melee.stop();walking_to=false;held_ground.cancel();movement_intent={};network->send(message);
      // PQ-469 (D-235): remember which skill this sequence number carried, so
      // the server's out_of_range refusal of it posts the policy's failed line.
      // PQ-479 (D-243): and whether its target was an NPC, for the policy's
      // refusal lines.
      bool npc=false;for(const auto&e:world.world.entities())if(e.id()==recipient)npc=e.npc();
      for(size_t i=0;i<release.skills->entries.size();++i)if(release.skills->entries[i].id==skill.id){skill_failures.send(action_seq,i,npc);break;}
#if N3E_HARNESS
      std::cout<<"SKILL_SENT skill="<<skill.id<<" target="<<recipient<<" seq="<<action_seq<<(hint?"":" unchecked")<<std::endl;
#endif
    };
    auto hotbar_use=[&](unsigned slot){
      if(!hud||!hud->data.hotbar||item_wait||feature_ui.prompt||feature_ui.drag)return;
      if(slot<8)if(auto skill=Hotbar::skill(release,hotbar.assignments[hotbar.page*8+slot])){skill_use(*skill);return;}
      if(auto command=hotbar.command(slot,release,world)){text_entry=*command;item_command();}
    };
    auto item_panel=[&]()->uint32_t{return bank_open?4:shop_open?3:bag_open?1:0;};
    uint64_t rest_seq=0;
    auto toggle_rest=[&](){
      if(!release.rest||!world.connected)return;
      for(const auto&e:world.world.entities())if(e.id()==world.world.self()&&e.health()){
        n3e::Envelope message;auto*q=message.mutable_rest();q->set_session(world.world.session());
        q->set_entity(e.id());q->set_seq(++rest_seq);q->set_sitting(!e.sitting());
        melee.stop();network->send(message);return;
      }
    };
    auto open_loot=[&](float x,float y,int width,int height){
      if(!uif_pickup||loot_mesh.empty())return false;
      for(const auto&e:world.world.entities())if(e.id()==world.world.self()&&!e.health())return false;
      auto id=pick_loot(world,loot_mesh,scene,orbit,x,y,width,height);
      if(!id||!loot_ui.open(world,release.loot_open_radius.value_or(release.claim_radius),x,y-150*hud->scale(width,height),id,release.loot_open_radius.has_value()))return false;
      walking_to=false;held_ground.cancel();melee.stop();return true;
    };
    auto cancel_item_drag=[&](){feature_ui.drag.reset();hotbar.drag.reset();if(hud)hud->drag_key.clear();};
    // Dialog windows in the order they were opened (PQ-010): the cancel action
    // closes the front-most one, as each KO window closes itself on Esc. The
    // party list, minimap and loot window are not dialogs here (KO's party and
    // state-bar windows forward Esc, and its loot window ignores it).
    n3e::windows::Stack window_stack;
    auto open_windows=[&]()->n3e::windows::Open{
      return {bag_open,equipment_open||friends_open,skills_ui.open,features_open,shop_open,bank_open};
    };
    // Closes one window the way its close button does (close:N below).
    auto close_window=[&](n3e::windows::Window window){
      using W=n3e::windows::Window;
      switch(window){
      case W::inventory:bag_open=false;break;
      case W::character:
        // The native layout shows equipment inside the bag panel (toggle_character).
        if(!uif_dialogs&&equipment_open)bag_open=false;
        equipment_open=friends_open=false;break;
      case W::skills:skills_ui.open=false;break;
      case W::help:features_open=false;break;
      case W::shop:shop_open=bag_open=false;break;
      case W::warehouse:bank_open=bag_open=false;break;
      }
      feature_ui.clear();
    };
    // Package-owned input map (PQ-009, D-136): the release names the keys, the
    // engine owns what each action does. run_action returns whether it took the
    // press; when it declines, the key's next bound action is tried.
    const n3e::input::Map input_map=n3e::input::Map::from(release);
    n3e::targeting::AutoMove auto_move;
    NameDisplay name_display{release.names};
    NameLifetime name_lifetime{release.names.lifetime,{}};NpcNameLifetime npc_name_lifetime{release.names.npc_lifetime};uint64_t name_party_group=0;
#if N3E_HARNESS
    // Replays press the key the package binds to an action, as a player would,
    // so they exercise the package's map rather than a fixed key.
    auto press_action=[&](n3e::input::Action action){
      auto key=input_map.key(action);
      if(!key)throw std::runtime_error("replay action has no key: "+std::string(n3e::input::action_names[size_t(action)]));
      SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.scancode=*key;e.key.key=SDL_GetKeyFromScancode(*key,SDL_KMOD_NONE,false);e.key.down=true;
      SDL_PushEvent(&e);
      e.type=SDL_EVENT_KEY_UP;e.key.down=false;SDL_PushEvent(&e);
    };
#endif
    const std::string loot_key_hint=input_map.label(n3e::input::Action::loot_nearest).empty()?"LOOT BUNDLE":"LOOT BUNDLE ["+input_map.label(n3e::input::Action::loot_nearest)+"]";
    // The help panel's key lines, from the package map.
    const std::array<std::string,2> help_keys=[&]{
      using A=n3e::input::Action;
      auto line=[&](std::initializer_list<std::pair<A,const char*>> items){
        std::string out;
        for(auto [action,what]:items)if(auto key=input_map.labels(action);!key.empty())out+=(out.empty()?"":" | ")+key+" "+what;
        return out;
      };
      return std::array<std::string,2>{line({{A::target_enemy,"nearest enemy"},{A::target_cycle,"next target"},{A::attack_toggle,"attack"},{A::attack_pick,"attack"},{A::attack_target,"attack target"},{A::loot_nearest,"collect loot"}}),
                                       line({{A::rest_toggle,"sit/stand"},{A::respawn,"respawn"},{A::run_toggle,"walk/run"},{A::auto_move,"auto-run"},{A::turbo,"turbo"}})};
    }();
    const std::string cancel_hint=[&]{
      auto key=input_map.label(n3e::input::Action::cancel);
      return key.empty()?std::string("Your progress saves on logout"):key+" closes the top window; progress saves on logout";
    }();
    const std::string legacy_key_hint=[&]{
      using A=n3e::input::Action;std::string hint;
      for(auto [action,what]:{std::pair{A::target_enemy," NEAREST  "},std::pair{A::target_cycle," CYCLE  "},std::pair{A::chat," CHAT"}})
        if(auto key=input_map.label(action);!key.empty())hint+=upper(key)+what;
      return hint;
    }();
    auto self_entity=[&]()->const n3e::Entity*{
      for(const auto&e:world.world.entities())if(e.id()==world.world.self())return &e;
      return nullptr;
    };
    // PQ-416 (D-216): the player's ranged basic attack, when the combat style
    // the server derives from its equipment is one, and the melee policy with
    // that profile's reach (KO's 00468620 adds the bow's range to the reach).
    auto ranged_attack=[&](const n3e::Entity*self)->const n3e::RangedAttack*{
      if(!release.combat_animation||!self||!self->combat_style()||self->combat_style()>release.combat_animation->profiles.size())return nullptr;
      const auto&r=release.combat_animation->profiles[self->combat_style()-1].ranged;
      return r.range>0?&r:nullptr;
    };
    auto melee_config=[&](const n3e::Entity*self){
      auto cfg=*release.melee;
      if(const auto*r=ranged_attack(self))cfg.reach=r->reach;
      return cfg;
    };
    // Turning toward the selection is existing n3e behaviour; KO's selection
    // call 005d9ce0 does not turn (fidelity gap, PQ-134).
    auto select_target=[&](uint64_t id){
      target=id;melee.select(target);
      if(target&&release.melee)
        for(const auto&c:world.world.entities())
          if(c.id()==target)n3e::face_target(world.predicted,{c.x(),c.y(),c.z()},heading);
    };
    // Ctrl+click (005e16f0) and double click (005e1490), camera mode 3, n3e's
    // only camera: attack when the predicate 00468750 holds, otherwise walk to
    // the actor (00465950), which on arrival attacks only an attackable target
    // (0046b0d0 -> 005d6850). Intent only: the server validates every attack
    // request (reach, hostility, life) as it does for the attack toggle.
    auto attack_actor=[&](uint64_t id,bool double_click)->bool{
      const auto *self=self_entity();
      const n3e::Entity *victim=nullptr;
      for(const auto&e:world.world.entities())if(id&&e.id()==id&&id!=world.world.self())victim=&e;
      if(!victim||!self||!self->health())return false;  // 005e16f0 returns in own states 4/5
      bool attackable=n3e::targeting::attackable(*victim);
      n3e::V at{victim->x(),victim->y(),victim->z()};
      if(!release.melee){
        // No melee policy, so no reach to walk to: an attackable target gets
        // the attack toggle's request.
        if(!attackable)return false;
        n3e::Envelope message;auto *a=message.mutable_action();
        a->set_session(world.world.session());a->set_seq(++action_seq);a->set_target(id);a->set_action(world.world.action());
        network->send(message);return true;
      }
      float range=melee_config(self).range();
      bool predicate=n3e::targeting::can_attack(attackable,world.predicted,at,range);
      auto click=double_click?n3e::targeting::double_click(true,predicate,world.predicted,at,range)
                             :n3e::targeting::ctrl_click(true,predicate);
      if(click==n3e::targeting::Click::none)return true;
      // A walk is KO's chase (3-D arrival, 0046b0d0); an attack in reach starts at once.
      if(attackable)melee.start(id,click==n3e::targeting::Click::approach);else melee.approach(id);
      walking_to=false;held_ground.cancel();
      return true;
    };
    auto unimplemented=[&](const char*what){
      if(hud)hud->post_notice(std::string("Unavailable: ")+what+" is not implemented.");
      return true;
    };
    auto toggle_character=[&](){
      // U (005c6990 -> 0056e510/0056e560): the character window opens or closes.
      if(uif_dialogs){
        bool open=!(equipment_open||friends_open);
        equipment_open=open&&character_page==2;friends_open=open&&character_page==5;
        if(open){n3e::Envelope q;q.mutable_bag_request();network->send(q);}
        return true;
      }
      if(!release.inventory||!release.equipment)return false;
      if(equipment_open){equipment_open=bag_open=false;return true;}
      bag_open=equipment_open=true;shop_open=bank_open=party_open=friends_open=features_open=false;bag_page=0;
      n3e::Envelope q;q.mutable_bag_request();network->send(q);return true;
    };
    auto run_action=[&](n3e::input::Action action)->bool{
      using A=n3e::input::Action;
      const auto *self=self_entity();
      switch(action){
      case A::hotbar_use_1:case A::hotbar_use_2:case A::hotbar_use_3:case A::hotbar_use_4:
      case A::hotbar_use_5:case A::hotbar_use_6:case A::hotbar_use_7:case A::hotbar_use_8:
        // 1-8 (004dfae0): the current page's slot.
        if(!window_focused||entry!=4||!hud||!hud->data.hotbar)return false;
        hotbar_use(unsigned(action)-unsigned(A::hotbar_use_1));return true;
      case A::hotbar_page_1:case A::hotbar_page_2:case A::hotbar_page_3:case A::hotbar_page_4:
      case A::hotbar_page_5:case A::hotbar_page_6:case A::hotbar_page_7:case A::hotbar_page_8:
        if(!hud||!hud->data.hotbar)return false;
        hotbar.select_page(unsigned(action)-unsigned(A::hotbar_page_1));return true;
      case A::hotbar_page_prev:case A::hotbar_page_next:
        if(!hud||!hud->data.hotbar)return false;
        hotbar.change_page(action==A::hotbar_page_next);return true;
      case A::move_forward:case A::move_backward:case A::turn_left:case A::turn_right:case A::turbo:
      case A::camera_pitch_up:case A::camera_pitch_down:
        return false;  // held actions are read every frame, not on a press
      case A::auto_move:{
        uint32_t mods=n3e::input::modifiers(SDL_GetModState());
        auto keys=SDL_GetKeyboardState(nullptr);
        bool move_key=input_map.down(A::move_forward,keys,mods)||input_map.down(A::move_backward,keys,mods);
        bool left_button=SDL_GetMouseState(nullptr,nullptr)&SDL_BUTTON_LMASK;
        if(auto_move.toggle(self&&self->health(),move_key,left_button)&&auto_move.active){walking_to=false;held_ground.cancel();}
        return true;
      }
      case A::run_toggle:
        if(!release.movement)return false;
        running=!running;
        if(hud){hud->running=running;hud->cancel_pointer();}
        return true;
      case A::attack_toggle:{
        if(!target)return false;
        // R is ignored while the target is dead (005c6990 checks its state).
        for(const auto&c:world.world.entities())if(c.id()==target&&!c.health())return true;
        if(release.melee){melee.toggle(target);walking_to=false;held_ground.cancel();}
        else{
          n3e::Envelope message;auto *a=message.mutable_action();
          a->set_session(world.world.session());a->set_seq(++action_seq);a->set_target(target);a->set_action(world.world.action());
          network->send(message);
        }
        return true;
      }
      case A::target_enemy:
        if(auto id=n3e::targeting::enemy(world))select_target(id);
        return true;
      case A::target_party:select_target(n3e::targeting::party_member(world));return true;
      case A::target_npc:select_target(n3e::targeting::npc(world,pick_frame.corpses));return true;
      case A::target_cycle:{
        // Legacy layout only: the next living NPC after the current target.
        std::vector<uint64_t> choices;
        for(const auto&c:world.world.entities())if(c.npc()&&c.health())choices.push_back(c.id());
        auto current=std::find(choices.begin(),choices.end(),target);
        select_target(choices.empty()?0:current!=choices.end()&&++current!=choices.end()?*current:choices.front());
        return true;
      }
      case A::rest_toggle:{
        auto pose=poses.find(world.world.self());
        if(pose==poses.end()||(pose->second.state!=7&&pose->second.state!=9))toggle_rest();
        return true;
      }
      case A::respawn:{
        if(!release.requested_respawn||!self||self->life_state()!=n3e::DEAD_READY)return false;
        n3e::Envelope message;auto *request=message.mutable_respawn();
        request->set_session(world.world.session());request->set_seq(++respawn_seq);request->set_entity(self->id());
        network->send(message);return true;
      }
      case A::loot_nearest:{
        if(release.protocol<5)return false;
        if(uif_pickup){
          int pw,ph;SDL_GetWindowSizeInPixels(w,&pw,&ph);float scale=hud->scale(pw,ph);
          if(loot_ui.encounter)loot_ui.close();
          else if(!loot_ui.open(world,release.loot_open_radius.value_or(release.claim_radius),hud->pointer_active?hud->pointer_x:pw*.5f,(hud->pointer_active?hud->pointer_y:ph*.5f)-150*scale,0,release.loot_open_radius.has_value()))hud->post_notice("No loot bundle within reach");
          walking_to=false;melee.stop();return true;
        }
        const n3e::LootDrop *nearest=nullptr;float distance=std::numeric_limits<float>::max();
        for(const auto&drop:world.loot.drops()){
          float d=std::pow(drop.x()-world.predicted[0],2)+std::pow(drop.y()-world.predicted[1],2)+std::pow(drop.z()-world.predicted[2],2);
          if(d<distance){distance=d;nearest=&drop;}
        }
        if(nearest){
          n3e::Envelope message;auto *a=message.mutable_claim();
          a->set_session(world.world.session());a->set_seq(++claim_seq);
          a->set_entity(world.world.self());a->set_operation(nearest->operation());
          a->set_encounter(nearest->encounter());a->set_item(nearest->item());a->set_quantity(nearest->quantity()?nearest->quantity():1);
          network->send(message);
        }
        return true;
      }
      case A::skills:
        if(!release.skills)return false;
        skills_ui.open=!skills_ui.open;if(skills_ui.open){bag_open=shop_open=bank_open=false;cancel_item_drag();}
        return true;
      case A::minimap:
        // 005c7264 -> 00564f70: M toggles the overview map.
        if(!hud||!hud->data.minimap)return false;
        hud->minimap_open=!hud->minimap_open;return true;
      case A::inventory:
        if(!release.inventory)return false;
        skills_ui.open=false;bag_open=!bag_open;features_open=false;
        if(uif_dialogs&&(bank_open||shop_open))bag_open=true;
        if(bag_open){if(!uif_dialogs){bank_open=shop_open=equipment_open=false;party_open=friends_open=false;}n3e::Envelope q;q.mutable_bag_request();network->send(q);}
        return true;
      case A::character:return toggle_character();
      case A::help:
        // F10 (005c6990: the help window's show/hide); n3e's help panel.
        if(!release.inventory&&!uif_dialogs)return false;
        features_open=!features_open;bag_open=bank_open=shop_open=equipment_open=party_open=friends_open=false;
        return true;
      case A::chat:entry=5;walking_to=false;return true;
      case A::window_page_prev:case A::window_page_next:{
        bool next=action==A::window_page_next;
        if(uif_dialogs&&(friends_open||bag_open)){
          feature_ui.act(friends_open?(next?"friend_next":"friend_prev"):bank_open?(next?"bank_next":"bank_prev"):(next?"bag_next":"bag_prev"),release,world,nearest_shop(),bank_open,shop_open);
          return true;
        }
        if(friends_open&&release.friends){unsigned pages=(release.friends->capacity+7)/8;friend_page=(friend_page+pages+(next?1:-1))%pages;return true;}
        if(bag_open){
          unsigned size=release.inventory->capacity;if(bank_open&&release.storage)size=std::max(size,release.storage->capacity);if(shop_open&&nearest_shop())size=std::max(size,unsigned(nearest_shop()->items.size()));
          unsigned pages=(size+7)/8;bag_page=(bag_page+pages+(next?1:-1))%pages;return true;
        }
        return false;
      }
      case A::command_list:return unimplemented("The command list");
      case A::names_toggle:name_display.toggle();return true;
      case A::camera_mode:return unimplemented("Camera mode selection");
      case A::hide_hud:return unimplemented("Hiding the interface");
      case A::chat_size:return unimplemented("Resizing the chat window");
      case A::message_size:return unimplemented("Resizing the message window");
      case A::screenshot:return unimplemented("Screenshot capture");
      case A::attack_pick:{
        // The left press's pick; bound to a key, the actor under the pointer,
        // selected as a click would select it.
        uint64_t id=click_actor.value_or(0);
        if(!click_actor){
          int pw,ph,lw,lh;SDL_GetWindowSizeInPixels(w,&pw,&ph);SDL_GetWindowSize(w,&lw,&lh);
          if(entry!=4||lw<=0||lh<=0)return false;
          id=n3e::targeting::pick(world,pick_frame,orbit.eye,orbit.ray(cursor_x*pw/lw,cursor_y*ph/lh,pw,ph),release.pick.mesh_lod);
          if(id){target=id;melee.select(target);}
        }
        return id&&attack_actor(id,false);
      }
      case A::attack_target:return target&&attack_actor(target,true);
      case A::cancel:{
        // Esc (005c6990 at 005c72b8; windows through 00648a40): the front-most
        // dialog closes itself, one per press. KO's same press also ends a
        // pending skill target pick and shows a hidden HUD; n3e has neither
        // state yet (PQ-140, PQ-138). Combat, movement and the target are left
        // alone: the KO handler touches none of them.
        window_stack.sync(open_windows());
        if(auto top=window_stack.top()){close_window(*top);window_stack.sync(open_windows());}
        return true;
      }
      }
      return false;
    };
    float drag_x=0,drag_y=0,drag_width=0,drag_height=0;bool drag_moved=false;
    // N3E_PROFILE: average CPU wall time per frame section, printed every 120 frames.
    const bool profile_frames=std::getenv("N3E_PROFILE")!=nullptr;
    std::array<double,8> profile_sum{};uint64_t profile_last=0;unsigned profile_count=0;
    auto profile_mark=[&](int section){
      if(!profile_frames)return;
      uint64_t now=SDL_GetTicksNS();if(section>=0)profile_sum[section]+=(now-profile_last)/1e6;profile_last=now;
    };
    while (run) {
      profile_mark(-1);
      SDL_Event e;
      while (SDL_PollEvent(&e)) {
        window_stack.sync(open_windows());
#if N3E_HARNESS
        // Replays push key events by keycode; the input map reads physical
        // keys, so give a synthetic event the scancode SDL gives a real one.
        if ((e.type == SDL_EVENT_KEY_DOWN || e.type == SDL_EVENT_KEY_UP) &&
            e.key.scancode == SDL_SCANCODE_UNKNOWN && e.key.key)
          e.key.scancode = SDL_GetScancodeFromKey(e.key.key, nullptr);
        // The panel replay owns the pointer: the desktop's real mouse must not
        // move a panel between its scripted events. So does the play replay
        // (PQ-238): in a desktop window the real cursor re-aimed its held
        // ground travel and moved its HUD pointer (its wheel too). So does the
        // item tooltip replay (PQ-355): its hover is one pushed motion, which a
        // desktop cursor's motion after it moves off the slot.
        if((panel_test||play_smoke||item_tooltip_test)&&((e.type==SDL_EVENT_MOUSE_MOTION&&e.motion.which!=replay_mouse)||
           ((e.type==SDL_EVENT_MOUSE_BUTTON_DOWN||e.type==SDL_EVENT_MOUSE_BUTTON_UP)&&e.button.which!=replay_mouse)||
           (play_smoke&&e.type==SDL_EVENT_MOUSE_WHEEL&&e.wheel.which!=replay_mouse)))continue;
        // Deterministic replay owns focus events (windowID=0); desktop activity
        // must not cancel a scripted start between stages. Normal play uses all
        // native focus events, and the replay explicitly exercises
        // cancellation. The play replay (PQ-238) runs in a desktop window under
        // make live-ko, where the compositor's focus loss and pointer leave
        // stopped its click travel and dropped its camera input; it owns them
        // too, and injects native-looking ones itself to prove it. The item
        // tooltip replay (PQ-355) owns them as well: a focus loss while its
        // hover is queued drops the hover (no game mouse), and a pointer leave
        // hides the tooltip.
        if ((melee_smoke || play_smoke || item_tooltip_test) &&
            (e.type == SDL_EVENT_WINDOW_FOCUS_LOST ||
             e.type == SDL_EVENT_WINDOW_FOCUS_GAINED ||
             ((play_smoke || item_tooltip_test) && e.type == SDL_EVENT_WINDOW_MOUSE_LEAVE)) &&
            e.window.windowID != 0)
          continue;
#endif
#if TOOLS
        bool terminal_toggle_text = e.type == SDL_EVENT_TEXT_INPUT &&
            (std::strcmp(e.text.text, "`") == 0 || std::strcmp(e.text.text, "~") == 0);
        if (!terminal_toggle_text) ImGui_ImplSDL3_ProcessEvent(&e);
        if (e.type == SDL_EVENT_KEY_DOWN && !e.key.repeat) {
          // Engine-reserved tools keys (D-136), outside every package's map.
          if (e.key.scancode == n3e::input::terminal_key) {
            editor.toggle_terminal();
            continue;
          }
          if (e.key.scancode == n3e::input::editor_key) {
            editor.open = !editor.open;
            continue;
          }
        }
        // The toggle's text event must not insert a stray backtick/tilde.
        if (terminal_toggle_text)
          continue;
        // ImGui receives the event, but gameplay chat/login/key handlers must
        // not consume the same keystroke while the editor owns input.
        if (network && editor.capture() &&
            (e.type == SDL_EVENT_KEY_DOWN || e.type == SDL_EVENT_TEXT_INPUT))
          continue;
#endif
        if ((feature_ui.drag||hotbar.drag) && (e.type==SDL_EVENT_KEY_DOWN||e.type==SDL_EVENT_WINDOW_FOCUS_LOST||
            e.type==SDL_EVENT_WINDOW_MOUSE_LEAVE||e.type==SDL_EVENT_WINDOW_RESIZED||
            (e.type==SDL_EVENT_MOUSE_BUTTON_DOWN&&e.button.button!=SDL_BUTTON_LEFT))){cancel_item_drag();if(e.type==SDL_EVENT_MOUSE_BUTTON_DOWN)continue;}
        if (network) {
          if (hud) hud->running = running;
          if (e.type == SDL_EVENT_WINDOW_FOCUS_LOST) {
            inventory_right_press.reset();
            if (hud) hud->cancel_pointer();
            melee.stop();
            walking_to = false;
            auto_move.active = false;  // n3e policy; KO not observed (gap, PQ-134)
            held_ground.cancel();
            window_focused = false;
            turbo_armed = false;
            orbit_drag = false;
            set_relative_mouse(false);
          }
          if (e.type == SDL_EVENT_WINDOW_FOCUS_GAINED)
            window_focused = true;
          if (e.type == SDL_EVENT_WINDOW_MOUSE_LEAVE && held_ground.active) {
            held_ground.cancel();
            walking_to = false;
          }
          if (e.type == SDL_EVENT_MOUSE_MOTION) {
            cursor_x = e.motion.x;
            cursor_y = e.motion.y;
          }
          if (e.type == SDL_EVENT_MOUSE_BUTTON_UP &&
              e.button.button == SDL_BUTTON_LEFT)
            held_ground.cancel();
          auto world_pointer = [&](float x, float y) {
            int pw, ph, lw, lh;
            SDL_GetWindowSizeInPixels(w, &pw, &ph);
            SDL_GetWindowSize(w, &lw, &lh);
            if (lw <= 0 || lh <= 0)
              return false;
            float mx = x * pw / lw, my = y * ph / lh;
            bool allowed = window_focused && entry == 4 && world.connected &&
                           mx >= 0 && mx < pw && my >= 0 && my < ph &&
                           (hud ? hud->hit(mx, my, pw, ph).empty()
                                : my > 120 && my < ph - 195 &&
                                      !(mx > pw - 180 && my < 180));
#if TOOLS
            allowed = allowed && !ImGui::GetIO().WantCaptureMouse;
#endif
            return allowed;
          };
          // Double click (PQ-011): 00640140 flags the second left release;
          // 005e1490 skips it when the UI took the mouse. Every left release
          // feeds the detector; the package's MouseLeftDouble actions run only
          // for one over the world.
          if (e.type == SDL_EVENT_MOUSE_BUTTON_UP && e.button.button == SDL_BUTTON_LEFT &&
              left_double.release(SDL_GetTicks(), e.button.x, e.button.y) && !orbit_drag &&
              !feature_ui.drag && !hotbar.drag && world_pointer(e.button.x, e.button.y))
            for (auto a : input_map.clicked(n3e::input::left_double, n3e::input::modifiers(SDL_GetModState())))
              if (run_action(a)) break;
          if (entry == 4 && e.type == SDL_EVENT_MOUSE_BUTTON_DOWN &&
              e.button.button == SDL_BUTTON_RIGHT) {
            held_ground.cancel();
            orbit_drag = world_pointer(e.button.x, e.button.y);
            if(orbit_drag){int pw,ph,lw,lh;SDL_GetWindowSizeInPixels(w,&pw,&ph);SDL_GetWindowSize(w,&lw,&lh);
              if(open_loot(e.button.x*pw/lw,e.button.y*ph/lh,pw,ph)){orbit_drag=false;continue;}
            }
            set_relative_mouse(orbit_drag);
          }
          if (e.type == SDL_EVENT_MOUSE_BUTTON_UP &&
              e.button.button == SDL_BUTTON_RIGHT) {
            orbit_drag = false;
            set_relative_mouse(false);
          }
          if (orbit_drag && (entry != 4 || !window_focused ||
                             !relative_mouse()
#if TOOLS
                             || editor.capture() || ImGui::GetIO().WantCaptureMouse
#endif
                             )) {
            orbit_drag = false;
            set_relative_mouse(false);
          }
          if (entry == 4 && window_focused && orbit_drag &&
              e.type == SDL_EVENT_MOUSE_MOTION &&
              (e.motion.state & SDL_BUTTON_RMASK))
            orbit.drag(e.motion.xrel, e.motion.yrel);
          if (e.type == SDL_EVENT_MOUSE_WHEEL &&
              world_pointer(e.wheel.mouse_x, e.wheel.mouse_y))
            orbit.zoom(e.wheel.y *
                       (e.wheel.direction == SDL_MOUSEWHEEL_FLIPPED ? -1 : 1));
          bool game_mouse = window_focused;
#if TOOLS
          game_mouse = game_mouse && !editor.capture() && !ImGui::GetIO().WantCaptureMouse;
#endif
          if (hud) {
            if (!game_mouse || orbit_drag || (entry != 4 && !(uif_dialogs&&entry==5&&(bank_secret||feature_ui.prompt))) ||
                e.type == SDL_EVENT_WINDOW_MOUSE_LEAVE) hud->cancel_pointer();
            else if (e.type == SDL_EVENT_MOUSE_MOTION || e.type == SDL_EVENT_MOUSE_BUTTON_DOWN ||
                     e.type == SDL_EVENT_MOUSE_BUTTON_UP) {
              int pw, ph, lw, lh;
              SDL_GetWindowSizeInPixels(w, &pw, &ph);
              SDL_GetWindowSize(w, &lw, &lh);
              float x = e.type == SDL_EVENT_MOUSE_MOTION ? e.motion.x : e.button.x;
              float y = e.type == SDL_EVENT_MOUSE_MOTION ? e.motion.y : e.button.y;
              auto old_hover=hud->hovered;
              hud->pointer(x * pw / std::max(1, lw), y * ph / std::max(1, lh), pw, ph,
                           e.type == SDL_EVENT_MOUSE_BUTTON_DOWN && e.button.button == SDL_BUTTON_LEFT);
              if(hud->hovered&&hud->hovered!=old_hover)sound("hover:"+std::to_string(hud->hovered));
              if(hud->pressed&&e.type==SDL_EVENT_MOUSE_BUTTON_DOWN&&e.button.button==SDL_BUTTON_LEFT)sound("click:"+std::to_string(hud->pressed));
              // Children take a click first; otherwise a press on a draggable
              // panel's handle moves its group until release (004020b0).
              float hx=x*pw/std::max(1,lw),hy=y*ph/std::max(1,lh);
              // PQ-408 (D-211): the message line's scroll bar takes its press,
              // motion and release first, as 1298's children do (0052a7e0).
              const bool scroll_press=e.type==SDL_EVENT_MOUSE_BUTTON_DOWN&&e.button.button==SDL_BUTTON_LEFT&&hud->message_press(hx,hy,pw,ph);
              if(e.type==SDL_EVENT_MOUSE_MOTION)hud->message_motion(hx,hy,pw,ph);
              if(e.type==SDL_EVENT_MOUSE_BUTTON_UP&&e.button.button==SDL_BUTTON_LEFT)hud->message_release(hx,hy,pw,ph);
              if(e.type==SDL_EVENT_MOUSE_BUTTON_DOWN&&e.button.button==SDL_BUTTON_LEFT&&!hud->pressed&&!scroll_press)hud->begin_panel_drag(hx,hy,pw,ph);
              if(e.type==SDL_EVENT_MOUSE_MOTION)hud->drag_panels(hx,hy,pw,ph);
              if (e.type == SDL_EVENT_MOUSE_BUTTON_UP && e.button.button == SDL_BUTTON_LEFT)
                hud->pressed = 0,hud->panel_drag.reset();
            }
          }
          if(skills_ui.drag&&(!game_mouse||entry!=4||!world.connected||!skills_ui.open||skills_ui.drag->self!=world.world.self()||skills_ui.drag->session!=world.world.session())){skills_ui.drag.reset();hud->drag_key.clear();}
          if(skills_ui.drag&&(e.type==SDL_EVENT_MOUSE_MOTION||(e.type==SDL_EVENT_MOUSE_BUTTON_UP&&e.button.button==SDL_BUTTON_LEFT))){
            int pw,ph,lw,lh;SDL_GetWindowSizeInPixels(w,&pw,&ph);SDL_GetWindowSize(w,&lw,&lh);
            float x=(e.type==SDL_EVENT_MOUSE_MOTION?e.motion.x:e.button.x)*pw/std::max(1,lw),y=(e.type==SDL_EVENT_MOUSE_MOTION?e.motion.y:e.button.y)*ph/std::max(1,lh);
            hud->drag_key="skill:"+std::to_string(skills_ui.drag->index);hud->drag_panel=10;hud->drag_rect={x-22,y-22,x+22,y+22};
            if(e.type==SDL_EVENT_MOUSE_BUTTON_UP){hotbar.bind_skill(hud->hit(x,y,pw,ph),release.skills->entries[skills_ui.drag->index],release,world.world.inventory().level());skills_ui.drag.reset();hud->drag_key.clear();}
            continue;
          }
          if(!skills_ui.open||!game_mouse||entry!=4||e.type==SDL_EVENT_WINDOW_MOUSE_LEAVE)skills_ui.right_press.reset();
          if(skills_ui.open&&game_mouse&&entry==4&&(e.type==SDL_EVENT_MOUSE_BUTTON_DOWN||e.type==SDL_EVENT_MOUSE_BUTTON_UP)&&e.button.button==SDL_BUTTON_RIGHT){
            int pw,ph,lw,lh;SDL_GetWindowSizeInPixels(w,&pw,&ph);SDL_GetWindowSize(w,&lw,&lh);
            int index=SkillsUI::index(hud->hit(e.button.x*pw/std::max(1,lw),e.button.y*ph/std::max(1,lh),pw,ph));
            auto pressed=skills_ui.right_press;skills_ui.right_press.reset();
            if(e.type==SDL_EVENT_MOUSE_BUTTON_DOWN){if(index>=0)skills_ui.right_press=SkillsUI::Drag{unsigned(index),world.world.self(),world.world.session()};}
            else if(pressed&&pressed->self==world.world.self()&&pressed->session==world.world.session()&&int(pressed->index)==index&&index>=0&&unsigned(index)<release.skills->entries.size()){hotbar.register_skill(release.skills->entries[index],release,world.world.inventory().level());continue;}
          }
          if(!game_mouse||entry!=4||orbit_drag||item_panel()!=1||
             e.type==SDL_EVENT_WINDOW_MOUSE_LEAVE)inventory_right_press.reset();
          if(uif_dialogs&&entry==4&&game_mouse&&!orbit_drag&&item_panel()==1&&
             (e.type==SDL_EVENT_MOUSE_BUTTON_DOWN||e.type==SDL_EVENT_MOUSE_BUTTON_UP)&&e.button.button==SDL_BUTTON_RIGHT){
            int pw,ph,lw,lh;SDL_GetWindowSizeInPixels(w,&pw,&ph);SDL_GetWindowSize(w,&lw,&lh);
            auto key=hud->hit(e.button.x*pw/std::max(1,lw),e.button.y*ph/std::max(1,lh),pw,ph);
            if(e.type==SDL_EVENT_MOUSE_BUTTON_DOWN){
              inventory_right_press.reset();
              if(feature_ui.slot(key)&&!item_wait&&!feature_ui.drag&&!feature_ui.prompt)
                inventory_right_press=InventoryRightPress{key,world.world.self(),world.world.session(),world.bag.revision(),feature_ui.bag_page,hotbar.page};
            }else{
              auto pressed=inventory_right_press;inventory_right_press.reset();
              if(pressed&&pressed->key==key&&pressed->self==world.world.self()&&pressed->session==world.world.session()&&
                 pressed->revision==world.bag.revision()&&pressed->bag_page==feature_ui.bag_page&&pressed->hotbar_page==hotbar.page&&!item_wait){
                bool registered=hud->data.hotbar&&hotbar.register_inventory(key,feature_ui,release,world);
                if(!registered)if(auto command=feature_ui.right_click(key,release,world)){text_entry=*command;item_command();}
              }
            }
            if(feature_ui.slot(key))continue;
          }
          if(uif_dialogs&&loot_ui.encounter){
            if(!game_mouse||entry!=4||orbit_drag)loot_ui.pressed=0;
            else if(e.type==SDL_EVENT_MOUSE_BUTTON_UP&&e.button.button==SDL_BUTTON_LEFT){
              int pw,ph,lw,lh;SDL_GetWindowSizeInPixels(w,&pw,&ph);SDL_GetWindowSize(w,&lw,&lh);
              auto key=hud->hit(e.button.x*pw/std::max(1,lw),e.button.y*ph/std::max(1,lh),pw,ph);
              loot_ui.sync(world,release.loot_open_radius.value_or(release.claim_radius),release.loot_open_radius.has_value());
              if(auto drop=loot_ui.up(key)){n3e::Envelope message;auto*a=message.mutable_claim();
                audio_claim=drop->operation();audio_claim_key=drop->kind()==1?"loot:coins":"loot:"+drop->item();
                a->set_session(world.world.session());a->set_seq(++claim_seq);a->set_entity(world.world.self());
                a->set_operation(drop->operation());a->set_encounter(drop->encounter());a->set_item(drop->item());a->set_quantity(drop->quantity()?drop->quantity():1);network->send(message);loot_retry_at=SDL_GetTicks()+3000;}
            }
          }
          if(hotbar.drag){
            if(!game_mouse||entry!=4||orbit_drag||!hotbar.drag_valid(world)){cancel_item_drag();}
            else if(e.type==SDL_EVENT_MOUSE_MOTION||(e.type==SDL_EVENT_MOUSE_BUTTON_UP&&e.button.button==SDL_BUTTON_LEFT)){
              int pw,ph,lw,lh;SDL_GetWindowSizeInPixels(w,&pw,&ph);SDL_GetWindowSize(w,&lw,&lh);
              float x=(e.type==SDL_EVENT_MOUSE_MOTION?e.motion.x:e.button.x)*pw/std::max(1,lw);
              float y=(e.type==SDL_EVENT_MOUSE_MOTION?e.motion.y:e.button.y)*ph/std::max(1,lh);
              drag_moved|=std::abs(x-drag_x)>2||std::abs(y-drag_y)>2;
              if(drag_moved){hud->drag_key="hotbar:"+std::to_string(hotbar.drag->slot);hud->drag_panel=hud->panel_of(hud->drag_key);hud->drag_rect={x-drag_width/2,y-drag_height/2,x+drag_width/2,y+drag_height/2};}
              if(e.type==SDL_EVENT_MOUSE_BUTTON_UP){
                auto source=hotbar.drag->slot;int destination=Hotbar::index(hud->hit(x,y,pw,ph));
                cancel_item_drag();
                if(destination==int(source))hotbar_use(source);else hotbar.move(source,destination);
              }
              continue;
            }
          }
          if(feature_ui.drag&&(!game_mouse||entry!=4||orbit_drag||feature_ui.drag->panel!=item_panel()||!feature_ui.drag_valid(world,nearest_shop())))cancel_item_drag();
          if(feature_ui.drag&&(e.type==SDL_EVENT_MOUSE_MOTION||
              (e.type==SDL_EVENT_MOUSE_BUTTON_UP&&e.button.button==SDL_BUTTON_LEFT))){
            int pw,ph,lw,lh;SDL_GetWindowSizeInPixels(w,&pw,&ph);SDL_GetWindowSize(w,&lw,&lh);
            float x=(e.type==SDL_EVENT_MOUSE_MOTION?e.motion.x:e.button.x)*pw/std::max(1,lw);
            float y=(e.type==SDL_EVENT_MOUSE_MOTION?e.motion.y:e.button.y)*ph/std::max(1,lh);
            drag_moved|=std::abs(x-drag_x)>2||std::abs(y-drag_y)>2;
            hud->drag_rect={x-drag_width/2,y-drag_height/2,x+drag_width/2,y+drag_height/2};
            if(e.type==SDL_EVENT_MOUSE_BUTTON_UP){
              auto destination=hud->hit(x,y,pw,ph);auto source=feature_ui.drag->key;
              if(!drag_moved&&destination==source){
                cancel_item_drag();feature_ui.act(source,release,world,nearest_shop(),bank_open,shop_open);
              }else{
                std::optional<std::string> command;
                if(hud->data.hotbar&&Hotbar::index(destination)>=0){
                  if(feature_ui.drag_valid(world,nearest_shop())&&feature_ui.drag->source.kind=="bag")
                    hotbar.bind(destination,feature_ui.drag->item,release);
                  cancel_item_drag();
                }else command=feature_ui.drop(destination,item_panel(),release,world,nearest_shop());
                hud->drag_key.clear();
                if(command){text_entry=*command;item_command();}
              }
              if(feature_ui.prompt){text_entry=feature_ui.prompt->value;entry=5;walking_to=false;}
            }
            continue;
          }
          if(uif_dialogs&&entry==5&&(bank_secret||feature_ui.prompt)&&game_mouse&&e.type==SDL_EVENT_MOUSE_BUTTON_DOWN&&e.button.button==SDL_BUTTON_LEFT){
            int pw,ph,lw,lh;SDL_GetWindowSizeInPixels(w,&pw,&ph);SDL_GetWindowSize(w,&lw,&lh);
            auto action=hud->hit(e.button.x*pw/std::max(1,lw),e.button.y*ph/std::max(1,lh),pw,ph);
            if(action=="confirm"||action=="cancel"){SDL_Event key{};key.type=SDL_EVENT_KEY_DOWN;key.key.key=action=="confirm"?SDLK_RETURN:SDLK_ESCAPE;SDL_PushEvent(&key);}
          }
          if (entry == 4 && game_mouse && !orbit_drag &&
              e.type == SDL_EVENT_MOUSE_BUTTON_DOWN &&
              e.button.button == SDL_BUTTON_LEFT) {
            held_ground.cancel();
            cursor_x = e.button.x;
            cursor_y = e.button.y;
            int pw, ph, lw, lh;
            SDL_GetWindowSizeInPixels(w, &pw, &ph);
            SDL_GetWindowSize(w, &lw, &lh);
            float mx = e.button.x * pw / lw, my = e.button.y * ph / lh;
            auto clicked = hud ? hud->hit(mx, my, pw, ph) : std::string{};
            if(!uif_dialogs&&release.inventory&&mx>=pw-178&&mx<pw-10&&my>=220&&my<220+28*feature_buttons().size())clicked=feature_buttons()[unsigned(my-220)/28].first;
            if(!uif_dialogs&&(bag_open||party_open||friends_open||features_open)&&mx>=10&&mx<std::min(pw-188,818)&&my>=215&&my<ph-65&&clicked.empty())clicked="panel";
            if(release.skills&&clicked=="skills"){
              skills_ui.open=!skills_ui.open;if(skills_ui.open){bag_open=shop_open=bank_open=false;cancel_item_drag();}continue;
            }
            if(skills_ui.open&&release.skills){
              int index=SkillsUI::index(clicked);
              if(index>=0&&unsigned(index)<release.skills->entries.size()){
                skills_ui.selected=index;
                if(e.button.clicks>=2)skill_use(release.skills->entries[index]);
                else skills_ui.drag=SkillsUI::Drag{unsigned(index),world.world.self(),world.world.session()};
                continue;
              }
            }
            if(uif_dialogs){
              if(hud->data.hotbar){
                if(auto slot=Hotbar::index(clicked);slot>=0){
                  if(hotbar.begin_drag(slot,world)){
                    drag_x=mx;drag_y=my;drag_moved=false;
                    for(const auto&q:hud->data.records)if(q.binding=="item"&&q.text==clicked){auto rect=hud->rectangle(q,pw,ph);drag_width=rect[2]-rect[0];drag_height=rect[3]-rect[1];break;}
                  }
                  continue;
                }
                if(clicked=="hotbar_prev"||clicked=="hotbar_next"){
                  hotbar.change_page(clicked=="hotbar_next");continue;
                }
              }
              loot_ui.down(clicked);
              if(clicked.starts_with("loot:")){walking_to=false;melee.stop();continue;}
              if(feature_ui.slot(clicked)&&item_wait)continue;
              if(feature_ui.begin_drag(clicked,item_panel(),world,nearest_shop())){
                sound("item:"+feature_ui.drag->item);
                for(const auto&q:hud->data.records)if(q.binding=="item"&&q.text==clicked&&q.panel==item_panel()&&hud->visible(q)){
                  auto rect=hud->rectangle(q,pw,ph);drag_width=rect[2]-rect[0];drag_height=rect[3]-rect[1];break;
                }
                drag_x=mx;drag_y=my;drag_moved=false;walking_to=false;melee.stop();
                hud->drag_key=clicked;hud->drag_panel=item_panel();
                hud->drag_rect={mx-drag_width/2,my-drag_height/2,mx+drag_width/2,my+drag_height/2};
                continue;
              }
              if(clicked.starts_with("close:")){
                if(clicked=="close:10")skills_ui.open=false;
                if(clicked=="close:2"||clicked=="close:5")equipment_open=friends_open=false;
                else if(clicked=="close:1")bag_open=false;
                else if(clicked=="close:3")shop_open=bag_open=false;
                else if(clicked=="close:4")bank_open=bag_open=false;
                else if(clicked=="close:6")party_open=false;
                else if(clicked=="close:7")features_open=false;
                feature_ui.clear();
              }
              else if(clicked=="tab:state"||clicked=="tab:friends"){
                character_page=clicked=="tab:state"?2:5;
                equipment_open=character_page==2;friends_open=character_page==5;
                if(friends_open){n3e::Envelope q;q.mutable_friend_request();network->send(q);}
                clicked="panel";
              }
              else if(clicked=="password"){bank_secret=2;bank_prompt="Current warehouse password";text_entry.clear();entry=5;walking_to=false;}
              else if(clicked=="friend_refresh"){friend_refresh=0;clicked="panel";}
              else if(clicked=="whisper"){entry=5;text_entry="/w "+feature_ui.friend_name+" ";walking_to=false;}
              else if(feature_ui.act(clicked,release,world,nearest_shop(),bank_open,shop_open)){
                if(feature_ui.prompt){text_entry=feature_ui.prompt->value;entry=5;walking_to=false;}
                clicked="panel";
              }
            }
            if (release.movement && (clicked == "walk" || clicked == "run")) {
              running = clicked == "run";
              hud->running = running;
              hud->cancel_pointer();
            }
            if (clicked == "rest")toggle_rest();
            if (clicked == "exit")
              run = false;
            if (clicked == "chat") {
              entry = 5;
              walking_to = false;
            }
            if (clicked == "unavailable")
              hud->post_notice("Unavailable: this feature is not implemented.");
            // Command-bar map button (00549210 -> 005d71d0 -> 00564f70).
            if(clicked=="toggle_minimap"&&hud->data.minimap){hud->minimap_open=!hud->minimap_open;clicked="panel";}
            if(uif_dialogs&&clicked=="equipment"){
              bool open=!(equipment_open||friends_open);
              equipment_open=open&&character_page==2;friends_open=open&&character_page==5;
              if(open){n3e::Envelope q;q.mutable_bag_request();network->send(q);}
              clicked="panel";
            }
            if(uif_dialogs&&clicked=="inventory"){
              skills_ui.open=false;
              if(!bank_open&&!shop_open){bag_open=!bag_open;if(bag_open){n3e::Envelope q;q.mutable_bag_request();network->send(q);}}
              clicked="panel";
            }
            if(clicked=="inventory"||clicked=="equipment"||clicked=="shop"){
              if(release.inventory){bool toggle=clicked=="inventory"&&bag_open&&!bank_open&&!shop_open&&!equipment_open;
                bag_open=!toggle;shop_open=clicked=="shop"&&bool(release.commerce);equipment_open=clicked=="equipment"&&bool(release.equipment);
                bank_open=party_open=friends_open=features_open=false;bag_page=0;
                if(uif_dialogs&&shop_open){feature_ui.clear();feature_ui.offer_page=feature_ui.bag_page=0;}
                if(bag_open){n3e::Envelope q;q.mutable_bag_request();network->send(q);}
              }else if(hud)hud->post_notice("Inventory shown below.");
            }
            if(clicked=="party"&&release.party){party_open=!party_open;bag_open=bank_open=shop_open=equipment_open=friends_open=features_open=false;
              n3e::Envelope q;q.mutable_party_request()->set_sequence(++party_seq);network->send(q);}
            if(clicked=="friends"&&release.friends){friends_open=true;equipment_open=false;character_page=5;if(!uif_dialogs)bag_open=bank_open=shop_open=party_open=features_open=false;
              n3e::Envelope q;q.mutable_friend_request();network->send(q);}
            if(clicked=="bank"&&release.storage){bag_open=bank_open=true;shop_open=equipment_open=party_open=friends_open=features_open=false;bag_page=0;
              n3e::Envelope q;q.mutable_bag_request();network->send(q);text_entry="/bank";item_command();}
            if(clicked=="unlock"&&release.storage_auth){bank_secret=1;bank_prompt="Warehouse password";text_entry.clear();entry=5;walking_to=false;features_open=false;}
            if(clicked=="features"){features_open=!features_open;bag_open=bank_open=shop_open=equipment_open=party_open=friends_open=false;}
            if (target && (hud ? clicked == "strike"
                               : mx >= 28 && mx <= 160 && my >= ph - 74 &&
                                     my <= ph - 28)) {
              if (release.melee) {
                melee.toggle(target);
                walking_to = false;
                held_ground.cancel();
              } else {
                n3e::Envelope message;
                auto *a = message.mutable_action();
                a->set_session(world.world.session());
                a->set_seq(++action_seq);
                a->set_target(target);
                a->set_action(world.world.action());
                network->send(message);
              }
            }
            bool in_world =
                hud ? clicked.empty()
                    : my > 120 && my < ph - 195 && !(mx > pw - 180 && my < 180);
            in_world = in_world && mx >= 0 && mx < pw && my >= 0 && my < ph;
#if TOOLS
            in_world = in_world && !ImGui::GetIO().WantCaptureMouse;
#endif
            // Pick set (PQ-011, 00472ab0): every other player and NPC in
            // view, party members included; a slain NPC only while dying
            // (PQ-199: KO moves it to the corpse map at the end of its dying
            // clip). Geometry (PQ-146, 004724c0): the cursor ray against the
            // boxes drawn last frame, nearest the eye first.
            uint64_t hit = in_world ? n3e::targeting::pick(world, pick_frame, orbit.eye, orbit.ray(mx, my, pw, ph), release.pick.mesh_lod) : 0;
            bool picked = hit != 0;
            if (picked)
              target = hit;
            if(in_world&&!picked&&open_loot(mx,my,pw,ph)){target=0;continue;}
            if (in_world && !picked) {
              target = 0;
              melee.stop();
            }
            melee.select(target);
            walking_to = in_world && !picked &&
                         orbit.ground_point(mx, my, pw, ph, scene, destination);
            // A ground click replaces E's continuous movement (one movement
            // source at a time). KO's handling of +0xae4 here is not decoded:
            // a fidelity gap, PQ-134.
            if (walking_to) auto_move.active = false;
            held_ground.begin(in_world && walking_to && !picked,
                              SDL_GetTicks() / 1000.0);
            // The left press's bindings (Ctrl+click: attack_pick) act on this
            // click's pick after the selection above: 005e16f0 selects through
            // 005d9ce0 before its Ctrl branch. With nothing picked the ordinary
            // click (walk, loot) is all KO does.
            if (picked) {
              click_actor = target;
              for (auto a : input_map.clicked(n3e::input::left_click, n3e::input::modifiers(SDL_GetModState())))
                if (run_action(a)) break;
              click_actor.reset();
            }
          }
          if (e.type == SDL_EVENT_TEXT_INPUT && entry != 2 && entry != 4 &&
              text_entry.size() + std::strlen(e.text.text) <= 128)
            text_entry += e.text.text;
          if (e.type == SDL_EVENT_KEY_DOWN && !e.key.repeat) {
            auto key = e.key.key;
            bool gameplay_keys = entry == 4;
#if TOOLS
            gameplay_keys =
                gameplay_keys && !editor.capture() && !ImGui::GetIO().WantCaptureKeyboard;
#endif
            if (key == SDLK_BACKSPACE && !text_entry.empty()) {
              do {
                unsigned char last = text_entry.back();
                text_entry.pop_back();
                if ((last & 0xc0) != 0x80)
                  break;
              } while (!text_entry.empty());
            }
            // F12 reconnects: engine-reserved, outside the KO key range (D-136).
            if (e.key.scancode == n3e::input::reconnect_key &&
                (entry == 4 || entry == 2 || !world.connected)) {
              network.reset();
              network = std::make_unique<n3e::WorldClient>(release, scene,
                                                           endpoint, ca);
              if (discord_flow) discord_flow->reset();
              world = {};
              notices_seen = 0;
              operator_notices_seen = 0;
              operator_line.clear();
              banner_until = {};
              walking_to = false;
              auto_move.active = false;
              running = release.movement.has_value();
              melee.stop();
              target = 0;
              action_seq = 0;rest_seq=0;skill_failures.reset();
              respawn_seq = 0;
              claim_seq = 0;party_open=false;party_seq=party_invitation=party_group=0;friends_open=false;friend_page=0;friend_seq=friend_query=friend_refresh=0;friend_retry.Clear(); bank_secret=0;bank_old.clear();bank_new.clear();bank_auth_retry.Clear();bank_prompt.clear();bank_open=false;storage_retry.Clear();bag_seq=0; bag_retry.Clear(); bag_open=false;
              entry = 0;
              text_entry.clear();
#if N3E_HARNESS
              automated_login = automated_select = false;
#endif
              continue;
            }
            // Package-bound actions (PQ-009): in play every binding; while a
            // text field has focus only those marked to fire while typing.
            bool typing_keys = entry == 5;
#if TOOLS
            typing_keys = typing_keys && !editor.capture() && !ImGui::GetIO().WantCaptureKeyboard;
#endif
            if (gameplay_keys || typing_keys) {
              bool taken = false;
              for (auto action : input_map.pressed(e.key.scancode, n3e::input::modifiers(e.key.mod), !gameplay_keys))
                if ((taken = run_action(action)))
                  break;
              if (taken)
                continue;
            }
            if ((key == SDLK_RETURN || key == SDLK_KP_ENTER) && entry != 4) {
              n3e::Envelope message;
              if (entry == 0 && discord_flow) {
                discord_start = true;
              } else if (entry == 0) {
                account = text_entry;
                entry = 1;
              } else if (entry == 1) {
                password = text_entry;
                auto *l = message.mutable_login();
                l->set_account(account);
                l->set_password(password);
                network->send(message);
                entry = 2;
              } else if (entry == 3) {
                message.mutable_create_character()->set_name(text_entry);
                network->send(message);
                entry = 2;
              } else if (entry == 5) {
                if(feature_ui.prompt){
                  auto command=feature_ui.confirm(world,text_entry,nearest_shop());
                  if(!command){if(!feature_ui.prompt){text_entry.clear();entry=4;}continue;}
                  text_entry=*command;
                }
                if(bank_secret){
                  if(bank_secret==2){bank_old=text_entry;bank_secret=3;bank_prompt="New warehouse password";text_entry.clear();continue;}
                  if(bank_secret==3){bank_new=text_entry;bank_secret=4;bank_prompt="Repeat new warehouse password";text_entry.clear();continue;}
                  if(bank_secret==4&&text_entry!=bank_new){bank_new.clear();bank_secret=3;bank_prompt="Passwords differ. Enter new warehouse password";text_entry.clear();continue;}
                  const auto *service=nearest_storage();if(service){n3e::Envelope message;auto *q=message.mutable_storage_auth_request();q->set_operation(bank_secret==1?1:2);q->set_service(service->id);q->set_request("credential-"+std::to_string(world.world.self())+"-"+std::to_string(++bag_seq));q->set_password(bank_secret==1?text_entry:bank_old);if(bank_secret==4)q->set_replacement(bank_new);bank_auth_retry=*q;network->send(message);}
                  bank_secret=0;bank_old.clear();bank_new.clear();bank_prompt.clear();text_entry.clear();entry=4;bank_open=true;bag_open=true;shop_open=false;equipment_open=false;continue;
                }
                if(release.storage_auth&&(text_entry=="/bankunlock"||text_entry=="/bankpassword")){
                  bank_secret=text_entry=="/bankunlock"?1:2;bank_prompt=bank_secret==1?"Warehouse password":"Current warehouse password";text_entry.clear();continue;
                }
                if(release.storage_auth&&(text_entry.starts_with("/bankunlock ")||text_entry.starts_with("/bankpassword "))){bank_secret=text_entry.starts_with("/bankunlock ")?1:2;bank_prompt="Enter warehouse password in this masked prompt";text_entry.clear();continue;}
                if(release.storage_auth&&text_entry=="/bankauthretry"){
                  if(!bank_auth_retry.request().empty()){n3e::Envelope message;*message.mutable_storage_auth_request()=bank_auth_retry;network->send(message);}entry=4;text_entry.clear();continue;
                }
                const auto pc=n3e::parse_party(text_entry,release.party?release.party->name_bytes:24);
                if(pc.kind!=n3e::PartyCommand::none){
                  if(!release.party||pc.kind==n3e::PartyCommand::invalid){text_entry="/party; /invite NAME; /accept; /leave";continue;}
                  if(pc.kind==n3e::PartyCommand::hide){party_open=false;entry=4;text_entry.clear();continue;}
                  if(pc.kind==n3e::PartyCommand::block){party_block=!party_block;party_open=true;entry=4;text_entry.clear();continue;}
                  if((pc.kind==n3e::PartyCommand::accept||pc.kind==n3e::PartyCommand::decline)&&!world.party.invitation()){text_entry="No pending party invitation";continue;}
                  auto*q=message.mutable_party_request();q->set_sequence(++party_seq);q->set_name(pc.name);
                  q->set_operation(pc.kind==n3e::PartyCommand::invite?1:pc.kind==n3e::PartyCommand::accept?2:pc.kind==n3e::PartyCommand::decline?3:(pc.kind==n3e::PartyCommand::leave||pc.kind==n3e::PartyCommand::kick)?4:pc.kind==n3e::PartyCommand::disband?5:0);
                  if(pc.kind==n3e::PartyCommand::accept||pc.kind==n3e::PartyCommand::decline)q->set_invitation(world.party.invitation());
                  network->send(message);party_open=true;friends_open=bag_open=bank_open=shop_open=equipment_open=false;entry=4;text_entry.clear();continue;
                }
                const auto fr=n3e::parse_friend(text_entry,release.friends?release.friends->name_bytes:24);
                if(fr.kind!=n3e::FriendCommand::none){
                  if(!release.friends||fr.kind==n3e::FriendCommand::invalid||(fr.kind==n3e::FriendCommand::retry&&friend_retry.request().empty())){text_entry="/friends; /friend NAME; /unfriend NAME";continue;}
                  if(fr.kind==n3e::FriendCommand::hide){friends_open=false;entry=4;text_entry.clear();continue;}
                  auto *q=message.mutable_friend_request();
                  if(fr.kind==n3e::FriendCommand::retry)*q=friend_retry;
                  else if(fr.kind!=n3e::FriendCommand::list){q->set_operation(fr.kind==n3e::FriendCommand::add?1:2);q->set_request("friend-"+std::to_string(world.world.self())+"-"+std::to_string(++friend_seq));q->set_expected_revision(world.friends.revision());q->set_name(fr.name);friend_retry=*q;}
                  network->send(message);party_open=false;friends_open=true;bag_open=bank_open=shop_open=equipment_open=false;entry=4;text_entry.clear();continue;
                }
                if(item_command())continue;
                const auto chat = n3e::parse_chat(text_entry);
                if (chat.kind == n3e::ChatInput::invalid) {
                  text_entry = "/w NAME MESSAGE";
                  continue;
                }
                if (chat.kind == n3e::ChatInput::whisper) {
                  auto *whisper = message.mutable_private_message();
                  whisper->set_recipient(chat.recipient);
                  whisper->set_text(chat.text);
                } else {
                  message.mutable_chat()->set_text(chat.text);
                }
                network->send(message);
                entry = 4;
              }
              text_entry.clear();
            } else if (entry == 2 && key == SDLK_N) {
              entry = 3;
              text_entry.clear();
            } else if (entry == 2 && key >= SDLK_1 && key <= SDLK_8) {
              int index = key - SDLK_1;
              if (index < world.characters.characters_size()) {
                n3e::Envelope message;
                message.mutable_select_character()->set_id(
                    world.characters.characters(index).id());
                network->send(message);
              }
            }
          }
        }
        if (e.type == SDL_EVENT_QUIT)
          run = false;
#if N3E_HARNESS
        if (e.type == SDL_EVENT_WINDOW_RESIZED)
          resized = true;
        if (e.type == SDL_EVENT_WINDOW_MINIMIZED)
          minimized = true;
        if (e.type == SDL_EVENT_WINDOW_RESTORED)
          restored = true;
#endif
        // Esc in play is the package's cancel action (input map, PQ-010). Here
        // it only ends text entry or a prompt (window-local), and quits before
        // the player is in the world.
        if (e.type == SDL_EVENT_KEY_DOWN && e.key.key == SDLK_ESCAPE) {
          if (network && entry >= 4) {
            if (entry == 5) {
              feature_ui.clear();bank_secret=0;bank_old.clear();bank_new.clear();bank_prompt.clear();bank_auth_retry.Clear();
              entry = 4;
              text_entry.clear();
            }
          } else if (discord_flow && discord_flow->phase() == n3e::login::Flow::Phase::browser)
            discord_cancel = true;
          else
            run = false;
        }
      }
      if (network) {
        bool typing = entry != 2 && entry != 4;
#if TOOLS
        // Gameplay stops text input so movement keys never reach a text field.
        // The terminal and inspectors own it back while they capture input,
        // otherwise SDL delivers them no SDL_EVENT_TEXT_INPUT at all.
        typing = typing || editor.capture();
#endif
        if (typing)
          SDL_StartTextInput(w);
        else
          SDL_StopTextInput(w);
        profile_mark(0);
        world = network->poll();
        // Spec 04 / Q10: exit 3 so the launcher fetches the realm's release.
        if (world.update_required && run) {
          std::cerr << world.status << "\n";
          exit_code = 3;
          run = false;
        }
        if (discord_flow && entry < 4) {
#if N3E_HARNESS
          // A suite's client starts the Discord flow itself.
          discord_start = discord_start || auto_login || world_smoke;
#endif
          if (auto message = discord_flow->update(world, discord_start, discord_cancel, std::time(nullptr)))
            network->send(*message);
          discord_start = discord_cancel = false;
          if (discord_flow->phase() == n3e::login::Flow::Phase::done) {
            if (entry < 2) entry = 2;
          } else {
            entry = 0;
            world.status = discord_flow->status();
          }
        }
        // PQ-406 (D-209): a new chat, whisper, rest or admin refusal takes the
        // HUD's message line, as the client's own notices do; PQ-407 (D-210):
        // the line keeps the newest of them, each in its kind's colour.
        if (world.notices != notices_seen) {
          notices_seen = world.notices;
          if (hud) hud->post_refusal(world.notice);
        }
        if (world.operator_notices != operator_notices_seen) {
          operator_notices_seen = world.operator_notices;
          operator_line = world.operator_notice;
          if (hud) hud->post_operator_notice(world.operator_notice);
          if (world.operator_notice_level == 2) {
            banner = world.operator_notice;
            banner_until = std::chrono::steady_clock::now() + std::chrono::seconds(6);
          }
#if N3E_HARNESS
          std::cout << "OPERATOR_NOTICE level=" << world.operator_notice_level << " text='" << world.operator_notice << "'" << std::endl;
#endif
        }
        // PQ-469 (D-235): the server refused a skill this client sent
        // `out_of_range`: post the policy's failed line, its %s the skill's
        // label, in the policy's colour, as 1298's 00586fa0 posts text 0xfa4
        // with the row's name in 0xffff3b3b on Ebenezer's -103. The cast
        // itself already ended by the server's state (its cast-end event).
        // PQ-479 (D-243): a refusal at the acceptance with a status the
        // policy has a refusal line for posts that line in its colour, as
        // 1298 posts its own text for a refusal it makes before it sends a
        // cast (0057f7f0) or text 0xfa2 on Ebenezer's -100 (00586fa0).
        for (const auto post : skill_failures.refused(world.action_outcomes, release.skills ? release.skills->refusals : std::vector<n3e::SkillRefusal>{})) {
          const auto &skill = release.skills->entries[post.skill];
          const auto &line = post.line < 0 ? release.skills->failed : release.skills->refusals[post.line].text;
          const auto colour = post.line < 0 ? release.skills->failed_color : release.skills->refusals[post.line].color;
          const auto text = n3e::skill_notice(line, skill.label);
          if (hud && !text.empty()) hud->post_refusal(text, colour);
#if N3E_HARNESS
          char color[16];
          std::snprintf(color, sizeof color, "%08x", colour);
          std::cout << "SKILL_FAILED skill=" << skill.id << " text='" << text << "' color=" << color << std::endl;
          if (hud && !text.empty()) skill_failed_drawn.push_back({text, colour});
#endif
        }
        const n3e::Entity *presentation_actor=nullptr;
        for(const auto&e:world.world.entities())if(e.id()==world.world.self())presentation_actor=&e;
        melee_presentation.context(world.connected?world.world.self():0,world.world.session(),presentation_actor&&presentation_actor->health(),presentation_actor&&!presentation_actor->cast_skill().empty(),SDL_GetTicks()/1000.,audio.mixer);
        melee_presentation.result(world.action_result_seq,world.combat,audio.mixer);
        if(presentation_actor)melee_presentation.reconcile(*presentation_actor);

        if(release.party&&(world.party.invitation()!=party_invitation||world.party.group()!=party_group)){
          party_invitation=world.party.invitation();party_group=world.party.group();
          if(party_invitation&&party_block){n3e::Envelope message;auto*q=message.mutable_party_request();q->set_sequence(++party_seq);q->set_operation(3);q->set_invitation(party_invitation);network->send(message);}
          else if(party_invitation||party_group){party_open=true;friends_open=bag_open=bank_open=shop_open=equipment_open=false;}
        }
        if(friends_open&&release.friends&&world.world.session()&&world.friends.entries_size()&&(!friend_refresh||world.world.tick()>=friend_refresh+release.friends->refresh_ticks)){
          n3e::Envelope message;auto*q=message.mutable_friend_presence_query();q->set_sequence(++friend_query);for(const auto&e:world.friends.entries())q->add_names(e.name());network->send(message);friend_refresh=world.world.tick();
        }
        if (last_self != world.world.self()) {
          loot_ui.close();
          if (hud) hud->cancel_pointer();
          melee.stop();
          walking_to = false;
          held_ground.cancel();
          heading = 0;
          feature_ui=FeatureUI{};item_wait.reset();
          last_self = world.world.self();
          target = 0;
          orbit_drag = false;
          set_relative_mouse(false);
        }
        for (const auto &e : world.world.entities())
          if (e.id() == last_self && !e.health()) {
            walking_to = false;
            melee.stop();
            target = 0;
            held_ground.cancel();
          }
        if (world.world.self() && entry == 2) {
          entry = 4;
          std::cout << "ENTERED map self=" << world.world.self()
                    << " visible=" << world.world.entities_size() << std::endl;
        }
#if N3E_HARNESS
        // Replays and developer sessions log in from the suite's credentials.
        if ((world_smoke || auto_login) && world.connected &&
            !automated_login && !discord_flow) {
          const char *a = std::getenv("N3E_TEST_ACCOUNT"),
                     *p = std::getenv("N3E_TEST_PASSWORD");
          if (!a || !p)
            throw std::runtime_error(
                "automatic login requires test credentials");
          n3e::Envelope e;
          account=a;
          e.mutable_login()->set_account(a);
          e.mutable_login()->set_password(p);
          network->send(e);
          automated_login = true;
          entry = 2;
        }
        if ((world_smoke || auto_login) && world.characters.characters_size() &&
            !automated_select) {
          n3e::Envelope e;
          e.mutable_select_character()->set_id(
              world.characters.characters(0).id());
          network->send(e);
          automated_select = true;
        }
#endif
      }
#if TOOLS && N3E_HARNESS
#include "harness/editor_replay.inc"
#endif
      bool capture_input = network && (entry != 4 || !window_focused || feature_ui.drag.has_value() || hotbar.drag.has_value());
#if TOOLS
      ImGui_ImplOpenGL3_NewFrame();
      ImGui_ImplSDL3_NewFrame();
      static ImVec2 translation_click, light_click;
#if N3E_HARNESS
      // Replay mouse clicks through ImGui's input queue; production input still
      // comes from SDL.
      auto &io = ImGui::GetIO();
      if (smoke && frame >= 2 && frame <= 4)
        io.AddMousePosEvent(translation_click.x, translation_click.y);
      if (smoke && frame == 3)
        io.AddMouseButtonEvent(0, true);
      if (smoke && frame == 4)
        io.AddMouseButtonEvent(0, false);
      if (smoke && frame >= 6 && frame <= 8)
        io.AddMousePosEvent(light_click.x, light_click.y);
      if (smoke && frame == 7)
        io.AddMouseButtonEvent(0, true);
      if (smoke && frame == 8)
        io.AddMouseButtonEvent(0, false);
      if (smoke && frame == 12)
        io.AddInputCharacter('w');
#endif
      int edit_width,edit_height;SDL_GetWindowSize(w,&edit_width,&edit_height);
      ImGui::NewFrame();
      editor.selection=target;  // PQ-194: `kill` with no id names the current target
      editor.draw(release,world,network.get(),orbit,edit_width,edit_height);

      static char text[128] = "Type WASD here";
      if (!network) {
        ImGui::SetNextWindowSize(ImVec2(360, 160), ImGuiCond_FirstUseEver);
        ImGui::Begin("Fixture editor");
        ImGui::SliderFloat("Translation X", &offset, -1, 1);
        translation_click = ImVec2(ImGui::GetItemRectMin().x + 150,
                                   ImGui::GetItemRectMin().y + 8);
        ImGui::SliderFloat("Light", &light, 0, 1);
        light_click = ImVec2(ImGui::GetItemRectMin().x + 70,
                             ImGui::GetItemRectMin().y + 8);
#if N3E_HARNESS
        if (smoke && frame == 10)
          ImGui::SetKeyboardFocusHere();
#endif
        ImGui::InputText("Focus check", text, sizeof text);
        ImGui::Text("Camera %.3f, %.3f", cx, cy);
        ImGui::End();
      }
      capture_input = capture_input || editor.capture() || ImGui::GetIO().WantCaptureKeyboard || ImGui::GetIO().WantCaptureMouse;
#if N3E_HARNESS
      if (smoke && frame == 13) {
        if (!capture_input || std::strchr(text, 'w') == nullptr)
          throw std::runtime_error("text input/focus failed");
        if (offset == 0 || light == .85f)
          throw std::runtime_error("slider clicks did not edit values");
        focus_checked = true;
        std::cout << "UI edited offset=" << offset << " light=" << light
                  << " text=" << text << "\n";
      }
#endif
#endif
      auto keys = SDL_GetKeyboardState(nullptr);
      auto input_now = SDL_GetTicks();
      double input_dt = (input_now - input_last) / 1000.0;
      bool mouse_captured = entry != 4 || !window_focused || !world.connected;
#if TOOLS
      mouse_captured = mouse_captured || editor.capture() || ImGui::GetIO().WantCaptureMouse;
#endif
      if (network && orbit_drag &&
          (mouse_captured || !relative_mouse())) {
        orbit_drag = false;
        set_relative_mouse(false);
      }
      input_last = input_now;
#if N3E_HARNESS
      float camera_before = cy;
#endif
      if (network) {
        // Held actions from the package map: forward/back and turning
        // (005c6990 reads W/S/A/D and the arrow keys every frame).
        const uint32_t held_mods = n3e::input::modifiers(SDL_GetModState());
        using HeldAction = n3e::input::Action;
        bool key_w = input_map.down(HeldAction::move_forward, keys, held_mods),
             key_s = input_map.down(HeldAction::move_backward, keys, held_mods),
             key_a = input_map.down(HeldAction::turn_left, keys, held_mods),
             key_d = input_map.down(HeldAction::turn_right, keys, held_mods);
#if N3E_HARNESS
        // Scripted keys: the replays hold the same keys a player would.
        if (controls_smoke && entry == 4) {
          if (!controls_start)
            controls_start = input_now;
          auto elapsed = input_now - controls_start;
          key_a = elapsed < 1500;
          key_d = false;
          key_w = elapsed >= 1500 && elapsed < 3000;
          key_s = elapsed >= 3000 && elapsed < 4000;
        }
        if (melee_smoke && melee_start) {
          auto elapsed = input_now - melee_start;
          key_w = elapsed >= 7500 && elapsed < 7800;
          key_a = key_d = key_s = false;
        }
        if(moving_test&&weapon_test&&(uif_stage==4||uif_stage==5)){
          key_s=true;key_w=key_a=key_d=false;
        }
        if(chest_test&&(uif_stage==35||uif_stage==36)){
          key_w=uif_stage==35;key_a=uif_stage==36;key_s=key_d=false;
        }
#endif
        bool living = false;
        for (const auto &entity : world.world.entities())
          if (entity.id() == world.world.self())
            living = entity.health() != 0;
        // E: continuous forward movement until a forward/back key or death
        // ends it. It keeps going while chat has focus: inferred from KO's
        // text focus (DAT_006dfe20) gating only key reading in 005c6990, not
        // observed. Losing window focus ends it (n3e policy; gap, PQ-134).
        auto_move.update(living, !capture_input && (key_w || key_s));
        bool auto_forward = auto_move.active && living && entry >= 4 && window_focused;
        bool forward = (!capture_input && key_w) || auto_forward;
        bool backward = !capture_input && key_s;
        bool layered_combat=release.combat_animation&&!release.combat_animation->upper_nodes.empty();
        bool movement_cancels=manual_attack_input.cancel(layered_combat,forward,backward,!capture_input&&(key_a||key_d));
        float dx = capture_input ? 0 : int(key_d) - int(key_a);
        float dz = float(int(backward) - int(forward));
        move_mode = release.movement ? (dz > 0 ? 2 : running ? 1 : 0) : 0;
        bool keyboard_navigation =
            forward || backward || (!capture_input && (key_a || key_d));
        if (release.camera.facing_relative &&
            (!world_smoke || play_smoke || controls_smoke || melee_smoke)) {
          int turn = capture_input || !living ? 0 : int(key_d) - int(key_a);
          int travel = !living  ? 0
                       : forward  ? 1
                       : backward ? -1
                                  : 0;
          auto direction = facing_input(heading, turn, travel, input_dt,
                                        release.camera.turn_rate);
          dx = direction[0];
          dz = direction[2];
          move_mode = release.movement ? (travel < 0 ? 2 : running ? 1 : 0) : 0;
        }
        if (!living && orbit_drag) {
          orbit_drag = false;
          set_relative_mouse(false);
        }
        // Camera keys and screen edges (PQ-012, D-143; KO 005c6990). The
        // package binds the held pitch keys and sets both rates (0: off);
        // camera_input decides when each may act.
        {
          camera_input::Context context;
          context.in_world = entry == 4 || entry == 5;
          context.typing = entry == 5;
          context.window_focused = window_focused;
          context.mouse_in_window = SDL_GetMouseFocus() == w;
#if N3E_HARNESS
          // The play replay owns the pointer (PQ-238): the desktop cursor
          // resting on an edge must not yaw its scripted camera.
          if (play_smoke) context.mouse_in_window = false;
          // SDL's offscreen driver gives its window the mouse focus when it is
          // shown (no ShowWindow hook, so SDL_ShowWindow calls
          // SDL_SetMouseFocus), and SDL's cursor stays at (0, 0), the left edge
          // column, because the replays push their events. There is no pointer
          // offscreen, so the test client there never edge-yaws (PQ-129): a
          // desktop window turns only while the user's pointer rests on its edge.
          if (offscreen) context.mouse_in_window = false;
          // The scene captures own the camera too (PQ-355): suites compare
          // captures of separate client runs (option on and off), so the
          // desktop cursor resting on an edge (or crossing one as the
          // compositor places windows) must not turn one run's camera. A
          // glow capture of PQ-350's desktop run drew a camera turned before
          // its 40th frame, the other's blade 11 px off the option-off run's.
          if (scene_captures) context.mouse_in_window = false;
#endif
          context.dragging = orbit_drag;
#if TOOLS
          context.tools_keyboard = editor.capture() || ImGui::GetIO().WantCaptureKeyboard;
          context.tools_mouse = editor.capture() || ImGui::GetIO().WantCaptureMouse;
#endif
          if (camera_input::pitch_keys(context))
            orbit.key_pitch(input_map.down(HeldAction::camera_pitch_up, keys, held_mods),
                            input_map.down(HeldAction::camera_pitch_down, keys, held_mods),
                            float(input_dt));
          if (camera_input::edge(context)) {
            float mx = 0, my = 0;
            int lw = 0, lh = 0;
            SDL_GetMouseState(&mx, &my);
            SDL_GetWindowSize(w, &lw, &lh);
            orbit.edge_yaw(Orbit::edge(mx, float(lw)),
                           float(input_dt));
          }
        }
        if (keyboard_navigation || capture_input || !living ||
            !world.connected) {
          if (hud && (capture_input || !living || !world.connected)) hud->cancel_pointer();
          if(movement_cancels||capture_input||!living||!world.connected)melee.stop();
          held_ground.cancel();
          walking_to = false;
        }
        bool cursor_allowed = !capture_input && living && !keyboard_navigation;
#if TOOLS
        cursor_allowed = cursor_allowed && !ImGui::GetIO().WantCaptureMouse;
#endif
        if (held_ground.active && !cursor_allowed)
          walking_to = false;
        if (held_ground.refresh(input_now / 1000.0, cursor_allowed)) {
          int pw, ph, lw, lh;
          SDL_GetWindowSizeInPixels(w, &pw, &ph);
          SDL_GetWindowSize(w, &lw, &lh);
          float mx = cursor_x * pw / lw, my = cursor_y * ph / lh;
          bool in_world =
              hud ? hud->hit(mx, my, pw, ph).empty()
                  : my > 120 && my < ph - 195 && !(mx > pw - 180 && my < 180);
          in_world = in_world && mx >= 0 && mx < pw && my >= 0 && my < ph;
          if (!in_world) {
            held_ground.cancel();
            walking_to = false;
          } else {
            walking_to = orbit.ground_point(mx, my, pw, ph, scene, destination);
          }
        }
#if N3E_HARNESS
#include "harness/input_replays.inc"
#endif
        if (!release.camera.facing_relative && (!world_smoke || play_smoke)) {
          float x = dx * std::cos(orbit.yaw) + dz * std::sin(orbit.yaw);
          dz = -dx * std::sin(orbit.yaw) + dz * std::cos(orbit.yaw);
          dx = x;
        }
        if (dx || dz)
          walking_to = false;
        if (walking_to && !capture_input) {
          move_mode = release.movement && running ? 1 : 0;
          dx = destination[0] - world.predicted[0];
          dz = destination[2] - world.predicted[2];
          float d = std::hypot(dx, dz);
          if (d < (release.movement
                       ? release.movement->speed(running ? 1 : 0) * .05f
                       : .15f)) {
            walking_to = false;
            dx = dz = 0;
          } else {
            dx /= d;
            dz /= d;
          }
        }
        if ((walking_to || (world_smoke && !controls_smoke) ||
             !release.movement) &&
            dx * dx + dz * dz > .01f)
          heading = move_mode == 2 ? std::atan2(dx, dz) : std::atan2(-dx, -dz);
        if (release.melee && melee.target) {
          melee.result(world.action_result_seq, world.combat);
          const n3e::Entity *victim = nullptr;
          const n3e::Entity *actor = nullptr;
          for (const auto &e : world.world.entities())
            if(e.id()==world.world.self())actor=&e;
            else if (e.id() == melee.target && (!melee.attack || (e.npc() && e.health())))
              victim = &e;  // an approach-only walk follows any actor (PQ-011)
          if (!victim || !actor || !actor->health() || !actor->cast_skill().empty() || actor->sitting())
            melee.stop();
          else if (melee.target) {
            auto position = n3e::V{victim->x(), victim->y(), victim->z()};
            double now = SDL_GetTicks() / 1000.0;
            const auto *ranged = ranged_attack(actor);
            const auto melee_cfg = melee_config(actor);
            melee.ranged = ranged ? melee_cfg.actor_radius + melee_cfg.target_radius + ranged->range : 0;
            // PQ-421 (D-218): the shot's ammunition, counted in the last bag
            // state the server sent (it removes one per landed shot).
            melee.ammo = !ranged || n3e::ammo_carried(world.bag, ranged->ammo, ranged->ammo_count);
            // PQ-439 (D-223): the server released the pending shot; its
            // result comes when the arrow arrives.
            if(ranged&&melee.pending&&actor->strike_sequence()==melee.pending&&actor->strike_result()=="released")
              melee.released(melee.pending);
            auto direction = melee.update(
                now, world.predicted, position, heading, melee_cfg,
                (release.movement ? release.movement->speed(running ? 1 : 0)
                                  : 3.f) *
                    .05f,layered_combat&&keyboard_navigation);
            if(!(layered_combat&&keyboard_navigation)){
              dx = direction[0];dz = direction[2];
              move_mode = release.movement && running ? 1 : 0;
            }
            walking_to = false;
#if N3E_HARNESS
            if(approach_test&&!approach_arrival&&std::hypot(world.predicted[0]-position[0],world.predicted[2]-position[2])<=release.melee->range())approach_arrival=now;
            if(approach_test&&approach_sequence==world.action_result_seq&&world.combat=="out_of_range")throw std::runtime_error("approach sent before confirmed range");
#endif
            uint32_t interval=0;
            if(release.combat_animation&&actor->combat_style())interval=release.combat_animation->profiles.at(actor->combat_style()-1).interval_ms;
            // A ranged shot is not loosed while the keys move the player (KO's
            // walk cancels the cast, 00585830); otherwise it stops the walk.
            bool walking=layered_combat&&(dx*dx+dz*dz>.000001f);
            // PQ-420 (D-217): a walk during a held shot cancels it (1298's
            // 00585830, the server's admission); the predicted clip stops now.
            if(ranged&&ranged->cast_ms&&walking&&melee.pending)
              if(auto*attempt=melee_presentation.find(melee.pending);attempt&&!attempt->cancelled){attempt->cancelled=true;audio.mixer.cancel(attempt->sequence);}
            if (melee.no_ammo(now, melee_cfg, interval)) {
              if(hud&&!release.combat_animation->ammo_notice.empty())hud->post_notice(release.combat_animation->ammo_notice);
#if N3E_HARNESS
              std::cout<<"RANGED_NO_AMMO target="<<melee.target<<" item="<<ranged->ammo<<" count="<<ranged->ammo_count
                       <<" notice='"<<release.combat_animation->ammo_notice<<"'"<<std::endl;
#endif
            } else if (melee.too_far(now, world.predicted, position, melee_cfg, interval)) {
              if(hud&&!release.combat_animation->ranged_notice.empty())hud->post_notice(release.combat_animation->ranged_notice);
#if N3E_HARNESS
              std::cout<<"RANGED_TOO_FAR target="<<melee.target<<" distance="<<std::sqrt(std::pow(position[0]-world.predicted[0],2.f)+std::pow(position[1]-world.predicted[1],2.f)+std::pow(position[2]-world.predicted[2],2.f))
                       <<" limit="<<melee.ranged<<" walking="<<walking<<" notice='"<<release.combat_animation->ranged_notice<<"'"<<std::endl;
#endif
            } else if (!(ranged && walking) && melee.ready(now, world.predicted, position, heading,
                            melee_cfg, {actor->x(),actor->y(),actor->z()})) {
              if (ranged) {
                // 00583f20 stops the walk (005d6430(0,1) at 005844c2).
                walking_to=false;held_ground.cancel();dx=dz=0;
                n3e::face_target(world.predicted, position, heading);
#if N3E_HARNESS
                std::cout<<"RANGED_SHOT seq="<<action_seq+1<<" target="<<melee.target<<" distance="<<std::sqrt(std::pow(position[0]-world.predicted[0],2.f)+std::pow(position[1]-world.predicted[1],2.f)+std::pow(position[2]-world.predicted[2],2.f))
                         <<" limit="<<melee.ranged<<" position="<<world.predicted[0]<<","<<world.predicted[2];
                if(!ranged->ammo.empty()){uint32_t carried=0;for(const auto&slot:world.bag.slots())if(slot.instance()&&slot.item()==ranged->ammo){carried=slot.quantity();break;}std::cout<<" ammo="<<carried;}
                std::cout<<std::endl;
#endif
              }
              n3e::Envelope message;
              auto *a = message.mutable_action();
              a->set_session(world.world.session());
              a->set_seq(++action_seq);
              a->set_target(melee.target);
              a->set_action(world.world.action());
              network->send(message);
              melee.sent(action_seq, now, *release.melee,interval,ranged?ranged->cast_ms:0);
              if(release.protocol>=28&&release.combat_animation&&actor->combat_style()){
                bool moving=layered_combat&&(dx*dx+dz*dz>.000001f);
                melee_presentation.begin(action_seq,melee.target,actor->combat_style(),moving,now);
                n3e::PresentationEvent swing;swing.set_kind(2);swing.set_actor(actor->id());swing.set_target(melee.target);
                swing.set_tick(world.world.tick());swing.set_request_sequence(action_seq);swing.set_style(actor->combat_style());swing.set_moving(moving);
                swing.set_x(world.predicted[0]);swing.set_y(world.predicted[1]);swing.set_z(world.predicted[2]);
                PresentationEvents::audio(audio.mixer,release,world,swing,now,now,false,action_seq);
              }
#if N3E_HARNESS
              if(approach_test&&!approach_request){approach_request=now;approach_sequence=action_seq;}
#endif
            }
          }
        }
        bool key_q=input_map.down(HeldAction::turbo,keys,held_mods);
        bool turbo_context=!capture_input && living && world.connected;
        if(!turbo_context || turbo_self!=world.world.self() || turbo_session!=world.world.session() ||
           turbo_generation!=world.world.permission_generation()) turbo_armed=false;
        turbo_self=world.world.self();turbo_session=world.world.session();
        turbo_generation=world.world.permission_generation();
        if(turbo_context && !key_q) turbo_armed=true;
        network->direction(dx, dz, move_mode, release.exploration && turbo_context && turbo_armed && key_q);
        movement_intent = {dx, 0, dz};
        // Binary movement hides pickup immediately; rotation keys do too.
        // Use admitted input, not positional drift from snapshot correction.
        if(living&&!capture_input&&(keyboard_navigation||dx||dz))loot_ui.close();
        cx = world.predicted[0];
        cy = world.predicted[1] - .6f;
      }
      if (!capture_input && !network) {
        cx += (keys[SDL_SCANCODE_D] - keys[SDL_SCANCODE_A]) * .02f;
        cy += (keys[SDL_SCANCODE_W] - keys[SDL_SCANCODE_S] +
               (TOOLS && smoke && frame == 13 ? 1 : 0)) *
              .02f;
      }
#if N3E_HARNESS
      if (TOOLS && smoke && frame == 13 && cy != camera_before)
        throw std::runtime_error("typing moved camera");
      if (smoke && frame == 16)
        SDL_SetWindowSize(w, 720, 540);
      if (smoke && frame == 22) {
        bool accepted = SDL_MinimizeWindow(w);
        std::cout << "minimize request=" << accepted
                  << " detail=" << (accepted ? "accepted" : SDL_GetError())
                  << "\n";
      }
      if (smoke && frame == 30) {
        bool accepted = SDL_RestoreWindow(w);
        std::cout << "restore request=" << accepted
                  << " detail=" << (accepted ? "accepted" : SDL_GetError())
                  << "\n";
      }
#endif
      int width, height;
      SDL_GetWindowSizeInPixels(w, &width, &height);
      if (width < 1 || height < 1) {
        SDL_Delay(10);
        ++frame;
        continue;
      }
      if (frame == 0 && fixed_width)
        std::cout << "fixed window requested=" << fixed_width << "x" << fixed_height
                  << " drawable=" << width << "x" << height << "\n";
      glViewport(0, 0, width, height);
      if (release.exploration) {
        auto c=release.exploration->fog_color; glClearColor(c[0],c[1],c[2],1);
      } else if (network)
        glClearColor(.35, .49, .58, 1);
      else
        glClearColor(.07, .09, .14, 1);
      profile_mark(1);
      // PQ-316: with the post-process on the world draws into its scene target.
      const bool postprocessed=postprocess.ready&&postprocess.begin(width,height);
      glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
      float time = fixed >= 0
                       ? fixed
                       : std::fmod((SDL_GetTicks() - start) / 2000.f, duration);
      if (time < 0 || time > duration)
        throw std::runtime_error("time range");
      // A package world replaces the collision stand-in, so connected frames
      // skin only the placeholder model.
      auto verts = network && world_asset ? scene.skin(scene.sample(time)) : scene.animate(time);
      std::vector<float> player_vertices;
      if(hud)hud->names.clear();
      std::vector<float> detail_vertices;
      // PQ-315: detail vertex ranges drawn with a glow (first vertex, count, shade).
      // PQ-348: and ranges drawn with an N3D3 key's render state (either or both).
      struct GlowRange{size_t first,count;std::optional<n3e::EquipmentGlow::Shade> shade;const n3e::AppearanceState*state=nullptr;};
      std::vector<GlowRange> detail_glow;
#if N3E_HARNESS
      glow_boxes.clear();part_corners.clear();
      part_states=part_states_default&&part_state_follow.left!=2;
#endif
      std::vector<n3e::targeting::PickVolume> pick_volumes;  // PQ-146: this frame's drawn actors
      // PQ-253: NPCs drawn with a looks model, batched per looks (one texture
      // each); the pick volumes recorded into a batch are moved to its place in
      // the merged buffer (pick buffer 3) once every batch is complete.
      std::vector<std::vector<float>> looks_batches(looks_scenes.size());
      // PQ-328: this frame's attached characters (8 floats per vertex), each
      // draw with its entry's model atlas and the shade of its lit indices.
      struct AttachedDraw{size_t entry,first,count,lit;n3e::AttachedCharacters::Shade shade;};
      std::vector<float> attached_vertices;
      std::vector<AttachedDraw> attached_draws;
#if N3E_HARNESS
      attached_boxes.clear();attached_part_boxes.clear();
#endif
      std::vector<std::pair<size_t, size_t>> looks_picks;  // pick volume, looks
      n3e::targeting::Corpses frame_corpses;  // PQ-199: NPCs past their dying clip (KO state 5)
      // The selected actor: its id, displayed position, NPC, drawn scale (PQ-296).
      struct MarkerTarget{uint64_t id;n3e::V position;bool npc;float scale;};
      std::optional<MarkerTarget> marker_target;
      std::map<uint64_t,n3e::V> effect_positions;
      std::map<std::pair<uint64_t,int>,n3e::V> effect_joints;
      std::map<uint64_t,float> effect_headings;  // PQ-423: each player's drawn facing, for its cast effects
      // PQ-211: this frame's equipped-item effect glow meshes and tail links.
      std::vector<n3e::EffectMesh> appearance_meshes;
      std::vector<const n3e::EffectInstance*> appearance_tails;
      float self_heading=heading; // the drawn facing of the controlled character
#if N3E_HARNESS
      uint64_t marker_drawn=0; // the target whose marker drew every part
#endif
      unsigned character_row=0;
      if (network) {
        auto mesh = verts;
        size_t model_vertices = scene.indices.size() + 3;
        verts.erase(verts.begin(), verts.begin() + model_vertices * 8);
        if (world_asset)
          // The package ships its own visible world, so the collision hull is
          // not drawn as a stand-in surface any more.
          verts.clear();
        else
          for (size_t i = 0; i < verts.size(); i += 8)
            verts[i + 6] = -1;
        double now = std::chrono::duration<double>(
                         std::chrono::steady_clock::now().time_since_epoch())
                         .count();
        bool alive = false;
        for (const auto &entity : world.world.entities())
          if (entity.id() == world.world.self())
            alive = entity.health() != 0;
        auto displayed = motion.update(
            world.predicted, now, world.world.session(), world.world.self(),
            alive, movement_intent[0] != 0 || movement_intent[2] != 0,
            release.animation.has_value());
        auto camera_focus =
            camera_motion.update(world.predicted, now, world.world.session(),
                                 world.world.self(), alive);
#if N3E_HARNESS
        if (animation_test && release.animation &&
            std::hypot(displayed[0] - camera_focus[0],
                       displayed[2] - camera_focus[2]) > .00001f)
          throw std::runtime_error("blended stop separated actor and camera");
        if (camera_smoke && controls_stage >= 20 && controls_stage <= 22) {
          camera_focus = {0, 0, 0};
          orbit.pitch = orbit.config.pitch_min;
          orbit.distance = orbit.config.distance_max;
          orbit.yaw = controls_stage <= 21 ? 1.5707963f : 0;
        }
        if (!showcase_views.empty()) {
          const double drawn = glow_self_first < 0 ? 0 : now - glow_self_first;
          const ShowcaseView *view = &showcase_views.front();
          for (const auto &v : showcase_views)
            if (v.at <= drawn) view = &v;
          orbit.yaw = view->yaw;
          orbit.pitch = view->pitch;
          orbit.distance = view->distance;
        }
        if (showcase_target_at >= 0 && glow_self_first >= 0 &&
            now - glow_self_first >= showcase_target_at) {
          const auto nearest = n3e::targeting::enemy(world);
          std::cout << "SHOWCASE_TARGET at=" << now - glow_self_first
                    << " nearest=" << nearest << std::endl;
          showcase_target_at = -1;
          press_action(n3e::input::Action::target_enemy);
        }
        if (showcase_attack_at >= 0 && glow_self_first >= 0 &&
            now - glow_self_first >= showcase_attack_at) {
          std::cout << "SHOWCASE_ATTACK at=" << now - glow_self_first
                    << " target=" << target << std::endl;
          showcase_attack_at = -1;
          press_action(n3e::input::Action::attack_toggle);
        }
        if (showcase_select_at >= 0 && glow_self_first >= 0 &&
            now - glow_self_first >= showcase_select_at) {
          bool seen = false;
          for (const auto &e : world.world.entities()) seen = seen || e.id() == showcase_select;
          std::cout << "SHOWCASE_SELECT at=" << now - glow_self_first << " id=" << showcase_select
                    << " seen=" << seen << std::endl;
          showcase_select_at = -1;
          if (seen) select_target(showcase_select);
        }
        for (auto use = showcase_skills.begin(); use != showcase_skills.end();)
          if (glow_self_first >= 0 && now - glow_self_first >= use->at) {
            std::cout << "SHOWCASE_SKILL at=" << now - glow_self_first << " index=" << use->index
                      << " target=" << target << (use->unchecked ? " unchecked" : "") << std::endl;
            const auto pressed = *use;
            use = showcase_skills.erase(use);
            skill_use(release.skills->entries[pressed.index], !pressed.unchecked);
          } else
            ++use;
#endif
        orbit.update(camera_focus, scene,
                     release.movement ? release.movement->height : 1.6f,
                     float(width) / height);
        if (animation_session != world.world.session()) {
          poses.clear();
          combat_poses.clear();
          animations.clear();
          entity_looks.clear();
          layers.clear();
          attachment_states.clear();
          attached_animations.clear();
          attached_plugs.clear();
          if(!attached.empty())attached.build(*release.attachments);
          name_lifetime.clear();
          npc_name_lifetime.clear();
          animation_session = world.world.session();
        }
        if(detail) {
          unsigned cost=0;
          for(const auto &e:world.world.entities()) if(!e.npc() && e.id()!=world.world.self()) {
            auto delta=camera_geometry::sub({e.x(),e.y(),e.z()},orbit.eye);
            float metric=std::sqrt(camera_geometry::dot(delta,delta))*release.camera.fov/detail->radius;
            int level=n3e::character_lod::level(*detail,metric,0);if(level>=0)cost+=4-level;
          }
          character_row=n3e::character_lod::row(*detail,cost);
        }
        // A player or NPC who left view loses its label (KO: user-out deletes
        // the player; for NPCs an n3e choice, PQ-174; NPC-in builds no label,
        // PQ-170, so one that returns waits for the next measurement).
        auto present=[&](uint64_t id){
          return std::any_of(world.world.entities().begin(),world.world.entities().end(),[&](const auto&e){return e.id()==id;});};
        name_lifetime.forget_absent(present);npc_name_lifetime.forget_absent(present);
        // PQ-177: the capability set the server projected last (session start
        // and every admin result). Nothing local, a tools build included, can
        // set it.
        const bool inspect=std::any_of(world.registry.capabilities().begin(),world.registry.capabilities().end(),
          [](const auto&capability){return capability==inspect_capability;});
        // The local player's party ended (PQ-166; KO 0051c030 on leaving,
        // disbanding or zone entry refreshes every member's label).
        if(name_party_group&&world.party.group()!=name_party_group)name_lifetime.party_ended();
        name_party_group=world.party.group();
        for (auto &entity : world.world.entities()) {
          n3e::V pos{entity.x(), entity.y(), entity.z()};
          if (entity.id() == world.world.self())
            pos = displayed;
          else
            pos = remote_position(world.previous, world.world, entity,
                                  now - world.received);
          effect_positions[entity.id()]=pos;
          // The NPC's looks entry (PQ-253): the one its looks key names. A key
          // the table lacks takes the first entry, as KO's NPC-in takes the
          // looks table's first node for an unknown resource ID (005cdc73 ->
          // 00473b10, 005cdc81-005cdc95; the lowest key, by inference); a valid
          // package never sends one,
          // since its table covers exactly its templates' keys.
          std::optional<size_t> looks;
          if (entity.npc() && !looks_scenes.empty()) {
            auto found = looks_index.find(entity.looks());
            looks = found == looks_index.end() ? 0 : found->second;
            // A reused entity id with another looks starts its animation over
            // (the skeletons differ).
            auto [was, made] = entity_looks.try_emplace(entity.id(), *looks);
            if (!made && was->second != *looks) {
              animations.erase(entity.id());
              was->second = *looks;
              made = true;
            }
#if N3E_HARNESS
            if (made)
              std::cout << "NPC_LOOKS entity=" << entity.id() << " key=" << entity.looks() << " looks=" << *looks
                        << " fallback=" << (found == looks_index.end()) << "\n";
#endif
          }
          // The NPC's drawn scale (PQ-272, D-179). KO's NPC-in gives it to the
          // character (slot +0x34, 0041f800), whose matrix +0x54 then carries
          // it on its diagonal (0043b650); the render passes that matrix to
          // device slot +0x94 with 256 (004197e0; the world transform by
          // inference) and the pick tests the box with it (PQ-146).
          const float npc_scale = drawn_scale(entity);
          // KO: the looks row's byte +0x14c keeps the name at any range and
          // past the camera limit (00470baa, 00459856), per row, so per looks.
          const bool looks_always = looks && release.npc_looks[*looks].name_always;
          // Another player in the local player's party (PQ-166; KO's party
          // marker, other-player +0x7dc).
          bool party_member=!entity.npc()&&entity.id()!=world.world.self()&&std::any_of(world.party.members().begin(),world.party.members().end(),
            [&](const auto&m){return m.entity()==entity.id();});
          uint32_t name_classes=party_member?n3e::NameLifetimePolicy::party:0u;
          // Other players' label lifetime (PQ-169): measured every frame from
          // the package's measuring point, both positions as displayed.
          if(name_lifetime.policy&&!entity.npc()&&entity.id()!=world.world.self()){
            const auto&life=*name_lifetime.policy;
            n3e::V from=life.from==n3e::NameLifetimePolicy::camera?orbit.eye:displayed;
            float distance=std::sqrt((pos[0]-from[0])*(pos[0]-from[0])+(pos[1]-from[1])*(pos[1]-from[1])+(pos[2]-from[2])*(pos[2]-from[2]));
            uint32_t exempt=name_classes;
            [[maybe_unused]]auto change=name_lifetime.update(entity.id(),distance,exempt);
#if N3E_HARNESS
            if(nameplate_test){
              static std::set<uint64_t> kept;
              if(change!=NameLifetime::none){
                kept.erase(entity.id());
                std::cout<<"NAME_LIFETIME "<<(change==NameLifetime::acquired?"acquired":"released")<<" entity="<<entity.id()<<" distance="<<distance<<" exempt="<<exempt<<"\n";
              }else if(name_lifetime.labelled(entity.id())&&distance>=life.acquire&&distance<=life.release&&kept.insert(entity.id()).second)
                std::cout<<"NAME_LIFETIME kept entity="<<entity.id()<<" distance="<<distance<<"\n";
            }
#endif
          }
          // The marker follows the actor's drawn scale as KO's symbol does
          // (005c4e20 -> 0045a1d0, 00459ff0: radius and height times +0x90).
          if(release.target_marker && world.connected && entity.id()==target)
            marker_target=MarkerTarget{entity.id(),pos,entity.npc(),npc_scale};
          // NPC label lifetime (PQ-174): measured every frame from the
          // package's measuring point, both positions as displayed; `dead`
          // once the NPC's death presentation has finished (KO state 5).
          // The info line (PQ-177) is set at each refresh while the projected
          // capability set holds the inspection capability (`inspect`).
          auto npc_label=[&](bool dead){
            if(!entity.npc())return;
            if(!npc_name_lifetime.policy){npc_name_lifetime.update(entity.id(),0,dead,inspect,looks_always);return;}
            const auto&life=npc_name_lifetime.policy->range;
            n3e::V from=life.from==n3e::NameLifetimePolicy::camera?orbit.eye:displayed;
            float distance=std::sqrt((pos[0]-from[0])*(pos[0]-from[0])+(pos[1]-from[1])*(pos[1]-from[1])+(pos[2]-from[2])*(pos[2]-from[2]));
            [[maybe_unused]]auto change=npc_name_lifetime.update(entity.id(),distance,dead,inspect,looks_always);
#if N3E_HARNESS
            if(nameplate_test){
              static std::set<uint64_t> kept;
              if(change!=NameLifetime::none){
                kept.erase(entity.id());
                std::cout<<"NPC_NAME_LIFETIME "<<(change==NameLifetime::acquired?"acquired":"released")<<" entity="<<entity.id()<<" distance="<<distance<<" dead="<<dead<<"\n";
              }else if(npc_name_lifetime.labelled(entity.id())&&distance>=life.acquire&&kept.insert(entity.id()).second)
                std::cout<<"NPC_NAME_LIFETIME kept entity="<<entity.id()<<" distance="<<distance<<"\n";
            }
#endif
          };
          auto add_name=[&](float root_y,bool seated){
            if(!hud||!hud->data.nameplates)return;
            if(!name_display.visible(entity.npc(),entity.id()==world.world.self(),party_member))return;
            if(!entity.npc()&&entity.id()!=world.world.self()&&!name_lifetime.labelled(entity.id()))return;
            if(entity.npc()&&!npc_name_lifetime.labelled(entity.id()))return;
            const auto&style=*hud->data.nameplates;
            auto anchor=name_anchor(style,entity.npc(),pos,root_y,seated,npc_scale);
#if N3E_HARNESS
            // PQ-272 (N3E_TEST_NPC_LOOKS=1): once per NPC, the height above it
            // of the anchor its name is drawn at.
            if(entity.npc()&&std::getenv("N3E_TEST_NPC_LOOKS")){static std::set<uint64_t> reported;
              if(reported.insert(entity.id()).second)std::cout<<"NPC_LABEL entity="<<entity.id()<<" height="<<anchor[1]-pos[1]<<" style=1\n";}
#endif
            auto q=orbit.project(anchor,width,height);
            if(q[2]<release.camera.near_plane||q[2]>release.camera.far_plane)return;
            // Party names (PQ-166): the camera limit is lifted while the player
            // is in the party (0046ea90 reads the marker); the colour is the one
            // set at the label's last refresh (0046e840).
            const auto&party_names=release.names.party;
            bool beyond=(party_member&&party_names&&party_names->beyond_distance)||(entity.npc()&&npc_name_lifetime.beyond_distance(looks_always));
            std::optional<uint32_t> color;
            if(party_names&&party_names->color&&(name_lifetime.refreshed(entity.id(),name_classes)&n3e::NameLifetimePolicy::party))color=party_names->color;
            // The class's camera limit (PQ-173: package data per class, else
            // the style's distance).
            float limit=name_distance(style,release.names,entity.npc(),entity.id()==world.world.self());
            if(auto label=nameplate(style,entity.id(),display_name(entity.name()),entity.npc(),entity.id()==world.world.self(),pos,orbit.eye,q,width,height,beyond,color,limit)){
              // The NPC info line (PQ-177): above the name, only with it.
              const auto&info=release.names.npc_info;
              bool informed=entity.npc()&&info&&npc_name_lifetime.informed(entity.id());
              // PQ-186: the traced NPC's last reported server state, else the package's fallback.
              auto traced=world.npc_states.find(entity.id());
              const std::string&state=traced==world.npc_states.end()?std::string():traced->second;
              auto text=informed?n3e::npc_info_line(*info,entity.id(),state):std::string();
#if N3E_HARNESS
              if(entity.npc())npc_info_seen(text,traced!=world.npc_states.end());
#endif
              // Drawn after the name, as 00459820 does (00459dfd).
              auto line=informed?std::optional(info_plate(style,*label,text,info->color)):std::nullopt;
              hud->names.push_back(std::move(*label));
              if(line)hud->names.push_back(std::move(*line));
            }
          };
          // Record a drawn actor for the next click's pick (PQ-146): its box
          // placed as drawn, its LOD and the triangles just appended to
          // `buffer` from float `first` on. The local player is not picked, and
          // an actor beyond the far plane is not drawn.
          bool pick_drawn=entity.id()!=world.world.self()&&orbit.project(pos,width,height)[2]<=release.camera.far_plane;
          auto record_pick=[&](unsigned buffer,const std::vector<float>&data,size_t first,size_t stride,const std::array<n3e::V,8>&box,int lod){
            if(!pick_drawn)return;
            pick_volumes.push_back({entity.id(),pos,lod,box,{buffer,first,(data.size()-first)/stride,stride}});
          };
          auto record_mesh_box=[&](unsigned buffer,const std::vector<float>&data,size_t first,size_t stride){
            // A model drawn without a skeleton (the procedural player): the box
            // of its drawn vertices.
            std::vector<n3e::V> points;
            for(size_t i=first;i+2<data.size();i+=stride)points.push_back({data[i],data[i+1],data[i+2]});
            auto b=n3e::targeting::bounds(points,release.pick);
            record_pick(buffer,data,first,stride,n3e::targeting::box_corners(b.lo,b.hi),0);
          };
          if (!entity.npc()) {
            bool ready = false;
            if (release.melee && world.connected && entity.health() &&
                entity.id() == world.world.self())
              for (const auto &candidate : world.world.entities())
                if (candidate.id() == target && candidate.npc() &&
                    candidate.health())
                  ready = true;
            if (player_scenes.empty()) {
              size_t pick_first=verts.size();
              player_mesh(verts, pos, entity.health() != 0,
                          entity.id() == world.world.self() ? heading : 0,
                          ready &&
                              movement_intent[0] * movement_intent[0] +
                                      movement_intent[2] * movement_intent[2] <
                                  .000001f);
              record_mesh_box(0,verts,pick_first,8);
              add_name(0,entity.sitting());
            } else {
              auto &pose = poses[entity.id()];
#if N3E_HARNESS
              int previous_state = pose.initialized ? pose.state : -1;
              auto previous_attack_key=pose.attack_key;
#endif
              auto &combat_pose=combat_poses[entity.id()];
              if(release.combat_animation)combat_pose.update(*release.combat_animation,entity);
              const auto*local=melee_presentation.current(entity);
              std::optional<StrikePresentation> local_view;
              if(local&&release.combat_animation){
                local_view=local->view();local_view->start=now-(SDL_GetTicks()/1000.-local->start);combat_pose.attack=melee_presentation.clip(*release.combat_animation,*local);
                combat_pose.layered=local->moving&&!release.combat_animation->upper_nodes.empty();
              }
              float attack_duration=player_durations[release.combat_animation?combat_pose.attack:2];
              pose.update(
                  pos, entity, now, attack_duration, world.world.tick(),
                  entity.id() == world.world.self() ? &movement_intent
                                                    : nullptr,
                  move_mode, release.locomotion, ready && release.ready_pose,release.rest?player_durations[7]:0,release.rest?player_durations[9]:0,local_view?&*local_view:nullptr);
#if N3E_HARNESS
              if(std::getenv("N3E_TEST_MELEE_SEQUENCE")&&local&&pose.state==2&&previous_attack_key!=pose.attack_key){
                double delay=SDL_GetTicks()/1000.-local->start;
                if(delay>.05||entity.strike_sequence()==local->sequence)throw std::runtime_error("local swing waited for authority");
                std::cout<<"MELEE_PREDICT request="<<local->sequence<<" delay="<<delay<<" server="<<entity.strike_sequence()<<"\n";
              }
              // PQ-420 (D-217): a predicted held shot's pose plays the stretched clip.
              if(local&&pose.state==2&&previous_attack_key!=pose.attack_key&&release.combat_animation&&local->style&&
                 local->style<=release.combat_animation->profiles.size()&&release.combat_animation->profiles[local->style-1].ranged.cast_ms)
                std::cout<<"RANGED_POSE request="<<local->sequence<<" clip="<<int(combat_pose.attack)-10<<" duration="<<attack_duration<<std::endl;
              if(approach_test&&entity.id()==world.world.self()&&pose.state==2&&!approach_pose){
                approach_pose=SDL_GetTicks()/1000.0;
                if(!approach_arrival||!approach_request||approach_pose-approach_arrival>.75)throw std::runtime_error("initial approach attack stalled");
                std::cout<<"APPROACH arrival="<<approach_arrival<<" request="<<approach_request<<" pose="<<approach_pose<<" delay="<<approach_pose-approach_arrival<<"\n";
              }
#endif
              if ((release.movement || release.melee) &&
                  entity.id() == world.world.self())
                pose.heading = heading;
#if N3E_HARNESS
              if ((play_smoke || combat_test || movement_smoke) &&
                  entity.id() == world.world.self() &&
                  pose.state != previous_state)
                std::cout << "POSE state=" << pose.state
                          << " tick=" << world.world.tick()
                          << " heading=" << pose.heading << "\n";
#endif
              if (pose.state == 2 && !combat_pose.layered && entity.id() == world.world.self())
                for (const auto &enemy : world.world.entities())
                  if (enemy.id() == target)
                    pose.heading =
                        std::atan2(pos[0] - enemy.x(), pos[2] - enemy.z());
              // The pick box: the idle pose's, or the final dying pose's once
              // the death clip has played (KO regenerates it at PSA_DEATH).
              auto player_pick_box=[&]{return pose.state==3&&player_dead_box&&now-pose.since>=player_durations[3]?*player_dead_box:*player_box;};
              unsigned clip_index=release.combat_animation?combat_pose.clip(*release.combat_animation,entity,pose.state):pose.state;
              const auto &model = player_scenes[clip_index];
              float t = std::max(0.f, float(now - pose.since));
              t = (pose.state == 2 || pose.state == 3)
                      ? std::min(t, player_durations[pose.state])
                      : std::fmod(t, player_durations[pose.state]);
              auto node_pose = release.animation && (!release.combat_animation||release.combat_animation->upper_nodes.empty())
                  ? animations[entity.id()].update(player_scenes,player_clips.data(),clip_index,pose.attack_key,pose.since,now,false,pose.state)
                  : model.sample(t);
              if(release.combat_animation&&!release.combat_animation->upper_nodes.empty()){
                unsigned base_clip=combat_pose.clip(*release.combat_animation,entity,pose.base_state);
                node_pose=layers[entity.id()].update(animations[entity.id()],player_scenes,player_clips.data(),clip_index,pose.state,pose.attack_key,pose.since,now,base_clip,pose.base_state,pose.base_since,release.combat_animation->upper_nodes,pose.state==2&&combat_pose.layered);
              }
              int cast_animation=-1;  // PQ-317: the skill animation the wearer casts, for a skeletal plug's clip
              if(!entity.cast_skill().empty())if(auto skill=Hotbar::skill(release,entity.cast_skill())){
                cast_animation=int(skill->animation);
                const auto&casting=skill_scenes.at(skill->animation);float duration=0;for(const auto&track:casting.tracks)duration=std::max(duration,track.keys.back().time);
                double elapsed=(double(world.world.tick())-entity.cast_start())*.05+std::max(0.,now-world.received);
                node_pose=casting.sample(float(std::clamp(elapsed/(skill->cast_ms/1000.),0.,1.)*duration));
                for(const auto&recipient:world.world.entities())if(recipient.id()==entity.cast_target()&&recipient.id()!=entity.id())pose.heading=std::atan2(pos[0]-recipient.x(),pos[2]-recipient.z());
              }
              if(entity.id()==world.world.self())self_heading=pose.heading;
              effect_headings[entity.id()]=pose.heading;
              for(unsigned joint=0;joint<model.joints.size();++joint){auto at=model.joint_position(node_pose,joint);float c=std::cos(pose.heading),s=std::sin(pose.heading);
                effect_joints[{entity.id(),int(joint)}]={pos[0]+at[0]*c+at[2]*s,pos[1]+at[1],pos[2]-at[0]*s+at[2]*c};
              }
              if(detail) {
                auto delta=camera_geometry::sub(pos,orbit.eye);
                float distance=std::sqrt(camera_geometry::dot(delta,delta));
                float metric=distance*release.camera.fov/detail->radius;
                int base=n3e::character_lod::level(*detail,metric,0);
                int selected=n3e::character_lod::level(*detail,metric,entity.id()==world.world.self()?0:character_row);
                if(base<0 || selected<0 || distance>release.camera.far_plane+2*detail->radius)continue;
                add_name(hud&&hud->data.nameplates?node_pose[hud->data.nameplates->profiles[0].root].t[1]*model.scale[1]:0,entity.sitting());
                auto append_detail=[&](const n3e::DetailMesh &geometry,std::span<const uint32_t> indices) {
                  auto animated=geometry.scene.skin(node_pose,indices);
                  float c=std::cos(pose.heading),sn=std::sin(pose.heading);
                  for(size_t j=0;j<indices.size();++j){const float *v=&animated[j*8];
                    detail_vertices.insert(detail_vertices.end(),{pos[0]+v[0]*c+v[2]*sn,pos[1]+v[1],pos[2]-v[0]*sn+v[2]*c,
                      v[3]*c+v[5]*sn,v[4],-v[3]*sn+v[5]*c,v[6],v[7],.5f,.5f,
                      native_textures.slots.at(geometry.slots.at(indices[j])),native_textures.slots[0]});
                  }
                };
                size_t pick_first=detail_vertices.size();
                if(!equipment_glow.records.empty())equipment_glow.clock(entity.id(),now);
#if N3E_HARNESS
                if(entity.id()==world.world.self()&&glow_self_first<0)glow_self_first=now;
#endif
                n3e::draw_appearance(*detail,release.appearance,entity.appearance(),selected,
                  [&](const n3e::DetailMesh &geometry,std::span<const uint32_t> indices,uint32_t key){
                    size_t first=detail_vertices.size()/12;
                    append_detail(geometry,indices);
                    // PQ-348 (D-191): the key's N3D3 render state, if it has one.
                    const n3e::AppearanceState*declared=key&&detail->appearances[key-1].state?&*detail->appearances[key-1].state:nullptr;
                    const n3e::AppearanceState*state=part_states?declared:nullptr;
                    if(state)detail_glow.push_back({first,detail_vertices.size()/12-first,std::nullopt,state});
#if N3E_HARNESS
                    if(key&&std::getenv("N3E_TEST_ATTACHMENTS")){
                      GlowBox box{entity.id(),entity.id()==world.world.self(),key,1e9f,1e9f,-1e9f,-1e9f};
                      for(size_t v=first;v<detail_vertices.size()/12;++v){
                        auto at=orbit.project({detail_vertices[v*12],detail_vertices[v*12+1],detail_vertices[v*12+2]},width,height);
                        if(at[2]<=0)continue;
                        box.x0=std::min(box.x0,at[0]);box.y0=std::min(box.y0,at[1]);box.x1=std::max(box.x1,at[0]);box.y1=std::max(box.y1,at[1]);
                      }
                      if(box.x0<=box.x1)attached_part_boxes.push_back(box);
                    }
                    if(part_state_test&&declared){
                      if(part_state_seen.insert({entity.id(),key}).second)
                        std::cout<<"PART_STATE entity="<<entity.id()<<" self="<<(entity.id()==world.world.self())<<" key="<<key
                                 <<" flags="<<declared->flags<<" reference="<<declared->alpha_reference<<" source="<<declared->source
                                 <<" destination="<<declared->destination<<" drawn="<<(state?1:0)
                                 <<" vertices="<<detail_vertices.size()/12-first<<std::endl;
                      if(detail_vertices.size()/12-first<=96){
                        PartCorners c{entity.id(),entity.id()==world.world.self(),key,{}};
                        for(size_t v=first;v<detail_vertices.size()/12;++v){
                          auto at=orbit.project({detail_vertices[v*12],detail_vertices[v*12+1],detail_vertices[v*12+2]},width,height);
                          c.corners.push_back({at[2]>0?at[0]:-1e9f,at[2]>0?at[1]:-1e9f});
                        }
                        part_corners.push_back(std::move(c));
                      }
                    }
#endif
                    if(!key||equipment_glow.records.empty())return;
                    bool started=false;
                    if(auto shade=equipment_glow.shade(entity.id(),key,now,&started)){
                      if(state)detail_glow.back().shade=*shade;
                      else detail_glow.push_back({first,detail_vertices.size()/12-first,*shade});
#if N3E_HARNESS
                      // N3E_TEST_EQUIPMENT_GLOW=1: each glow when first drawn, then
                      // its clock and intensity twice a second.
                      if(std::getenv("N3E_TEST_EQUIPMENT_GLOW")){
                        const auto&g=*equipment_glow.records.at(key);
                        if(started)std::cout<<"EQUIPMENT_GLOW entity="<<entity.id()<<" self="<<(entity.id()==world.world.self())<<" key="<<key
                                            <<" wave="<<(g.wave==n3e::AppearanceGlow::PULSE?"pulse":"steady")<<" modulate="<<g.modulate
                                            <<" color="<<g.color[0]<<","<<g.color[1]<<","<<g.color[2]<<" vertices="<<detail_glow.back().count<<std::endl;
                        GlowBox box{entity.id(),entity.id()==world.world.self(),key,1e9f,1e9f,-1e9f,-1e9f};
                        for(size_t v=first;v<detail_vertices.size()/12;++v){
                          auto at=orbit.project({detail_vertices[v*12],detail_vertices[v*12+1],detail_vertices[v*12+2]},width,height);
                          if(at[2]<=0)continue;
                          box.x0=std::min(box.x0,at[0]);box.y0=std::min(box.y0,at[1]);box.x1=std::max(box.x1,at[0]);box.y1=std::max(box.y1,at[1]);
                        }
                        if(box.x0<=box.x1)glow_boxes.push_back(box);
                        if(equipment_glow.sample(entity.id(),key,now,.5))
                          std::cout<<"EQUIPMENT_GLOW_SAMPLE entity="<<entity.id()<<" key="<<key<<" t="<<now-equipment_glow.clocks.at(entity.id()).first
                                   <<" intensity="<<shade->intensity<<std::endl;
                      }
#else
                      (void)started;
#endif
                    }
                  });
                if(!appearance_effects.models.empty()){
                  size_t first_mesh=appearance_meshes.size();
                  auto started=appearance_effects.draw(entity.id(),release.appearance,entity.appearance(),node_pose,pos,pose.heading,
                                                       SDL_GetTicks()/1000.,orbit.eye,appearance_meshes,appearance_tails);
#if N3E_HARNESS
                  // N3E_TEST_APPEARANCE_EFFECTS=1: each effect when first drawn,
                  // with its first copy's centre and its trail colour.
                  if(std::getenv("N3E_TEST_APPEARANCE_EFFECTS"))for(auto key:started){
                    const auto&m=appearance_effects.models.at(key);n3e::V centre{};size_t n=0;
                    size_t floats=m.data->copies.empty()?0:m.data->copies[0].vertices.size()*9;
                    for(size_t i=first_mesh;i<appearance_meshes.size()&&n==0&&floats;++i)if(appearance_meshes[i].vertices.size()==floats){
                      const auto&v=appearance_meshes[i].vertices;n=v.size()/9;for(size_t j=0;j<v.size();j+=9)for(int k=0;k<3;++k)centre[k]+=v[j+k]/n;}
                    std::cout<<"APPEARANCE_EFFECT entity="<<entity.id()<<" self="<<(entity.id()==world.world.self())<<" key="<<key
                             <<" copies="<<m.data->copies.size()<<" vertices="<<n<<" tails="<<m.data->tails
                             <<" trace="<<std::hex<<m.data->trace_color<<std::dec<<" x="<<centre[0]<<" y="<<centre[1]<<" z="<<centre[2]
                             <<" body_x="<<pos[0]<<" body_y="<<pos[1]<<" body_z="<<pos[2]<<std::endl;
                  }
#else
                  (void)first_mesh;(void)started;
#endif
                }
                // Body parts only: KO's per-mesh test walks the character's
                // parts (0041c7d0), not its plugs (the attachments below).
                record_pick(2,detail_vertices,pick_first,12,n3e::targeting::place(player_pick_box(),pos,pose.heading),selected);
                auto [it,inserted]=attachment_states.try_emplace(entity.id());
                if(inserted)it->second=n3e::character_lod::initial(*detail);
                for(size_t a=0;a<it->second.size();++a){auto &state=it->second[a];n3e::character_lod::update(state,metric);
                  append_detail(detail->attachments[a].mesh,std::span(state.indices).first(state.part.progressive.indices));}
                // PQ-328 (2233 0056a710, 00569590): each attached character
                // on its wearer joint, its clip from the wearer's state, its
                // shade from the wearer's one clock; the optional ones only
                // with Option.ini [Effect] Wing on (00568f30).
                if(!attached.empty()){
                  auto entries=attached.resolve(entity.appearance());
                  auto shades=attached.advance(entity.id(),entries,now);
                  for(size_t k=0;k<entries.size();++k){
                    const size_t e=entries[k];const auto&entry=release.attachments->entries[e];
                    if((entry.flags&n3e::Attachment::OPTIONAL)&&!client_options.wing)continue;
                    const auto&scenes=attachment_scenes[e];
                    auto&animation=attached_animations[{entity.id(),e}];
                    // PQ-317 (D-187): a skeletal plug plays its own clock with the
                    // slot its clip map names for the wearer's drawn clip, and
                    // sits at the joint times its placement (2233 00434980:
                    // plug matrix x joint x the inner character).
                    const bool plug=entry.flags&n3e::Attachment::PLUG;
                    float plug_time=-1;
                    if(plug){
#if N3E_HARNESS
                      // PQ-347: the wearer's drawn clip, on each change: its
                      // combat-animation clip (or -1), pose state and cast.
                      if(std::getenv("N3E_TEST_ATTACHMENTS")){
                        static std::map<std::pair<uint64_t,size_t>,std::pair<int,int>> wearer_shown;
                        const std::pair<int,int> drawn{int(clip_index),cast_animation};
                        if(auto[it,made]=wearer_shown.try_emplace({entity.id(),e},drawn);made||it->second!=drawn){it->second=drawn;
                          std::cout<<"WEARER_CLIP entity="<<entity.id()<<" self="<<(entity.id()==world.world.self())<<" entry="<<e
                                   <<" combat="<<(clip_index>=combat_base?int(clip_index-combat_base):-1)<<" state="<<clip_index
                                   <<" cast="<<cast_animation<<" style="<<entity.combat_style()<<" strike_style="<<entity.strike_style()
                                   <<std::endl;}
                      }
#endif
                      auto&state=attached_plugs[{entity.id(),e}];
                      const auto[kind,id]=cast_animation>=0?std::pair{n3e::PlugClip::SKILL,uint32_t(cast_animation)}
                        :clip_index>=combat_base?std::pair{n3e::PlugClip::COMBAT,uint32_t(clip_index-combat_base)}
                        :std::pair{n3e::PlugClip::STATE,uint32_t(clip_index)};
                      state=n3e::AttachedCharacters::plug_clip(entry,kind,id,state);
                      animation.update(scenes,entry.clips.data(),state.slot,0,now,now,false,state.once?AnimationPlayer::HOLD:0);
                      animation.evaluate(scenes,entry.clips.data(),now,&plug_time);
                    }else animation.update(scenes,entry.clips.data(),
                      n3e::AttachedCharacters::clip_state(pose.state),pose.attack_key,pose.since,now);
                    const auto&apose=animation.current;
                    auto mesh=scenes[0].skin(apose);mesh.resize(scenes[0].indices.size()*8); // drop the marker vertices
#if N3E_HARNESS
                    n3e::V model_centre{},model_low{1e9f,1e9f,1e9f},model_high{-1e9f,-1e9f,-1e9f};
                    for(size_t v=0;v<mesh.size();v+=8)for(int a=0;a<3;++a){model_centre[a]+=mesh[v+a]/float(mesh.size()/8);
                      model_low[a]=std::min(model_low[a],mesh[v+a]);model_high[a]=std::max(model_high[a],mesh[v+a]);}
#endif
                    auto joint=model.joint_matrix(node_pose,entry.joint);
                    if(plug)joint=n3e::multiply(joint,n3e::placement_matrix(entry.placement));
                    n3e::transform_skinned(mesh,joint,entry.scale);
                    float c=std::cos(pose.heading),sn=std::sin(pose.heading);
                    size_t first=attached_vertices.size()/8;
                    for(size_t j=0;j<mesh.size();j+=8){const float*v=&mesh[j];
                      attached_vertices.insert(attached_vertices.end(),{pos[0]+v[0]*c+v[2]*sn,pos[1]+v[1],pos[2]-v[0]*sn+v[2]*c,
                        v[3]*c+v[5]*sn,v[4],-v[3]*sn+v[5]*c,v[6],v[7]});}
                    // PQ-337 (2233 0056ea30 -> 0042de90, then 00430f40 from
                    // 00434980): a skeletal plug hands its key's equipment glow
                    // to every part of its inner character, so the whole model
                    // takes the key's N3E3 shade on the wearer's glow clock; the
                    // CPlayerWing pulse above stays out of it.
                    auto shade=shades[k];size_t lit=entry.lit;
                    if(plug&&!equipment_glow.records.empty()){
                      bool glow_started=false;
                      if(auto g=equipment_glow.shade(entity.id(),entry.key,now,&glow_started)){
                        shade.emissive=g->emissive;shade.modulate=g->modulate;shade.intensity=g->intensity;
                        lit=mesh.size()/8;
#if N3E_HARNESS
                        // N3E_TEST_EQUIPMENT_GLOW=1: each plug glow when first drawn,
                        // its intensity twice a second, and its screen box for the
                        // glow captures.
                        if(std::getenv("N3E_TEST_EQUIPMENT_GLOW")){
                          const auto&rec=*equipment_glow.records.at(entry.key);
                          if(glow_started)std::cout<<"PLUG_GLOW entity="<<entity.id()<<" self="<<(entity.id()==world.world.self())<<" key="<<entry.key
                                                   <<" entry="<<e<<" wave="<<(rec.wave==n3e::AppearanceGlow::PULSE?"pulse":"steady")<<" modulate="<<rec.modulate
                                                   <<" color="<<rec.color[0]<<","<<rec.color[1]<<","<<rec.color[2]<<" vertices="<<lit<<std::endl;
                          GlowBox box{entity.id(),entity.id()==world.world.self(),entry.key,1e9f,1e9f,-1e9f,-1e9f};
                          for(size_t v=first;v<attached_vertices.size()/8;++v){
                            auto at=orbit.project({attached_vertices[v*8],attached_vertices[v*8+1],attached_vertices[v*8+2]},width,height);
                            if(at[2]<=0)continue;
                            box.x0=std::min(box.x0,at[0]);box.y0=std::min(box.y0,at[1]);box.x1=std::max(box.x1,at[0]);box.y1=std::max(box.y1,at[1]);
                          }
                          if(box.x0<=box.x1)glow_boxes.push_back(box);
                          if(equipment_glow.sample(entity.id(),entry.key,now,.5))
                            std::cout<<"PLUG_GLOW_SAMPLE entity="<<entity.id()<<" key="<<entry.key<<" t="<<now-equipment_glow.clocks.at(entity.id()).first
                                     <<" intensity="<<g->intensity<<std::endl;
                        }
#else
                        (void)glow_started;
#endif
                      }
                    }
                    attached_draws.push_back({e,first,mesh.size()/8,lit,shade});
                    [[maybe_unused]] const bool started=attached.draw(entity.id(),e);
#if N3E_HARNESS
                    // N3E_TEST_ATTACHMENTS=1: each attachment when first drawn,
                    // then twice a second its clock, clip and placement: the
                    // wearer joint's world position beside the wearer's.
                    if(std::getenv("N3E_TEST_ATTACHMENTS")){
                      const auto&clock=attached.clocks.at(entity.id());
                      AttachedBox box{entity.id(),entity.id()==world.world.self(),e,1e9f,1e9f,-1e9f,-1e9f};
                      for(size_t v=first;v<attached_vertices.size()/8;++v){
                        auto q=orbit.project({attached_vertices[v*8],attached_vertices[v*8+1],attached_vertices[v*8+2]},width,height);
                        if(q[2]<=0)continue;
                        box.x0=std::min(box.x0,q[0]);box.y0=std::min(box.y0,q[1]);box.x1=std::max(box.x1,q[0]);box.y1=std::max(box.y1,q[1]);
                      }
                      if(box.x0<=box.x1)attached_boxes.push_back(box);
                      n3e::V at{pos[0]+joint[12]*c+joint[14]*sn,pos[1]+joint[13],pos[2]-joint[12]*sn+joint[14]*c};
                      static std::map<std::pair<uint64_t,size_t>,double> sampled;
                      if(started){sampled.erase({entity.id(),e});
                        std::cout<<"ATTACHMENT entity="<<entity.id()<<" self="<<(entity.id()==world.world.self())<<" key="<<entry.key<<" entry="<<e
                                 <<" group="<<entry.group<<" joint="<<entry.joint<<" vertices="<<mesh.size()/8<<" lit="<<entry.lit
                                 <<" modulate="<<entry.modulate<<" emissive="<<((entry.flags&n3e::Attachment::EMISSIVE)?1:0)<<std::endl;}
                      // The clip the attachment's own player is playing, and the
                      // centre of the vertices placed for the draw.
                      static std::map<std::pair<uint64_t,size_t>,int> clip_shown;
                      const int clip=animation.state;
                      n3e::V placed{};const size_t placed_count=attached_vertices.size()/8-first;
                      for(size_t v=first;v<attached_vertices.size()/8;++v)for(int a=0;a<3;++a)placed[a]+=attached_vertices[v*8+a]/float(placed_count);
                      if(auto[it,made]=clip_shown.try_emplace({entity.id(),e},clip);made||it->second!=clip){it->second=clip;
                        std::cout<<"ATTACHMENT_CLIP entity="<<entity.id()<<" entry="<<e<<" clip="<<clip<<std::endl;}
                      auto&last=sampled.try_emplace({entity.id(),e},-1e9).first->second;
                      if(now-last>=.5){last=now;
                        std::cout<<"ATTACHMENT_SAMPLE entity="<<entity.id()<<" entry="<<e<<" t="<<clock.t<<" total="<<clock.total
                                 <<" intensity="<<shades[k].intensity<<" clip="<<clip
                                 <<" joint="<<at[0]<<","<<at[1]<<","<<at[2]<<" placed="<<placed[0]<<","<<placed[1]<<","<<placed[2]
                                 <<" wearer="<<pos[0]<<","<<pos[1]<<","<<pos[2]<<std::endl;
                        // PQ-317: a skeletal plug's clip time, the centre and box of
                        // its skinned model before placement, and the wearer joint's
                        // frame without the placement (the wearer's heading, then
                        // the joint matrix's 12 rotation and translation terms).
                        if(plug){const auto bare=model.joint_matrix(node_pose,entry.joint);
                          std::cout<<"PLUG_SAMPLE entity="<<entity.id()<<" entry="<<e<<" slot="<<clip<<" time="<<plug_time
                                   <<" model="<<model_centre[0]<<","<<model_centre[1]<<","<<model_centre[2]
                                   <<" bounds="<<model_low[0]<<","<<model_low[1]<<","<<model_low[2]<<","<<model_high[0]<<","<<model_high[1]<<","<<model_high[2]
                                   <<" placed="<<placed[0]<<","<<placed[1]<<","<<placed[2]<<" heading="<<pose.heading<<" joint_matrix=";
                          for(int col=0;col<4;++col)for(int row=0;row<3;++row)std::cout<<bare[col*4+row]<<(col==3&&row==2?"":",");
                          std::cout<<" wearer="<<pos[0]<<","<<pos[1]<<","<<pos[2]<<std::endl;}}
                    }
#endif
                  }
#if N3E_HARNESS
                  if(entity.id()==world.world.self()&&attached.clocks.contains(entity.id()))attachment_self_drawn=attached.clocks.at(entity.id()).drawn;
#endif
                }
                continue;
              }
              add_name(hud&&hud->data.nameplates?node_pose[hud->data.nameplates->profiles[0].root].t[1]*model.scale[1]:0,entity.sitting());
              auto animated = model.skin(node_pose);
              float c = std::cos(pose.heading), s = std::sin(pose.heading);
              size_t pick_first=player_vertices.size();
              for (size_t j = 0; j < model.indices.size(); ++j) {
                const auto *v = &animated[j * 8];
                player_vertices.insert(
                    player_vertices.end(),
                    {pos[0] + v[0] * c + v[2] * s, pos[1] + v[1],
                     pos[2] - v[0] * s + v[2] * c, v[3] * c + v[5] * s, v[4],
                     -v[3] * s + v[5] * c, v[6], v[7]});
              }
              record_pick(1,player_vertices,pick_first,8,n3e::targeting::place(player_pick_box(),pos,pose.heading),0);
            }
            continue;
          }
          if (release.animation && release.animation->size() >= 11) {
            auto &pose = poses[entity.id()];
            // PQ-253: the NPC's looks model and clip timing, else the
            // package's single NPC set.
            const auto &scenes = looks ? looks_scenes[*looks] : npc_scenes;
            const auto *clips = looks ? release.npc_looks[*looks].clips.data()
                                      : release.animation->data() + (release.rest?10:7);
            pose.update(pos, entity, now, clips[2].duration + clips[2].blend,
                        world.world.tick());
            // A looks model keeps its atlas and mesh in its first scene.
            const auto &model = looks ? scenes[0] : scenes[pose.state];
            bool final_pose=pose.state==3&&now-pose.since>=clips[3].duration+clips[3].blend;
            // KO's state 5: the manager tick moves the NPC to the corpse map,
            // out of the actor pick and B (00470b25, PQ-199).
            if(final_pose)frame_corpses.insert(entity.id());
            npc_label(final_pose);
            add_name(0,false);
            auto node_pose=animations[entity.id()].update(scenes, clips, pose.state, pose.strike, pose.since, now);
            auto animated = model.skin(node_pose);
            // Joints, vertices and pick boxes scale about the NPC's position
            // (PQ-272); a uniform scale leaves the normals as they are.
            const float k = npc_scale;
            for(unsigned joint=0;joint<model.joints.size();++joint){auto at=model.joint_position(node_pose,joint);float c=std::cos(pose.heading),s=std::sin(pose.heading);
              effect_joints[{entity.id(),int(joint)}]={pos[0]+(at[0]*c+at[2]*s)*k,pos[1]+at[1]*k,pos[2]+(-at[0]*s+at[2]*c)*k};
            }
            float c = std::cos(pose.heading), s = std::sin(pose.heading);
            auto &out = looks ? looks_batches[*looks] : verts;
            size_t pick_first=out.size();
            for (size_t j = 0; j < model.indices.size(); ++j) {
              const auto *v = &animated[j * 8];
              out.insert(out.end(),
                           {pos[0] + (v[0] * c + v[2] * s) * k, pos[1] + v[1] * k,
                            pos[2] + (-v[0] * s + v[2] * c) * k, v[3] * c + v[5] * s,
                            v[4], -v[3] * s + v[5] * c, v[6], v[7]});
            }
            const auto &box = looks ? (final_pose ? looks_boxes[*looks].second : looks_boxes[*looks].first)
                                    : (final_pose ? *npc_dead_box : *npc_box);
            size_t volumes = pick_volumes.size();
            auto placed = n3e::targeting::place(box, pos, pose.heading, k);
#if N3E_HARNESS
            // PQ-272 (N3E_TEST_NPC_LOOKS=1): once per NPC, its drawn scale and
            // the height of the pick box it was placed with (NPC_LABEL reports
            // the label from where it is drawn).
            if (looks && std::getenv("N3E_TEST_NPC_LOOKS")) {
              static std::set<uint64_t> scale_reported;
              if (scale_reported.insert(entity.id()).second) {
                float lo = placed[0][1], hi = placed[0][1];
                for (const auto &corner : placed) lo = std::min(lo, corner[1]), hi = std::max(hi, corner[1]);
                std::cout << "NPC_SCALE entity=" << entity.id() << " scale=" << k << " box_height=" << hi - lo
                          << "\n";
              }
            }
            // PQ-288 (N3E_TEST_NPC_LOOKS=1): once per NPC drawn from the
            // package's one NPC set, the set's instance scale (its drawn size
            // when no template scale reaches it), the wire scale and the placed
            // box's height.
            if (!looks && std::getenv("N3E_TEST_NPC_LOOKS")) {
              static std::set<uint64_t> set_reported;
              if (set_reported.insert(entity.id()).second) {
                float lo = placed[0][1], hi = placed[0][1];
                for (const auto &corner : placed) lo = std::min(lo, corner[1]), hi = std::max(hi, corner[1]);
                std::cout << "NPC_SET_SCALE entity=" << entity.id() << " scale=" << k << " model_scale=" << model.scale[1]
                          << " box_height=" << hi - lo << "\n";
              }
            }
#endif
            record_pick(looks ? 3 : 0, out, pick_first, 8, placed, 0);
            if (looks && pick_volumes.size() > volumes) looks_picks.emplace_back(volumes, *looks);
          } else {
            npc_label(!entity.health()); // no death clip: final once dead
            if(!entity.health())frame_corpses.insert(entity.id());
            add_name(0,false);
            size_t pick_first=verts.size();
            for (size_t j = 0; j < scene.indices.size(); ++j) {
              for (int k = 0; k < 8; ++k) {
                float v = mesh[j * 8 + k];
                if (k < 3)
                  v = v * (entity.health() ? 1.f : .3f) + pos[k];
                if (k == 1 && entity.strike_tick() &&
                    world.world.tick() - entity.strike_tick() < 4)
                  v += .12f;
                verts.push_back(v);
              }
            }
            // The stand-in model is drawn unturned, at 0.3 scale when slain.
            record_pick(0,verts,pick_first,8,n3e::targeting::place(legacy_box,pos,0,entity.health()?1.f:.3f),0);
          }
        }
      }
      std::erase_if(poses, [&](const auto &pose) {
        return std::none_of(
            world.world.entities().begin(), world.world.entities().end(),
            [&](const auto &e) { return e.id() == pose.first; });
      });
      std::erase_if(animations,
                    [&](const auto &a) { return !poses.contains(a.first); });
      std::erase_if(layers,[&](const auto &a){return !poses.contains(a.first);});
      std::erase_if(entity_looks,[&](const auto &a){return !poses.contains(a.first);});
      std::erase_if(combat_poses,[&](const auto &a){return !poses.contains(a.first);});
      std::erase_if(attachment_states,
                    [&](const auto &a) { return !poses.contains(a.first); });
      // PQ-211: an effect not drawn this frame ends (the actor left the view,
      // or the key left its equipment); a later draw starts it afresh.
      for([[maybe_unused]] const auto&[actor,key]:appearance_effects.retire()){
#if N3E_HARNESS
        if(std::getenv("N3E_TEST_APPEARANCE_EFFECTS"))std::cout<<"APPEARANCE_EFFECT_END entity="<<actor<<" key="<<key<<std::endl;
#endif
      }
      // PQ-328: an attachment not drawn this frame ends; a wearer not drawn
      // loses its clock and its attachments' animation.
      for([[maybe_unused]] const auto&[wearer,entry]:attached.retire()){
        attached_animations.erase({wearer,entry});
        attached_plugs.erase({wearer,entry});
#if N3E_HARNESS
        if(std::getenv("N3E_TEST_ATTACHMENTS"))std::cout<<"ATTACHMENT_END entity="<<wearer<<" entry="<<entry<<std::endl;
#endif
      }
      // PQ-315: a glow not drawn this frame ends; an actor not drawn loses its clock.
      for([[maybe_unused]] const auto&[actor,key]:equipment_glow.retire()){
#if N3E_HARNESS
        if(std::getenv("N3E_TEST_EQUIPMENT_GLOW"))std::cout<<"EQUIPMENT_GLOW_END entity="<<actor<<" key="<<key<<std::endl;
#endif
      }
      if(!release.editing.empty()) {
        std::vector<float> values;for(const auto&p:release.editing)values.push_back(p.initial);
        const auto &live=world.world.revision();
        if(live.base()==release.hash&&live.values_size()==int(values.size()))for(size_t i=0;i<values.size();++i)values[i]=live.values(i).value();
#if TOOLS
        if(editor.preview)values=editor.values();
#endif
        auto val=[&](unsigned kind,unsigned target,float fallback){for(size_t i=0;i<values.size();++i)if(release.editing[i].kind==kind&&release.editing[i].target==target)return values[i];return fallback;};
        light=val(0,0,.85f);
        auto prop=scene.skin(scene.sample(0));
        for(const auto &p:release.editing)if(p.kind==1){float x=val(1,p.target,0),y=val(2,p.target,0),z=val(3,p.target,0),yaw=val(4,p.target,0),scale=val(5,p.target,1),c=std::cos(yaw),s=std::sin(yaw);
          for(size_t j=0;j<scene.indices.size();++j){auto*v=&prop[j*8];verts.insert(verts.end(),{x+scale*(c*v[0]+s*v[2]),y+scale*v[1],z+scale*(-s*v[0]+c*v[2]),c*v[3]+s*v[5],v[4],-s*v[3]+c*v[5],v[6],v[7]});}}
      }
      std::vector<float> loot_vertices;
#if N3E_HARNESS
      if(expiry_test&&!loot_seen&&world.loot.drops_size()){
        loot_seen=SDL_GetTicks()/1000.0;const auto&d=world.loot.drops(0);
        std::cout<<"EXPIRING_LOOT "<<d.operation()<<" "<<d.encounter()<<" "<<d.item()<<" "<<d.quantity()<<"\n";
      }
#endif
      if(network&&!loot_mesh.empty())for(const auto&[id,position]:loot_instances(world)){
        auto q=orbit.project(position,width,height);if(q[2]<-2||q[2]>release.camera.far_plane+2)continue;
        for(size_t i=0;i<loot_mesh.size();i+=8){
          loot_vertices.insert(loot_vertices.end(),loot_mesh.begin()+i,loot_mesh.begin()+i+8);
          auto at=loot_vertices.size()-8;for(unsigned k=0;k<3;++k)loot_vertices[at+k]+=position[k];
        }
      }
      profile_mark(2);
      int world_vertices = verts.size() / 8;
      verts.insert(verts.end(), player_vertices.begin(), player_vertices.end());
      verts.insert(verts.end(),loot_vertices.begin(),loot_vertices.end());
      // The looks batches, merged after the loot (PQ-253).
      std::vector<float> looks_vertices;
      std::vector<size_t> looks_base(looks_batches.size());
      for (size_t i = 0; i < looks_batches.size(); ++i) {
        looks_base[i] = looks_vertices.size();
        looks_vertices.insert(looks_vertices.end(), looks_batches[i].begin(), looks_batches[i].end());
      }
      for (const auto &[volume, i] : looks_picks) pick_volumes[volume].mesh.first += looks_base[i];
      const size_t looks_first = verts.size() / 8;
      verts.insert(verts.end(), looks_vertices.begin(), looks_vertices.end());
      const size_t attached_first = verts.size() / 8;
      verts.insert(verts.end(), attached_vertices.begin(), attached_vertices.end());
      glBindVertexArray(vao);
      glBindBuffer(GL_ARRAY_BUFFER, vbo);
      glBufferData(GL_ARRAY_BUFFER, verts.size() * 4, verts.data(),
                   GL_DYNAMIC_DRAW);
      glUseProgram(p);
      glUniform1f(glGetUniformLocation(p, "gui"), 0);
      glUniform2f(glGetUniformLocation(p, "camera"), cx, cy);
      glUniform1f(glGetUniformLocation(p, "offset"), offset);
      glUniform1f(glGetUniformLocation(p, "light"), light);
      glUniform1f(glGetUniformLocation(p, "aspect"), (float)width / height);
#if N3E_HARNESS
      // N3E_TEST_WORLD_VIEW="eye target": a fixed diagnostic camera for world captures.
      bool diagnostic_view=false;
      if(smoke && !network && world_asset && !capture_path.empty()) {
        if(const char *view=std::getenv("N3E_TEST_WORLD_VIEW")) {
          std::istringstream input(view); n3e::V target;
          for(auto *v:{&orbit.eye,&target}) for(float &x:*v)
            if(!(input>>x) || !std::isfinite(x) || std::abs(x)>10000) throw std::runtime_error("world test view");
          auto delta=camera_geometry::sub(orbit.eye,target);
          if(camera_geometry::dot(delta,delta)<.001f || std::hypot(delta[0],delta[2])<.001f)
            throw std::runtime_error("world test view direction");
          // N3E_TEST_WORLD_PATH="dx dy dz frames": the camera moves by that
          // offset over that many frames, then holds (PQ-232).
          if(const char *path=std::getenv("N3E_TEST_WORLD_PATH")) {
            std::istringstream steps(path); n3e::V move; float frames=0;
            for(float &x:move) if(!(steps>>x) || !std::isfinite(x) || std::abs(x)>10000) throw std::runtime_error("world test path");
            if(!(steps>>frames) || frames<1 || frames>100000) throw std::runtime_error("world test path frames");
            const float t=std::min(float(frame),frames)/frames;
            for(int a=0;a<3;++a) { orbit.eye[a]+=move[a]*t; target[a]+=move[a]*t; }
          }
          orbit.back=camera_geometry::unit(delta);
          orbit.right=camera_geometry::unit(camera_geometry::cross({0,1,0},orbit.back));
          orbit.up=camera_geometry::cross(orbit.back,orbit.right);
          diagnostic_view=true;
          world_vertices=0;
        }
      }
#else
      constexpr bool diagnostic_view=false;
#endif
      glUniform1f(glGetUniformLocation(p, "gameplay"), network || diagnostic_view ? 1.f : 0.f);

      auto uniform = [&](const char *name, n3e::V v) {
        glUniform3f(glGetUniformLocation(p, name), v[0], v[1], v[2]);
      };
      glUniform1f(glGetUniformLocation(p,"farplane"), detail ? release.camera.far_plane : (release.exploration ? release.exploration->fog_end : 100.f));
      glUniform2f(glGetUniformLocation(p,"foglimits"), release.exploration ? release.exploration->fog_start : 0,
                  release.exploration ? release.exploration->fog_end : 0);
      if (release.exploration) uniform("fogcolor",release.exploration->fog_color);
      glUniform1f(glGetUniformLocation(p,"nearplane"),release.camera.near_plane);
      glUniform1f(glGetUniformLocation(p,"projection"),1.f/std::tan(release.camera.fov/2));
      uniform("eye", orbit.eye);
      uniform("rightward", orbit.right);
      uniform("upward", orbit.up);
      uniform("backward", orbit.back);
      auto world_uniform = glGetUniformLocation(p, "world");
      if (world_stream && width > 0 && height > 0) {
        // Bounded per frame: evictions, at most STREAM_UPLOADS finished chunks
        // uploaded, new requests to the worker. A chunk that failed validation
        // throws here, before it is uploaded or drawn.
        const float far = detail ? release.camera.far_plane : release.exploration->fog_end;
        auto step = world_stream->update(orbit.eye, n3e::view_reach(far, float(width) / height, release.camera.fov));
        for (size_t c : step.evict) free_chunk(c);
        for (auto &u : step.upload) {
          world_asset->chunks[u.index] = std::move(u.chunk);
          upload_chunk(u.index);
        }
        // Once per run: chunks in reach beyond the limits are not drawn.
        if (!world_limited_noticed && world_stream->stats().limited) {
          world_limited_noticed = true;
          std::cerr << "world streaming: " << world_stream->stats().limited
                    << " chunks in reach exceed the client limits (" << n3e::STREAM_CHUNKS << " chunks, "
                    << (n3e::STREAM_BYTES >> 20) << " MiB); the farthest are not drawn\n";
        }
      }
      world_alpha.clear();
      // D-212: one frame time per frame for every texture sequence, bounded
      // as 1298 bounds its own (1/30 s on the first frame, as 1298 starts).
      float sequence_dt;
      {
        const uint64_t now_ns=SDL_GetTicksNS();
        sequence_dt=n3e::world_lod::sequence_seconds(sequence_last_ns?double(now_ns-sequence_last_ns)/1e9:0);
        sequence_last_ns=now_ns;
#if N3E_HARNESS
        if(sequence_fixed)sequence_dt=std::stof(sequence_fixed);
#endif
      }
      if (world_asset) {
        glUniform1f(world_uniform, 1);
        glUniform4f(glGetUniformLocation(p, "partstate"), 0, 0, 0, 0);
        glUniform4f(glGetUniformLocation(p, "grid"), float(world_asset->width),
                    float(world_asset->height), float(world_asset->cell),
                    float(world_asset->pad));
        glActiveTexture(GL_TEXTURE1);
        glBindTexture(GL_TEXTURE_2D_ARRAY, world_texture);
        glActiveTexture(GL_TEXTURE0);
        if(release.world_chunked)world_banks.bind();
        else if(detail)native_textures.bind();
        glUniform1f(glGetUniformLocation(p,"native_detail"),detail||release.world_chunked?1:0);
        if (world_asset->chunks.size() == 1 && world_asset->chunks[0].parts.empty()) {
          // N3W1 without a LOD file: every index in one draw.
          glBindVertexArray(world_buffers[0].vao);
          glDrawElements(GL_TRIANGLES, GLsizei(world_asset->chunks[0].indices.size()), GL_UNSIGNED_INT, nullptr);
        } else {
#if N3E_HARNESS
          // Matched-camera world captures: the same frame drawn twice.
          const bool compare_sampling = std::getenv("N3E_TEST_WORLD_SAMPLING") &&
              !capture_path.empty() && !world_sampling_captured && entry == 4;
          // A streamed world is compared once every chunk in reach is resident.
          const bool compare_lod = std::getenv("N3E_TEST_WORLD_LOD") &&
              !capture_path.empty() && !world_sampling_captured && frame >= 40 + world_path_frames && (entry == 4 || diagnostic_view) &&
              (!world_stream || world_stream->settled());
          // PQ-387: the same frame without (pass 0) and with (pass 1) the N3WO
          // maps; N3E_TEST_WORLD_OVERLAY_OFF never draws them (a negative control).
          const bool compare_overlay = std::getenv("N3E_TEST_WORLD_OVERLAY") && !compare_lod &&
              !capture_path.empty() && !world_sampling_captured && frame >= 40 + world_path_frames && (entry == 4 || diagnostic_view) &&
              (!world_stream || world_stream->settled());
          const bool overlay_off = std::getenv("N3E_TEST_WORLD_OVERLAY_OFF") != nullptr;
#else
          constexpr bool compare_sampling = false, compare_lod = false, compare_overlay = false, overlay_off = false;
#endif
          // Render the same world/camera twice without advancing simulation.
          const auto saved_world = compare_lod || compare_overlay ? std::optional<n3e::WorldMesh>(*world_asset) : std::nullopt;
          if (terrain_overlay) terrain_overlay->follow(world_asset->terrain, orbit.eye);
          // 1298 draws the maps blended over equal depth (005a2d3b-005a2d5f;
          // no ZFUNC write, so Direct3D's LESSEQUAL); the world pass's blend
          // and depth state are put back after each patch's maps.
          GLint saved_depth_func = GL_LESS, saved_blend[4] = {GL_ONE, GL_ZERO, GL_ONE, GL_ZERO};
          const GLboolean saved_blending = glIsEnabled(GL_BLEND);
          if (terrain_overlay) {
            glGetIntegerv(GL_DEPTH_FUNC, &saved_depth_func);
            glGetIntegerv(GL_BLEND_SRC_RGB, &saved_blend[0]); glGetIntegerv(GL_BLEND_DST_RGB, &saved_blend[1]);
            glGetIntegerv(GL_BLEND_SRC_ALPHA, &saved_blend[2]); glGetIntegerv(GL_BLEND_DST_ALPHA, &saved_blend[3]);
            const auto &o = terrain_overlay->overlay;
            const float tile = world_asset->terrain.patch_size / float(o.patch_tiles);
            glUniform4f(glGetUniformLocation(p, "overlaygrid"), world_asset->terrain.origin[0], world_asset->terrain.origin[2],
                        tile, float(o.patch_tiles));
            glUniform4f(glGetUniformLocation(p, "overlaycell"), float(o.block_tiles), float(o.cell), float(o.inset), float(o.side));
            terrain_overlay->bind();
          }
          const GLint overlay_uniform = glGetUniformLocation(p, "overlay");
          const GLint overlay_patch_uniform = glGetUniformLocation(p, "overlaypatch");
          const GLint overlay_layers_uniform = glGetUniformLocation(p, "overlaylayers");
          const int passes = (compare_sampling || compare_lod || compare_overlay) ? 2 : 1;
          const GLint sequence_uniform = glGetUniformLocation(p, "sequence");
          for (int pass=0; pass<passes; ++pass) {
            uint64_t overlay_patches = 0, overlay_withheld = 0;
            if (compare_overlay && pass == 1) {
              *world_asset = *saved_world;
              for (size_t c = 0; c < world_buffers.size(); ++c) {
                if (!world_asset->chunks[c].resident) continue;
                glBindVertexArray(world_buffers[c].vao);
                const auto &indices = world_asset->chunks[c].indices;
                glBufferSubData(GL_ELEMENT_ARRAY_BUFFER, 0, indices.size()*4, indices.data());
              }
            }
            if (compare_lod && pass == 1) {
              *world_asset = *saved_world;
              for (size_t c = 0; c < world_buffers.size(); ++c) {
                if (!world_asset->chunks[c].resident) continue;
                glBindVertexArray(world_buffers[c].vao);
                const auto &indices = world_asset->chunks[c].indices;
                glBufferSubData(GL_ELEMENT_ARRAY_BUFFER, 0, indices.size()*4, indices.data());
              }
            }
            if ((compare_sampling || compare_lod || compare_overlay) && pass == 1) glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
            uint64_t drawn=0, reduced=0, visible=0, chunks_drawn=0, missing=0;
            world_alpha.clear();  // the last pass's parts are the frame's
            const GLint world_part_state=glGetUniformLocation(p,"partstate");
            auto sphere_visible=[&](const n3e::V &center,float radius,bool radial) {
              return n3e::world_lod::sphere_visible(center,radius,orbit.eye,orbit.right,orbit.up,orbit.back,
                  release.camera.near_plane,detail ? release.camera.far_plane : release.exploration->fog_end,float(width)/height,std::tan(release.camera.fov/2),radial);
            };
            for (size_t c = 0; c < world_asset->chunks.size(); ++c) {
            auto &chunk = world_asset->chunks[c];
            auto box_visible=[&] {
              return n3e::world_lod::box_visible(chunk.lo,chunk.hi,orbit.eye,orbit.right,orbit.up,orbit.back,
                  release.camera.near_plane,detail ? release.camera.far_plane : release.exploration->fog_end,float(width)/height,std::tan(release.camera.fov/2));
            };
            // A streamed chunk not yet resident is not drawn; one the view
            // could show is counted (PQ-232).
            if(!chunk.resident) { missing+=box_visible(); continue; }
            // The chunk's box covers every part sphere it holds, so a box
            // outside the view culls only what its parts' tests would. The
            // matched-camera full pass skips it, so the two passes show that.
            if(chunk.bounded && !(compare_lod && pass==0) && !box_visible())
              continue;
            ++chunks_drawn;
            glBindVertexArray(world_buffers[c].vao);
            std::vector<bool> parents_visible;
            for(const auto &parent:chunk.parents) {
              auto d=camera_geometry::sub(parent.position,orbit.eye);
              parents_visible.push_back(std::sqrt(camera_geometry::dot(d,d))<=release.exploration->fog_end+parent.distance_radius &&
                                        sphere_visible(parent.center,parent.radius,true));
            }
            for (auto &part : chunk.parts) {
              if(part.kind==1 && !parents_visible[part.parent]) continue;
              if(!sphere_visible(part.center,part.radius,part.radial_cull)) continue;
              auto d=camera_geometry::sub(part.center,orbit.eye);
              float metric=std::sqrt(camera_geometry::dot(d,d))*release.camera.fov/part.scale;
              const auto *level=&part.levels.front();
              uint32_t count=level->count;
              if(part.kind==1) {
                auto target=n3e::world_lod::budget(part.progressive,metric);
                if(compare_lod && pass==0) target=part.progressive.maximum;
                if(target && n3e::world_lod::refine(part,chunk.indices,*target)) {
                  glBufferSubData(GL_ELEMENT_ARRAY_BUFFER,size_t(level->first)*4,
                                  size_t(part.progressive.indices)*4,chunk.indices.data()+level->first);
                }
                count=part.progressive.indices;
              } else if(part.kind==2) {
                level=&part.levels[compare_lod && pass==0 ? 0 : n3e::world_lod::terrain_variant(world_asset->terrain,part,orbit.eye,release.exploration->fog_end)];
                count=level->count;
              } else {
                for (const auto &candidate:part.levels) if(metric>=candidate.distance) level=&candidate;
                count=level->count;
              }
              // PQ-394 (D-212): a drawn sequence part advances once per frame,
              // as 1298's part tick advances a part that passed its tests
              // (004429b0), and draws the frame it reaches (00443090). Both
              // passes of a matched capture draw the same frame; the last
              // keeps it.
              float sequence_slot=-1;
              if(part.sequence) {
                auto &q=*part.sequence;
                const auto frames=uint32_t(q.slots.size());
                const float next=n3e::world_lod::sequence_advance(q.index,sequence_dt,q.fps,frames);
                const auto k=n3e::world_lod::sequence_frame(next,frames);
                sequence_slot=q.slots[k];
                if(pass==passes-1) {
                  q.index=next;++q.advances;
#if N3E_HARNESS
                  if(sequence_log)
                    std::printf("WORLD_SEQUENCE frame=%d chunk=%zu part=%zu advances=%u index=%.9g frame_index=%u frames=%u fps=%.9g seconds=%.9g matched=%d center=%.9g,%.9g,%.9g\n",
                                frame,c,size_t(&part-chunk.parts.data()),q.advances,q.index,k,frames,q.fps,sequence_dt,passes>1,
                                part.center[0],part.center[1],part.center[2]);
#endif
                }
              }
              if(part.alpha) {
                // PQ-379 (D-201): 1298 queues this part into its frame alpha
                // list (00443090) instead of drawing it; the effect pass draws
                // it at its place in the far-to-near order, this level.
                world_alpha.push_back({c,size_t(&part-chunk.parts.data()),level->first,count,
                                       n3e::eye_distance(part.alpha->sort_point,orbit.eye),sequence_slot});
                drawn+=count/3; reduced+=part.levels.front().count/3-count/3; ++visible;
                continue;
              }
              if(part.two_sided) glDisable(GL_CULL_FACE);
              glUniform1f(glGetUniformLocation(p,"nofog"),part.no_fog ? 1.f : 0.f);
              // PQ-382 (D-202): 1298 draws an opaque part alpha-tested as its
              // device set-up leaves it (0043ade0: GREATER against reference
              // 0) and unlit for RF_NOTUSELIGHT (00443090 at 004432da); the
              // world shader takes both from partstate x (y the reference 0,
              // z 0: alpha out 1) and w. A part without the bits keeps the
              // one-half cut and the light.
              glUniform4f(world_part_state,part.cut_zero ? 1.f : 0.f,0,0,part.unlit ? 1.f : 0.f);
              if(release.world_chunked)world_banks.sampling(part.mirrored && !(compare_sampling && pass==0),world_samplers);
              else if(detail)native_textures.sampling(part.mirrored && !(compare_sampling && pass==0),world_samplers);
              else glBindSampler(1, world_samplers[part.mirrored && !(compare_sampling && pass == 0) ? 1 : 0]);
              if(part.sequence) glUniform2f(sequence_uniform,1,sequence_slot);
              glDrawElements(GL_TRIANGLES, count, GL_UNSIGNED_INT,
                             reinterpret_cast<void *>(size_t(level->first)*sizeof(uint32_t)));
              if(part.sequence) glUniform2f(sequence_uniform,0,0);
              // PQ-387 (D-204): a near patch within the eye's window draws its
              // maps right after its tiles, over the same indices, as 1298's
              // 005a2640 draws the light-map fans after the 64 tiles.
              std::array<int, 16> overlay_layers;
              const bool overlay_near = terrain_overlay && part.kind == 2 && level == &part.levels.front();
              const bool overlay_window = overlay_near && terrain_overlay->layers(part.patch_x, part.patch_z, overlay_layers);
              // A near patch with maps outside the window: 1298 draws none there.
              if (overlay_near && !overlay_window && terrain_overlay->any_map(part.patch_x, part.patch_z)) ++overlay_withheld;
              if (overlay_window && !overlay_off && !(compare_overlay && pass == 0)) {
                glUniform1iv(overlay_layers_uniform, 16, overlay_layers.data());
                glUniform2f(overlay_patch_uniform, float(part.patch_x * terrain_overlay->overlay.patch_tiles),
                            float(part.patch_z * terrain_overlay->overlay.patch_tiles));
                glUniform1f(overlay_uniform, 1);
                glEnable(GL_BLEND);
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
                glDepthFunc(GL_LEQUAL);
                glDrawElements(GL_TRIANGLES, count, GL_UNSIGNED_INT,
                               reinterpret_cast<void *>(size_t(level->first)*sizeof(uint32_t)));
                glDepthFunc(saved_depth_func);
                glBlendFuncSeparate(saved_blend[0], saved_blend[1], saved_blend[2], saved_blend[3]);
                if (!saved_blending) glDisable(GL_BLEND);
                glUniform1f(overlay_uniform, 0);
                ++overlay_patches;
              }
              if(part.two_sided) glEnable(GL_CULL_FACE);
              drawn+=count/3; reduced+=part.levels.front().count/3-count/3; ++visible;
            }
            }
            if(terrain_overlay && (frame==40 || compare_overlay))
              std::cout<<"WORLD_OVERLAY pass="<<pass<<" patches="<<overlay_patches<<" centre="<<terrain_overlay->cx<<","
                       <<terrain_overlay->cz<<" uploads="<<terrain_overlay->uploads<<" withheld="<<overlay_withheld<<"\n";
            if(frame==40 || compare_lod) std::cout<<"WORLD_DETAIL visible="<<visible<<" triangles="<<drawn<<" reduced="<<reduced<<" fog="<<release.exploration->fog_start<<":"<<release.exploration->fog_end<<" chunks="<<chunks_drawn<<"/"<<world_asset->chunks.size()<<"\n";
            (void)missing;
#if N3E_HARNESS
            if(world_stream && pass==0) {
              const auto &st=world_stream->stats();
              std::cout<<"WORLD_STREAM frame="<<frame<<" eye="<<orbit.eye[0]<<","<<orbit.eye[2]<<" resident="<<st.resident<<" bytes="<<st.bytes
                       <<" inflight="<<st.in_flight<<" wanted="<<st.wanted<<" limited="<<st.limited<<" missing="<<missing
                       <<" uploaded="<<st.uploaded<<" evicted="<<st.evicted<<" discarded="<<st.discarded
                       <<" max="<<st.max_resident<<"/"<<st.max_bytes<<" settled="<<world_stream->settled()<<"\n";
            }
            if(compare_overlay) {
              capture(capture_path+(pass==0 ? ".no-overlay.ppm" : ".overlay.ppm"),width,height);
              if(pass==1) { world_sampling_captured=true; std::cout<<"PASS world overlay matched-camera captures\n"; }
            }
            if(compare_lod) {
              capture(capture_path+(pass==0 ? ".full.ppm" : ".lod.ppm"),width,height);
              if(pass==1) { world_sampling_captured=true; std::cout<<"PASS world LOD matched-camera captures\n"; }
            }
            if (compare_sampling) {
              capture(capture_path + (pass == 0 ? ".terrain-repeat.ppm" : ".terrain-mirror.ppm"), width, height);
              if (pass == 1) {
                world_sampling_captured = true;
                std::cout << "PASS world sampling matched-camera repeat/mirror captures\n";
              }
            }
#endif
          }
        }
        profile_mark(3);
        glBindSampler(1, 0);
        native_textures.mirrored=-1;
        world_banks.mirrored=-1;
        glUniform1f(glGetUniformLocation(p,"nofog"),0);
        glUniform4f(glGetUniformLocation(p,"partstate"),0,0,0,0);
        glBindVertexArray(vao);
        glBindBuffer(GL_ARRAY_BUFFER, vbo);
      }
      glUniform1f(world_uniform, 0);
      glBindTexture(GL_TEXTURE_2D, texture);
      glDrawArrays(GL_TRIANGLES, 0, world_vertices);
      if(!detail_vertices.empty()) {
        glBindVertexArray(detail_vao);glBindBuffer(GL_ARRAY_BUFFER,detail_vbo);
        glBufferData(GL_ARRAY_BUFFER,detail_vertices.size()*4,detail_vertices.data(),GL_STREAM_DRAW);
        native_textures.bind();native_textures.sampling(false,world_samplers);
        glUniform1f(glGetUniformLocation(p,"world"),1);glUniform1f(glGetUniformLocation(p,"native_detail"),1);
        glUniform1f(glGetUniformLocation(p,"nofog"),0);
        // PQ-315: glowing ranges with their shade, the rest without. PQ-348
        // (D-191): an N3D3 key's range with its part's state, in draw order
        // and z-write on, as 00412570 sets it for each part's draw: the blend
        // with its factors (KO flag 1), culling off (4) and the alpha test
        // against its reference (0043ade0's GREATER); the glow, when it has
        // one, in the same draw (2233 0042cf30 sets both).
        const GLint glow_uniform=glGetUniformLocation(p,"glow"),partstate=glGetUniformLocation(p,"partstate");size_t drawn=0;
        const GLboolean was_blending=glIsEnabled(GL_BLEND),was_culling=glIsEnabled(GL_CULL_FACE);
        GLint blend_state[4];
        glGetIntegerv(GL_BLEND_SRC_RGB,&blend_state[0]);glGetIntegerv(GL_BLEND_DST_RGB,&blend_state[1]);
        glGetIntegerv(GL_BLEND_SRC_ALPHA,&blend_state[2]);glGetIntegerv(GL_BLEND_DST_ALPHA,&blend_state[3]);
        glUniform4f(partstate,0,0,0,0);
        for(const auto&range:detail_glow){
          if(range.first>drawn)glDrawArrays(GL_TRIANGLES,GLint(drawn),GLsizei(range.first-drawn));
          if(range.shade)glUniform4f(glow_uniform,range.shade->emissive[0],range.shade->emissive[1],range.shade->emissive[2],range.shade->modulate);
          if(const auto*st=range.state){
            glUniform4f(partstate,1,st->alpha_reference,(st->flags&n3e::MaterialRun::BLEND)?1.f:0.f,0);
            if(st->flags&n3e::MaterialRun::DOUBLE_SIDED)glDisable(GL_CULL_FACE);else glEnable(GL_CULL_FACE);
            if(st->flags&n3e::MaterialRun::BLEND){glEnable(GL_BLEND);glBlendFunc(part_blend_factors[st->source],part_blend_factors[st->destination]);}
            else glDisable(GL_BLEND);
          }
          glDrawArrays(GL_TRIANGLES,GLint(range.first),GLsizei(range.count));
          glUniform4f(glow_uniform,0,0,0,0);drawn=range.first+range.count;
          if(range.state){
            glUniform4f(partstate,0,0,0,0);
            if(was_culling)glEnable(GL_CULL_FACE);else glDisable(GL_CULL_FACE);
            if(was_blending)glEnable(GL_BLEND);else glDisable(GL_BLEND);
          }
        }
        glBlendFuncSeparate(blend_state[0],blend_state[1],blend_state[2],blend_state[3]);
        if(detail_vertices.size()/12>drawn)glDrawArrays(GL_TRIANGLES,GLint(drawn),GLsizei(detail_vertices.size()/12-drawn));
        glUniform1f(glGetUniformLocation(p,"world"),0);glBindVertexArray(vao);glBindBuffer(GL_ARRAY_BUFFER,vbo);
      }
      if(!loot_vertices.empty()){
        glBindTexture(GL_TEXTURE_2D,loot_texture);
        glDrawArrays(GL_TRIANGLES,world_vertices+player_vertices.size()/8,loot_vertices.size()/8);
      }
      if (!player_vertices.empty()) {
        glBindTexture(GL_TEXTURE_2D, player_texture);
        glDrawArrays(GL_TRIANGLES, world_vertices, player_vertices.size() / 8);
      }
      // One draw per looks in view, with that looks' own atlas (PQ-253). An
      // N3MM looks (PQ-265, D-173) draws each NPC's runs in order, each with
      // its render state, as KO's character render 004196a0 draws each part
      // through 00412570 in part order: the blend with the run's factors,
      // culling off when double-sided, the texture's own colour when unlit,
      // and the alpha test on every run. The state the frame had is
      // put back after.
      static const GLenum blend_factors[] = {GL_ZERO, GL_ONE, GL_SRC_COLOR, GL_ONE_MINUS_SRC_COLOR, GL_SRC_ALPHA,
                                             GL_ONE_MINUS_SRC_ALPHA, GL_DST_ALPHA, GL_ONE_MINUS_DST_ALPHA,
                                             GL_DST_COLOR, GL_ONE_MINUS_DST_COLOR};
      for (size_t i = 0; i < looks_batches.size(); ++i)
        if (!looks_batches[i].empty()) {
          glBindTexture(GL_TEXTURE_2D, looks_textures[i]);
          const GLint batch_first = GLint(looks_first + looks_base[i] / 8);
          const auto &runs = looks_scenes[i][0].runs;
          if (runs.empty()) {
            glDrawArrays(GL_TRIANGLES, batch_first, GLsizei(looks_batches[i].size() / 8));
            continue;
          }
          const GLboolean was_blending = glIsEnabled(GL_BLEND), was_culling = glIsEnabled(GL_CULL_FACE);
          GLint blend_state[4];
          glGetIntegerv(GL_BLEND_SRC_RGB, &blend_state[0]);
          glGetIntegerv(GL_BLEND_DST_RGB, &blend_state[1]);
          glGetIntegerv(GL_BLEND_SRC_ALPHA, &blend_state[2]);
          glGetIntegerv(GL_BLEND_DST_ALPHA, &blend_state[3]);
          const auto partstate = glGetUniformLocation(p, "partstate");
          const GLint per_npc = GLint(looks_scenes[i][0].indices.size());
          for (GLint at = 0; at + per_npc <= GLint(looks_batches[i].size() / 8); at += per_npc)
            for (const auto &run : runs) {
              glUniform4f(partstate, 1, run.alpha_reference, (run.flags & n3e::MaterialRun::UNLIT) ? 1.f : 0.f, 0);
              if (run.flags & n3e::MaterialRun::DOUBLE_SIDED) glDisable(GL_CULL_FACE);
              else glEnable(GL_CULL_FACE);
              if (run.flags & n3e::MaterialRun::BLEND) {
                glEnable(GL_BLEND);
                glBlendFunc(blend_factors[run.source], blend_factors[run.destination]);
              } else {
                glDisable(GL_BLEND);
              }
              glDrawArrays(GL_TRIANGLES, batch_first + at + GLint(run.first), GLsizei(run.count));
            }
          glUniform4f(partstate, 0, 0, 0, 0);
          if (was_culling) glEnable(GL_CULL_FACE);
          else glDisable(GL_CULL_FACE);
          if (was_blending) glEnable(GL_BLEND);
          else glDisable(GL_BLEND);
          glBlendFuncSeparate(blend_state[0], blend_state[1], blend_state[2], blend_state[3]);
        }
      // PQ-328: the attached characters, each with its model's atlas: the lit
      // indices with the entry's shade (the emissive added to the light,
      // clamped, then the modulate, as the detail glow), the rest without; a
      // model with render runs draws them in order with their states, as the
      // looks models do. PQ-359: every one with its wearer's part light (the
      // wearer uniform), as the wearer's equipped parts above take it; the
      // glow, the unlit runs and the render states stay the model's own.
      if(!attached_draws.empty()){
        const GLint glow_uniform=glGetUniformLocation(p,"glow"),partstate=glGetUniformLocation(p,"partstate"),
                    wearer_uniform=glGetUniformLocation(p,"wearer");
        glUniform1f(wearer_uniform,1);
        const GLboolean was_blending=glIsEnabled(GL_BLEND),was_culling=glIsEnabled(GL_CULL_FACE);
        GLint blend_state[4];
        glGetIntegerv(GL_BLEND_SRC_RGB,&blend_state[0]);glGetIntegerv(GL_BLEND_DST_RGB,&blend_state[1]);
        glGetIntegerv(GL_BLEND_SRC_ALPHA,&blend_state[2]);glGetIntegerv(GL_BLEND_DST_ALPHA,&blend_state[3]);
        for(const auto&d:attached_draws){
          glBindTexture(GL_TEXTURE_2D,attachment_textures[d.entry]);
          const GLint first=GLint(attached_first+d.first);
          auto shade=[&](bool lit){if(lit)glUniform4f(glow_uniform,d.shade.emissive[0],d.shade.emissive[1],d.shade.emissive[2],d.shade.modulate);
                                   else glUniform4f(glow_uniform,0,0,0,0);};
          const auto&runs=attachment_scenes[d.entry][0].runs;
          if(runs.empty()){
            if(d.lit){shade(true);glDrawArrays(GL_TRIANGLES,first,GLsizei(d.lit));}
            if(d.count>d.lit){shade(false);glDrawArrays(GL_TRIANGLES,first+GLint(d.lit),GLsizei(d.count-d.lit));}
          }else for(const auto&run:runs){
            glUniform4f(partstate,1,run.alpha_reference,(run.flags&n3e::MaterialRun::UNLIT)?1.f:0.f,0);
            if(run.flags&n3e::MaterialRun::DOUBLE_SIDED)glDisable(GL_CULL_FACE);else glEnable(GL_CULL_FACE);
            if(run.flags&n3e::MaterialRun::BLEND){glEnable(GL_BLEND);glBlendFunc(blend_factors[run.source],blend_factors[run.destination]);}
            else glDisable(GL_BLEND);
            shade(run.first+run.count<=d.lit);
            glDrawArrays(GL_TRIANGLES,first+GLint(run.first),GLsizei(run.count));
          }
          glUniform4f(glow_uniform,0,0,0,0);glUniform4f(partstate,0,0,0,0);
        }
        glUniform1f(wearer_uniform,0);
        if(was_culling)glEnable(GL_CULL_FACE);else glDisable(GL_CULL_FACE);
        if(was_blending)glEnable(GL_BLEND);else glDisable(GL_BLEND);
        glBlendFuncSeparate(blend_state[0],blend_state[1],blend_state[2],blend_state[3]);
      }
      // The drawn actors and their triangles become the next click's pick
      // geometry (PQ-146); the buffers are not used again this frame.
      pick_frame.buffers={std::move(verts),std::move(player_vertices),std::move(detail_vertices),std::move(looks_vertices)};
      pick_frame.volumes=std::move(pick_volumes);
      pick_frame.corpses=std::move(frame_corpses);
#if N3E_HARNESS
      // PQ-253 (N3E_TEST_NPC_LOOKS=1): once per NPC drawn with a looks model,
      // aim the click pick at the centre of its own box; report what the pick
      // returns and whether the ray meets the triangles recorded for it in
      // pick buffer 3 (its batch, moved to its place in the merged buffer).
      if (network && std::getenv("N3E_TEST_NPC_LOOKS"))
        for (const auto &e : world.world.entities()) {
          static std::set<uint64_t> looks_picked;
          auto *volume = n3e::targeting::volume(pick_frame, e.id());
          if (!e.npc() || !volume || volume->mesh.buffer != 3 || looks_picked.contains(e.id())) continue;
          auto q = orbit.project(n3e::targeting::box_centre(volume->box), width, height);
          if (q[2] <= 0 || q[0] < 0 || q[0] >= width || q[1] < 0 || q[1] >= height) continue;
          auto ray = orbit.ray(q[0], q[1], width, height);
          looks_picked.insert(e.id());
          std::cout << "NPC_LOOKS_PICK entity=" << e.id() << " picked="
                    << n3e::targeting::pick(world, pick_frame, orbit.eye, ray, release.pick.mesh_lod)
                    << " mesh=" << n3e::targeting::ray_mesh(orbit.eye, ray, pick_frame, volume->mesh)
                    << " vertices=" << volume->mesh.vertices << "\n";
          if (release.target_marker) marker_queue.push_back(e.id());
        }
      // PQ-296 (N3E_TEST_NPC_LOOKS=1, a package with a target marker): select
      // each picked looks NPC in turn until its marker has been drawn and
      // reported (TARGET_MARKER), then clear the selection.
      if (network && release.target_marker && std::getenv("N3E_TEST_NPC_LOOKS") &&
          (!target || marker_reported.contains(target))) {
        if (!marker_queue.empty()) target = marker_queue.front(), marker_queue.pop_front(), melee.select(target);
        else if (target) target = 0, melee.select(0);
      }
#endif
#if N3E_HARNESS
      // N3E_TEST_MARKER_AT="x y z" (PQ-380): offline, a selected NPC at that
      // point (drawn scale 1), so the marker draws without a session.
      if(const char*at=std::getenv("N3E_TEST_MARKER_AT");at&&!network&&release.target_marker){
        std::istringstream fields(at);n3e::V point{};
        if(!(fields>>point[0]>>point[1]>>point[2]))throw std::runtime_error("marker test point");
        marker_target=MarkerTarget{~uint64_t(0),point,true,1};
      }
#endif
      // PQ-380: the target marker's parts are draws of the effect pass's one
      // far-to-near list, as 1298's symbol (005c4e20) draws its shape through
      // slot +0x48 (005c5129: 004442e0 -> 00443090), which queues each part
      // with every other alpha primitive of the frame for the flush at
      // 005c4d98. Each keeps N3TM's material (ONE/ONE, depth test and writes,
      // back faces culled) and is keyed by target_marker_key.
      struct MarkerDraw{unsigned part;float key;std::vector<float> vertices;};
      std::vector<MarkerDraw> marker_draws;
#if N3E_HARNESS
      bool marker_comparison=false;
#endif
      if(marker_target){
        const auto&marker=*release.target_marker;
#if N3E_HARNESS
        marker_comparison=marker_test&&uif_stage==4&&!walking_to&&!capture_path.empty();
        auto size=n3e::target_marker_size(marker,marker_target->npc,marker_target->scale);
#endif
        for(unsigned i=0;i<marker.parts.size();++i){
          auto vertices=n3e::target_marker_vertices(marker,marker.parts[i],marker_target->npc,marker_target->scale,marker_target->position,orbit.eye,marker_ground);
          if(vertices.empty())continue; // No drawable terrain outside the package surface.
#if N3E_HARNESS
          // PQ-296 (N3E_TEST_TARGET_MARKER or N3E_TEST_NPC_LOOKS): once per
          // selected actor, each part's drawn extent on the three axes.
          if((marker_test||std::getenv("N3E_TEST_NPC_LOOKS"))&&!marker_reported.contains(marker_target->id)){
            n3e::V lo{vertices[0],vertices[1],vertices[2]},hi=lo;
            for(size_t at=0;at+8<=vertices.size();at+=8)for(int k=0;k<3;++k)lo[k]=std::min(lo[k],vertices[at+k]),hi[k]=std::max(hi[k],vertices[at+k]);
            std::cout<<"TARGET_MARKER entity="<<marker_target->id<<" npc="<<marker_target->npc<<" scale="<<marker_target->scale
                     <<" horizontal="<<size[0]<<" vertical="<<size[1]<<" part="<<i<<" mode="<<marker.parts[i].mode
                     <<" x="<<hi[0]-lo[0]<<" y="<<hi[1]-lo[1]<<" z="<<hi[2]-lo[2]<<"\n";
          }
#endif
          float key=n3e::target_marker_key(marker,marker.parts[i],marker_target->npc,marker_target->scale,marker_target->position,orbit.eye);
          marker_draws.push_back({i,key,std::move(vertices)});
        }
#if N3E_HARNESS
        marker_drawn=marker_draws.size()==marker.parts.size()?marker_target->id:0;
        if(marker_drawn&&(marker_test||std::getenv("N3E_TEST_NPC_LOOKS")))marker_reported.insert(marker_drawn);
#endif
      }
      auto draw_marker=[&](size_t i){
        const auto&d=marker_draws[i];
        glUseProgram(p);glBindVertexArray(vao);glBindBuffer(GL_ARRAY_BUFFER,vbo);
        glActiveTexture(GL_TEXTURE0);glBindSampler(0,0);
        glUniform1f(glGetUniformLocation(p,"marker"),1);
        glEnable(GL_BLEND);glBlendFunc(GL_ONE,GL_ONE);
        glEnable(GL_DEPTH_TEST);glDepthMask(GL_TRUE);glEnable(GL_CULL_FACE);
        glBufferData(GL_ARRAY_BUFFER,d.vertices.size()*sizeof(float),d.vertices.data(),GL_STREAM_DRAW);
        glBindTexture(GL_TEXTURE_2D,marker_textures[d.part]);glDrawArrays(GL_TRIANGLES,0,GLsizei(d.vertices.size()/8));
        glUniform1f(glGetUniformLocation(p,"marker"),0);
      };
      double effect_now=SDL_GetTicks()/1000.;
      if(!world.connected||audio_session!=world.world.session()){
        effect_player.active.clear();local_release.reset();audio.clear();audio_claim=0;audio_claim_responses=world.claim_responses;audio_session=world.world.session();
      }
      // PQ-445 (D-226): the archer's own shots. One whose predicted release
      // (its drawn clip at the marker, as 1298's cast tick 00585830
      // releases) has come launches, before the frame's release events
      // confirm them.
      {
        PresentationEvents::Boxes local_boxes;
        for(const auto&v:pick_frame.volumes)local_boxes[v.id]=v.box;
        for(const auto&l:local_release.launch(melee_presentation,effect_player,audio.mixer,release,effect_now,effect_positions,effect_joints,effect_headings,local_boxes)){
#if N3E_HARNESS
          const auto&f=l.flight;
          std::cout<<"RANGED_FLIGHT local actor="<<melee_presentation.actor<<" self=1 request="<<l.request<<" target="<<f.target
                   <<" age="<<effect_now-l.start<<" predicted="<<l.predicted<<" late="<<l.start-l.due<<" from="<<f.from[0]<<","<<f.from[1]<<","<<f.from[2]
                   <<" dir="<<f.dir[0]<<","<<f.dir[1]<<","<<f.dir[2]<<" speed="<<f.speed<<" launch="<<f.launch
                   <<" box="<<local_boxes.contains(f.target)<<std::endl;
          for(const auto&c:l.casts)std::cout<<"RANGED_CAST_FX stop actor="<<c.actor<<" self=1 tick="<<c.tag.substr(7)
                                            <<" joint="<<c.joint<<" age="<<c.stop<<std::endl;
#else
          (void)l;
#endif
        }
      }
      for(const auto&event:presentation_events.poll(world)){
        auto*local=event.kind()==2&&event.actor()==melee_presentation.actor?melee_presentation.find(event.request_sequence()):nullptr;
        double local_start=local?local->start:-1;
        // PQ-445: the archer's own release event confirms its predicted
        // flight, or launches it when there is none.
        auto*own=event.kind()==7&&event.actor()==melee_presentation.actor&&event.request_sequence()?melee_presentation.find(event.request_sequence()):nullptr;
        bool predicted=false;
        if(own){
          auto c=local_release.confirm(event.request_sequence(),event.tick(),effect_player,release,effect_now,effect_positions,effect_joints);
          predicted=c.found;
          if(!predicted)own->released=effect_now;
#if N3E_HARNESS
          if(predicted)std::cout<<"RANGED_FLIGHT confirm actor="<<event.actor()<<" self=1 request="<<event.request_sequence()<<" tick="<<event.tick()
                                <<" lead="<<c.lead<<" held="<<c.held.size()<<std::endl;
#endif
          for(size_t n=0;n<c.hits.size();++n){
            const auto&a=c.hits[n];
            if(release.audio)audio.mixer.play(*release.audio,"effect:"+a.hit,effect_now,a.point,true,0,true);
#if N3E_HARNESS
            std::cout<<"RANGED_FLIGHT hit actor="<<a.actor<<" self=1 tick="<<event.tick()<<" request="<<a.request<<" target="<<a.target<<" reach="<<a.reach
                     <<" late=0 held="<<c.held[n]<<" at="<<a.point[0]<<","<<a.point[1]<<","<<a.point[2]<<" box="<<a.box<<" clip="<<a.hit<<" joint="<<a.joint<<std::endl;
#endif
          }
        }
#if N3E_HARNESS
        if(local&&std::getenv("N3E_TEST_MELEE_SEQUENCE"))std::cout<<"MELEE_CONFIRM request="<<event.request_sequence()<<" elapsed="<<effect_now-local->start<<" hit="<<event.hit()<<"\n";
        // PQ-420 (D-217): a held shot's start (kind 2, no hit) and landing
        // (kind 6); PQ-439 (D-223): its release (kind 7) under a flight.
        if(release.combat_animation&&event.style()&&event.style()<=release.combat_animation->profiles.size()&&
           release.combat_animation->profiles[event.style()-1].ranged.cast_ms&&(event.kind()==2||event.kind()==6||event.kind()==7))
          std::cout<<(event.kind()==6?"RANGED_LANDED":event.kind()==7?"RANGED_RELEASED":"RANGED_CAST_START")<<" actor="<<event.actor()<<" self="<<(event.actor()==world.world.self())
                   <<" request="<<event.request_sequence()<<" tick="<<event.tick()<<" hit="<<event.hit()<<std::endl;
#endif
        PresentationEvents::effects(effect_player,release,world,event,effect_now,effect_positions,effect_joints,local_start);
#if N3E_HARNESS
        size_t effects_before=effect_player.active.size();
#endif
        // PQ-445: not for an own shot whose release the client already predicted.
        if(!local||local->released<0)
          PresentationEvents::cast_effect(effect_player,release,world,event,effect_now,effect_positions,effect_joints,effect_headings,local_start);
#if N3E_HARNESS
        // PQ-423 (D-220): each ranged cast effect started, with its joint and start age.
        for(size_t n=effects_before;n<effect_player.active.size();++n){const auto&i=effect_player.active[n];
          if(i.tag.starts_with("ranged:"))std::cout<<"RANGED_CAST_FX start actor="<<i.actor<<" self="<<(i.actor==world.world.self())
            <<" tick="<<event.tick()<<" request="<<event.request_sequence()<<" joint="<<i.joint<<" age="<<effect_now-i.start<<std::endl;}
#endif
        // PQ-417 (D-222): a held shot's release (since PQ-439) launches its flight.
        PresentationEvents::Boxes flight_boxes;
        if(PresentationEvents::ranged_flight(release,event))for(const auto&v:pick_frame.volumes)flight_boxes[v.id]=v.box;
#if N3E_HARNESS
        size_t flights_before=effect_player.active.size();
#endif
        if(!predicted)PresentationEvents::flight(effect_player,release,world,event,effect_now,effect_positions,effect_joints,effect_headings,flight_boxes);
#if N3E_HARNESS
        // PQ-417 (D-222): each flight launched: its start, direction (pitch
        // included), speed, launch distance and whether it aims at a box.
        for(size_t n=flights_before;n<effect_player.active.size();++n){const auto&i=effect_player.active[n];
          if(!i.flight)continue;const auto&f=*i.flight;
          std::cout<<"RANGED_FLIGHT start actor="<<i.actor<<" self="<<(i.actor==world.world.self())<<" tick="<<event.tick()
                   <<" request="<<f.request<<" target="<<f.target<<" hit="<<event.hit()<<" age="<<effect_now-i.start<<" from="<<f.from[0]<<","<<f.from[1]<<","<<f.from[2]
                   <<" dir="<<f.dir[0]<<","<<f.dir[1]<<","<<f.dir[2]<<" speed="<<f.speed<<" launch="<<f.launch
                   <<" box="<<flight_boxes.contains(f.target)<<std::endl;}
#endif
        PresentationEvents::audio(audio.mixer,release,world,event,effect_now,local_start,local!=nullptr,0,predicted);
      }
      // PQ-445: after the release events, a predicted flight whose shot the
      // server will not release ends, and one whose result came unconfirmed
      // is confirmed.
      for(const auto&c:local_release.reconcile(melee_presentation,effect_player,audio.mixer,release,effect_now,effect_positions,effect_joints)){
#if N3E_HARNESS
        std::cout<<"RANGED_FLIGHT cancel actor="<<melee_presentation.actor<<" self=1 request="<<c.request<<" age="<<c.age<<" held="<<c.held<<std::endl;
#else
        (void)c;
#endif
      }
      for(const auto&a:local_release.settled)if(release.audio)audio.mixer.play(*release.audio,"effect:"+a.hit,effect_now,a.point,true,0,true);
      for(const auto&event:local_casts){PresentationEvents::effects(effect_player,release,world,event,effect_now,effect_positions,effect_joints);PresentationEvents::audio(audio.mixer,release,world,event,effect_now);}
      local_casts.clear();
      for(const auto&e:world.world.entities())if(e.id()==world.world.self()&&!e.cast_skill().empty())melee.stop();
      if(audio_claim_responses!=world.claim_responses){
        audio_claim_responses=world.claim_responses;
        if(audio_claim&&world.claim.operation()==audio_claim&&world.claim.status()!="pending"){
          if(world.claim.status()=="claimed")sound(audio_claim_key);
          audio_claim=0;
        }
      }
      // KO 00646550 places the listener at the player's position and facing
      // (up 0,1,0); the effect start test still measures from the camera eye.
      n3e::AudioListener listener{orbit.eye,orbit.eye,orbit.right};
      if(release.audio&&release.audio->spatial.listener==1&&world.connected)
        if(auto self=effect_positions.find(world.world.self());self!=effect_positions.end())
          listener={orbit.eye,self->second,{std::cos(self_heading),0,-std::sin(self_heading)}};
      audio.tick(effect_now,listener);
      // PQ-379 (D-201): each world alpha part at its place in the effect
      // pass's order, with the world shader: its factors, depth writes and
      // tests unless its state turns them off, its fog and culling, no light
      // for 0x40, fragments cut at texture alpha 0 (0043ade0's GREATER 0) and
      // the texture's alpha to the blend.
      world_alpha_keys.clear();
      for(const auto&d:world_alpha)world_alpha_keys.push_back(d.key);
      auto draw_world_alpha=[&](size_t i){
        const auto&d=world_alpha[i];const auto&part=world_asset->chunks[d.chunk].parts[d.part];const auto&a=*part.alpha;
        glUseProgram(p);
        const GLint world_on=glGetUniformLocation(p,"world"),state=glGetUniformLocation(p,"partstate"),fog=glGetUniformLocation(p,"nofog");
        glUniform1f(world_on,1);
        glActiveTexture(GL_TEXTURE1);glBindTexture(GL_TEXTURE_2D_ARRAY,world_texture);glActiveTexture(GL_TEXTURE0);
        if(release.world_chunked)world_banks.bind();else if(detail)native_textures.bind();
        glUniform1f(glGetUniformLocation(p,"native_detail"),detail||release.world_chunked?1:0);
        glUniform4f(state,1,0,1,(a.state&0x40)?1.f:0.f);
        glUniform4f(glGetUniformLocation(p,"glow"),0,0,0,0);
        glUniform1f(fog,part.no_fog?1.f:0.f);
        if(release.world_chunked){world_banks.mirrored=-1;world_banks.sampling(part.mirrored,world_samplers);}
        else if(detail){native_textures.mirrored=-1;native_textures.sampling(part.mirrored,world_samplers);}
        else glBindSampler(1,world_samplers[part.mirrored?1:0]);
        glBindVertexArray(world_buffers[d.chunk].vao);
        glEnable(GL_BLEND);glBlendFunc(EffectsView::blend(a.source),EffectsView::blend(a.destination));
        glDepthMask(!(a.state&0x100));
        if(a.state&0x400)glDisable(GL_DEPTH_TEST);else glEnable(GL_DEPTH_TEST);
        if(part.two_sided)glDisable(GL_CULL_FACE);else glEnable(GL_CULL_FACE);
        // D-212: a sequence part draws the frame the world pass reached.
        const GLint sequence_on=glGetUniformLocation(p,"sequence");
        if(d.slot>=0)glUniform2f(sequence_on,1,d.slot);
        glDrawElements(GL_TRIANGLES,GLsizei(d.count),GL_UNSIGNED_INT,reinterpret_cast<void*>(size_t(d.first)*sizeof(uint32_t)));
        glUniform2f(sequence_on,0,0);
        glUniform4f(state,0,0,0,0);glUniform1f(world_on,0);glUniform1f(fog,0);
        glBindSampler(1,0);native_textures.mirrored=-1;world_banks.mirrored=-1;
      };
      // The pass's external draws: the world's alpha parts, then the marker's
      // parts (PQ-380). A marker comparison frame (N3E_TEST_TARGET_MARKER)
      // leaves the marker out and draws it after the pass, between captures.
      std::vector<float> alpha_keys=world_alpha_keys;
#if N3E_HARNESS
      if(!marker_comparison)
#endif
        for(const auto&d:marker_draws)alpha_keys.push_back(d.key);
      auto draw_alpha=[&](size_t i){if(i<world_alpha.size())draw_world_alpha(i);else draw_marker(i-world_alpha.size());};
#if N3E_HARNESS
      // N3E_TEST_MARKER_AT (PQ-380): at frame 40, the marker parts' keys.
      if(frame==40&&std::getenv("N3E_TEST_MARKER_AT")){
        std::cout<<"MARKER_ALPHA frame=40 parts="<<marker_draws.size()<<" eye="<<orbit.eye[0]<<","<<orbit.eye[1]<<","<<orbit.eye[2]<<" keys=";
        for(size_t i=0;i<marker_draws.size();++i)std::cout<<(i?",":"")<<marker_draws[i].key;
        std::cout<<std::endl;
      }
      // N3E_TEST_EFFECT_AT="key x y z[;key x y z...]" (PQ-379): offline, keep
      // one instance of each listed clip playing at that point, restarted when
      // it ends; and at frame 40 report the world's alpha parts and keys.
      if(const char*at=std::getenv("N3E_TEST_EFFECT_AT");at&&!network&&release.effects){
        std::istringstream list(at);std::string entry;size_t n=0;
        while(std::getline(list,entry,';')){
          std::istringstream fields(entry);std::string key;n3e::V point{};
          if(!(fields>>key>>point[0]>>point[1]>>point[2]))throw std::runtime_error("effect test point");
          const std::string tag="test-at-"+std::to_string(n++);
          bool playing=false;
          for(const auto&i:effect_player.active)
            playing=playing||(i.tag==tag&&effect_now-i.start<double(i.clip->frames.size())/i.clip->rate);
          if(!playing){
            if(!effect_player.start(*release.effects,key,~uint64_t(0)-n,point,{},1,effect_now))throw std::runtime_error("effect test clip");
            effect_player.active.back().tag=tag;
          }
        }
      }
      if(frame==40&&std::getenv("N3E_TEST_EFFECT_AT")){
        std::cout<<"WORLD_ALPHA frame=40 parts="<<world_alpha.size()<<" eye="<<orbit.eye[0]<<","<<orbit.eye[1]<<","<<orbit.eye[2]<<" keys=";
        for(size_t i=0;i<world_alpha_keys.size();++i)std::cout<<(i?",":"")<<world_alpha_keys[i];
        std::cout<<" effects=";
        for(size_t i=0;i<effect_player.active.size();++i)std::cout<<(i?",":"")<<n3e::eye_distance(effect_player.active[i].positions.back().second,orbit.eye);
        std::cout<<std::endl;
      }
#endif
      if(release.effects){
#if N3E_HARNESS
        std::map<const n3e::EffectInstance*,float> cast_stops_before;
        for(const auto&i:effect_player.active)if(i.tag.starts_with("ranged:"))cast_stops_before[&i]=i.stop;
#endif
        PresentationEvents::cast_stops(effect_player,world,effect_now);
        {
          // PQ-417 (D-222): flights that arrived end there; their hit clips
          // start on the target, with the clip's sound at the target.
          PresentationEvents::Boxes flight_boxes;
          for(const auto&i:effect_player.active)if(i.flight&&i.flight->reach<0){for(const auto&v:pick_frame.volumes)flight_boxes[v.id]=v.box;break;}
          for(const auto&a:PresentationEvents::flights(effect_player,release,effect_now,effect_positions,effect_joints,flight_boxes)){
            // PQ-445: a predicted flight's hit waits for its release event.
            if(a.pending){
              local_release.hold(a);
#if N3E_HARNESS
              std::cout<<"RANGED_FLIGHT held actor="<<a.actor<<" self=1 request="<<a.request<<" target="<<a.target<<" reach="<<a.reach
                       <<" late="<<effect_now-a.at<<" box="<<a.box<<std::endl;
#endif
              continue;
            }
            if(release.audio&&!a.hit.empty())audio.mixer.play(*release.audio,"effect:"+a.hit,a.at,a.point,true,0,true);
#if N3E_HARNESS
            std::cout<<"RANGED_FLIGHT hit actor="<<a.actor<<" self="<<(a.actor==world.world.self())<<" tick="<<a.tag.substr(7)<<" request="<<a.request
                     <<" target="<<a.target<<" reach="<<a.reach<<" late="<<effect_now-a.at<<" held=0 at="<<a.point[0]<<","<<a.point[1]<<","<<a.point[2]
                     <<" box="<<a.box<<" clip="<<a.hit<<" joint="<<a.joint<<std::endl;
#endif
          }
        }
        effect_player.tick(effect_now,effect_positions,effect_joints,effect_headings);
#if N3E_HARNESS
        // PQ-423 (D-220): when a ranged cast effect ends (its caster's strike
        // fields stopped showing the cast), and once, 0.1 s or more into it,
        // where it is drawn: the centroid of its drawn vertices less the joint
        // (`offset`), the caster's facing and the centroid of the clip's own
        // records (`base`), which turned by the facing gives `offset`.
        {
          static std::set<std::pair<uint64_t,std::string>> drawn_casts;
          for(const auto&i:effect_player.active){
            if(!i.tag.starts_with("ranged:"))continue;
            float age=float(effect_now-i.start);
            if(auto b=cast_stops_before.find(&i);b!=cast_stops_before.end()&&b->second!=i.stop)
              std::cout<<"RANGED_CAST_FX stop actor="<<i.actor<<" self="<<(i.actor==world.world.self())<<" tick="<<i.tag.substr(7)
                       <<" joint="<<i.joint<<" age="<<i.stop<<std::endl;
            auto frame=size_t(std::max(0.f,age)*i.clip->rate);
            if(age<.1f||age>=i.stop||frame>=i.clip->frames.size()||i.clip->frames[frame].empty()||
               !drawn_casts.insert({i.actor,i.tag+":"+std::to_string(i.joint)}).second)continue;
            double sum[3]={},base[3]={};size_t n=0;
            for(const auto&batch:i.clip->frames[frame]){
              auto v=n3e::effect_vertices(i,batch,age,orbit.right,orbit.up);
              for(size_t k=0;k+8<v.size();k+=9){for(int a=0;a<3;++a)sum[a]+=v[k+a];++n;}
              for(size_t k=0;k+8<batch.records.size();k+=9)for(int a=0;a<3;++a)base[a]+=batch.records[k+a]*i.scale;
            }
            if(!n)continue;
            auto at=i.position(age);
            std::cout<<"RANGED_CAST_FX draw actor="<<i.actor<<" self="<<(i.actor==world.world.self())<<" tick="<<i.tag.substr(7)
                     <<" joint="<<i.joint<<" vertices="<<n<<" heading="<<i.heading<<" offset="<<sum[0]/n-at[0]<<","<<sum[1]/n-at[1]<<","<<sum[2]/n-at[2]
                     <<" base="<<base[0]/n<<","<<base[1]/n<<","<<base[2]/n<<std::endl;
          }
          // PQ-417 (D-222): once per flight, in flight, where it is drawn:
          // its age, its anchor (the start plus the direction x speed x age),
          // the centroid of its drawn vertices less the anchor (`offset`) and
          // of the clip's own records (`base`), which the turn to the
          // direction takes to `offset`.
          static std::set<std::pair<uint64_t,std::string>> drawn_flights;
          for(const auto&i:effect_player.active){
            if(!i.flight)continue;
            float age=float(effect_now-i.start);auto frame=size_t(std::max(0.f,age)*i.clip->rate);
            if(age<.01f||age>=i.stop||frame>=i.clip->frames.size()||i.clip->frames[frame].empty()||
               !drawn_flights.insert({i.actor,i.tag}).second)continue;
            double sum[3]={},base[3]={};size_t n=0;
            for(const auto&batch:i.clip->frames[frame]){
              auto v=n3e::effect_vertices(i,batch,age,orbit.right,orbit.up);
              for(size_t k=0;k+8<v.size();k+=9){for(int a=0;a<3;++a)sum[a]+=v[k+a];++n;}
              for(size_t k=0;k+8<batch.records.size();k+=9)for(int a=0;a<3;++a)base[a]+=batch.records[k+a]*i.scale;
            }
            if(!n)continue;
            auto at=i.position(age);
            std::cout<<"RANGED_FLIGHT draw actor="<<i.actor<<" self="<<(i.actor==world.world.self())<<" tick="<<i.tag.substr(7)
                     <<" request="<<i.flight->request<<" age="<<age<<" vertices="<<n<<" anchor="<<at[0]<<","<<at[1]<<","<<at[2]
                     <<" offset="<<sum[0]/n-at[0]<<","<<sum[1]/n-at[1]<<","<<sum[2]/n-at[2]
                     <<" base="<<base[0]/n<<","<<base[1]/n<<","<<base[2]/n<<std::endl;
          }
        }
#endif
#if N3E_HARNESS
        // N3E_TEST_EFFECTS: capture each effect clip once, before and after its draw.
        std::string effect_capture;
        if(std::getenv("N3E_TEST_EFFECTS")&&!capture_path.empty())for(const auto&i:effect_player.active){
          double age=effect_now-i.start;size_t onset=0;while(onset<i.clip->frames.size()&&i.clip->frames[onset].empty())++onset;
          // PQ-417: a flight lasts a fraction of a second; take it in flight.
          if(i.flight?age<.02||age>=i.stop:age<std::max(.15,double(onset)/i.clip->rate+.1))continue;
          auto frame=size_t(age*i.clip->rate);if(frame>=i.clip->frames.size()||i.clip->frames[frame].empty())continue;
          for(const auto&[key,clip]:release.effects->clips)if(&clip==i.clip&&captured_effects.insert(key).second){effect_capture=capture_path+".effect-"+key;break;}
          if(!effect_capture.empty())break;
        }
        // PQ-379: the before/after pair brackets the effect draws alone, so
        // in the capture frame the world's alpha parts (drawn in the same
        // pass otherwise) are drawn first, on their own, before the
        // `.before` capture; the effect pass then draws without them.
        bool effect_split=!effect_capture.empty();
        if(effect_split){
          static const n3e::EffectPlayer no_effects;
          effect_view.draw(no_effects,effect_now,orbit,release.camera,float(width)/height,{},{},alpha_keys,draw_alpha);
          capture(effect_capture+".before.ppm",width,height);
          effect_view.draw(effect_player,effect_now,orbit,release.camera,float(width)/height,appearance_tails,appearance_meshes);
        }
#else
        constexpr bool effect_split=false;
#endif
        if(!effect_split)
          effect_view.draw(effect_player,effect_now,orbit,release.camera,float(width)/height,appearance_tails,appearance_meshes,
                           alpha_keys,draw_alpha);
#if N3E_HARNESS
        // N3E_TEST_APPEARANCE_TAIL_THIN=1 (PQ-342): each tail link's N3E4
        // particle rules every 0.25 s: the camera distance to its bundle, the
        // live count that gives, the candidates it draws now, the earlier
        // link's taken live ones it counted (one tail copy's live list) and,
        // summed over the copy's links apart from that count, what the copy
        // draws.
        if(std::getenv("N3E_TEST_APPEARANCE_TAIL_THIN")){
          static std::map<std::tuple<uint64_t,size_t,double>,double> printed;
          for(const auto*t:appearance_tails)for(size_t k=0;k<t->thin.size();++k){
            auto&last=printed.try_emplace({t->actor,k,t->start},-1.).first->second;
            if(effect_now-last<.25)continue;
            last=effect_now;
            const auto&r=t->clip->thinning[k];const auto&s=t->thin[k];
            // Every link of the same tail copy (group): what that copy draws.
            uint32_t copy=0;
            for(const auto*o:appearance_tails)if(o->group&&o->group==t->group&&o->clip==t->clip&&k<o->thin.size()
                                                 &&o->thin[k].target!=0)copy+=o->thin[k].alive;
            std::cout<<"APPEARANCE_TAIL_THIN entity="<<t->actor<<" self="<<(t->actor==world.world.self())<<" rule="<<k
                     <<" texture="<<r.texture<<" count="<<r.count<<" near="<<r.near<<" far="<<r.far<<" link="<<t->start
                     <<" age="<<effect_now-t->start<<" distance="<<s.distance<<" target="<<s.target
                     <<" drawn="<<(s.target==0?0u:s.alive)<<" carried="<<s.carried<<" copy="<<copy<<"\n";
          }
        }
        // N3E_TEST_EFFECT_PIXELS=r0,r1,g0,g1,b0,b1 (PQ-376): after the effect
        // pass of every frame that draws an appearance effect, the pixels of
        // rows h/10..9h/10 whose channels all lie in those ranges, and the eye.
        if(const char*range=std::getenv("N3E_TEST_EFFECT_PIXELS");range&&(!appearance_meshes.empty()||!appearance_tails.empty())){
          int b[6]{};
          if(std::sscanf(range,"%d,%d,%d,%d,%d,%d",b,b+1,b+2,b+3,b+4,b+5)!=6)throw std::runtime_error("N3E_TEST_EFFECT_PIXELS: six channel bounds");
          int y0=height/10,y1=height*9/10;std::vector<unsigned char> px(size_t(width)*size_t(y1-y0)*3);
          glPixelStorei(GL_PACK_ALIGNMENT,1);glReadPixels(0,height-y1,width,y1-y0,GL_RGB,GL_UNSIGNED_BYTE,px.data());
          size_t n=0;
          for(size_t i=0;i<px.size();i+=3)n+=px[i]>=b[0]&&px[i]<=b[1]&&px[i+1]>=b[2]&&px[i+1]<=b[3]&&px[i+2]>=b[4]&&px[i+2]<=b[5];
          std::cout<<"EFFECT_PIXELS frame="<<frame<<" count="<<n<<" eye="<<orbit.eye[0]<<","<<orbit.eye[1]<<","<<orbit.eye[2]<<"\n";
        }
        if(!effect_capture.empty()){capture(effect_capture+".after.ppm",width,height);if(glGetError()!=GL_NO_ERROR)throw std::runtime_error("effect GL error");std::cout<<"EFFECT_CAPTURE "<<effect_capture<<"\n";}
#endif
      } else if(!alpha_keys.empty()) {
        // No effects.bin: the world's and the marker's alpha parts alone, far to near.
        effect_view.draw(effect_player,effect_now,orbit,release.camera,float(width)/height,{},{},alpha_keys,draw_alpha);
      }
#if N3E_HARNESS
      // PQ-296/PQ-380: a marker comparison frame brackets the marker's parts
      // alone (far to near among themselves) after the alpha pass, so the
      // pair differs by the marker only (tests/target_marker_pixels.py).
      if(marker_comparison){
        capture(capture_path+".world-without-marker.ppm",width,height);
        std::vector<size_t> order(marker_draws.size());for(size_t i=0;i<order.size();++i)order[i]=i;
        std::stable_sort(order.begin(),order.end(),[&](size_t a,size_t b){return marker_draws[a].key>marker_draws[b].key;});
        for(auto i:order)draw_marker(i);
        glDisable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
        capture(capture_path+".world-with-marker.ppm",width,height);
      }
#endif
      // PQ-316: the post-process chain over the world, before the HUD (2233
      // 00537030 runs 00476b40 after the scene and before its UI).
      if(postprocessed){
#if N3E_HARNESS
        const PatternPhase*phase=nullptr;
        for(const auto&ph:pattern)if(frame>=ph.frame)phase=&ph;
        if(phase){
          GLfloat clear[4];glGetFloatv(GL_COLOR_CLEAR_VALUE,clear);const bool scissored=glIsEnabled(GL_SCISSOR_TEST);
          auto fill=[&](int x,int y,int w,int h,const std::array<float,3>&c){glScissor(x,height-y-h,w,h);glClearColor(c[0],c[1],c[2],1);glClear(GL_COLOR_BUFFER_BIT);};
          glEnable(GL_SCISSOR_TEST);
          if(phase->stripes){fill(0,0,width,height,{0,0,0});for(int x=0;x<width;x+=2)fill(x,0,1,height,{1,1,1});}
          else fill(0,0,width,height,phase->background);
          for(const auto&r:phase->rects)fill(r.x,r.y,r.w,r.h,r.rgb);
          if(!scissored)glDisable(GL_SCISSOR_TEST);glClearColor(clear[0],clear[1],clear[2],clear[3]);
        }
        const bool dump=postprocess_stages.count(frame)&&!capture_path.empty();
        // A dumped frame reads its measurement synchronously, so the suite can
        // check the read-back against the frame's own scene.
        if(dump)postprocess.sync_once=true;
        auto write=[&](const std::string&name,const PostProcessView::Target&t){
          auto pixels=postprocess.pixels(t);auto path=capture_path+".stage-"+std::to_string(frame)+"-"+name+".ppm";
          std::ofstream f(path,std::ios::binary);f<<"P6\n"<<t.width<<" "<<t.height<<"\n255\n";f.write((const char*)pixels.data(),pixels.size());
          std::cout<<"POSTPROCESS_STAGE frame="<<frame<<" name="<<name<<" width="<<t.width<<" height="<<t.height<<" path="<<path<<std::endl;};
        if(dump){using P=PostProcessView;write("scene",postprocess.targets[P::scene]);}
#endif
        const uint64_t now_ns=SDL_GetTicksNS();
        const double dt=postprocess_last?double(now_ns-postprocess_last)/1e9:0;
        postprocess_last=now_ns;
        postprocess.finish(dt);
#if N3E_HARNESS
        if(postprocess_test){const auto&m=postprocess.measured;const auto&a=postprocess.adapted;
          std::cout<<"POSTPROCESS frame="<<frame<<" dt="<<dt<<" read="<<postprocess.read<<" measured="<<m[0]<<","<<m[1]<<","<<m[2]
                   <<" adapted="<<a[0]<<","<<a[1]<<","<<a[2]<<" used="<<postprocess.used_average<<","<<postprocess.used_maximum<<std::endl;}
        if(dump){using P=PostProcessView;
          for(auto[name,stage]:{std::pair{"bright",P::bright},{"down",P::down},{"blur",P::blur},{"bloom",P::bloom}})write(name,postprocess.targets[stage]);
          auto path=capture_path+".stage-"+std::to_string(frame)+"-final.ppm";capture(path,width,height);
          std::cout<<"POSTPROCESS_STAGE frame="<<frame<<" name=final width="<<width<<" height="<<height<<" path="<<path<<std::endl;}
#endif
      } else postprocess_last=0;
#if TOOLS
      if(!network){ImGui::Render();ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());}
#endif
      auto draw_fps = [&]() {
        // Count completed presentations over a half-second window, including
        // swap blocking and frame pacing, rather than showing reciprocal CPU dt.
        auto fps_now = SDL_GetTicksNS();
        if (fps_now - fps_start >= 500000000ull) {
          fps_label = "FPS " + std::to_string(std::lround(
              double(fps_frames) * 1e9 / double(fps_now - fps_start)));
          fps_start = fps_now;
          fps_frames = 0;
        }
        // Diagnostic paint must not conceal a package dialog's title/controls.
        if(hud)for(const auto&q:hud->data.records)if(q.panel&&hud->visible(q)){
          auto r=hud->rectangle(q,width,height);
          if(r[0]<width-8&&r[2]>std::max(0,width-126)&&r[1]<36&&r[3]>8)return;
        }
        glEnable(GL_SCISSOR_TEST);
        glScissor(std::max(0, width - 126), height - 36, 118, 28);
        glClearColor(.02f, .025f, .03f, 1);
        profile_mark(4);
        glClear(GL_COLOR_BUFFER_BIT);
        glDisable(GL_SCISSOR_TEST);
        hud_text(fps_label, std::max(0, width - 120), 15, height);
      };
      if (network) {
        if(auto retry=item_wait.sync(world,SDL_GetTicks()/1000.))network->send(*retry);
        if(hud&&!item_wait.notice.empty()){hud->post_notice(item_wait.notice);item_wait.notice.clear();}
        if (hud && entry >= 4) {
          // The overview map follows the player with or without feature dialogs
          // (N3HD and N3HE, PQ-217).
          if(hud->data.minimap){
            // 005daba0: markers rebuilt every frame; party members draw on top.
            hud->minimap_self={world.predicted[0],world.predicted[2],heading};hud->minimap_markers.clear();
            const auto&colors=hud->data.minimap->colors;
            for(const auto&e:world.world.entities()){if(e.id()==world.world.self())continue;
              bool party=!e.npc()&&std::any_of(world.party.members().begin(),world.party.members().end(),[&](const auto&m){return m.entity()==e.id();});
              hud->minimap_markers.push_back({e.x(),e.z(),e.npc()?colors[1]:party?colors[3]:colors[4],party});}
          }
          if(uif_dialogs){
            bool drag_allowed=entry==4&&window_focused&&!orbit_drag&&feature_ui.drag_valid(world,nearest_shop())&&feature_ui.drag->panel==item_panel();
#if TOOLS
            drag_allowed=drag_allowed&&!editor.capture()&&!ImGui::GetIO().WantCaptureMouse;
#endif
            for(const auto&e:world.world.entities())if(e.id()==world.world.self()&&!e.health())drag_allowed=false;
            if(feature_ui.drag&&!drag_allowed)cancel_item_drag();
            bool hotbar_drag_allowed=entry==4&&window_focused&&!orbit_drag&&hotbar.drag_valid(world);
#if TOOLS
            hotbar_drag_allowed=hotbar_drag_allowed&&!editor.capture()&&!ImGui::GetIO().WantCaptureMouse;
#endif
            if(hotbar.drag&&!hotbar_drag_allowed)cancel_item_drag();
            loot_ui.sync(world,release.loot_open_radius.value_or(release.claim_radius),release.loot_open_radius.has_value());
            if(loot_ui.pending&&SDL_GetTicks()>=loot_retry_at){n3e::Envelope q;q.mutable_claim_status()->set_operation(loot_ui.pending);network->send(q);loot_retry_at=SDL_GetTicks()+3000;}
            feature_ui.update(release,world,nearest_shop(),shop_open);
            if(!hud->data.movables.empty())for(const auto&e:world.world.entities())if(e.id()==world.world.self()){
              auto scope=endpoint+"\n"+release.game+"\n"+account+"\n"+e.name();
              if(panel_state.identity!=scope){
                // Save the previous character's layout, then restore this one's.
                if(!panel_state.identity.empty())panel_state.save(hud->saved_positions(panel_width,panel_height));
                for(const auto&m:hud->data.movables)hud->panel_offsets.erase(m.panel);
                hud->panel_drag.reset();panel_state.context(scope);hud->restore_positions(panel_state.load(),width,height);
              }
              panel_width=width;panel_height=height;break;
            }
            if(hud->data.hotbar){
              for(const auto&e:world.world.entities())if(e.id()==world.world.self()){
                hotbar.context(endpoint+"\n"+release.game+"\n"+account+"\n"+e.name(),e.id(),release);break;
              }
              // A notice is posted once (PQ-407: the message line keeps a log).
              if(!hotbar.notice.empty()){hud->post_notice(hotbar.notice);hotbar.notice.clear();}
              hotbar.skill_cooldowns(release,world,SDL_GetTicks()/1000.);
              hotbar.tick(world,SDL_GetTicks()/1000.);
              hotbar.update(feature_ui,release,world);hud->cooldowns.clear();
              for(unsigned i=0;i<8;++i){auto it=hotbar.timers.find(hotbar.assignments[hotbar.page*8+i]);
                if(it!=hotbar.timers.end()){const auto&t=it->second;hud->cooldowns["hotbar:"+std::to_string(i)]={float(std::clamp(1-(SDL_GetTicks()/1000.-t.start)/t.duration,0.,1.)),t.flash};}
              }
            }
            skills_ui.update(feature_ui,release,world);
            loot_ui.values(feature_ui,release);
            float scale=hud->scale(width,height);
            hud->panel_offsets[9]={std::clamp(loot_ui.x,0.f,std::max(0.f,width-104*scale)),std::clamp(loot_ui.y,0.f,std::max(0.f,height-152*scale))};
            hud->values=feature_ui.values;hud->items=feature_ui.items;hud->tooltips=feature_ui.tooltips;hud->meters=feature_ui.meters;hud->colors=feature_ui.colors;
            if(!world.party.invitation()||!party_open)hud->values["selection"]=feature_ui.selection+"\n"+(friends_open?world.friend_status:party_open?world.party_status:bank_open?world.storage_status:world.bag_status);
            hud->input_panel=(bank_secret||feature_ui.prompt)?8:0;
            hud->panels=1u|(bag_open&&!bank_open&&!shop_open?2u:0u)|(equipment_open?4u:0u)|(shop_open?8u:0u)|(bank_open?16u:0u)|(friends_open?32u:0u)|(party_open?64u:0u)|(features_open?128u:0u)|(loot_ui.encounter&&!hud->input_panel?512u:0u)|(skills_ui.open?1024u:0u);
            if(bank_secret||feature_ui.prompt){hud->panels|=256u;hud->values["prompt_title"]=bank_secret?bank_prompt:feature_ui.prompt->title;hud->values["prompt_input"]=bank_secret?std::string(std::min<size_t>(32,text_entry.size()),'*'):text_entry;}
          }
          hud->running = running;
          hud->sitting=false;for(const auto&e:world.world.entities())if(e.id()==world.world.self())hud->sitting=e.sitting();
          hud->moving = movement_intent[0] != 0 || movement_intent[2] != 0;
          hud->primary_active = melee.target != 0 && melee.attack;
          if (!window_focused || orbit_drag || (entry != 4 && !(uif_dialogs&&entry==5&&(bank_secret||feature_ui.prompt)))) hud->cancel_pointer();
#if TOOLS
          if (editor.capture() || ImGui::GetIO().WantCaptureMouse) hud->cancel_pointer();
#endif
          {
            // PQ-408: a held scroll button repeats on every frame (00403c80).
            const uint64_t ns=SDL_GetTicksNS();
            hud->message_frame(message_frame_ns?float(double(ns-message_frame_ns)/1e9):0.f,width,height);
            message_frame_ns=ns;
          }
          glBindVertexArray(vao);
          glBindBuffer(GL_ARRAY_BUFFER, vbo);
          glUseProgram(p);
          glUniform1f(glGetUniformLocation(p, "gui"), 1);
          hud->render(world, target, (bank_secret||feature_ui.prompt)?4:entry, (bank_secret||feature_ui.prompt)?std::string():text_entry, width, height,
            [&](const n3e::HudPortrait&view,const std::array<float,4>&rect){
              if(player_scenes.empty())return;
              auto vertices=portrait_vertices(player_scenes.front(),time,view,rect,width,height);
              bool native=detail&&!detail->appearances.empty();
              if(native){
                vertices.clear();const auto& model=player_scenes.front();float duration=0;
                for(const auto&t:model.tracks)duration=std::max(duration,t.keys.back().time);
                auto pose=model.sample(duration>0?std::fmod(time,duration):0);
                std::vector<uint32_t> keys;
                for(const auto&e:world.world.entities())if(e.id()==world.world.self())keys.assign(e.appearance().begin(),e.appearance().end());
                n3e::draw_appearance(*detail,release.appearance,keys,0,[&](const n3e::DetailMesh&mesh,std::span<const uint32_t> indices){
                  auto posed=mesh.scene.skin(pose,indices);
                  for(size_t i=0;i<indices.size();++i){vertices.insert(vertices.end(),posed.begin()+i*8,posed.begin()+i*8+8);
                    vertices.insert(vertices.end(),{.5f,.5f,native_textures.slots.at(mesh.slots.at(indices[i])),native_textures.slots[0]});}
                });
                auto base=model.skin(model.sample(0));base.resize(model.indices.size()*8);
                vertices=project_portrait(std::move(vertices),base,view,rect,width,height,12);
              }
              if(vertices.empty())return;
              int left=std::clamp(int(std::floor(rect[0])),0,width),right=std::clamp(int(std::ceil(rect[2])),0,width);
              int top=std::clamp(int(std::floor(rect[1])),0,height),bottom=std::clamp(int(std::ceil(rect[3])),0,height);
              glEnable(GL_SCISSOR_TEST);glScissor(left,height-bottom,right-left,bottom-top);
              glClear(GL_DEPTH_BUFFER_BIT);glEnable(GL_DEPTH_TEST);glDisable(GL_CULL_FACE);
              glUniform1f(glGetUniformLocation(p,"gui"),native?3:2);
              glUniform1f(glGetUniformLocation(p,"native_detail"),native?1:0);
              glBindTexture(GL_TEXTURE_2D,player_texture);
              glBufferData(GL_ARRAY_BUFFER,vertices.size()*sizeof(float),vertices.data(),GL_DYNAMIC_DRAW);
              if(native){
                native_textures.bind();native_textures.sampling(false,world_samplers);
                for(unsigned a=0;a<5;++a){glEnableVertexAttribArray(a);glVertexAttribPointer(a,a<2?3:2,GL_FLOAT,GL_FALSE,12*sizeof(float),(void*)((a==0?0:a==1?3:a==2?6:a==3?8:10)*sizeof(float)));}
              }
              glDrawArrays(GL_TRIANGLES,0,vertices.size()/(native?12:8));
              if(native){
                for(unsigned a=0;a<3;++a)glVertexAttribPointer(a,a<2?3:2,GL_FLOAT,GL_FALSE,8*sizeof(float),(void*)((a==0?0:a==1?3:6)*sizeof(float)));
                glDisableVertexAttribArray(3);glDisableVertexAttribArray(4);
              }
              glDisable(GL_SCISSOR_TEST);glEnable(GL_CULL_FACE);
              glUniform1f(glGetUniformLocation(p,"gui"),1);
            });
#if N3E_HARNESS
          // PQ-469: report each failed line once the HUD has drawn it in its row.
          for (auto at = skill_failed_drawn.begin(); at != skill_failed_drawn.end();)
            if (std::find(hud->messages_drawn.begin(), hud->messages_drawn.end(), *at) != hud->messages_drawn.end()) {
              char color[16];
              std::snprintf(color, sizeof color, "%08x", at->color);
              std::cout << "SKILL_FAILED_DRAWN text='" << at->text << "' color=" << color << std::endl;
              at = skill_failed_drawn.erase(at);
            } else
              ++at;
#endif
        } else
          play_hud(world, target, entry, bank_secret?std::string():text_entry, width, height, legacy_key_hint, release.names.operator_chat, discord_flow != nullptr);
        // Spec 02: a session the server ended in the world says why (an operator's kick).
        if (entry >= 4 && network && !world.connected)
          hud_text(world.status.substr(0, size_t(std::max(1, (width - 32) / 12))), 16, height / 2, height, 1, .4f, .3f);
        if (entry >= 4 && !hud && !operator_line.empty())
          hud_text(operator_line.substr(0, 42), 28, height - 230, height, 1, 1, 0);
        if (entry >= 4 && std::chrono::steady_clock::now() < banner_until) {
          const auto line = banner.substr(0, size_t(std::max(1, (width - 32) / 12)));
          hud_text(line, (width - int(line.size()) * 12) / 2, height / 3, height, 1, .85f, .2f);
        }
        if (!uif_dialogs && release.melee && entry == 4)
          hud_text(std::string("Melee: ") + melee.state +
                       " | " + input_map.labels(n3e::input::Action::attack_toggle) + ": start-stop",
                   hud ? 60 : 18, 145, height);
        if (!uif_dialogs && entry >= 4 && release.movement) {
          const char *label = move_mode == 2 ? "BACKWARD"
                              : running      ? "RUN"
                                             : "WALK";
          hud_text(std::string("MODE ") + label + "  V WALK/RUN  S BACKWARD",
                   18, 112, height);
        }
        if (entry >= 4 && (!hud||!hud->data.nameplates))
          for (const auto &entity : world.world.entities()) {
            if (entity.id() == world.world.self() ||
                !name_display.visible(entity.npc(), false,
                                      !entity.npc() && std::any_of(world.party.members().begin(), world.party.members().end(),
                                                                   [&](const auto &m) { return m.entity() == entity.id(); })) ||
                (!entity.npc() && !name_lifetime.labelled(entity.id())) ||
                (entity.npc() && !npc_name_lifetime.labelled(entity.id())))
              continue;
            // Without a nameplate style the label stands at a fixed height,
            // an NPC's times its drawn scale (PQ-272), as KO's name height
            // multiplies by it (00459820).
            const float label_height = entity.npc() ? legacy_npc_label_height * drawn_scale(entity) : 1.9f;
#if N3E_HARNESS
            // PQ-272 (N3E_TEST_NPC_LOOKS=1): once per NPC, the height its
            // label is drawn at.
            if (entity.npc() && std::getenv("N3E_TEST_NPC_LOOKS")) {
              static std::set<uint64_t> reported;
              if (reported.insert(entity.id()).second)
                std::cout << "NPC_LABEL entity=" << entity.id() << " height=" << label_height << " style=0\n";
            }
#endif
            auto q = orbit.project({entity.x(), entity.y() + label_height, entity.z()}, width, height);
            if (q[2] > .1f && q[0] > 0 && q[0] < width - 100 && q[1] > 120 &&
                q[1] < height - 195) {
              hud_text((entity.id() == target ? "> " : "") +
                           display_name(entity.name()),
                       int(q[0]) - 30, int(q[1]), height);
              // The NPC info line (PQ-177), one text line above the label.
              const auto &info = release.names.npc_info;
              bool informed = entity.npc() && info && npc_name_lifetime.informed(entity.id());
              auto traced = world.npc_states.find(entity.id());
              auto text = informed ? n3e::npc_info_line(*info, entity.id(),
                                                        traced == world.npc_states.end() ? std::string() : traced->second)
                                   : std::string();
#if N3E_HARNESS
              if (entity.npc())
                npc_info_seen(text, traced != world.npc_states.end());
#endif
              if (informed)
                hud_text(text, int(q[0]) - 30, int(q[1]) - 18, height,
                         (info->color >> 16 & 255) / 255.f, (info->color >> 8 & 255) / 255.f,
                         (info->color & 255) / 255.f);
            }
          }
        if (release.protocol >= 5 && entry >= 4) {
          if(!uif_dialogs)hud_text("F CLAIM NEAREST | DROPS " + std::to_string(world.loot.drops_size()) + " | " + world.loot_status, 18, 170, height);
          std::set<uint64_t> bundles;
          for (const auto &drop : world.loot.drops()) {
            if(release.loot_model)continue;
            if(uif_pickup&&!bundles.insert(drop.encounter()).second)continue;
            auto q=orbit.project({drop.x(),drop.y()+.3f,drop.z()},width,height);
            if (q[2]>.1f && q[0]>0 && q[0]<width-120 && q[1]>190 && q[1]<height-195)
              hud_text(uif_pickup?loot_key_hint:"LOOT: " + display_name(drop.item()),int(q[0])-30,int(q[1]),height);
          }
        }
        if (release.requested_respawn && entry >= 4)
          life_hud(world, width, height, input_map.label(n3e::input::Action::respawn));
        if(release.commerce && entry>=4) {
          for(const auto &shop:release.commerce->shops) {
            auto q=orbit.project({shop.position[0],shop.position[1]+1,shop.position[2]},width,height);
            if((!uif_dialogs||!(bag_open||equipment_open||friends_open||party_open||features_open))&&q[2]>.1f&&q[0]>0&&q[0]<width-100&&q[1]>210&&q[1]<height-195)hud_text(shop.label+" | /shop",int(q[0])-30,int(q[1]),height);
          }
          if(!uif_dialogs&&bank_open&&bag_open&&release.storage){
            int x=18,y=445,h=release.storage_auth?266:244;glEnable(GL_SCISSOR_TEST);glScissor(x-8,std::max(0,height-y-h),std::max(0,std::min(width-x,780)),h);glClearColor(.02f,.025f,.03f,1);glClear(GL_COLOR_BUFFER_BIT);glDisable(GL_SCISSOR_TEST);
            hud_text("ACCOUNT STORAGE | "+std::to_string(world.storage.coins())+" COIN | "+world.storage_status,x,y,height);
            for(unsigned row=0;row<8;++row){unsigned j=bag_page*8+row;if(j>=unsigned(world.storage.slots_size()))break;
              const auto &i=world.storage.slots(j);std::string label="Empty";
              if(i.instance()){auto d=std::find_if(release.inventory->items.begin(),release.inventory->items.end(),[&](const auto &d){return d.id==i.item();});label=d->label+" x"+std::to_string(i.quantity())+" | Durability "+std::to_string(i.durability());}
              hud_text(std::to_string(j+1)+": "+label,x,y+22+int(row)*20,height);
            }
            hud_text("/deposit BAG BANK QTY | /withdraw BANK BAG QTY",x,y+190,height);
            hud_text("/bankmove A B | /bankcoins QTY | /takecoins QTY",x,y+212,height);
            if(release.storage_auth)hud_text(world.storage_auth_status+" | /bankunlock /bankpassword",x,y+234,height);
          }
          if(!uif_dialogs&&shop_open&&bag_open) {
            const auto *shop=nearest_shop();int x=18,y=445;
            glEnable(GL_SCISSOR_TEST);glScissor(x-8,std::max(0,height-y-230),std::min(width-x,660),230);glClearColor(.02f,.025f,.03f,1);glClear(GL_COLOR_BUFFER_BIT);glDisable(GL_SCISSOR_TEST);
            hud_text(shop->label+" | /buy OFFER SLOT QTY | /sell SLOT QTY",x,y,height);
            for(unsigned j=0;j<8&&bag_page*8+j<shop->items.size();++j) {
              auto index=bag_page*8+j;const auto &id=shop->items[index];std::string label;unsigned price=0;
              for(const auto &i:release.inventory->items)if(i.id==id)label=i.label;
              for(const auto &i:release.commerce->items)if(i.item==id)price=i.price;
              hud_text(std::to_string(index+1)+": "+label+" | buy "+std::to_string(price),x,y+24+j*20,height);
            }
          }
        }
        if(release.inventory && entry>=4) {
          if(!uif_dialogs)hud_text("I INVENTORY | ENTER /bag, /swap 1 2, /retry",18,192,height);
          if(!uif_dialogs&&bag_open&&equipment_open&&release.equipment){
            int x=18,y=460;
            int panel=50+20*std::min(8,int(release.equipment->slots.size()))+(world.world.has_stats()?60:0);
            glEnable(GL_SCISSOR_TEST);glScissor(x-8,std::max(0,height-y-panel),std::max(0,std::min(width-x,800)),panel);
            glClearColor(.02f,.025f,.03f,1);glClear(GL_COLOR_BUFFER_BIT);glDisable(GL_SCISSOR_TEST);
            hud_text("EQUIPMENT | /equip BAG SLOT | /unequip SLOT BAG",x,y,height);
            hud_text("/gearswap A B | /repairgear SLOT",x,y+20,height);
            if(world.world.has_stats()&&world.world.stats().equipment_revision()==world.bag.revision()) {
              const auto &s=world.world.stats();int sy=y+44+20*std::min(8,int(release.equipment->slots.size()));
              hud_text("Attack "+std::to_string(s.attack())+" | Defense "+std::to_string(s.defense())+" | HP "+std::to_string(s.max_health())+" | Resource "+std::to_string(s.max_resource())+" | Carry "+std::to_string(s.carry_limit()),x,sy,height);
              hud_text("Accuracy "+std::to_string(s.accuracy())+" | Evasion "+std::to_string(s.evasion()),x,sy+20,height);
              std::string attributes="Attributes";for(auto a:s.attributes())attributes+=" | "+std::to_string(a);hud_text(attributes,x,sy+40,height);
            }else if(world.world.has_stats())hud_text("Updating stats...",x,y+44+20*std::min(8,int(release.equipment->slots.size())),height);
            for(unsigned j=0;j<release.equipment->slots.size();++j){
              std::string label="Empty";
              if(j<unsigned(world.bag.equipment_size())){
                const auto &s=world.bag.equipment(j);uint32_t maximum=0,price=0;
                for(const auto&i:release.inventory->items)if(i.id==s.item()){label=i.label+" | durability "+std::to_string(s.durability());maximum=i.durability;}
                if(release.commerce&&release.commerce->repair){const auto&r=*release.commerce->repair;
                  for(const auto&i:release.commerce->items)if(i.item==s.item())price=i.price;
                  if(std::find(r.items.begin(),r.items.end(),s.item())!=r.items.end())if(auto cost=r.cost(price,s.durability(),maximum))label+=" | repair "+std::to_string(*cost);
                }
              }
              hud_text(std::to_string(j+1)+": "+release.equipment->slots[j]+" - "+label,x+(j/8)*500,y+42+(j%8)*20,height);
            }
          }
          if(bag_open&&!uif_dialogs) {
            int x=18,y=220;
            glEnable(GL_SCISSOR_TEST); glScissor(x-8,std::max(0,height-y-224),std::min(width-x,660),224);
            glClearColor(.02f,.025f,.03f,1); glClear(GL_COLOR_BUFFER_BIT); glDisable(GL_SCISSOR_TEST);
            hud_text("INVENTORY | "+std::to_string(world.bag.coins())+" "+display_name(release.inventory->currency)+" | "+world.bag_status,x,y,height);
            for(unsigned row=0;row<8;++row) {
              unsigned index=bag_page*8+row; if(index>=unsigned(world.bag.slots_size())) break;
              const auto &slot=world.bag.slots(index); std::string label="Empty";
              if(slot.instance()) {
                for(const auto &item:release.inventory->items) if(item.id==slot.item()) label=item.label;
                label+=" x"+std::to_string(slot.quantity())+" | durability "+std::to_string(slot.durability());
                if(release.commerce&&release.commerce->repair) {
                  const auto &repair=*release.commerce->repair;
                  if(std::find(repair.items.begin(),repair.items.end(),slot.item())!=repair.items.end()) {
                    uint32_t price=0,maximum=0;
                    for(const auto &i:release.commerce->items)if(i.item==slot.item())price=i.price;
                    for(const auto &i:release.inventory->items)if(i.id==slot.item())maximum=i.durability;
                    if(auto cost=repair.cost(price,slot.durability(),maximum))label+=" | repair "+std::to_string(*cost);
                  }
                }
              }
              hud_text(std::to_string(index+1)+": "+label,x,y+22+row*20,height);
            }
            hud_text("[ / ] PAGE "+std::to_string(bag_page+1)+(release.equipment?" | /equipment | /repair SLOT":release.commerce&&release.commerce->repair?" | /repair SLOT":" | slots numbered from 1"),x,y+190,height);
          }
        }
        if(!uif_dialogs&&party_open&&release.party&&entry>=4){int x=18,y=220;panel(x,y,std::min(720,width-36),332,height);
          hud_text("PARTY "+std::to_string(world.party.members_size())+"/"+std::to_string(release.party->capacity)+" | "+(world.party.invitation()?"INVITATION":world.party.members_size()>1?"ACTIVE":world.party.group()?"FORMING":"NO PARTY"),x+12,y+14,height);
          int row=0;for(const auto&m:world.party.members()){hud_text(std::string(m.character()==world.party.leader()?"* ":"  ")+m.name()+" LV"+std::to_string(m.level())+" HP "+std::to_string(m.health())+"/"+std::to_string(m.max_health())+" MP "+std::to_string(m.resource())+"/"+std::to_string(m.max_resource()),x+12,y+40+20*row++,height);}
          if(world.party.invitation())hud_text(world.party.inviter_name()+" invites you: /accept or /decline",x+12,y+208,height);
          else if(!world.party.group())hud_text("No party. /invite NAME",x+12,y+208,height);
          hud_text("/invite NAME | /kick NAME | /leave | /disband",x+12,y+238,height);
          hud_text(std::string("/partyblock | INVITATIONS ")+(party_block?"BLOCKED":"ALLOWED"),x+12,y+264,height);
          hud_text("/partyhide | Last: "+world.party_status,x+12,y+290,height);
        }
        if(!uif_dialogs&&friends_open&&release.friends&&entry>=4){int x=18,y=220;panel(x,y,std::min(660,width-36),252,height);
          hud_text("FRIENDS "+std::to_string(world.friends.entries_size())+"/"+std::to_string(release.friends->capacity)+" | "+world.friend_status,x+12,y+14,height);
          for(unsigned row=0;row<8;++row){unsigned slot=friend_page*8+row;if(slot>=release.friends->capacity)break;std::string text="Empty";
            for(const auto &e:world.friends.entries())if(e.slot()==slot){std::string state="Updating";for(const auto &p:world.friend_presence.entries())if(p.name()==e.name())state=p.online()&&p.character()==e.character()?(p.in_party()?"Online / Party":"Online"):"Offline";text=e.name()+" | "+state;}
            hud_text(std::to_string(slot+1)+": "+text,x+12,y+40+row*19,height);}
          hud_text("/friend NAME /unfriend NAME /friendretry",x+12,y+206,height);hud_text("[ / ] PAGE "+std::to_string(friend_page+1)+" | /friendhide",x+12,y+230,height);
        }
        if(!uif_dialogs&&entry>=4&&release.inventory){
          int y=220;for(const auto &[action,label]:feature_buttons()){panel(width-178,y,168,26,height);hud_text(label,width-170,y+8,height);y+=28;}
        }
        if(!uif_dialogs&&features_open&&entry>=4){int x=18,y=220;panel(x,y,std::min(790,width-214),330,height);
          std::vector<std::string> lines={"FEATURE HELP | ENTER TO TYPE A COMMAND", "I or Inventory: view bag; [ ] change page", "/swap 1 2 | /equip 1 1 | /unequip 1 10", "/repair 1 | /repairgear 1", "Shop: /buy OFFER BAG QTY | /sell BAG QTY", "Warehouse: Unlock bank, then Warehouse", "/deposit BAG BANK QTY | /withdraw BANK BAG QTY", "/bankcoins QTY | /takecoins QTY | /bankpassword", "/w NAME MESSAGE | /friend NAME | /unfriend NAME", "/invite NAME | /accept | /leave | /disband", help_keys[0], help_keys[1], cancel_hint};
          for(size_t i=0;i<lines.size();++i)hud_text(lines[i],x+12,y+14+22*i,height);
        }
        if(entry==5&&!bank_secret&&!feature_ui.prompt&&release.inventory){
          panel(18,height-104,width-36,38,height);auto shown=text_entry;size_t limit=std::max(1,(width-90)/12);
          if(shown.size()>limit)shown=shown.substr(shown.size()-limit);
          hud_text("> "+shown,30,height-92,height);
        }
        if(bank_secret&&!uif_dialogs){int x=std::max(10,(width-720)/2),y=std::max(10,(height-124)/2);panel(x,y,std::min(720,width-20),124,height);
          hud_text(bank_prompt.substr(0,55),x+20,y+18,height);hud_text(std::string(std::min<size_t>(48,text_entry.size()),'*'),x+20,y+53,height);hud_text("ENTER CONTINUE / ESC CANCEL",x+20,y+94,height);}
#if TOOLS
        ImGui::Render();ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
#endif
        profile_mark(5);
        draw_fps();
#if N3E_HARNESS
        // The replays read the frame just drawn and queue the next input.
#include "harness/feature_replays.inc"
#include "harness/uif_replays.inc"
#include "harness/field_replays.inc"
#endif
      }
      if (!network) draw_fps();
#if N3E_HARNESS
      if (frame == 40 && !capture_path.empty() && !world_smoke)
        capture(capture_path, width, height);
      if(!capture_path.empty()&&!attachment_capture_at.empty()&&attachment_self_drawn>=attachment_capture_at.back()){
        std::ostringstream name;name<<capture_path<<".attachment-"<<attachment_capture_at.back()<<".ppm";
        capture(name.str(),width,height);
        std::cout<<"ATTACHMENT_CAPTURE at="<<attachment_capture_at.back()<<" drawn="<<attachment_self_drawn<<" path="<<name.str()<<std::endl;
        capture_camera(attachment_capture_at.back());
        for(const auto&box:attached_boxes)
          std::cout<<"ATTACHMENT_BOX at="<<attachment_capture_at.back()<<" entity="<<box.entity<<" self="<<box.self<<" entry="<<box.entry
                   <<" box="<<int(std::floor(box.x0))<<","<<int(std::floor(box.y0))<<","<<int(std::ceil(box.x1))<<","<<int(std::ceil(box.y1))<<std::endl;
        for(const auto&box:attached_part_boxes)
          std::cout<<"ATTACHMENT_PART_BOX at="<<attachment_capture_at.back()<<" entity="<<box.entity<<" self="<<box.self<<" key="<<box.key
                   <<" box="<<int(std::floor(box.x0))<<","<<int(std::floor(box.y0))<<","<<int(std::ceil(box.x1))<<","<<int(std::ceil(box.y1))<<std::endl;
        attachment_capture_at.pop_back();
      }
      if(part_state_follow.left>0){
        // PQ-348: the frames after a glow capture, the states ignored, then drawn.
        const std::string path=part_state_follow.base+(part_state_follow.left==2?".ignored.ppm":".again.ppm");
        capture(path,width,height);
        std::cout<<"PART_STATE_COMPARE at="<<part_state_follow.at<<" mode="<<(part_state_follow.left==2?"ignored":"again")
                 <<" path="<<path<<std::endl;
        --part_state_follow.left;
      }
      if(!capture_path.empty()&&!glow_capture_at.empty()&&glow_self_first>=0){
        double drawn=std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count()-glow_self_first;
        if(drawn>=glow_capture_at.back()){
          std::ostringstream name;name<<capture_path<<".glow-"<<glow_capture_at.back()<<".ppm";
          capture(name.str(),width,height);
          std::cout<<"EQUIPMENT_GLOW_CAPTURE at="<<glow_capture_at.back()<<" drawn="<<drawn<<" path="<<name.str()<<std::endl;
          capture_camera(glow_capture_at.back());
          for(const auto&box:glow_boxes)
            std::cout<<"EQUIPMENT_GLOW_BOX at="<<glow_capture_at.back()<<" entity="<<box.entity<<" self="<<box.self<<" key="<<box.key
                     <<" box="<<int(std::floor(box.x0))<<","<<int(std::floor(box.y0))<<","<<int(std::ceil(box.x1))<<","<<int(std::ceil(box.y1))<<std::endl;
          // PQ-348: each small state range's drawn corners, in draw order.
          for(const auto&c:part_corners){
            std::cout<<"PART_STATE_CORNERS at="<<glow_capture_at.back()<<" entity="<<c.entity<<" self="<<c.self<<" key="<<c.key<<" corners=";
            for(size_t i=0;i<c.corners.size();++i)std::cout<<(i?";":"")<<c.corners[i][0]<<","<<c.corners[i][1];
            std::cout<<std::endl;
          }
          if(part_state_compare)part_state_follow={name.str(),glow_capture_at.back(),2};
          glow_capture_at.pop_back();
        }
      }
#endif
      if (glGetError() != GL_NO_ERROR)
        throw std::runtime_error("GL error");
      profile_mark(6);
      SDL_GL_SwapWindow(w);
#if N3E_HARNESS
      if (offscreen) {
        // The next 60 Hz vertical blank a display would have waited for.
        const uint64_t now = SDL_GetTicksNS(), since = now - offscreen_origin;
        SDL_DelayPrecise(offscreen_vblank_ns - since % offscreen_vblank_ns);
      }
#endif
      profile_mark(7);
      if(profile_frames&&++profile_count==120){
        const char*names[]={"input","network+sim","entities+verts","world","world-tail","overlay","ui+scripts","swap"};
        std::cout<<"PROFILE "<<fps_label<<" entities="<<world.world.entities_size()<<" pos="<<world.predicted[0]<<","<<world.predicted[2];
        for(int i=0;i<8;++i){std::cout<<" "<<names[i]<<"="<<profile_sum[i]/profile_count;profile_sum[i]=0;}
        std::cout<<"\n"<<std::flush;profile_count=0;
      }
      ++fps_frames;
#if N3E_HARNESS
      if (movement_smoke || controls_smoke || melee_smoke || npc_observe || life_smoke) {
        if (const char *delay = std::getenv("N3E_TEST_FRAME_MS"))
          SDL_Delay(std::clamp(std::atoi(delay), 1, 50));
      }
#endif
      // Automated modes keep the fixed 10 ms pacing their frame-numbered stages
      // were tuned against. Play is paced by vsync and only yields without it.
      if (smoke || world_smoke)
        SDL_Delay(10);
      else if (!vsync)
        SDL_Delay(1);
      ++frame;
#if N3E_HARNESS
      // A streamed world capture waits for its chunks, up to 600 frames more.
      if (smoke && frame == smoke_quit && world_stream && (std::getenv("N3E_TEST_WORLD_LOD") || std::getenv("N3E_TEST_WORLD_OVERLAY")) &&
          !capture_path.empty() && !world_sampling_captured) {
        if (frame >= 50 + world_path_frames + 600) throw std::runtime_error("world stream did not settle");
        ++smoke_quit;
      } else if (smoke && frame == smoke_quit) {
        SDL_Event quit{};
        quit.type = SDL_EVENT_QUIT;
        SDL_PushEvent(&quit);
      }
      if (smoke && frame > smoke_quit + 10)
        throw std::runtime_error("quit event not processed");
#endif
    }
    // Normal exit saves the draggable panel layout (00645ea0).
    if(hud&&!panel_state.identity.empty()&&!panel_state.save(hud->saved_positions(panel_width,panel_height)))
      std::cerr<<"could not save panel positions\n";
#if N3E_HARNESS
    if (smoke && std::getenv("N3E_TEST_TEXTURE_BANKS")) check_texture_bank(p);
    std::cout << "events resize=" << resized << " minimize=" << minimized
              << " restore=" << restored << " focus=" << focus_checked
              << " frames=" << frame << "\n";
#endif
#if TOOLS
    ImGui_ImplOpenGL3_Shutdown();
    ImGui_ImplSDL3_Shutdown();
    ImGui::DestroyContext();
#endif
    hud.reset();
    glDeleteSamplers(2, world_samplers);
    glDeleteTextures(1, &world_texture);
    for (auto &b : world_buffers) {
      glDeleteBuffers(1, &b.vbo);
      glDeleteBuffers(1, &b.ebo);
      glDeleteVertexArrays(1, &b.vao);
    }
    native_textures.destroy();
    world_banks.destroy();
    audio.close();
    effect_view.destroy();
    postprocess.destroy();
    if(detail_vao)glDeleteVertexArrays(1,&detail_vao);
    if(detail_vbo)glDeleteBuffers(1,&detail_vbo);
    if(!marker_textures.empty())glDeleteTextures(marker_textures.size(),marker_textures.data());
    if(loot_texture)glDeleteTextures(1,&loot_texture);
    if (player_texture)
      glDeleteTextures(1, &player_texture);
    if (!looks_textures.empty())
      glDeleteTextures(GLsizei(looks_textures.size()), looks_textures.data());
    glDeleteTextures(1, &texture);
    glDeleteBuffers(1, &vbo);
    glDeleteVertexArrays(1, &vao);
    glDeleteProgram(p);
    SDL_GL_DestroyContext(ctx);
    SDL_DestroyWindow(w);
    SDL_Quit();
    return exit_code;
  } catch (const std::exception &e) {
    std::cerr << "viewer: " << e.what() << "\n";
    SDL_Quit();
    return 1;
  }
}
