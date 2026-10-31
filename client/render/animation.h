#pragma once
#include "assets/assets.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>

// Full-body local TRS blending before skinning; no simulation callbacks.
inline std::vector<n3e::Node> blend_pose(const std::vector<n3e::Node> &a,
                                         std::vector<n3e::Node> b,
                                         float weight) {
  if (a.size() != b.size())
    throw std::runtime_error("blend skeleton");
  weight = std::clamp(weight, 0.f, 1.f);
  for (size_t i = 0; i < b.size(); ++i) {
    for (int k = 0; k < 3; ++k) {
      b[i].t[k] = a[i].t[k] + (b[i].t[k] - a[i].t[k]) * weight;
      b[i].s[k] = a[i].s[k] + (b[i].s[k] - a[i].s[k]) * weight;
    }
    auto from = a[i].q, to = b[i].q;
    float dot = 0;
    for (int k = 0; k < 4; ++k)
      dot += from[k] * to[k];
    if (dot < 0) {
      for (auto &v : to)
        v = -v;
      dot = -dot;
    }
    float x = 1 - weight, y = weight;
    if (dot < .9995f) {
      float theta = std::acos(std::clamp(dot, -1.f, 1.f));
      x = std::sin((1 - weight) * theta) / std::sin(theta);
      y = std::sin(weight * theta) / std::sin(theta);
    }
    float length = 0;
    for (int k = 0; k < 4; ++k) {
      b[i].q[k] = from[k] * x + to[k] * y;
      length += b[i].q[k] * b[i].q[k];
    }
    for (auto &v : b[i].q)
      v /= std::sqrt(length);
  }
  return b;
}
struct AnimationPlayer {
  // A role that plays its clip once and holds the end, with no other rule
  // (a skeletal plug's once clip, PQ-317: 2233's bOnceAndFreeze in 0042e070).
  static constexpr int HOLD = 100;
  int state = -1, role = -1;
  uint64_t strike = 0;
  double start = 0, last = 0;
  float entry = 0, previous_time = -1;
  unsigned markers = 0; // one-frame cosmetic pulse; never an action request
  std::vector<n3e::Node> from, current;
  std::vector<n3e::Node> evaluate(const std::vector<n3e::Scene> &scenes,
                                  const n3e::Clip *clips, double now,
                                  float *sampled = nullptr) const {
    const auto &clip = clips[state];
    float elapsed = float(std::max(0., now - start));
    float t = std::max(0.f, elapsed - entry);
    bool looping = role != 2 && role != 3 && role != 7 && role != 9 && role != HOLD;
    float cycle = clip.duration + (clip.loop_blend ? clip.blend : 0);
    if (looping)
      t = std::fmod(t, cycle);
    else
      t = std::min(t, clip.duration);
    if (sampled)
      *sampled = std::min(t, clip.duration);
    auto pose = scenes[state].sample(std::min(t, clip.duration));
    if (looping && t > clip.duration)
      pose = blend_pose(pose, scenes[state].sample(0),
                        (t - clip.duration) / clip.blend);
    if (entry > 0 && elapsed < entry)
      pose = blend_pose(from, std::move(pose), elapsed / entry);
    return pose;
  }
  const std::vector<n3e::Node> &update(const std::vector<n3e::Scene> &scenes,
                                       const n3e::Clip *clips, int desired,
                                       uint64_t event, double since, double now,
                                       bool reset = false, int logical_role = -1) {
    if(logical_role<0)logical_role=desired;
    markers = 0;
    bool gap = state >= 0 && (now < last || now - last > .5);
    if (reset || state < 0 || now < last) {
      state = desired;
      role = logical_role;
      strike = event;
      start = since;
      entry = 0;
      from.clear();
      // First sight of a corpse (including reconnect) holds its final pose.
      if (role == 3)
        start = now - clips[state].duration;
      if (role == 2) {
        entry = clips[state].blend;
        from = scenes[state].sample(0);
      }
      previous_time = -1;
    } else if (state != desired || role != logical_role || (logical_role == 2 && event != strike)) {
      from = evaluate(scenes, clips, now);
      if(role==6&&logical_role==6)since=now;
      state = desired;
      role = logical_role;
      strike = event;
      start = since;
      entry = clips[state].blend;
      previous_time = -1;
    }
    float t;
    current = evaluate(scenes, clips, now, &t);
    if (now - start < entry)
      t = -1; // Clip-zero markers occur after the entry blend, once playback
              // begins.
    if (role == 2 && !gap && !reset)
      for (int i = 0; i < 2; ++i)
        if (clips[state].markers[i] >= 0 &&
            previous_time < clips[state].markers[i] &&
            t >= clips[state].markers[i])
          markers |= 1u << i;
    previous_time = t;
    last = now;
    return current;
  }
};

// Two independent local-TRS controllers. Only the declared upper joints are
// replaced; the root and lower body keep their locomotion phase throughout.
struct LayeredAnimation {
  AnimationPlayer base;
  std::vector<n3e::Node> current, outgoing;
  bool was_upper=false, was_full=false;
  double fade_start=0;
  float fade_duration=0;
  std::vector<n3e::Node> update(AnimationPlayer &action,
      const std::vector<n3e::Scene>&scenes,const n3e::Clip*clips,
      int clip,int role,uint64_t event,double since,double now,
      int base_clip,int base_role,double base_since,
      const std::vector<uint32_t>&mask,bool upper) {
    bool full=(role==2&&!upper) || role==3 || role==7 || role==8 || role==9;
    bool transition=action.state!=clip||action.role!=role||(role==2&&action.strike!=event);
    auto action_pose=action.update(scenes,clips,clip,event,since,now,false,role);
    if(transition&&!current.empty()&&action.entry>0){
      action.from=current;action.current=action.evaluate(scenes,clips,now);action_pose=action.current;
    }
    auto lower=base.update(scenes,clips,base_clip,0,base_since,now,false,base_role);
    if(was_full&&!full&&!current.empty()){
      base.from=current;base.start=now;base.entry=clips[base_clip].blend;
      lower=base.evaluate(scenes,clips,now);
    }
    if(was_upper&&!upper&&!full){outgoing=current;fade_start=now;fade_duration=clips[base_clip].blend;}
    if(full){current=action_pose;outgoing.clear();}
    else {
      current=lower;
      if(upper){for(auto node:mask)current.at(node)=action_pose.at(node);outgoing.clear();}
      else if(!outgoing.empty()&&fade_duration>0&&now-fade_start<fade_duration){
        auto fading=blend_pose(outgoing,lower,float((now-fade_start)/fade_duration));
        for(auto node:mask)current.at(node)=fading.at(node);
      }else outgoing.clear();
    }
    was_upper=upper;was_full=full;return current;
  }
};
