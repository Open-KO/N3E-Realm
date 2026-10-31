#pragma once
#include "melee_presentation.h"
#include "presentation_events.h"
#include <set>
#include <deque>
#include <algorithm>

// PQ-445 (D-226): the local archer's own release, predicted. 1298's shooter
// releases when its own clip passes the marker (the cast tick 00585830 calls
// the release 00584b00 once 004689f0 sees the first marker pass), stops its
// self FX there (0047a710 at 00584f6f, 00584f84) and flies the arrow at once
// on its own client (005855bc -> 00587ac0 -> 0047a2d0) as it sends the
// flying phase; observers fly it on the flying packet (00585f20, only for a
// caster other than the local player). n3e's server still releases and lands
// the shot on its own clock (D-223, D-224), so this is presentation only:
// nothing here changes a snapshot, a result or a request. The predicted
// flight is pending until the server's release event (kind 7) for its request
// confirms it; a pending flight that arrives holds its hit until then, and a
// shot the server does not release (a refusal, a cancel, death, a session
// change) ends it and drops the held hit.
struct LocalRelease {
  std::vector<PresentationEvents::Arrival> held;
  // Requests whose predicted flight was confirmed (by their release event or
  // their hit or miss result), newest last: a later release event for one of
  // them launches nothing (both can reach the client in one frame).
  std::deque<uint64_t> confirmed;
  // A session change restarts the request sequences.
  void reset(){held.clear();confirmed.clear();}
  // The flight a shot under profile `style` flies at a predicted release
  // (a held ranged profile with a flight), or null.
  static const n3e::RangedAttack*flight(const n3e::Release&r,unsigned style){
    if(!r.combat_animation||!style||style>r.combat_animation->profiles.size())return nullptr;
    const auto&p=r.combat_animation->profiles[style-1];
    return p.ranged.cast_ms&&!p.ranged.flight.empty()&&p.attacks.size()==1?&p.ranged:nullptr;
  }
  // The predicted release of a shot started locally at `start`: where its
  // drawn attack clip, stretched to the cast, passes its first marker (the
  // entry blend plus the stretched marker; the server's landing_ticks before
  // it rounds up to the tick).
  static double at(const n3e::Release&r,unsigned style,double start){
    const auto&c=r.combat_animation->clips[r.combat_animation->profiles[style-1].attacks[0]];
    return start+c.blend+c.markers[0];
  }
  // The audio request of a predicted launch's sounds: apart from the shot's
  // own, which a refused result cancels after its release too.
  static uint64_t voice(uint64_t request){return request|uint64_t(1)<<63;}
  struct Cast {uint64_t actor;std::string tag;int joint;float stop;};
  // `start`: the launching frame; `due`: the predicted release; `predicted`:
  // that less the shot's local start.
  struct Launched {uint64_t request;double start,due,predicted;n3e::EffectInstance::Flight flight;std::vector<Cast> casts;};
  // Launches the flight of each of the archer's own shots whose predicted
  // release has come and that no release event has launched: on the first
  // frame at or after that time, toward its target as drawn now, with the flight and release sounds at the
  // archer, and ends the archer's cast effect there. A shot whose archer or
  // target is not drawn then is left to its release event.
  std::vector<Launched> launch(MeleePresentation&shots,n3e::EffectPlayer&player,n3e::AudioMixer&mixer,const n3e::Release&r,double now,
                               const std::map<uint64_t,n3e::V>&positions,const std::map<std::pair<uint64_t,int>,n3e::V>&joints,
                               const std::map<uint64_t,float>&headings,const PresentationEvents::Boxes&boxes){
    std::vector<Launched> out;
    for(auto&a:shots.attempts){
      auto*ranged=a.cancelled||a.released>=0?nullptr:flight(r,a.style);
      if(!ranged)continue;
      double when=at(r,a.style,a.start);
      if(now<when)continue;
      a.released=when;
      auto self=positions.find(shots.actor),target=positions.find(a.target);
      if(self==positions.end()||target==positions.end())continue;
      // The frame that sees the marker passed releases, as 1298's per-frame
      // cast tick does: the flight starts at this frame, so this frame draws
      // it at its start however short it is.
      auto*i=PresentationEvents::launch(player,r,*ranged,shots.actor,a.target,self->second,target->second,now,"flight:0",a.sequence,
                                        positions,joints,headings,boxes);
      if(!i)continue;
      i->flight->pending=true;
      Launched l{a.sequence,now,when,when-a.start,*i->flight,{}};
      for(auto&c:player.active)
        if(c.actor==shots.actor&&c.tag.starts_with("ranged:")&&c.stop>float(now-c.start)){
          c.stop=float(std::max(0.,now-c.start));l.casts.push_back({c.actor,c.tag,c.joint,c.stop});
        }
      if(r.audio){
        mixer.play(*r.audio,"effect:"+ranged->flight,now,self->second,true,voice(a.sequence),true);
        if(!ranged->release.empty())mixer.play(*r.audio,ranged->release,now,self->second,true,voice(a.sequence),false);
      }
      out.push_back(std::move(l));
    }
    return out;
  }
  // Holds a pending flight's arrival until its release is confirmed.
  void hold(const PresentationEvents::Arrival&a){
    if(held.size()==16)held.erase(held.begin());
    held.push_back(a);
  }
  struct Confirmed {bool found=false;double lead=0;std::vector<PresentationEvents::Arrival> hits;std::vector<double> held;};
  // The server released `request` at `tick` (its release event): its pending
  // flight flies on as the server's, and a held hit starts now. `found`:
  // there was one, so the event launches no second flight; `lead`: how long
  // the predicted flight had flown.
  Confirmed confirm(uint64_t request,uint64_t tick,n3e::EffectPlayer&player,const n3e::Release&r,double now,
                    const std::map<uint64_t,n3e::V>&positions,const std::map<std::pair<uint64_t,int>,n3e::V>&joints){
    Confirmed c;
    if(!request)return c;
    if(std::find(confirmed.begin(),confirmed.end(),request)!=confirmed.end()){c.found=true;return c;}
    for(auto&i:player.active)if(i.flight&&i.flight->pending&&i.flight->request==request){
      i.flight->pending=false;i.tag="flight:"+std::to_string(tick);c.found=true;c.lead=now-i.start;
    }
    std::vector<PresentationEvents::Arrival> due;
    for(auto it=held.begin();it!=held.end();){
      if(it->request!=request){++it;continue;}
      auto a=*it;a.tag="flight:"+std::to_string(tick);a.pending=false;
      if(!c.found)c.lead=now-a.launched;
      c.found=true;c.held.push_back(now-a.at);due.push_back(a);
      it=held.erase(it);
    }
    if(c.found){if(confirmed.size()==32)confirmed.pop_front();confirmed.push_back(request);}
    // Started after the loops: a start may drop the oldest instance.
    for(const auto&a:due)if(PresentationEvents::hit(player,r,a,now,positions,joints))c.hits.push_back(a);
    return c;
  }
  struct Cancelled {uint64_t request;double age;bool held;};
  // The held hits the last reconcile started (their shots' results came).
  std::vector<PresentationEvents::Arrival> settled;
  // Ends every pending flight, and drops every held hit, whose shot the
  // server will not release: its result was a refusal or a cancel, or its
  // attempt is gone (death, a skill cast, a session change, the 10 s bound).
  // A shot whose result was a hit or a miss flew (its release event was not
  // seen): its flight is confirmed. The viewer runs it after the frame's
  // release events, so a release event and its result in one frame confirm
  // through the event.
  std::vector<Cancelled> reconcile(MeleePresentation&shots,n3e::EffectPlayer&player,n3e::AudioMixer&mixer,const n3e::Release&r,double now,
                                   const std::map<uint64_t,n3e::V>&positions,const std::map<std::pair<uint64_t,int>,n3e::V>&joints){
    std::vector<Cancelled> out;
    auto state=[&](uint64_t request){auto*a=shots.find(request);return !a||a->cancelled?0:a->landed?2:1;};
    std::set<uint64_t> landed;
    for(auto&i:player.active){
      if(!i.flight||!i.flight->pending)continue;
      auto&f=*i.flight;int s=state(f.request);
      if(s==2)landed.insert(f.request);
      if(s!=0)continue;
      double age=std::max(0.,now-i.start);
      if(f.reach<0)f.reach=std::min(float(age)*f.speed,f.launch);
      f.pending=false;f.hit.clear();i.stop=std::min(i.stop,float(age));
      mixer.cancel(voice(f.request));
      out.push_back({f.request,age,false});
    }
    for(auto it=held.begin();it!=held.end();){
      int s=state(it->request);
      if(s==2)landed.insert(it->request);
      if(s!=0){++it;continue;}
      mixer.cancel(voice(it->request));
      out.push_back({it->request,now-it->launched,true});
      it=held.erase(it);
    }
    settled.clear();
    for(auto request:landed)for(auto&a:confirm(request,0,player,r,now,positions,joints).hits)settled.push_back(a);
    return out;
  }
};
