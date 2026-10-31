#pragma once
#include "combat_pose.h"
#include "player_pose.h"
#include "audio.h"
#include <deque>

// Local cosmetics only. Nothing here mutates a world snapshot or grants a hit.
// Server-authored request identities reconcile across delayed/out-of-order views.
struct MeleePresentation {
  struct Attempt {
    uint64_t sequence, target;
    unsigned style;
    bool moving;
    double start;
    bool confirmed=false, cancelled=false;
    // PQ-445: a held ranged shot with a flight: when its release was
    // predicted or its release event launched its flight (-1: neither yet),
    // and whether its result (hit or miss) came.
    double released=-1;
    bool landed=false;
    StrikePresentation view() const { return {sequence,start,cancelled}; }
  };
  uint64_t actor=0,session=0;
  std::deque<Attempt> attempts;
  void context(uint64_t id,uint64_t generation,bool living,bool casting,
               double now,n3e::AudioMixer &audio) {
    if(actor!=id||session!=generation){
      for(const auto&a:attempts)audio.cancel(a.sequence);
      attempts.clear();actor=id;session=generation;
    }
    for(auto&a:attempts)if(!a.cancelled&&(!living||casting||(!a.confirmed&&now-a.start>=2))){
      a.cancelled=true;audio.cancel(a.sequence);
    }
    while(!attempts.empty()&&now-attempts.front().start>10)attempts.pop_front();
  }
  Attempt* find(uint64_t seq) {
    for(auto&a:attempts)if(a.sequence==seq)return &a;
    return nullptr;
  }
  void begin(uint64_t seq,uint64_t target,unsigned style,bool moving,double now){
    if(!seq||!actor||find(seq))return;
    if(attempts.size()==16)attempts.pop_front();
    attempts.push_back({seq,target,style,moving,now});
  }
  void result(uint64_t seq,const std::string &status,n3e::AudioMixer &audio){
    if(auto*a=find(seq)){
      if(status=="hit"||status=="miss")a->confirmed=a->landed=true;
      else {a->cancelled=true;audio.cancel(seq);}
    }
  }
  void reconcile(const n3e::Entity &entity){
    if(entity.id()!=actor)return;
    if(auto*a=find(entity.strike_sequence())){
      a->confirmed=true;a->style=entity.strike_style();a->moving=entity.strike_moving();
    }
  }
  const Attempt* current(const n3e::Entity &entity) const {
    if(entity.id()!=actor)return nullptr;
    for(auto it=attempts.rbegin();it!=attempts.rend();++it)
      if(it->sequence==entity.strike_sequence()||(it->sequence>entity.strike_sequence()&&!it->cancelled))return &*it;
    if(!attempts.empty()&&attempts.back().sequence>entity.strike_sequence())return &attempts.back();
    return nullptr;
  }
  unsigned clip(const n3e::CombatAnimation &policy,const Attempt&a) const {
    const auto&p=policy.profiles.at(a.style-1);
    return 10+(a.moving&&!policy.upper_nodes.empty()?p.moving:p.attacks.at(CombatPose::sample(actor,a.sequence)%p.attacks.size()));
  }
};
