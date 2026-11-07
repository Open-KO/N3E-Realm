#pragma once
#include "assets/assets.h"
#include "animation.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>

// Independent idle pose of the package's player model. CPU projection keeps the
// preview independent of the world camera and supplies depth within the UI rect.
inline std::vector<float> project_portrait(std::vector<float> vertices, const std::vector<float>&base,
    const n3e::HudPortrait&view,const std::array<float,4>&rect,int w,int h,size_t stride=8){
  if(w<=0||h<=0||rect[2]<=rect[0]||rect[3]<=rect[1])return {};
  const float yaw=view.yaw*float(M_PI)/180,pitch=view.pitch*float(M_PI)/180;
  auto rotate=[&](float x,float y,float z){
    float rx=std::cos(yaw)*x+std::sin(yaw)*z,rz=-std::sin(yaw)*x+std::cos(yaw)*z;
    // Imported models face -Z; the portrait camera looks towards +Z.
    return std::array<float,3>{-rx,std::cos(pitch)*y+std::sin(pitch)*rz,-std::sin(pitch)*y+std::cos(pitch)*rz};
  };
  if(base.empty())return {};
  std::array<float,3> lo{INFINITY,INFINITY,INFINITY},hi{-INFINITY,-INFINITY,-INFINITY};
  for(size_t i=0;i<base.size();i+=8){auto p=rotate(base[i],base[i+1],base[i+2]);for(int j=0;j<3;++j){lo[j]=std::min(lo[j],p[j]);hi[j]=std::max(hi[j],p[j]);}}
  float fit=std::max((hi[1]-lo[1])*view.framing,(hi[0]-lo[0])*view.framing*(rect[3]-rect[1])/(rect[2]-rect[0]));
  if(fit<=0)return {};
  float pixels=(rect[3]-rect[1])/fit,depth=std::max(.01f,(hi[2]-lo[2])*2);
  for(size_t i=0;i<vertices.size();i+=stride){
    auto p=rotate(vertices[i],vertices[i+1],vertices[i+2]);
    auto n=rotate(vertices[i+3],vertices[i+4],vertices[i+5]);
    float light=.45f+.55f*std::max(0.f,(n[1]*.2f-n[2])/1.019803903f);
    vertices[i]=((rect[0]+rect[2])*.5f+(p[0]-(lo[0]+hi[0])*.5f)*pixels)*2/w-1;
    vertices[i+1]=1-((rect[1]+rect[3])*.5f-(p[1]-(lo[1]+hi[1])*.5f)*pixels)*2/h;
    vertices[i+2]=(p[2]-(lo[2]+hi[2])*.5f)/depth;
    vertices[i+3]=vertices[i+5]=light*.92f;vertices[i+4]=light;
  }
  return vertices;
}

// RQ-208: the paperdoll's idle pose after `seconds` of the paperdoll's own
// clock (the time it has been drawn; the viewer holds it while the inventory
// is closed, as KO's CUIInventory::Tick returns while hidden). KO ticks the
// inventory model with the world model's CN3Chr::Tick (1097 00459a20 ->
// vtable 0058cedc +0x1c 004457d0, frame tick 00445bb0), so its breath clip
// runs at the clip's own rate and wraps at the clip's own end, or, with the
// clip's loop flag, holds the end and blends back to the start over its blend
// time: what AnimationPlayer does for the world's idle. `clip` is the scene's
// animation.bin record (null without one: a plain wrap).
inline std::vector<n3e::Node> paperdoll_pose(const n3e::Scene&scene,const n3e::Clip*clip,double seconds){
  float duration=0;for(const auto&t:scene.tracks)duration=std::max(duration,t.keys.back().time);
  if(duration<=0||!std::isfinite(seconds)||seconds<0)return scene.sample(0);
  const bool blended=clip&&clip->loop_blend&&clip->blend>0;
  const float t=float(std::fmod(seconds,double(duration)+(blended?clip->blend:0)));
  auto pose=scene.sample(std::min(t,duration));
  if(blended&&t>duration)pose=blend_pose(pose,scene.sample(0),(t-duration)/clip->blend);
  return pose;
}

// RQ-208: the paperdoll's idle clock. It advances by the frame time only
// between consecutive frames that draw the paperdoll, so it holds, not resets,
// while the inventory is closed: KO's CUIInventory::Tick returns while hidden
// before it ticks the inventory model (KO-FINDINGS §10.13).
struct PaperdollClock {
  double seconds = 0;
  int frame = -2;
  uint64_t ns = 0;
  // The clock for frame `at`, drawn at `now_ns`; repeated calls in one frame
  // (several previews) advance it once.
  double tick(int at, uint64_t now_ns) {
    if (at != frame) {
      if (at == frame + 1 && now_ns >= ns) seconds += double(now_ns - ns) / 1e9;
      frame = at;
      ns = now_ns;
    }
    return seconds;
  }
};

inline std::vector<float> portrait_vertices(const n3e::Scene&scene,const n3e::Clip*clip,double seconds,
    const n3e::HudPortrait&view,const std::array<float,4>&rect,int w,int h){
  auto base=scene.skin(scene.sample(0));base.resize(scene.indices.size()*8);
  auto vertices=scene.skin(paperdoll_pose(scene,clip,seconds));
  vertices.resize(scene.indices.size()*8);
  return project_portrait(std::move(vertices),base,view,rect,w,h);
}
