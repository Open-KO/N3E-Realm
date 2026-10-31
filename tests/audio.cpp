#include "render/audio.h"
#include "render/melee_presentation.h"
#include "render/presentation_events.h"
#include "render/local_release.h"
#include <iostream>
#include <stdexcept>
#include <source_location>
void need(bool value,std::source_location where=std::source_location::current()){if(!value)throw std::runtime_error("audio/event check line "+std::to_string(where.line()));}
bool near(float a,float b){return std::abs(a-b)<1e-5f;}
float energy(const std::vector<float>&out){float sum=0;for(float x:out)sum+=std::abs(x);return sum;}
// PQ-013: KO effect start test, listener frame, curves and fixed source positions.
void spatial_checks(){
  const n3e::AudioSpatial legacy,ko{1,48,20,48,30,2};
  // Sound.Distance: default 48; a player's integer option clamps to 20..48 (0064b9b0).
  need(ko.start_distance()==48&&ko.start_distance(10)==20&&ko.start_distance(30)==30&&ko.start_distance(100)==48);
  need(legacy.start_distance()==0&&legacy.start_distance(30)==0);
  // Strict "<" against the camera eye (00475d20 FCOMP/TEST AH,1).
  need(n3e::effect_starts({47.99f,0,0},{},48)&&!n3e::effect_starts({48,0,0},{},48)&&!n3e::effect_starts({0,0,60},{},48));
  // Curves: full gain to the reference, inverse distance beyond it; the cut-off
  // fades over its last 5 m only for voices without the start test.
  n3e::AudioListener at{{},{},{1,0,0}};
  need(near(n3e::place_sound(ko,{1,0,0},at,false).gain,1)&&near(n3e::place_sound(ko,{4,0,0},at,false).gain,.5f));
  need(near(n3e::place_sound(ko,{27.5f,0,0},at,false).gain,2/27.5f*.5f)&&n3e::place_sound(ko,{30,0,0},at,false).gain==0);
  need(near(n3e::place_sound(ko,{40,0,0},at,true).gain,2/40.f)&&near(n3e::place_sound(ko,{47.9f,0,0},at,true).gain,2/47.9f));
  need(near(n3e::place_sound(ko,{0,0,5},at,true).pan,0)&&near(n3e::place_sound(ko,{3,0,4},at,true).pan,.6f));
  // The listener frame pans: facing heading 0 hears +x on the right, heading pi on the left.
  auto facing=[](float h){return n3e::AudioListener{{50,9,50},{},{std::cos(h),0,-std::sin(h)}};};
  need(n3e::place_sound(ko,{5,0,0},facing(0),true).pan>.99f&&n3e::place_sound(ko,{5,0,0},facing(3.14159265f),true).pan<-.99f);
  n3e::Audio a;a.clips.push_back({8,std::vector<float>(48000,.5f)});a.bindings["effect:x"]=0;a.bindings["swing:player"]=0;
  n3e::AudioMixer m;m.spatial=ko;
  // Started at 47 m from the eye: audible with no cut-off (the 30 m cut-off would silence it).
  need(m.play(a,"effect:x",1,{47,0,0},true,0,true));need(m.play(a,"swing:player",1,{47,0,0},true));
  auto out=m.mix(1,100,{{},{},{1,0,0}});need(m.voices.size()==2&&energy(out)>0);
  need(near(out[1],.5f*.6f*2/47*std::sqrt(1.f))&&out[0]<1e-6f); // only the effect, fully right
  // At exactly 48 m from the eye it never starts, though the listener stands on it,
  // and it stays silent when the eye comes near later.
  m.voices.clear();need(m.play(a,"effect:x",1,{48,0,0},true,0,true));
  need(energy(m.mix(1,100,{{},{48,0,0},{1,0,0}}))==0&&m.voices.empty());
  need(energy(m.mix(1.01,100,{{48,0,0},{48,0,0},{1,0,0}}))==0);
  // The test runs in the chunk where the voice begins, not when it is queued.
  need(m.play(a,"effect:x",2,{10,0,0},true,0,true));
  m.mix(1,100,{{100,0,0},{},{1,0,0}});need(m.voices.size()==1&&!m.voices[0].checked);
  need(energy(m.mix(2,100,{{},{},{1,0,0}}))>0&&m.voices[0].checked);
  // Once started it keeps playing however far the eye moves (KO halts no 3-D sample on distance).
  need(energy(m.mix(2.1,100,{{500,0,0},{},{1,0,0}}))>0);
  // The source keeps its start position (KO 004501b0 sets it once; 0044fdf0 changes
  // only volume); the moving listener changes the gain chunk by chunk.
  auto near_chunk=m.mix(2.2,100,{{},{8,0,0},{1,0,0}}),far_chunk=m.mix(2.3,100,{{},{-10,0,0},{1,0,0}});
  need(m.voices[0].position==n3e::V{10,0,0}&&energy(near_chunk)>energy(far_chunk)*4);
  // Without N3A2 data an effect takes the 30 m cut-off like any positional voice.
  n3e::AudioMixer old;need(old.play(a,"effect:x",1,{40,0,0},true,0,true));
  need(energy(old.mix(1,100,{{},{},{1,0,0}}))==0&&old.voices.size()==1);
  // Presentation events flag effect-bundle sounds ("effect:" keys) for the start test only.
  n3e::Release r;r.audio=a;r.audio->bindings["blow"]=0;r.effects.emplace();r.effects->bindings.push_back({2,"*",0,0,{"x"}});
  n3e::WorldState w;w.world.set_tick(50);n3e::PresentationEvent e;e.set_kind(2);e.set_tick(50);e.set_npc(true);e.set_hit(true);
  n3e::AudioMixer events;PresentationEvents::audio(events,r,w,e,5);
  need(events.voices.size()==2&&!events.voices[0].effect&&events.voices[1].effect&&events.voices[1].positional);
  std::cout<<"PASS KO effect start test (<48 m from the eye, 20-48 option), listener frame, curves and fixed source positions\n";
}
// PQ-445 (D-226): the archer's own held shot launches its flight at its
// predicted release (the local start plus the stretched clip's blend and
// first marker; 1298's cast tick 00585830 releases at the marker and
// 00584b00 flies the arrow at once, 005855bc -> 00587ac0), pending until the
// server's release event confirms it; the event then launches no second
// flight. A pending flight that arrives holds its hit until the release
// event; a refused shot ends its flight and drops its hit; a hit or miss
// result confirms a flight whose release event was not seen. Nothing here
// changes the snapshot.
void local_release_checks(){
  n3e::Release r;r.combat_animation.emplace();auto&p=*r.combat_animation;
  p.clips.resize(2);for(auto&c:p.clips){c.duration=.9f;c.blend=.2f;c.markers={.72f,-1};c.stretch=.9f;}
  p.profiles={{0,{0}},{0,{1}}};p.profiles[1].moving=1;
  auto&ranged=p.profiles[1].ranged;ranged.cast_ms=900;ranged.flight="arrow";ranged.flight_speed=10;ranged.hit="blow";ranged.release="pull";
  r.effects.emplace();n3e::EffectBatch tri{0,0,5,6,199,{0,0,-1,0,0,1,1,1,1, .1f,0,0,0,0,1,1,1,1, 0,.1f,0,0,0,1,1,1,1}};
  r.effects->clips.emplace("arrow",n3e::EffectClip{false,10,std::vector<std::vector<n3e::EffectBatch>>(100,{tri})});
  r.effects->clips.emplace("blow",n3e::EffectClip{false,10,std::vector<std::vector<n3e::EffectBatch>>(5,{tri})});
  r.audio.emplace();r.audio->clips.push_back({16,std::vector<float>(4800,.5f)});r.audio->bindings["pull"]=0;r.audio->bindings["effect:arrow"]=0;
  need(LocalRelease::flight(r,1)==nullptr&&LocalRelease::flight(r,2)==&ranged&&LocalRelease::flight(r,3)==nullptr);
  need(std::abs(LocalRelease::at(r,2,10)-10.92)<1e-6);
  n3e::WorldState w;w.connected=true;w.world.set_session(1);w.world.set_self(7);w.world.set_tick(100);
  auto*actor=w.world.add_entities();actor->set_id(7);actor->set_health(100);actor->set_combat_style(2);
  const auto before=w.world.SerializeAsString();
  std::map<uint64_t,n3e::V> positions{{7,{0,0,0}},{8,{0,0,-10}}};std::map<std::pair<uint64_t,int>,n3e::V> joints;std::map<uint64_t,float> headings;
  // A box in pick_attack.h's corner order (tests/effects.cpp).
  auto corners=[](n3e::V lo,n3e::V hi){return std::array<n3e::V,8>{{{lo[0],hi[1],lo[2]},{hi[0],hi[1],lo[2]},{hi[0],lo[1],lo[2]},{lo[0],lo[1],lo[2]},
                                                                  {hi[0],hi[1],hi[2]},{lo[0],hi[1],hi[2]},{lo[0],lo[1],hi[2]},{hi[0],lo[1],hi[2]}}};};
  PresentationEvents::Boxes boxes;boxes[8]=corners({-.5f,0,-10.5f},{.5f,2,-9.5f});
  n3e::AudioMixer mixer;MeleePresentation shots;shots.context(7,1,true,false,10,mixer);
  n3e::EffectPlayer fx;LocalRelease local;
  // The archer's cast effect, drawn since the shot's start.
  r.effects->clips.emplace("cast",n3e::EffectClip{false,10,std::vector<std::vector<n3e::EffectBatch>>(30,{tri})});
  need(fx.start(*r.effects,"cast",7,{0,0,0},{},1,10));fx.active.back().tag="ranged:100";
  shots.begin(41,8,2,false,10);
  // Before the marker: nothing; at it: one pending flight from the marker's time.
  need(local.launch(shots,fx,mixer,r,10.9,positions,joints,headings,boxes).empty());
  auto l=local.launch(shots,fx,mixer,r,10.93,positions,joints,headings,boxes);
  need(l.size()==1&&l[0].request==41&&std::abs(l[0].start-10.93)<1e-6&&std::abs(l[0].due-10.92)<1e-6&&std::abs(l[0].predicted-.92)<1e-6); // at the frame that sees it
  need(fx.active.size()==2&&fx.active.back().flight&&fx.active.back().flight->pending&&fx.active.back().flight->request==41);
  need(std::abs(fx.active.back().flight->dir[1]-1/std::sqrt(101.f))<1e-5f&&std::abs(fx.active.back().flight->launch-std::sqrt(101.f))<1e-4f); // toward the box centre (0, 1, -10)
  // The cast effect ends at the release (00584b00 stops the self FX).
  need(l[0].casts.size()==1&&std::abs(fx.active[0].stop-.93f)<1e-5f);
  // The flight and release sounds at the archer, under the launch's own request.
  need(mixer.voices.size()==2&&std::all_of(mixer.voices.begin(),mixer.voices.end(),[](const auto&v){return v.request==LocalRelease::voice(41)&&std::abs(v.start-10.93)<1e-6;}));
  need(local.launch(shots,fx,mixer,r,11,positions,joints,headings,boxes).empty()); // once
  // The release event confirms it: no second flight, its tick on the tag.
  auto c=local.confirm(41,119,fx,r,11.,positions,joints);
  need(c.found&&c.hits.empty()&&std::abs(c.lead-.07)<1e-6&&!fx.active.back().flight->pending&&fx.active.back().tag=="flight:119");
  {auto again=local.confirm(41,119,fx,r,11.,positions,joints);need(again.found&&again.hits.empty());} // a repeat still launches nothing
  // A confirmed flight's hit starts at its arrival (the box's face 9.5 m ahead).
  auto arrived=PresentationEvents::flights(fx,r,11.9,positions,joints,boxes);
  need(arrived.size()==1&&!arrived[0].pending&&fx.active.back().tag=="hit:119");
  // A second shot arrives before its release event: the hit waits for it.
  shots.begin(42,8,2,false,12);positions[8]={0,0,-1.5f};boxes[8]=corners({-.5f,0,-2},{.5f,2,-1});
  need(local.launch(shots,fx,mixer,r,12.93,positions,joints,headings,boxes).size()==1);
  arrived=PresentationEvents::flights(fx,r,13.1,positions,joints,boxes);
  need(arrived.size()==1&&arrived[0].pending&&arrived[0].request==42);
  auto hits=std::count_if(fx.active.begin(),fx.active.end(),[](const auto&i){return i.tag.starts_with("hit:");});
  local.hold(arrived[0]);need(local.held.size()==1);
  need(local.reconcile(shots,fx,mixer,r,13.15,positions,joints).empty()); // still awaited
  c=local.confirm(42,140,fx,r,13.2,positions,joints);
  need(c.found&&c.hits.size()==1&&c.held.size()==1&&std::abs(c.held[0]-(13.2-arrived[0].at))<1e-6&&local.held.empty());
  need(std::count_if(fx.active.begin(),fx.active.end(),[](const auto&i){return i.tag=="hit:140";})==1&&std::abs(fx.active.back().start-13.2)<1e-9);
  need(std::count_if(fx.active.begin(),fx.active.end(),[](const auto&i){return i.tag.starts_with("hit:");})==hits+1);
  // A third shot is refused (no_ammo at its release): its flight ends where
  // it is, its sounds stop, and a late release event finds none to confirm.
  positions[8]={0,0,-10};boxes.erase(8);
  shots.begin(43,8,2,false,14);need(local.launch(shots,fx,mixer,r,14.93,positions,joints,headings,boxes).size()==1);
  auto*third=&fx.active.back();need(third->flight->request==43);
  shots.result(43,"no_ammo",mixer);
  auto x=local.reconcile(shots,fx,mixer,r,15.02,positions,joints);
  need(x.size()==1&&x[0].request==43&&!x[0].held&&std::abs(x[0].age-.09)<1e-6);
  need(!third->flight->pending&&third->flight->hit.empty()&&std::abs(third->stop-.09f)<1e-5f&&std::abs(third->flight->reach-.9f)<1e-4f);
  need(std::none_of(mixer.voices.begin(),mixer.voices.end(),[](const auto&v){return v.request==LocalRelease::voice(43);}));
  need(PresentationEvents::flights(fx,r,20,positions,joints,boxes).empty());   // it never arrives
  need(!local.confirm(43,160,fx,r,15.1,positions,joints).found);
  // A fourth arrives, then is cancelled (the walk, death, a refusal): its held hit is dropped.
  positions[8]={0,0,-1.5f};
  shots.begin(44,8,2,false,16);need(local.launch(shots,fx,mixer,r,16.93,positions,joints,headings,boxes).size()==1);
  arrived=PresentationEvents::flights(fx,r,17.2,positions,joints,boxes);
  need(arrived.size()==1&&arrived[0].pending);local.hold(arrived[0]);
  shots.find(44)->cancelled=true;
  x=local.reconcile(shots,fx,mixer,r,17.3,positions,joints);
  need(x.size()==1&&x[0].request==44&&x[0].held&&local.held.empty());
  // A fifth's release event is never seen, but its result (a hit) is: it flew.
  shots.begin(45,8,2,false,18);need(local.launch(shots,fx,mixer,r,18.93,positions,joints,headings,boxes).size()==1);
  arrived=PresentationEvents::flights(fx,r,19.2,positions,joints,boxes);local.hold(arrived[0]);
  shots.result(45,"hit",mixer);
  hits=std::count_if(fx.active.begin(),fx.active.end(),[](const auto&i){return i.tag.starts_with("hit:");});
  need(local.reconcile(shots,fx,mixer,r,19.3,positions,joints).empty()&&local.held.empty());
  need(std::count_if(fx.active.begin(),fx.active.end(),[](const auto&i){return i.tag.starts_with("hit:");})==hits+1);
  // Its hit result and its release event in one frame: the result confirms
  // it, and the event then finds it confirmed and launches nothing.
  need(local.confirm(45,170,fx,r,19.3,positions,joints).found);
  // So too for a shot still in the air: one flight, one pair of launch sounds.
  positions[8]={0,0,-10};shots.begin(49,8,2,false,19.5);need(local.launch(shots,fx,mixer,r,20.43,positions,joints,headings,boxes).size()==1);
  shots.result(49,"hit",mixer);need(local.reconcile(shots,fx,mixer,r,20.45,positions,joints).empty());
  need(local.confirm(49,180,fx,r,20.45,positions,joints).found);
  need(std::count_if(fx.active.begin(),fx.active.end(),[](const auto&i){return i.flight&&i.flight->request==49;})==1);
  need(std::count_if(mixer.voices.begin(),mixer.voices.end(),[](const auto&v){return v.request==LocalRelease::voice(49);})==2);
  local.reset();need(!local.confirm(49,180,fx,r,20.5,positions,joints).found&&local.held.empty());
  // An undrawn target leaves the shot to its release event; a session change forgets every shot.
  positions.erase(8);shots.begin(46,8,2,false,20.5);
  need(local.launch(shots,fx,mixer,r,21.43,positions,joints,headings,boxes).empty()&&shots.find(46)->released>=0);
  positions[8]={0,0,-10};shots.begin(47,8,2,false,21);need(local.launch(shots,fx,mixer,r,21.93,positions,joints,headings,boxes).size()==1);
  shots.context(7,2,true,false,22,mixer);
  x=local.reconcile(shots,fx,mixer,r,22,positions,joints);need(x.size()==1&&x[0].request==47);
  // A melee profile predicts nothing.
  shots.begin(48,8,1,false,23);need(local.launch(shots,fx,mixer,r,30,positions,joints,headings,boxes).empty());
  need(w.world.SerializeAsString()==before);
  std::cout<<"PASS PQ-445 local release: the archer's own shot flies at its predicted release (start + blend + marker) with its "
             "sounds, ending its cast effect there; the release event confirms it without a second flight; an early arrival "
             "holds its hit until then; a refused, cancelled or forgotten shot ends its flight and drops its hit; a hit result "
             "confirms an unseen release, after which its release event launches nothing; an undrawn target or a melee profile predicts nothing\n";
}
int main(int argc,char**argv){try{
  if(argc==2){auto a=n3e::load_audio(argv[1]);const auto&s=a.spatial;
    std::cout<<"PASS audio clips="<<a.clips.size()<<" bindings="<<a.bindings.size()<<" listener="<<s.listener<<" effect="<<s.effect_distance
             <<" option="<<s.effect_distance_min<<'-'<<s.effect_distance_max<<" cutoff="<<s.cutoff<<" reference="<<s.reference<<'\n';return 0;}
  {
    n3e::Release r;r.combat_animation.emplace();auto&p=*r.combat_animation;
    p.profiles={{0,{1,2}}};p.profiles[0].moving=3;p.upper_nodes={1};p.clips.resize(4);
    for(auto&clip:p.clips){clip.duration=.8;clip.blend=.1;clip.markers={.3,-1};}
    r.audio.emplace();auto&data=*r.audio;data.clips.push_back({16,std::vector<float>(4800,.5f)});
    for(auto key:{"swing:player","blow","struck:npc"})data.bindings[key]=0;
    data.timings[{1,1}]={.15};data.timings[{1,2}]={.15};data.timings[{1,3}]={.15};
    n3e::WorldState w;w.connected=true;w.world.set_session(1);w.world.set_self(7);w.world.set_tick(100);
    auto*actor=w.world.add_entities();actor->set_id(7);actor->set_health(100);actor->set_combat_style(1);
    auto*target=w.world.add_entities();target->set_id(8);target->set_health(100);target->set_npc(true);
    n3e::AudioMixer audio;MeleePresentation local;local.context(7,1,true,false,10,audio);
    const auto before=w.world.SerializeAsString();local.begin(129,8,1,false,10);
    PlayerPose pose;auto update=[&](double now){auto*a=local.current(*actor);auto view=a?a->view():StrikePresentation{};pose.update({},*actor,now,.9,w.world.tick(),nullptr,0,true,true,0,0,a?&view:nullptr);};
    update(10);need(pose.state==2&&pose.since==10&&pose.attack_key==129);
    n3e::PresentationEvent event;event.set_sequence(1);event.set_tick(100);event.set_actor(7);event.set_target(8);event.set_kind(2);event.set_style(1);event.set_request_sequence(129);
    PresentationEvents::audio(audio,r,w,event,10,10,false,129);need(audio.started==1&&std::abs(audio.voices[0].start-10.15)<.00001);
    r.effects.emplace();r.effects->clips.emplace("impact",n3e::EffectClip{false,30,{{},{}}});
    r.effects->bindings.push_back({2,"*",0,0,{"impact"}});n3e::EffectPlayer fx;
    PresentationEvents::effects(fx,r,w,event,10,{}, {},10);need(fx.active.empty());
    need(w.world.SerializeAsString()==before); // no predicted health, result, tick, or rewards
    // Reliable result before snapshot must retain the original start/variant.
    local.result(129,"hit",audio);update(10.1);need(pose.state==2&&pose.since==10);
    actor->set_strike_tick(102);actor->set_strike_sequence(129);actor->set_strike_style(1);w.world.set_tick(102);
    local.reconcile(*actor);update(10.2);need(pose.since==10&&pose.attack_key==129);
    CombatPose remote;remote.update(p,*actor);need(remote.attack==local.clip(p,*local.find(129)));
    event.set_tick(102);event.set_hit(true);
    PresentationEvents::effects(fx,r,w,event,10.2,{}, {},10);need(fx.active.size()==1&&std::abs(fx.active.back().start-10.4)<.0001);
    PresentationEvents::effects(fx,r,w,event,11.5,{}, {},10);need(fx.active.size()==2&&fx.active.back().start==11.5);
    PresentationEvents::audio(audio,r,w,event,10.2,10,true);need(audio.started==3); // impact+struck, no second swing
    need(std::abs(audio.voices.back().start-10.4)<.0001);
    // Late confirmation is visible on receipt, without replaying the swing.
    audio.voices.clear();PresentationEvents::audio(audio,r,w,event,11.5,10,true);need(audio.started==5&&audio.voices.back().start==11.5);
    update(11.5);need(pose.state!=2);
    // New moving request, rejected result, and stale acknowledgement isolation.
    local.begin(130,8,1,true,12);update(12);need(pose.since==12);
    need(local.clip(p,*local.find(130))==13);
    event.set_hit(false);event.set_request_sequence(130);event.set_moving(true);
    PresentationEvents::audio(audio,r,w,event,12,12,false,130);
    local.result(129,"hit",audio);need(!local.find(130)->confirmed);
    local.result(130,"out_of_range",audio);update(12.1);need(pose.state!=2);
    need(std::none_of(audio.voices.begin(),audio.voices.end(),[](const auto&v){return v.request==130;}));
    local.begin(131,8,1,false,13);local.context(7,1,true,false,15.1,audio);need(local.find(131)->cancelled);
    local.begin(132,8,1,false,16);local.context(7,1,true,true,16.1,audio);need(local.find(132)->cancelled);
    local.begin(133,8,1,false,17);local.context(7,1,false,false,17.1,audio);need(local.find(133)->cancelled);
    local.context(9,2,true,false,18,audio);need(local.attempts.empty());
    for(unsigned seq=1;seq<=40;++seq)local.begin(seq,8,1,false,19);need(local.attempts.size()==16);
    local.context(0,2,false,false,20,audio);need(local.attempts.empty());
    actor->set_strike_tick(0);actor->set_strike_sequence(0);actor->set_id(7);pose={};
    local.context(7,3,true,false,21,audio);local.begin(1,8,1,false,21);update(21);need(pose.state==2);
    local.result(1,"cooldown",audio);update(21.1);need(pose.state!=2);
    // Snapshot before ActionResult and duplicate snapshots preserve the start.
    local.begin(2,8,1,false,22);update(22);
    actor->set_strike_tick(120);actor->set_strike_sequence(2);local.reconcile(*actor);update(22.15);need(pose.since==22);
    local.result(2,"miss",audio);update(22.2);need(pose.since==22);
    local.context(0,3,false,false,22.25,audio);update(22.25);need(pose.state!=2);
    audio.voices.clear();event.set_hit(false);event.set_request_sequence(2);
    auto count=audio.started;PresentationEvents::audio(audio,r,w,event,22.2,22,true);need(audio.started==count);
    std::cout<<"PASS predicted swing, immutable authority, accepted identity/variant, no restart/duplicate audio, late impact, rejection/timeout/cast/death/reconnect and bounded history\n";
  }
  n3e::Audio a;a.clips.push_back({2,std::vector<float>(4800,.5f)});a.bindings["tone"]=0;
  n3e::AudioMixer m;need(m.play(a,"tone",1,{3,0,0},true));need(!m.play(a,"absent",1));
  auto before=m.mix(.98,480,{{},{},{1,0,0}});need(std::all_of(before.begin(),before.end(),[](float x){return x==0;}));
  auto right=m.mix(1,100,{{},{},{1,0,0}});need(right[0]==0&&right[1]>0);
  auto left=m.mix(1,100,{{},{},{-1,0,0}});need(left[0]>0&&left[1]==0);
  auto far=m.mix(1,100,{{40,0,0},{40,0,0},{1,0,0}});need(far[0]==0&&far[1]==0);
  need(m.play(a,"tone",1));need(!m.play(a,"tone",1));m.retire(1.2);need(m.voices.empty());
  spatial_checks();
  local_release_checks();
  n3e::WorldState w;w.connected=true;w.world.set_self(7);w.world.set_session(1);w.world.set_tick(100);w.world.set_event_cursor(10);
  auto*e=w.world.add_events();e->set_sequence(10);e->set_tick(100);
  PresentationEvents events;need(events.poll(w).empty()); // reconnect baseline
  e->set_sequence(11);w.world.set_event_cursor(11);need(events.poll(w).size()==1);need(events.poll(w).empty());
  e->set_sequence(12);e->set_tick(1);w.world.set_event_cursor(12);need(events.poll(w).empty());
  w.world.set_session(2);e->set_sequence(13);e->set_tick(100);w.world.set_event_cursor(13);need(events.poll(w).empty());
  w.connected=false;events.poll(w);need(events.cursor==0);
  std::cout<<"PASS audio timing, panning, attenuation, retirement/voice bounds and presentation reconnect/dedup\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
