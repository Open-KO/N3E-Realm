#pragma once
#include "assets/assets.h"
#include "effects.h"
#include <cmath>
#include <deque>
#include <map>
#include <random>
#include <set>
#include <span>

namespace n3e {
// An EffectMesh (effects.h) is one textured triangle batch for the effect
// pass, in world space: position, UV and RGBA, 9 floats a vertex, as
// effect_vertices writes them.

// N3E2 effects on equipped appearance keys (PQ-211), KO's hand-plug weapon
// effect. KO's plug setter 0045c6e0 loads the main bundle and its tail through
// 00415370; while the WeaponEffect.EffectVisible option is on the plug draw
// 004158d0 calls 00415910, which
//  - draws the plug's FX mesh three times with the main bundle's first part's
//    texture sequence: as placed (frame i), turned -pi/36 about the plug's y
//    and moved +v (frame i+1), turned +pi/36 and moved -v (frame i+2), where
//    v is the FX mesh's first vertex normal times frac(life x 1.2) x 0.07 -
//    0.035 (the cook turns the copies and gives the rate, amplitude and axis);
//  - moves each of its two tail bundles, every frame, to a random point of the
//    FX mesh's box, min + interval x (0.25 + (rand % 50) x 0.01) on each axis,
//    then ticks and draws it.
// 1298 queues every copy and every tail spark in one alpha list sorted far to
// near (0043dd80): a copy keyed by the eye distance to its matrix's
// translation plus the FX mesh's y extent, a spark by the eye distance to its
// quad's first three corners (PQ-373). An effect with an N3E5 sort record
// (PQ-376, D-200) sorts so; one without keeps n3e's order, each copy by its
// vertex centroid and each tail link by its newest point.
// The main part's life starts at (rand % 1000) x 0.01 s (00415370), so frames
// are out of step between weapons. A tail emits for ever; n3e plays its cooked
// clip as a chain, each link emitting for the first half of the clip.
struct AppearanceEffects {
  struct Model {
    const AppearanceEffect *data = nullptr;
    const EffectClip *tail = nullptr;
    Scene scene;          // every copy's vertices, then the seven reference points
    std::vector<uint32_t> indices;
  };
  struct State {
    double start = 0;
    float phase = 0;
    std::minstd_rand rng;
    std::vector<std::deque<EffectInstance>> tails;
    bool seen = false;
  };
  std::map<uint32_t, Model> models;
  std::map<std::pair<uint64_t, uint32_t>, State> states;

