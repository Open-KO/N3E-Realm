#include "render/loot_visual.h"
#include "render/loot_ui.h"
#include <iostream>
#include <stdexcept>
void check(bool b){if(!b)throw std::runtime_error("loot picking regression");}
int main(){try{
  n3e::WorldState w;w.connected=true;w.predicted={0,0,0};
  for(auto id:{1,1,2}){auto*d=w.loot.add_drops();d->set_encounter(id);d->set_operation(w.loot.drops_size());d->set_z(id==1?0:-2);}
  check(loot_instances(w).size()==2);
  std::vector<float> mesh={-1,-1,0,0,0,1,0,0, 1,-1,0,0,0,1,1,0, 0,1,0,0,0,1,.5,1};
  n3e::Scene scene;Orbit orbit(n3e::CameraConfig{});orbit.eye={0,0,5};orbit.back={0,0,1};orbit.right={1,0,0};orbit.up={0,1,0};
  check(pick_loot(w,mesh,scene,orbit,320,240,640,480)==1);
  check(!pick_loot(w,mesh,scene,orbit,0,0,640,480));
  check(!pick_loot(w,mesh,scene,orbit,NAN,240,640,480));
  scene.collision=n3e::Collision(std::vector<n3e::V>{{-2,-2,2},{2,-2,2},{0,2,2}});
  check(!pick_loot(w,mesh,scene,orbit,320,240,640,480));scene.collision={};
  LootUI ui;check(ui.open(w,3,10,20,2)&&ui.encounter==2&&ui.slots[0].operation()==3);
  check(!ui.open(w,3,10,20,99));
  // Closing or opening another bundle must not abandon a claim whose result
  // is still pending. A late response belongs to the operation, not the panel.
  ui.down("loot:0");check(ui.up("loot:0")->operation()==3);
  ui.close();ui.sync(w,3);check(!ui.encounter&&ui.pending==3);
  check(ui.open(w,3,10,20,1));ui.down("loot:0");check(!ui.up("loot:0"));
  w.claim.set_operation(99);w.claim.set_status("claimed");++w.claim_responses;
  ui.sync(w,3);check(ui.pending==3);
  w.claim.set_operation(3);w.claim.set_status("inventory_full_not_committed");++w.claim_responses;
  ui.sync(w,3);check(!ui.pending&&ui.encounter==1);
  ui.down("loot:0");check(ui.up("loot:0")->operation()==1);
  w.predicted={0,0,10};ui.sync(w,3);check(!ui.encounter&&ui.pending==1);
  w.connected=false;ui.sync(w,3);check(!ui.pending&&!ui.open(w,3,10,20));
  w.connected=true;w.predicted={0,0,0};check(ui.open(w,3,10,20,2));
  ui.down("loot:0");check(ui.up("loot:0")->operation()==3);
  w.world.set_session(2);ui.sync(w,3);check(!ui.encounter&&!ui.pending);
  check(ui.open(w,3,10,20,2));
  ui.down("loot:0");check(ui.up("loot:0")->operation()==3);
  auto* self=w.world.add_entities();self->set_id(w.world.self());self->set_health(0);
  ui.sync(w,3);check(!ui.encounter&&ui.pending==3&&!ui.open(w,3,10,20,2));
  w.claim.set_status("claimed");++w.claim_responses;ui.sync(w,3);check(!ui.pending);
  self->set_health(100);check(ui.open(w,3,10,20,2));
  w.predicted={0,0,10};check(!ui.open(w,3,10,20,2));ui.sync(w,3);check(!ui.encounter);
  w.loot.mutable_drops()->DeleteSubrange(0,2);check(pick_loot(w,mesh,scene,orbit,320,240,640,480)==2);
  w.connected=false;check(loot_instances(w).empty());check(!pick_loot(w,mesh,scene,orbit,320,240,640,480));
  w.connected=true;w.predicted={0,0,3}; // remaining bundle at z=-2, five meters away
  check(!ui.open(w,3,10,20,2));check(ui.open(w,10,10,20,2,true));ui.sync(w,10,true);check(ui.encounter==2);
  w.predicted={0,0,8};check(!ui.open(w,10,10,20,2,true));ui.sync(w,10,true);check(!ui.encounter);
  w.predicted={0,0,7.999f};check(ui.open(w,10,10,20,2,true));
  w.predicted={0,10,-2};check(!ui.open(w,10,10,20,2,true));
  std::cout<<"PASS separate strict 10m opening versus unchanged 3m claim radius, inclusive legacy policy and 3D boundary\n";
  std::cout<<"PASS bundle deduplication, mesh picking/occlusion, stable encounter selection, claim tracking through close/switch/range/death, session reset and disconnect\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
