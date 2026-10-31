#include "render/hotbar.h"
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <unistd.h>
void check(bool value){if(!value)throw std::runtime_error("hotbar behavior regression");}
int main(){try{
  char root[]="/tmp/n3e-hotbar-XXXXXX";check(mkdtemp(root));setenv("XDG_STATE_HOME",root,1);
  n3e::Release r{};r.consumables={{"test:health",90,0,500,2000},{"test:mana",0,120,500,2000}};
  n3e::WorldState w{};w.connected=true;w.world.set_self(2);auto*e=w.world.add_entities();e->set_id(2);e->set_health(10);
  for(unsigned i=0;i<4;++i)w.bag.add_slots();
  auto*s=w.bag.mutable_slots(1);s->set_instance(15);s->set_item("test:health");s->set_quantity(5);
  Hotbar bar;bar.context("server/game/account/character",2,r);
  FeatureUI ui;auto before=w.bag.SerializeAsString();
  check(bar.register_inventory("bag:1",ui,r,w)&&bar.assignments[0]=="test:health");
  check(bar.register_inventory("bag:1",ui,r,w)&&bar.assignments[1]=="test:health");
  bar.assignments[0].clear();check(bar.register_inventory("bag:1",ui,r,w)&&bar.assignments[0]=="test:health");
  for(unsigned i=0;i<8;++i)bar.assignments[i]="test:mana";
  auto full=bar.assignments;check(bar.register_inventory("bag:1",ui,r,w)&&bar.assignments==full);
  bar.page=1;check(bar.register_inventory("bag:1",ui,r,w)&&bar.assignments[8]=="test:health"&&bar.assignments[0]=="test:mana");
  check(!bar.register_inventory("gear:1",ui,r,w)&&!bar.register_inventory("bag:0",ui,r,w));
  w.connected=false;check(!bar.register_inventory("bag:1",ui,r,w));w.connected=true;
  check(w.bag.SerializeAsString()==before&&!ui.right_click("bag:1",r,w));
  bar.assignments={};bar.page=0;
  check(bar.bind("hotbar:0","test:health",r));check(bar.bind("hotbar:1","test:health",r));
  check(!bar.bind("hotbar:8","test:health",r)&&!bar.bind("hotbar:0","test:gear",r));
  check(bar.command(0,r,w)=="/use 2");
  w.bag.mutable_slots(3)->Swap(w.bag.mutable_slots(1));check(bar.command(1,r,w)=="/use 4");
  bar.page=7;check(!bar.command(0,r,w));check(bar.bind("hotbar:7","test:mana",r));
  Hotbar loaded;loaded.context(bar.identity,3,r);check(loaded.assignments==bar.assignments&&loaded.page==0);
  loaded.context("other character",4,r);check(loaded.assignments[0].empty());
  bar.change_page(true);check(bar.page==7);bar.page=0;bar.change_page(false);check(bar.page==0);
  check(bar.begin_drag(1,w)&&bar.drag_valid(w));w.world.set_session(99);check(!bar.drag_valid(w));bar.drag.reset();
  bar.move(1,2);check(bar.assignments[1].empty()&&bar.assignments[2]=="test:health");bar.move(2,-1);check(bar.assignments[2].empty());bar.bind("hotbar:1","test:health",r);
  bar.page=0;bar.begin("test:health","a",r,10);w.bag_results.push_back({"other","consumed"});bar.tick(w,10.5);check(!bar.timers.at("test:health").confirmed);
  w.bag_results.push_back({"a","consumed"});bar.tick(w,11);check(bar.timers.at("test:health").confirmed);
  bar.begin("test:health","rejected-reuse",r,11.1);check(bar.timers.at("test:health").request=="a");
  bar.tick(w,12);check(bar.timers.at("test:health").flash==0);bar.tick(w,12.01);check(bar.timers.at("test:health").flash==1);bar.tick(w,12.02);check(bar.timers.at("test:health").flash==2);bar.tick(w,12.03);check(bar.timers.empty());
  bar.begin("test:mana","b",r,13);w.bag_results.push_back({"b","cooldown"});bar.tick(w,13.5);check(bar.timers.empty());
  bar.begin("test:health","c",r,14);bar.tick(w,25);check(bar.timers.empty());
  w.bag.mutable_slots(3)->Clear();check(!bar.command(0,r,w)&&!bar.assignments[0].empty());
  w.world.mutable_entities(0)->set_health(0);check(!bar.command(0,r,w));
  bar.clear("hotbar:0");check(bar.assignments[0].empty()&&!bar.assignments[1].empty());
  for(float remaining:{0.f,.01f,.125f,.25f,.5f,.75f,.875f,1.f}){
    auto points=cooldown_polygon(remaining);double area=0;
    for(size_t i=1;i+1<points.size();++i){auto a=points[0],b=points[i],c=points[i+1];area+=std::abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2;}
    for(auto p:points)check(p[0]>=-1e-6&&p[0]<=1+1e-6&&p[1]>=-1e-6&&p[1]<=1+1e-6);
    if(remaining==0||remaining==.25f||remaining==.5f||remaining==.75f||remaining==1)check(std::abs(area-remaining)<1e-5);
  }
  {// PQ-481 (D-245): a skill goes on the hotbar only at or above its level,
   // as 1298's skill tree refuses its enigma icon (004e3120); a locked skill
   // changes nothing, by drop or by the right button's copy, and an already
   // bound one stays.
   n3e::Release k{};k.skills=n3e::Skills{};
   n3e::Skill low{};low.id="test:skill/low";low.level=1;n3e::Skill high=low;high.id="test:skill/high";high.level=5;
   k.skills->entries={low,high};
   Hotbar sb;sb.context("skills character",7,k);
   check(!sb.bind_skill("hotbar:0",high,k,4)&&sb.assignments[0].empty());
   check(!sb.register_skill(high,k,4)&&std::all_of(sb.assignments.begin(),sb.assignments.end(),[](const auto&a){return a.empty();}));
   check(sb.bind_skill("hotbar:0",high,k,5)&&sb.assignments[0]=="test:skill/high");
   check(sb.register_skill(low,k,1)&&sb.assignments[1]=="test:skill/low");
   check(!sb.register_skill(high,k,4)&&sb.assignments[2].empty());
   check(Hotbar::skill(k,sb.assignments[0])==&k.skills->entries[1]);
   for(unsigned i=2;i<8;++i)sb.assignments[i]="test:skill/low";
   check(!sb.register_skill(low,k,1));}
  auto quarter=cooldown_polygon(.75f);check(std::abs(quarter[1][0]-1)<1e-5&&std::abs(quarter[1][1]-.5f)<1e-5);
  std::filesystem::remove_all(root);
  std::cout<<"PASS hotbar movable stacks, duplicate/page/empty bindings, character-scoped persistence, result identity/rejection/timeout, three-frame flash and radial quadrant geometry\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
