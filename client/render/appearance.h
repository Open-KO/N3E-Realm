#pragma once
#include "assets/assets.h"
#include <set>
#include <span>
#include <type_traits>

namespace n3e {
// World and portrait use the same composition. Unknown cosmetic keys leave the
// default body intact; a missing low-detail part falls back to its highest mesh.
// `draw` takes (mesh, indices), or (mesh, indices, key) with key 0 for the
// default body and the appearance key for each selected mesh (PQ-315).
template<class Keys, class Draw>
void draw_appearance(const RenderDetail& detail, const std::vector<AppearanceRule>& rules,
                     const Keys& keys, unsigned level, Draw draw) {
  std::set<unsigned> selected, slots, hidden;
  for (auto key : keys) {
    if (!key || key > rules.size() || key > detail.appearances.size()) continue;
    if (!slots.insert(rules[key-1].slot).second) continue;
    selected.insert(key-1);
    for (auto texture : detail.appearances[key-1].replaces) hidden.insert(texture);
  }
  const auto& base=detail.levels.at(level);
  std::vector<uint32_t> indices;
  for(size_t i=0;i<base.scene.indices.size();i+=3) {
    // Material assignment is per triangle, validated by the package reader.
    if(!hidden.contains(base.slots.at(base.scene.indices[i])))
      indices.insert(indices.end(),base.scene.indices.begin()+i,base.scene.indices.begin()+i+3);
  }
  auto call=[&](const auto& mesh,std::span<const uint32_t> span,uint32_t key){
    if constexpr(std::is_invocable_v<Draw&,decltype(mesh),std::span<const uint32_t>,uint32_t>)draw(mesh,span,key);
    else draw(mesh,span);
  };
  call(base,std::span<const uint32_t>(indices),0);
  for(auto key:selected) {
    const auto& levels=detail.appearances[key].levels;
    const auto& mesh=levels.at(level).scene.indices.empty()?levels.front():levels.at(level);
    if(mesh.scene.indices.empty())continue;  // a skeletal plug's key (PQ-317): no rigid mesh
    call(mesh,std::span<const uint32_t>(mesh.scene.indices),key+1);
  }
}
}
