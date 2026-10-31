#pragma once
#include "assets/assets.h"
#include "assets/world_lod.h"
#include <cmath>

namespace n3e::character_lod {
inline int level(const RenderDetail &d, float metric, unsigned row) {
  for(int i=0;i<4;++i) if(metric<d.thresholds.at(row)[i]) return i;
  return -1;
}
inline unsigned row(const RenderDetail &d, unsigned cost) {
  return unsigned(cost>=d.workload[0])+unsigned(cost>=d.workload[1])+unsigned(cost>=d.workload[2]);
}
// Every instance owns its own reversible attachment topology.
struct AttachmentState { WorldPart part; std::vector<uint32_t> indices; };
inline std::vector<AttachmentState> initial(const RenderDetail &d) {
  std::vector<AttachmentState> result;
  for(const auto &a:d.attachments) result.push_back({a.part,a.mesh.scene.indices});
  return result;
}
inline void update(AttachmentState &s,float metric) {
  if(auto target=world_lod::budget(s.part.progressive,metric))
    world_lod::refine(s.part,s.indices,*target);
}
}
