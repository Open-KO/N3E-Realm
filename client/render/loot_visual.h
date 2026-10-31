#pragma once
#include "orbit.h"
#include "network/world.h"
#include <map>

// The server supplies the eligible bundles. Mesh picking never invents rewards
// or authorizes a claim; it only chooses which existing bundle to inspect.
inline std::map<uint64_t,n3e::V> loot_instances(const n3e::WorldState&w){
  std::map<uint64_t,n3e::V> result;
  if(w.connected)for(const auto&d:w.loot.drops())if(d.encounter())result.try_emplace(d.encounter(),n3e::V{d.x(),d.y(),d.z()});
  return result;
}
inline uint64_t pick_loot(const n3e::WorldState&w,const std::vector<float>&mesh,const n3e::Scene&scene,
                          const Orbit&orbit,float x,float y,int width,int height){
  if(width<=0||height<=0||!std::isfinite(x)||!std::isfinite(y)||x<0||x>=width||y<0||y>=height)return 0;
  n3e::V ray;
  for(unsigned k=0;k<3;++k)ray[k]=-orbit.back[k]+orbit.right[k]*(x-width*.5f)/(height*(.5f/std::tan(orbit.config.fov/2)))+orbit.up[k]*(height*.5f-y)/(height*(.5f/std::tan(orbit.config.fov/2)));
  ray=camera_geometry::unit(ray);for(auto&v:ray)v*=orbit.config.far_plane;
  float nearest=1;uint64_t picked=0;
  for(const auto&[id,position]:loot_instances(w))for(size_t i=0;i+23<mesh.size();i+=24){
    n3e::V v[3];for(unsigned corner=0;corner<3;++corner)for(unsigned k=0;k<3;++k)v[corner][k]=mesh[i+corner*8+k]+position[k];
    float t=camera_geometry::hit(orbit.eye,ray,v[0],v[1],v[2],0);
    if(t>=0&&t<nearest&&t*orbit.config.far_plane>=orbit.config.near_plane){nearest=t;picked=id;}
  }
  if(picked){const auto near=scene.collision.segment(orbit.eye,ray,0);for(size_t i=0;i+2<near.size();i+=3){
    float t=camera_geometry::hit(orbit.eye,ray,near[i],near[i+1],near[i+2],0);
    if(t>=0&&t<nearest-1e-5f)return 0;
  }}
  return picked;
}