  void build(const Effects &effects, const Scene &skeleton) {
    models.clear();
    states.clear();
    for (const auto &e : effects.appearance) {
      Model m;
      m.data = &e;
      m.scene = skeleton;
      m.scene.vertices.clear();
      m.scene.indices.clear();
      m.scene.influences.clear();
      m.scene.tracks.clear();
      m.scene.texture.clear();
      m.scene.collision = {};
      auto add = [&](V p, std::array<float, 2> uv) {
        Vertex v{};
        v.p = p;
        v.n = {0, 1, 0};
        v.uv = uv;
        v.joints = {e.joint, 0, 0, 0};
        v.weights = {1, 0, 0, 0};
        m.indices.push_back(uint32_t(m.scene.vertices.size()));
        m.scene.vertices.push_back(v);
      };
      for (const auto &c : e.copies)
        for (const auto &v : c.vertices) add({v[0], v[1], v[2]}, {v[3], v[4]});
      for (const auto &p : e.jitter) add(p, {0, 0});
      for (const auto &p : e.tail_box) add(p, {0, 0});
      add(e.sort_origin, {0, 0});
      if (e.tails) m.tail = &effects.clips.at(e.tail_clip);
      models.emplace(e.key, std::move(m));
    }
  }
  // The first key per equipment slot, as draw_appearance selects them.
  template <class Keys>
  static std::vector<uint32_t> selected(const std::vector<AppearanceRule> &rules, const Keys &keys) {
    std::set<uint32_t> slots;
    std::vector<uint32_t> out;
    for (auto key : keys)
      if (key && key <= rules.size() && slots.insert(rules[key - 1].slot).second) out.push_back(key);
    return out;
  }
  // Draws actor's effects for this frame. Returns the keys first drawn now.
  template <class Keys>
  std::vector<uint32_t> draw(uint64_t actor, const std::vector<AppearanceRule> &rules, const Keys &keys,
                             const std::vector<Node> &pose, V position, float heading, double now, V eye,
                             std::vector<EffectMesh> &meshes, std::vector<const EffectInstance *> &tails) {
    std::vector<uint32_t> started;
    float c = std::cos(heading), sn = std::sin(heading);
    for (auto key : selected(rules, keys)) {
      auto found = models.find(key);
      if (found == models.end()) continue;
      const auto &model = found->second;
      const auto &e = *model.data;
      auto [it, inserted] = states.try_emplace({actor, key});
      auto &state = it->second;
      if (inserted) {
        state.start = now;
        state.rng.seed(uint32_t(actor * 2654435761u) ^ (key * 40503u) ^ 0x9e3779b9u);
        state.phase = float(state.rng() % e.phase_steps) * e.phase_step;
        state.tails.resize(e.tails);
        started.push_back(key);
      }
      state.seen = true;
      auto skinned = model.scene.skin(pose, model.indices);
      auto world = [&](size_t i) {
        const float *v = &skinned[i * 8];
        return V{position[0] + v[0] * c + v[2] * sn, position[1] + v[1], position[2] - v[0] * sn + v[2] * c};
      };
      size_t refs = model.indices.size() - 7;
      V origin = world(refs), tip = world(refs + 1), axis{};
      for (int k = 0; k < 3; ++k) axis[k] = tip[k] - origin[k];
      float t = float(now - state.start);
      float cycle = t * e.jitter_rate;
      float offset = ((cycle - std::floor(cycle)) * 2 - 1) * e.jitter_amplitude;
      auto frame = int64_t(std::floor((t + state.phase) * e.fps));
      size_t at = 0;
      for (const auto &copy : e.copies) {
        EffectMesh mesh{e.frames[size_t(frame + copy.frame_offset) % e.frames.size()], e.source_blend,
                        e.destination_blend, e.flags, 0, {}};
        V centre{};
        for (size_t k = 0; k < copy.vertices.size(); ++k, ++at) {
          V p = world(at);
          for (int a = 0; a < 3; ++a) p[a] += copy.jitter * offset * axis[a], centre[a] += p[a] / copy.vertices.size();
          mesh.vertices.insert(mesh.vertices.end(), {p[0], p[1], p[2], copy.vertices[k][3], copy.vertices[k][4], 1, 1, 1, 1});
        }
        if (e.sorted) {
          // 00415910 (00416839, 00416a0d, 00416b72): the copy matrix's
          // translation, the plug origin moved by the copy's +-v, plus the bias.
          V origin = world(refs + 6);
          for (int a = 0; a < 3; ++a) origin[a] += copy.jitter * offset * axis[a];
          mesh.distance = eye_distance(origin, eye) + e.sort_bias;
        } else
          mesh.distance = eye_distance(centre, eye);
        meshes.push_back(std::move(mesh));
      }
      if (!model.tail) continue;
      V box = world(refs + 2), edges[3];
      for (int k = 0; k < 3; ++k) {
        V end = world(refs + 3 + k);
        for (int a = 0; a < 3; ++a) edges[k][a] = end[a] - box[a];
      }
      auto point = [&] {
        V p = box;
        for (int k = 0; k < 3; ++k) {
          float f = e.tail_low + float(state.rng() % e.tail_steps) * e.tail_step;
          for (int a = 0; a < 3; ++a) p[a] += f * edges[k][a];
        }
        return p;
      };
      float length = float(model.tail->frames.size()) / model.tail->rate, half = length / 2;
      for (auto &chain : state.tails) {
        if (chain.empty() || now - chain.back().start >= half) {
          if (!chain.empty()) chain.back().stop = std::min(chain.back().stop, float(now - chain.back().start));
          chain.push_back({model.tail, actor, now, 1, 10, {}, {{0, point()}}, -1, {}, {}, &chain});
          chain.back().quad_keys = e.sorted; // 004840b0: one key per spark
        }
        while (!chain.empty() && now - chain.front().start >= length) chain.pop_front();
        for (auto &i : chain) {
          float age = float(now - i.start);
          auto last = i.positions.back().first;
          // One position per sample interval, as EffectPlayer::tick keeps them.
          if (age > last && int(age * i.clip->rate) != int(last * i.clip->rate) && i.positions.size() < 602)
            i.positions.push_back({age, point()});
          tails.push_back(&i);
        }
      }
    }
    return started;
  }
  // Drops every effect not drawn since the last call: its actor left the view,
  // or the key left its equipment. Returns them.
  std::vector<std::pair<uint64_t, uint32_t>> retire() {
    std::vector<std::pair<uint64_t, uint32_t>> gone;
    for (auto it = states.begin(); it != states.end();) {
      if (!it->second.seen) {
        gone.push_back(it->first);
        it = states.erase(it);
      } else {
        it->second.seen = false;
        ++it;
      }
    }
    return gone;
  }
};
}
