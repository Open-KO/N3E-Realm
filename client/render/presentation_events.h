#pragma once
#include "effects.h"
#include "audio.h"
#include "combat_pose.h"
#include "network/world.h"

struct PresentationEvents {
  uint64_t self=0,session=0,cursor=0;
  std::vector<n3e::PresentationEvent> poll(const n3e::WorldState&state){
    if(!state.connected){self=session=cursor=0;return {};}
    const auto&w=state.world;
    if(self!=w.self()||session!=w.session()){
      self=w.self();session=w.session();cursor=w.event_cursor();return {};
    }
    std::vector<n3e::PresentationEvent> result;
    for(const auto&e:w.events())if(e.sequence()>cursor&&e.tick()<=w.tick()&&w.tick()-e.tick()<=40)result.push_back(e);
    cursor=std::max(cursor,w.event_cursor());return result;
  }
  static unsigned selector(const n3e::Release&r,const n3e::PresentationEvent&e){
    if(e.npc())return 4;
    if(e.moving())return 3;
    if(!r.combat_animation||!e.style()||e.style()>r.combat_animation->profiles.size())return 0;
    const auto&profile=r.combat_animation->profiles[e.style()-1];
    return 1+CombatPose::sample(e.actor(),e.request_sequence()?e.request_sequence():e.tick())%profile.attacks.size();
  }
  static double delay(const n3e::Release&r,const n3e::PresentationEvent&e){
    const n3e::Clip*clip=nullptr;
    if(e.npc()&&r.animation&&r.animation->size()>(r.rest?12u:9u))clip=&r.animation->at(r.rest?12:9);
    else if(r.combat_animation&&e.style()&&e.style()<=r.combat_animation->profiles.size()){
      const auto&p=r.combat_animation->profiles[e.style()-1];
      auto index=e.moving()?p.moving:p.attacks[CombatPose::sample(e.actor(),e.request_sequence()?e.request_sequence():e.tick())%p.attacks.size()];
      clip=&r.combat_animation->clips[index];
    }
    if(!clip)return 0;
    float marker=clip->markers[0]>=0?clip->markers[0]:clip->markers[1];
    return marker>=0?clip->blend+marker:0;
  }
  // PQ-420 (D-217): a held ranged shot's landing (kind 6) is the hit half of a
  // strike: the strike's bindings and sounds, at the event, with no marker
  // delay; its start (a kind 2 with no hit) draws only the clip and swing.
  static unsigned binding_kind(const n3e::PresentationEvent&e){return e.kind()==6?2:e.kind();}
  // A stretched clip's swing markers move with it (blend + time x stretch).
  static float swing_at(const n3e::Release&r,const n3e::PresentationEvent&e,float marker){
    if(e.npc()||!r.combat_animation||!e.style()||e.style()>r.combat_animation->profiles.size())return marker;
    const auto&p=r.combat_animation->profiles[e.style()-1];
    if(!p.ranged.cast_ms)return marker;
    const auto&clip=r.combat_animation->clips[p.attacks[0]];
    return clip.blend+(marker-clip.blend)*clip.stretch;
  }
  // PQ-423 (D-220): the cast effect of a held ranged shot's start (a kind 2
  // strike event under a profile with a cast time and a cast effect), or
  // null. 1298's cast start 00583f20 (and an observer's casting phase
  // 00585a90) triggers the archery row's self FX on the caster (00479de0).
  static const n3e::RangedAttack*ranged_cast(const n3e::Release&r,const n3e::PresentationEvent&e){
    if(e.kind()!=2||e.npc()||!r.combat_animation||!e.style()||e.style()>r.combat_animation->profiles.size())return nullptr;
    const auto&ranged=r.combat_animation->profiles[e.style()-1].ranged;
    return ranged.cast_ms&&!ranged.cast_effect.empty()?&ranged:nullptr;
  }
  // Whether `entity`'s strike fields still show the cast that started at `tick`.
  static bool casting(const n3e::Entity&entity,uint64_t tick){return entity.strike_tick()==tick&&entity.strike_result()=="casting";}
  // Starts the cast effect on each of its joints (-1: the actor), from the
  // shot's local start or the event tick, turned with the caster's facing,
  // and tagged with the cast's start tick for cast_stops. Nothing starts when
  // the caster's strike fields no longer show this cast.
  static void cast_effect(n3e::EffectPlayer&player,const n3e::Release&r,const n3e::WorldState&w,const n3e::PresentationEvent&e,double now,
                          const std::map<uint64_t,n3e::V>&positions,const std::map<std::pair<uint64_t,int>,n3e::V>&joints,
                          const std::map<uint64_t,float>&headings,double local_start=-1){
    auto*ranged=ranged_cast(r,e);if(!ranged||!r.effects)return;
    const n3e::Entity*caster=nullptr;for(const auto&a:w.world.entities())if(a.id()==e.actor())caster=&a;
    if(!caster||!casting(*caster,e.tick()))return;
    double start=local_start>=0?local_start:now-double(w.world.tick()-e.tick())*.05;
    for(int joint:ranged->cast_joints){
      n3e::V root{e.x(),e.y(),e.z()};
      if(auto it=positions.find(e.actor());it!=positions.end())root=it->second;
      if(auto it=joints.find({e.actor(),joint});joint>=0&&it!=joints.end())root=it->second;
      if(!player.start(*r.effects,ranged->cast_effect,e.actor(),root,{},1,start,10))continue;
      auto&i=player.active.back();i.joint=joint;i.turn=true;i.tag="ranged:"+std::to_string(e.tick());
      if(auto h=headings.find(e.actor());h!=headings.end())i.heading=h->second;
    }
  }
  // Ends at once every cast effect whose caster's strike fields no longer
  // show its cast (the landing, a cancel, death, a session change): 1298
  // stops the self FX with 0047a710(..., 1) at the release (00584b00) and
  // on a cancel (00586fa0), and 00475e30(1) ends the bundle at once.
  static void cast_stops(n3e::EffectPlayer&player,const n3e::WorldState&w,double now){
    for(auto&i:player.active){
      if(!i.tag.starts_with("ranged:"))continue;
      uint64_t tick=std::stoull(i.tag.substr(7));bool on=false;
      for(const auto&a:w.world.entities())if(a.id()==i.actor)on=casting(a,tick);
      if(!on)i.stop=std::min(i.stop,float(std::max(0.,now-i.start)));
    }
  }
  // PQ-417 (D-222): the flight of a held ranged shot's release, or null.
  // Since PQ-439 (D-223) the server releases a shot under a profile with a
  // flight at its landing tick (a kind 7 event) and lands it when the arrow
  // arrives (the kind 6 event). 1298's release 00584b00 and an observer's
  // flying receive 00585f20 call 00587ac0, which flies the row's flying FX
  // for a type-2 row.
  static const n3e::RangedAttack*ranged_flight(const n3e::Release&r,const n3e::PresentationEvent&e){
    if(e.kind()!=7||e.npc()||!r.combat_animation||!e.style()||e.style()>r.combat_animation->profiles.size())return nullptr;
    const auto&ranged=r.combat_animation->profiles[e.style()-1].ranged;
    return ranged.cast_ms&&!ranged.flight.empty()?&ranged:nullptr;
  }
  using Boxes=std::map<uint64_t,std::array<n3e::V,8>>;
  static n3e::V box_centre(const std::array<n3e::V,8>&box){n3e::V c{};for(const auto&p:box)for(int k=0;k<3;++k)c[k]+=p[k]/8;return c;}
  // Launches `ranged`'s flight for `actor` at `start`: from the shooter's
  // source joint as drawn (004770c0 puts the bundle at the source joint,
  // 0045e160) toward the centre of `target`'s box as last drawn (00587ac0
  // aims at 00460bd0, the actor box's centre), else the target's drawn
  // position (`from` and `aim` when either is not drawn); the direction
  // keeps its pitch (004770c0 normalises the difference), the shooter's
  // facing when the two points meet. Returns the flight, or null.
  static n3e::EffectInstance*launch(n3e::EffectPlayer&player,const n3e::Release&r,const n3e::RangedAttack&ranged,uint64_t actor,uint64_t target,
                                    n3e::V from,n3e::V aim,double start,const std::string&tag,uint64_t request,
                                    const std::map<uint64_t,n3e::V>&positions,const std::map<std::pair<uint64_t,int>,n3e::V>&joints,
                                    const std::map<uint64_t,float>&headings,const Boxes&boxes){
    if(!r.effects)return nullptr;
    if(auto it=positions.find(actor);it!=positions.end())from=it->second;
    if(auto it=joints.find({actor,ranged.flight_joint});ranged.flight_joint>=0&&it!=joints.end())from=it->second;
    if(auto it=positions.find(target);it!=positions.end())aim=it->second;
    if(auto it=boxes.find(target);it!=boxes.end())aim=box_centre(it->second);
    n3e::V dir{aim[0]-from[0],aim[1]-from[1],aim[2]-from[2]};
    float length=std::sqrt(dir[0]*dir[0]+dir[1]*dir[1]+dir[2]*dir[2]);
    if(length>1e-4f)for(auto&v:dir)v/=length;
    else{float h=0;if(auto it=headings.find(actor);it!=headings.end())h=it->second;dir={-std::sin(h),0,-std::cos(h)};length=0;}
    if(!player.start(*r.effects,ranged.flight,actor,from,{},1,start,10))return nullptr;
    auto&i=player.active.back();i.tag=tag;
    i.flight=n3e::EffectInstance::Flight{from,dir,ranged.flight_speed,-1,length,n3e::flight_rotation(dir),target,ranged.hit,ranged.hit_joint,request};
    return &i;
  }
  // Launches the release event's flight at the event's time.
  static void flight(n3e::EffectPlayer&player,const n3e::Release&r,const n3e::WorldState&w,const n3e::PresentationEvent&e,double now,
                     const std::map<uint64_t,n3e::V>&positions,const std::map<std::pair<uint64_t,int>,n3e::V>&joints,
                     const std::map<uint64_t,float>&headings,const Boxes&boxes){
    auto*ranged=ranged_flight(r,e);if(!ranged)return;
    launch(player,r,*ranged,e.actor(),e.target(),{e.x(),e.y(),e.z()},{e.target_x(),e.target_y(),e.target_z()},
           now-double(w.world.tick()-e.tick())*.05,"flight:"+std::to_string(e.tick()),e.request_sequence(),positions,joints,headings,boxes);
  }
  // PQ-445: `pending`: the local archer's predicted flight, whose hit waits
  // for the server's release (LocalRelease).
  struct Arrival{uint64_t actor,target;std::string tag,hit;int joint;double at;float reach;n3e::V point;bool box;uint64_t request=0;bool pending=false;double launched=0;};
  // Starts an arrival's hit clip at `at` on the target's hit joint (its
  // position without one; the arrival point when the target is not drawn).
  static bool hit(n3e::EffectPlayer&player,const n3e::Release&r,const Arrival&a,double at,const std::map<uint64_t,n3e::V>&positions,
                  const std::map<std::pair<uint64_t,int>,n3e::V>&joints){
    if(!r.effects||a.hit.empty())return false;
    n3e::V root=a.point;
    if(auto it=positions.find(a.target);it!=positions.end())root=it->second;
    if(auto it=joints.find({a.target,a.joint});a.joint>=0&&it!=joints.end())root=it->second;
    if(!player.start(*r.effects,a.hit,a.target,root,{},1,at,10))return false;
    auto&h=player.active.back();h.joint=a.joint;h.tag="hit:"+a.tag.substr(7);return true;
  }
  // Ends every flight that has arrived, as of `now`, and starts its hit
  // clip on the target: where the ray from the flight's start first enters
  // the target's current box (1298's 0047a8d0 stops the bundle at the
  // collision with the actor's box, 0045c2c0), or, when the ray no longer
  // meets the box, at the launch distance. The hit clip follows the
  // target's hit joint (00586fa0's -101 receive triggers the row's target
  // FX at the target's part through 00479de0, move type -1). A pending
  // flight's hit is left to its caller (PQ-445).
  static std::vector<Arrival> flights(n3e::EffectPlayer&player,const n3e::Release&r,double now,const std::map<uint64_t,n3e::V>&positions,
                                      const std::map<std::pair<uint64_t,int>,n3e::V>&joints,const Boxes&boxes){
    std::vector<Arrival> arrived;
    for(auto&i:player.active){
      if(!i.flight)continue;
      auto b=boxes.find(i.flight->target);bool box=false;
      if(!n3e::flight_arrive(i,now,b!=boxes.end()?&b->second:nullptr,box))continue;
      const auto&f=*i.flight;
      arrived.push_back({i.actor,f.target,i.tag,f.hit,f.hit_joint,i.start+f.reach/f.speed,f.reach,i.position(f.reach/f.speed),box,f.request,f.pending,i.start});
      i.flight->pending=false; // a pending arrival's hit is its caller's now
    }
    for(const auto&a:arrived)if(!a.pending)hit(player,r,a,a.at,positions,joints);
    return arrived;
  }
  static void effects(n3e::EffectPlayer&player,const n3e::Release&r,const n3e::WorldState&w,const n3e::PresentationEvent&e,double now,const std::map<uint64_t,n3e::V>&positions,const std::map<std::pair<uint64_t,int>,n3e::V>&joints={},double local_start=-1){
    if(!r.effects||((e.kind()==2||e.kind()==6)&&!e.hit()))return;
    if(e.kind()>=3&&r.skills)for(const auto&s:r.skills->entries)if(s.id==e.key()){
      auto tag="cast:"+s.id;
      if(e.kind()!=3)for(auto&i:player.active)if(i.actor==e.actor()&&i.tag==tag)i.stop=std::min(i.stop,float(now-i.start));
      if(e.kind()==5)return;
      auto start=[&](int joint,const std::string&clip,uint64_t actor,float duration){
        n3e::V root{e.target_x(),e.target_y(),e.target_z()};
        if(auto it=positions.find(actor);it!=positions.end())root=it->second;
        if(auto it=joints.find({actor,joint});it!=joints.end())root=it->second;
        double age=double(w.world.tick()-e.tick())*.05;
        if(player.start(*r.effects,clip,actor,root,{},1,now-age,duration)){auto&i=player.active.back();i.joint=joint;i.tag=e.kind()==3?tag:"";}
      };
      if(e.kind()==3)for(int joint:s.cast_joints)start(joint,s.cast_effect,e.actor(),s.cast_ms/1000.f);
      else start(s.target_joint,s.target_effect,e.target(),10);
      return;
    }
    unsigned selected=binding_kind(e)==2?selector(r,e):0;
    double start=local_start>=0?std::max(now,local_start+delay(r,e)):now-double(w.world.tick()-e.tick())*.05+(e.kind()==2?delay(r,e):0);
    n3e::V root{e.target_x(),e.target_y(),e.target_z()};
    if(auto it=positions.find(e.target());it!=positions.end())root=it->second;
    bool npc=false;for(const auto&actor:w.world.entities())if(actor.id()==e.target())npc=actor.npc();
    for(const auto&binding:r.effects->bindings){
      if(binding.kind!=binding_kind(e)||(binding.key!="*"&&binding.key!=e.key())||(binding.selector&&binding.selector!=selected))continue;
      n3e::V offset{};
      if(binding.anchor==1&&r.target_marker)offset[1]=r.target_marker->bounds[npc?1:0][1]*.5f;
      int joint=int(binding.anchor)-2;
      if(binding.anchor>=2)if(auto it=joints.find({e.target(),joint});it!=joints.end())root=it->second;
      const auto&key=binding.clips[CombatPose::sample(e.actor(),e.sequence())%binding.clips.size()];
      float stop=10;if(e.kind()==3)for(const auto&c:r.consumables)if(c.item==e.key())stop=std::max(.05f,c.delay_ms/1000.f);
      if(player.start(*r.effects,key,e.target(),root,offset,1,start,stop)&&binding.anchor>=2)player.active.back().joint=joint;
    }
  }
  static void audio(n3e::AudioMixer&mixer,const n3e::Release&r,const n3e::WorldState&w,const n3e::PresentationEvent&e,double now,double local_start=-1,bool skip_swing=false,uint64_t request=0,bool skip_flight=false){
    if(!r.audio)return;
    const auto&data=*r.audio;
    // "effect:" keys are effect-bundle sounds, which take the package start test (PQ-013).
    auto play=[&](const std::string&key,double when,bool target){mixer.play(data,key,when,target?n3e::V{e.target_x(),e.target_y(),e.target_z()}:n3e::V{e.x(),e.y(),e.z()},true,request,key.starts_with("effect:"));};
    double start=local_start>=0?local_start:now-double(w.world.tick()-e.tick())*.05;
    if(e.kind()>=3&&r.skills)for(const auto&s:r.skills->entries)if(s.id==e.key()){
      if(e.kind()!=5)play("effect:"+(e.kind()==3?s.cast_effect:s.target_effect),start,e.kind()!=3);
      return;
    }
    // PQ-423 (D-220): a ranged cast effect's bundle sound, once per joint
    // at the cast start (1298's trigger 00475d20 plays the FX row's sound).
    if(auto*ranged=ranged_cast(r,e))for(size_t n=0;n<ranged->cast_joints.size();++n)play("effect:"+ranged->cast_effect,start,false);
    // PQ-417 (D-222): the flight's bundle sound (0047a2d0 -> 00475d20) and
    // the release sound (00587ac0 plays 0x157c for a kind 70-79 bow) at the
    // shooter when the flight launches. PQ-445: not for the archer's own
    // release whose flight its client already launched (LocalRelease).
    if(auto*ranged=skip_flight?nullptr:ranged_flight(r,e)){play("effect:"+ranged->flight,start,false);if(!ranged->release.empty())play(ranged->release,start,false);}
    auto selected=binding_kind(e)==2?selector(r,e):0;
    if(e.kind()==2){
      auto timing=data.timings.find({e.npc()?0:e.style(),selected});
      if(!skip_swing&&timing!=data.timings.end())for(float marker:timing->second)play(e.npc()?"swing:npc":"swing:player",start+swing_at(r,e,marker),false);
      if(!e.hit())return;
      start+=delay(r,e);if(local_start>=0)start=std::max(now,start);play("blow",start,true);
      for(const auto&target:w.world.entities())if(target.id()==e.target())play(target.npc()?"struck:npc":"struck:player",start,true);
    }
    if(e.kind()==6){
      if(!e.hit())return;
      play("blow",start,true);
      for(const auto&target:w.world.entities())if(target.id()==e.target())play(target.npc()?"struck:npc":"struck:player",start,true);
    }
    if(r.effects)for(const auto&b:r.effects->bindings){
      if(b.kind!=binding_kind(e)||(b.key!="*"&&b.key!=e.key())||(b.selector&&b.selector!=selected))continue;
      play("effect:"+b.clips[CombatPose::sample(e.actor(),e.sequence())%b.clips.size()],start,true);
    }
  }
};
