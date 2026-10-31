#pragma once
#include "assets/assets.h"
#include <array>
#include <cmath>
#include <stdexcept>

namespace n3e {
// The full-detail terrain parts (kind 2, level 0) of a whole world, as
// triangles: the marker ground of an N3W1 package (excludes object meshes).
inline Collision world_terrain_ground(const WorldMesh& world) {
  std::vector<V> ground;
  for(const auto&chunk:world.chunks)for(const auto&part:chunk.parts)if(part.kind==2){
    const auto&level=part.levels.front();
    for(unsigned i=level.first;i<level.first+level.count;++i){
      auto at=size_t(chunk.indices[i])*WORLD_FLOATS;
      ground.push_back({chunk.vertices[at],chunk.vertices[at+1],chunk.vertices[at+2]});
    }
  }
  return Collision(std::move(ground));
}
// The surface ground parts sample (PQ-235). An N3W2 world is streamed and
// never resident whole, so its marker follows the package's native terrain
// heightfield (N3C2, which the cooker always writes beside an N3W2 world):
// bounded, loaded at start and independent of streaming; the object triangles
// are left out, as the terrain parts leave out object meshes. An N3W1 world
// keeps its full-detail terrain parts; a package without a world uses its
// collision surface. `whole` is the loaded N3W1 world, if any.
inline Collision target_marker_ground(const Collision& collision, bool chunked, const WorldMesh* whole) {
  if(chunked){
    if(!collision.has_terrain())throw std::runtime_error("target marker on an N3W2 world needs an N3C2 terrain heightfield");
    return Collision(collision.terrain(),{});
  }
  return whole?world_terrain_ground(*whole):collision;
}
// The symbol's horizontal and vertical scale for an actor drawn at `scale`.
// KO's symbol (005c4e20, binary) scales X/Z by twice the selected actor's
// radius and Y by 1.3 times its height, both read through getters that
// multiply the character's radius (+0x168) and box top (+0x17c) by its scale
// +0x90 (0045a1d0, 00459ff0), the NPC-in's sSize x 0.01 (005cdd82-005cdda9,
// 0041f800; PQ-296). The package profile is the actor class's size as the
// package draws it; `scale` is the actor's own drawn scale on top of that (a
// template's, Entity.scale, PQ-272; 1 for a player or an untemplated NPC).
inline std::array<float,2> target_marker_size(const TargetMarker& marker, bool npc, float scale) {
  auto bounds=marker.bounds[npc?1:0];
  return {marker.diameter_scale*bounds[0]*scale,marker.height_scale*bounds[1]*scale};
}
// PQ-380: a part's key in the frame's one far-to-near alpha list, as 1298
// keys every shape part it queues (00443090, 00443103): the linear distance
// from the eye to the part matrix's translation. That matrix is the pivot as a
// translation times the symbol's matrix (004447f0; 004429b0 for an upright
// part), the scale and position 005c4e20 sets (0043b650; the cooker refuses a
// turned shape), so the point is the position plus the pivot at the symbol's
// horizontal and vertical scale, for both kinds of part. A ground part's
// conformed vertices do not move it.
inline float target_marker_key(const TargetMarker& marker, const TargetMarkerPart& part, bool npc, float scale, V position, V eye) {
  auto [horizontal,vertical]=target_marker_size(marker,npc,scale);
  float total=0;
  for(unsigned k=0;k<3;++k){float d=position[k]+part.pivot[k]*(k==1?vertical:horizontal)-eye[k];total+=d*d;}
  return std::sqrt(total);
}
// Match the displayed actor position. Terrain sample spacing deliberately uses
// height scale, while the visible footprint uses diameter (binary005c4e20).
inline std::vector<float> target_marker_vertices(const TargetMarker& marker,
    const TargetMarkerPart& part, bool npc, float scale, V position, V eye, const Scene& ground) {
  auto [horizontal,vertical]=target_marker_size(marker,npc,scale);
  float dx=eye[0]-position[0]-part.pivot[0]*horizontal;
  float dz=eye[2]-position[2]-part.pivot[2]*horizontal;
  float length=std::hypot(dx,dz);float s=length>1e-6f?dx/length:0,c=length>1e-6f?dz/length:1;
  std::vector<float> out;out.reserve(part.indices.size()*8);
  for(auto index:part.indices){
    auto v=part.vertices[index];float x=v[0],z=v[2],nx=v[3],nz=v[5];
    if(part.mode==1){v[0]=c*x+s*z;v[2]=-s*x+c*z;v[3]=c*nx+s*nz;v[5]=-s*nx+c*nz;}
    v[0]=position[0]+(v[0]+part.pivot[0])*horizontal;
    v[2]=position[2]+(v[2]+part.pivot[2])*horizontal;
    v[1]=part.mode==0?ground.ground_height(position[0]+x*vertical,position[2]+z*vertical)+marker.ground_lift+part.pivot[1]*vertical:
                          position[1]+(v[1]+part.pivot[1])*vertical;
    if(!std::isfinite(v[1]))return {}; // No drawable terrain outside the package surface.
    // Inverse-transpose for nonuniform model scale; the fragment shader normalizes.
    v[3]/=horizontal;v[4]/=vertical;v[5]/=horizontal;
    out.insert(out.end(),v.begin(),v.end());
  }
  return out;
}
}
