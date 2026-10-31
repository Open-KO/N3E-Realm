#pragma once
#include "assets/assets.h"
#include "wire.pb.h"

// Cosmetic variant derived once from a public strike identity. It never draws
// from gameplay RNG and every observer selects the same frozen strike profile.
struct CombatPose {
  uint64_t entity=0,strike=0;
  unsigned attack=2;bool layered=false;
  static uint64_t sample(uint64_t id,uint64_t tick){
    uint64_t x=id^(tick+0x9e3779b97f4a7c15ULL);
    x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;
    x=(x^(x>>27))*0x94d049bb133111ebULL;
    return x^(x>>31);
  }
  void update(const n3e::CombatAnimation&policy,const n3e::Entity&e){
    if(entity!=e.id()){*this=CombatPose{};entity=e.id();}
    if(strike==e.strike_tick())return;
    strike=e.strike_tick();
    if(!strike||!e.strike_style())return;
    const auto&p=policy.profiles.at(e.strike_style()-1);
    layered=e.strike_moving()&&!policy.upper_nodes.empty();
    attack=10+(layered?p.moving:p.attacks.at(sample(entity,e.strike_sequence()?e.strike_sequence():strike)%p.attacks.size()));
  }
  unsigned clip(const n3e::CombatAnimation&policy,const n3e::Entity&e,int role) const {
    if(role==2)return attack;
    if(role==6)return 10+policy.profiles.at(e.combat_style()-1).ready;
    return role;
  }
};
