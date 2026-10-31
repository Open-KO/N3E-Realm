#include <algorithm>
#include "assets/assets.h"
#include "assets/world_stream.h"
#include "render/target_marker.h"
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
int main(int argc, char **argv) {
  try {
    if (argc >= 4 && std::string(argv[2]) == "--looks") {
      // --looks i [t ...] (PQ-283): looks entry i's idle clip skinned by the
      // client (Scene::skin) at each time t in seconds (default 0, 0.25,
      // 0.5, 0.75 and 1); one line per time: the time, then x y z of every
      // mesh output vertex in draw order.
      auto r = n3e::load_release(argv[1]);
      size_t end = 0;
      auto index = std::stoul(argv[3], &end);
      if (end != std::string(argv[3]).size()) throw std::runtime_error("looks index");
      std::vector<float> times{0.f, .25f, .5f, .75f, 1.f};
      if (argc > 4) times.clear();
      for (int i = 4; i < argc; ++i) {
        times.push_back(std::stof(argv[i], &end));
        if (end != std::string(argv[i]).size() || !std::isfinite(times.back()) || times.back() < 0)
          throw std::runtime_error("looks time");
      }
      auto clips = n3e::load_npc_looks(r, index);
      std::cout << std::setprecision(9);
      for (float t : times) {
        auto out = clips[0].skin(clips[0].sample(t));
        std::cout << t;
        for (size_t v = 0; v < clips[0].indices.size(); ++v)
          std::cout << ' ' << out[v * 8] << ' ' << out[v * 8 + 1] << ' ' << out[v * 8 + 2];
        std::cout << "\n";
      }
      return 0;
    }
    if (argc != 2 && argc != 6 && argc != 8 && argc != 11)
      throw std::runtime_error("asset-check package");
    auto r = n3e::load_release(argv[1]);
    if (argc == 11) {
      // --stream x0 y0 z0 x1 y1 z1 steps reach (PQ-232): the N3W2 streamer
      // without GL, along a straight camera path, settling at each step.
      if (std::string(argv[2]) != "--stream" || !r.world_chunked) throw std::runtime_error("stream needs an N3W2 world");
      float v[8];
      for (int i = 0; i < 8; ++i) { v[i] = std::stof(argv[3 + i]); if (!std::isfinite(v[i])) throw std::runtime_error("stream number"); }
      const int steps = int(v[6]);
      if (steps < 1 || steps > 100000 || v[7] <= 0) throw std::runtime_error("stream steps/reach");
      n3e::WorldTable table;
      auto index = n3e::load_world_index(r, table);
      n3e::WorldStream stream(std::move(table), index.terrain);
      for (int step = 0; step <= steps; ++step) {
        const float t = float(step) / steps;
        const n3e::V eye{v[0] + (v[3] - v[0]) * t, v[1] + (v[4] - v[1]) * t, v[2] + (v[5] - v[2]) * t};
        int spins = 0;
        do {
          stream.update(eye, v[7]);
          if (!stream.settled()) std::this_thread::sleep_for(std::chrono::milliseconds(1));
        } while (!stream.settled() && ++spins < 60000);
        if (!stream.settled()) throw std::runtime_error("stream did not settle");
        const auto &s = stream.stats();
        std::cout << "WORLD_STREAM step=" << step << " eye=" << eye[0] << "," << eye[2] << " resident=" << s.resident
                  << " bytes=" << s.bytes << " wanted=" << s.wanted << " limited=" << s.limited
                  << " uploaded=" << s.uploaded << " evicted=" << s.evicted << "\n";
      }
      const auto &s = stream.stats();
      std::cout << "WORLD_STREAM_MAX resident=" << s.max_resident << " bytes=" << s.max_bytes << " limits="
                << n3e::STREAM_CHUNKS << " " << n3e::STREAM_BYTES << " chunks=" << stream.table().entries.size() << "\n";
      return 0;
    }
    if (argc == 8) {
      // --marker x0 z0 x1 z1 steps (PQ-235): the target marker's ground parts
      // along a straight path on an N3W2 world, built from the ground the
      // client uses (target_marker_ground) and from the all-resident world's
      // full-detail terrain parts; prints the largest height difference. The
      // package's marker, or a synthetic one (NPC bounds 2 x 3 m) without one.
      if (std::string(argv[2]) != "--marker" || !r.world_chunked) throw std::runtime_error("marker path needs an N3W2 world");
      float v[5];
      for (int i = 0; i < 5; ++i) { v[i] = std::stof(argv[3 + i]); if (!std::isfinite(v[i])) throw std::runtime_error("marker number"); }
      const int steps = int(v[4]);
      if (steps < 1 || steps > 100000) throw std::runtime_error("marker steps");
      auto scene = n3e::load_scene(r);
      n3e::Scene streamed, whole;
      streamed.collision = n3e::target_marker_ground(scene.collision, true, nullptr);
      whole.collision = n3e::world_terrain_ground(n3e::load_world(r));
      n3e::TargetMarker synthetic{2, 1.3f, .1f, {{{1, 2}, {2, 3}}}, {}};
      if (!r.target_marker) {
        n3e::TargetMarkerPart part{};
        part.vertices = {{{-.5f, 0, -.5f, 0, 1, 0, 0, 0}}, {{.5f, 0, -.5f, 0, 1, 0, 1, 0}},
                         {{.5f, 0, .5f, 0, 1, 0, 1, 1}}, {{-.5f, 0, .5f, 0, 1, 0, 0, 1}}};
        part.indices = {0, 1, 2, 0, 2, 3};
        synthetic.parts.push_back(part);
      }
      const auto &marker = r.target_marker ? *r.target_marker : synthetic;
      size_t compared = 0, drawn = 0, above = 0;
      double worst = 0;
      for (int step = 0; step <= steps; ++step) {
        const float t = float(step) / steps;
        const n3e::V at{v[0] + (v[2] - v[0]) * t, 0, v[1] + (v[3] - v[1]) * t};
        for (const auto &part : marker.parts) {
          if (part.mode != 0) continue;
          auto a = n3e::target_marker_vertices(marker, part, true, 1, at, {at[0], 30, at[2] + 10}, streamed);
          auto b = n3e::target_marker_vertices(marker, part, true, 1, at, {at[0], 30, at[2] + 10}, whole);
          if (a.size() != b.size()) throw std::runtime_error("marker ground coverage differs at step " + std::to_string(step));
          drawn += !a.empty();
          for (size_t i = 0; i < a.size(); i += 8) {
            for (int k = 0; k < 8; ++k) worst = std::max(worst, double(std::abs(a[i + k] - b[i + k])));
            ++compared;
            // The collision surface with objects stands above the marker here.
            above += scene.collision.ground_height(a[i], a[i + 2]) > a[i + 1] + .5f;
          }
        }
      }
      std::cout << "MARKER_PATH steps=" << steps << " drawn=" << drawn << " vertices=" << compared
                << " objects_above=" << above << " max_diff=" << std::setprecision(9) << worst << "\n";
      return 0;
    }
    if(argc==6) {
      if(std::string(argv[2])!="--repair-cost"||!r.commerce||!r.commerce->repair)throw std::runtime_error("repair quote requires policy");
      uint32_t values[3];for(int i=0;i<3;++i){size_t end=0;auto v=std::stoull(argv[i+3],&end);if(end!=std::string(argv[i+3]).size()||v>4294967295ULL)throw std::runtime_error("quote number");values[i]=uint32_t(v);}
      auto cost=r.commerce->repair->cost(values[0],values[1],values[2]);if(!cost)throw std::runtime_error("invalid repair quote");std::cout<<*cost<<"\n";return 0;
    }
    auto s = n3e::load_scene(r);
    if(r.loot_model)n3e::load_scene(r,"loot-model.bin");
    if(r.skills){auto base=n3e::load_scene(r,"player-idle.bin");for(const auto&skill:r.skills->entries){auto clip=n3e::load_scene(r,"player-skill-"+std::to_string(skill.animation)+".bin");if(!base.compatible(clip))throw std::runtime_error("skill skeleton");for(int joint:skill.cast_joints)if(joint>=int(clip.joints.size()))throw std::runtime_error("skill joint index");clip.animate(.5f);}}
    if (r.presentation) {
      auto hud = n3e::load_hud(r);
      if (hud.target_health != float(r.npc_health))
        throw std::runtime_error("HUD must use gameplay NPC maximum");
      for (const auto *name : {"player-idle.bin", "player-walk.bin",
                               "player-attack.bin", "player-death.bin"}) {
        auto player = n3e::load_scene(r, name);
        for (float t : {0.f, .25f, .5f})
          player.animate(t);
      }
    }
    if (r.animation) {
      for (const char *role : {"player", "npc"}) {
        if (std::string(role) == "npc" && r.animation->size() == 7) continue;
        auto base = n3e::load_scene(r, std::string(role) + "-idle.bin");
        bool npc = std::string(role) == "npc";
        int index = npc ? (r.rest ? 10 : 7) : 0;
        int remaining = npc ? 4 : (r.rest ? 10 : 7);
        for (const char *state :
             {"idle", "walk", "attack", "death", "run", "backward", "ready",
              "sit-down", "sit-idle", "stand-up"}) {
          if (remaining-- == 0)
            break;
          auto clip =
              n3e::load_scene(r, std::string(role) + "-" + state + ".bin");
          if (!base.compatible(clip))
            throw std::runtime_error("incompatible animation skeleton/mesh");
          float duration = 0;
          for (auto &track : clip.tracks)
            duration = std::max(duration, track.keys.back().time);
          if (std::abs(duration - (*r.animation)[index++].duration) > .001f)
            throw std::runtime_error("animation duration mismatch");
        }
      }
    }
    if (!r.npc_looks.empty()) {
      // PQ-253: every looks model, posed in each state; the load is timed
      // (the client parses them all once at start, after the release index).
      auto start = std::chrono::steady_clock::now();
      uint64_t texels = 0;
      size_t vertices = 0;
      for (size_t i = 0; i < r.npc_looks.size(); ++i) {
        auto clips = n3e::load_npc_looks(r, i);
        texels += clips[0].texture.size();
        vertices += clips[0].vertices.size();
        for (const auto &clip : clips) clips[0].skin(clip.sample(0));
      }
      std::cout << "npc looks " << r.npc_looks.size() << " texture_bytes " << texels << " vertices " << vertices
                << " ms " << std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start).count()
                << "\n";
    }
    if (r.attachments) {
      // PQ-328: every attachment model, posed in each state, on a joint the
      // player skeleton has (the client refuses the package otherwise).
      auto player = n3e::load_scene(r, "player-idle.bin");
      uint64_t texels = 0;
      for (size_t i = 0; i < r.attachments->entries.size(); ++i) {
        auto clips = n3e::load_attachment(r, i);
        if (r.attachments->entries[i].joint >= player.joints.size()) throw std::runtime_error("attachment joint");
        texels += clips[0].texture.size();
        for (const auto &clip : clips) clips[0].skin(clip.sample(0));
      }
      std::cout << "attachments " << r.attachments->entries.size() << " texture_bytes " << texels << "\n";
    }
    if(r.combat_animation){
      auto base=n3e::load_scene(r,"player-idle.bin");
      for(auto node:r.combat_animation->upper_nodes)if(node>=base.nodes.size()||std::none_of(base.joints.begin(),base.joints.end(),[&](const auto&j){return j.node==node;}))throw std::runtime_error("combat mask is not a skeleton joint");
      for(size_t i=0;i<r.combat_animation->clips.size();++i){
        auto clip=n3e::load_scene(r,"combat-"+std::to_string(i)+".bin");float duration=0;
        for(const auto&t:clip.tracks)duration=std::max(duration,t.keys.back().time*r.combat_animation->clips[i].stretch);
        if(!base.compatible(clip)||std::abs(duration-r.combat_animation->clips[i].duration)>.001f)throw std::runtime_error("combat animation geometry/duration");
      }
    }
    if (r.ready_pose) {
      auto ready = n3e::load_scene(r, "player-ready.bin");
      for (float t : {0.f, .25f, .5f})
        ready.animate(t);
    }
    if(r.render_detail) {
      auto detail=n3e::load_render_detail(r,n3e::load_scene(r,"player-idle.bin"));
      std::cout << "detail textures=" << detail.textures.size() << " radius=" << detail.radius << " levels=" << detail.levels.size() << " attachments=" << detail.attachments.size() << "\n";
    }
    if (r.world) {
      auto w = n3e::load_world(r);
      size_t vertices = 0, indices = 0, parts = 0, alpha = 0, cut_zero = 0, unlit = 0, single = 0, sequences = 0;
      const n3e::WorldPart *first_alpha = nullptr, *first_sequence = nullptr;
      for (const auto &c : w.chunks) {
        vertices += c.vertices.size() / n3e::WORLD_FLOATS;
        for (size_t i = 11; i < c.vertices.size(); i += n3e::WORLD_FLOATS)
          single += c.vertices[i] == n3e::WORLD_UNLIT_VERTEX;
        indices += c.indices.size();
        parts += c.parts.size();
        for (const auto &p : c.parts) {
          if (p.alpha) { ++alpha; if (!first_alpha) first_alpha = &p; }
          else { cut_zero += p.cut_zero; unlit += p.unlit; }
          if (p.sequence) { ++sequences; if (!first_sequence) first_sequence = &p; }
        }
      }
      std::cout << "world " << w.width << " " << w.height << " "
                << vertices << " " << indices / 3 << "\n";
      if (r.world_chunked)
        std::cout << "world chunks " << w.chunks.size() << " parts " << parts << "\n";
      // PQ-379 (D-201): N3L4 / N3W3 alpha parts, and the first one's record.
      if (alpha) {
        const auto &a = *first_alpha->alpha;
        std::cout << "world alpha parts " << alpha << " first " << a.source << " " << a.destination << " " << a.state
                  << " " << a.sort_point[0] << " " << a.sort_point[1] << " " << a.sort_point[2] << "\n";
      }
      // PQ-382 (D-202): N3L5 / N3W4 opaque parts cut at zero and unlit.
      if (cut_zero || unlit)
        std::cout << "world opaque parts cut-zero " << cut_zero << " unlit " << unlit << "\n";
      // PQ-388 (D-203): N3W5 single-layer unlit vertices.
      if (single)
        std::cout << "world unlit vertices " << single << "\n";
      // PQ-394 (D-212): N3W6 texture sequences, and the first one's record.
      if (sequences) {
        const auto &q = *first_sequence->sequence;
        std::cout << "world sequence parts " << sequences << " first " << q.fps << " frames";
        for (float slot : q.slots) std::cout << " " << slot;
        std::cout << "\n";
      }
      // PQ-387 (D-204): N3WO maps over the near terrain, against its policy.
      if (r.world_overlay) {
        auto o = n3e::load_world_overlay(r, w.terrain);
        std::cout << "world overlay maps " << o.maps.size() << " side " << o.side << " levels " << o.levels
                  << " window " << o.window << " layers " << o.layers() << "\n";
      }
    }
    if (r.world_textures) {
      // N3WT (PQ-233): banks at the full 2048 layers a bank may hold.
      auto t = n3e::load_world_textures(r);
      std::cout << "world textures " << t.chains.size() << " banks "
                << n3e::world_texture_banks(t, n3e::WORLD_TEXTURE_BANK_LAYERS).size() << " pixels " << t.pixels << "\n";
    }
    std::cout << std::setprecision(9) << r.hash << "\n";
    for (float t : {0.f, .25f, .5f, .75f, 1.f}) {
      auto v = s.animate(t);
      std::cout << t;
      for (size_t i : {16u, 17u, 18u, 48u, 49u, 50u})
        std::cout << " " << v.at(i);
      std::cout << "\n";
    }
    for (auto p : {n3e::V{0, 0, 0}, n3e::V{1, 0, 1}, n3e::V{-1, 0, .5}})
      std::cout << "height " << p[0] << " " << p[2] << " "
                << s.ground_height(p[0], p[2]) << "\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << "\n";
    return 1;
  }
}
