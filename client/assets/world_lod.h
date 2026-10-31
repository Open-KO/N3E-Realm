#pragma once
#include "assets/assets.h"
#include <algorithm>
#include <cmath>
#include <limits>

namespace n3e::world_lod {
inline bool sphere_visible(V center,float radius,V eye,V right,V up,V back,
                           float near,float far,float aspect,float tangent,bool radial) {
  V d{center[0]-eye[0],center[1]-eye[1],center[2]-eye[2]};
  auto dot=[&](V v){return d[0]*v[0]+d[1]*v[1]+d[2]*v[2];};
  if(radial && std::sqrt(dot(d))>far+radius) return false;
  float depth=-dot(back),tx=aspect*tangent;
  return depth+radius>near && depth-radius<far &&
      std::abs(dot(right))<depth*tx+radius*std::sqrt(1+tx*tx) &&
      std::abs(dot(up))<depth*tangent+radius*std::sqrt(1+tangent*tangent);
}
// The box test behind sphere_visible's planes (PQ-231). Each of sphere_visible's
// six tests is a signed plane distance; a box is culled only when every corner
// is more than a centimetre outside one plane, so every sphere inside the box
// fails that plane too, and the chunk cull never hides a part its own test
// would draw. Radial culling is a part option and is not applied here.
inline bool box_visible(V lo,V hi,V eye,V right,V up,V back,
                        float near,float far,float aspect,float tangent) {
  const double tx=double(aspect)*tangent, kx=std::sqrt(1+tx*tx), ky=std::sqrt(1+double(tangent)*tangent);
  constexpr double slack=.01;
  double low[6]; for(double &v:low) v=std::numeric_limits<double>::infinity();
  for(int corner=0;corner<8;++corner) {
    double d[3];
    for(int a=0;a<3;++a) d[a]=double((corner>>a)&1 ? hi[a] : lo[a])-eye[a];
    auto dot=[&](V v){return d[0]*v[0]+d[1]*v[1]+d[2]*v[2];};
    double depth=-dot(back), x=dot(right), y=dot(up);
    const double outside[6]={near-depth, depth-far, (x-tx*depth)/kx, (-x-tx*depth)/kx,
                             (y-tangent*depth)/ky, (-y-tangent*depth)/ky};
    for(int i=0;i<6;++i) low[i]=std::min(low[i],outside[i]);
  }
  for(double v:low) if(v>slack) return false;
  return true;
}
// A missing budget preserves the existing state at the last-control equality.
inline std::optional<uint32_t> budget(const ProgressiveMesh &p, float metric) {
  if (p.controls.empty()) return std::numeric_limits<int32_t>::max();
  if (metric < p.controls.front().distance) return p.controls.front().vertices;
  if (metric > p.controls.back().distance) return p.controls.back().vertices;
  for (size_t i=1;i<p.controls.size();++i) {
    const auto &a=p.controls[i-1], &b=p.controls[i];
    if (metric < b.distance) {
      // Preserve the x87 extended intermediate and truncate the signed change,
      // not the final (positive) count. The input metric is float32.
      long double delta=(int64_t(b.vertices)-a.vertices)*
          (static_cast<long double>(metric)-a.distance)/(static_cast<long double>(b.distance)-a.distance);
      return uint32_t(int64_t(a.vertices)+int64_t(delta));
    }
  }
  return std::nullopt;
}

inline bool refine(WorldPart &part, std::vector<uint32_t> &indices, uint32_t target) {
  auto &p=part.progressive;
  if (p.splits.empty() || target==p.vertices) return false;
  auto previous=p.step;
  auto split=[&] {
    auto &s=p.splits[p.step++]; p.vertices+=s.vertices; p.indices+=s.indices;
    for(uint32_t j=0;j<s.changes;++j)
      indices[part.levels[0].first+p.edits[s.first+j]]=p.base+p.vertices-1;
  };
  if(target>p.vertices) {
    while(p.step<p.splits.size() && p.vertices<target &&
          p.vertices+p.splits[p.step].vertices<=target) split();
  } else {
    while(p.step && target<p.vertices) {
      auto &s=p.splits[--p.step]; p.indices-=s.indices;
      for(uint32_t j=0;j<s.changes;++j)
        indices[part.levels[0].first+p.edits[s.first+j]]=p.base+s.target;
      p.vertices-=s.vertices;
    }
  }
  while(p.step<p.splits.size() && p.splits[p.step].grouped) split();
  return previous!=p.step;
}

inline int terrain_level(const TerrainDetail &t,int x,int z,const V &eye,float far) {
  int cx=int((eye[0]-t.origin[0])/t.patch_size);
  int cz=int((t.origin[2]-eye[2])/t.patch_size);
  int dx=x-cx,dz=z-cz;
  int distance=int(std::sqrt(double(dx)*dx+double(dz)*dz)+double(t.bias));
  int near=std::max(int(t.minimum),int(far*t.far_factor));
  return distance<=near ? 1 : distance<=near+int(t.band) ? 2 : 3;
}

inline uint32_t terrain_variant(const TerrainDetail &t,const WorldPart &p,const V &eye,float far) {
  int x=p.patch_x,z=p.patch_z,level=terrain_level(t,x,z,eye,far);
  if(level==1) return 0;
  constexpr int dx[4]={-1,0,1,0}, dz[4]={0,1,0,-1};
  uint32_t mask=0;
  for(int edge=0;edge<4;++edge) {
    int neighbor=terrain_level(t,x+dx[edge],z+dz[edge],eye,far);
    if(level==2 ? neighbor<level : neighbor<=level) mask|=1u<<edge;
  }
  return 1+(level-2)*16+mask;
}

// D-212 (PQ-394): a world part's texture sequence. The frame time between two
// world passes, bounded to (0.001, 1.0) s with 1/30 s outside it, the bound
// 1298 puts on its own frame time (0043ac60, PQ-012); here a stall guard.
inline float sequence_seconds(double seconds) {
  return seconds>0.001 && seconds<1.0 ? float(seconds) : 1.f/30.f;
}
// One advance of a sequence index, as 1298's part tick (004429b0) takes it:
// index + seconds x fps, and 0 once that reaches the frame count, the
// remainder dropped (00442c9b-00442cb2). n3e rounds each step to float32.
inline float sequence_advance(float index,float seconds,float fps,uint32_t frames) {
  const float step=seconds*fps;  // float32 each step; 1298's x87 precision is not modelled
  float next=step+index;
  return next>=float(frames) ? 0.f : next;
}
// The frame a sequence draws at `index`: its integer part (00443090's ftol).
inline uint32_t sequence_frame(float index,uint32_t frames) {
  auto k=uint32_t(index);
  return k<frames ? k : frames-1;
}
}
