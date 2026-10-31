#pragma once
#include "feature_ui.h"
#include <array>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <openssl/sha.h>

// Local shortcuts name package actions, never bag slots or trusted consumption.
struct Hotbar {
  static constexpr unsigned pages=8, slots=8;
  std::array<std::string,pages*slots> assignments{};
  unsigned page=0;
  struct Drag {unsigned slot,page;uint64_t self,session;};
  std::optional<Drag> drag;
  struct Timer {double start,duration;std::string request;bool confirmed=false;int flash=-1;};
  std::map<std::string,Timer> timers;
  std::filesystem::path file;
  std::string identity,notice;
  uint64_t self=0;
  static int index(const std::string&key){
    return key.size()==8&&key.starts_with("hotbar:")&&key[7]>='0'&&key[7]<='7'?key[7]-'0':-1;
  }
  static const n3e::Consumable* policy(const n3e::Release&r,const std::string&item){
    for(const auto&c:r.consumables)if(c.item==item)return &c;
    return nullptr;
  }
  static const n3e::Skill* skill(const n3e::Release&r,const std::string&id){
    if(r.skills)for(const auto&s:r.skills->entries)if(s.id==id)return &s;
    return nullptr;
  }
  static bool known(const n3e::Release&r,const std::string&id){return policy(r,id)||skill(r,id);}
  void context(const std::string&scope,uint64_t entity,const n3e::Release&r){
    if(self!=entity){timers.clear();drag.reset();self=entity;}
    if(identity==scope)return;
    identity=scope;assignments={};page=0;file.clear();notice.clear();
    const char*base=std::getenv("XDG_STATE_HOME");
    std::filesystem::path root;
    if(base&&*base&&std::filesystem::path(base).is_absolute())root=base;
    else if(const char*home=std::getenv("HOME");home&&*home)root=std::filesystem::path(home)/".local/state";
    if(root.empty())return;
    unsigned char digest[SHA256_DIGEST_LENGTH];SHA256(reinterpret_cast<const unsigned char*>(scope.data()),scope.size(),digest);
    std::string key;for(auto b:digest){key+="0123456789abcdef"[b>>4];key+="0123456789abcdef"[b&15];}
    file=root/"n3e/hotbars"/(key+".txt");
    std::error_code ec;auto size=std::filesystem::file_size(file,ec);if(ec||size>16384)return;
    std::ifstream in(file);std::string version;if(!std::getline(in,version)||version!="N3B1")return;
    std::array<std::string,pages*slots> loaded{};
    for(auto&item:loaded)if(!std::getline(in,item)||item.size()>200)return;
    if(in.peek()!=std::char_traits<char>::eof())return;
    for(auto&item:loaded)if(!known(r,item))item.clear();
    assignments=std::move(loaded);
  }
  void save(){
    if(file.empty())return;
    std::error_code ec;std::filesystem::create_directories(file.parent_path(),ec);
    auto tmp=file;tmp+=".tmp";
    {std::ofstream out(tmp,std::ios::trunc);out<<"N3B1\n";for(const auto&item:assignments)out<<item<<'\n';out.close();if(!out){notice="Could not save hotbar";return;}}
    std::filesystem::rename(tmp,file,ec);if(ec)notice="Could not save hotbar";
  }
  bool bind(const std::string&key,const std::string&item,const n3e::Release&r){
    int i=index(key);if(i<0||!known(r,item))return false;
    assignments[page*slots+i]=item;save();return true;
  }
  // PQ-481 (D-245): a skill goes on the hotbar only at or above its level.
  // 1298's skill tree gives a basic skill (NeedSkill % 10 == 0) above the
  // player's level the enigma icon (004e7320 -> 004ea6f0 with 0), and both
  // of its ways onto the hotbar refuse that icon with no line: the right
  // button's copy (004e3120, 004e3ff5-004e400c) and a drop on the hotbar
  // (004e3895-004e38e3, else 004df680 -> 004df710). A skill already bound
  // stays pressable, as 1298's hotbar restore 004de6f0 keeps any skill its
  // tree holds (004e2ca0); the server then refuses `level_required`.
  bool bind_skill(const std::string&key,const n3e::Skill&s,const n3e::Release&r,uint32_t level){
    return level>=s.level&&bind(key,s.id,r);
  }
  // The right button's copy: the first empty slot on this page (1298's
  // 004df6e0), or nothing when the page is full or the skill is locked.
  bool register_skill(const n3e::Skill&s,const n3e::Release&r,uint32_t level){
    for(unsigned i=0;i<slots;++i)if(assignments[page*slots+i].empty())return bind_skill("hotbar:"+std::to_string(i),s,r,level);
    return false;
  }
  bool register_inventory(const std::string&key,const FeatureUI&ui,const n3e::Release&r,const n3e::WorldState&w){
    if(ui.drag||ui.prompt||!w.connected)return false;
    auto source=ui.slot(key);
    if(!source||source->kind!="bag"||source->index>=unsigned(w.bag.slots_size()))return false;
    const auto&item=w.bag.slots(source->index);
    if(!item.instance()||!item.quantity()||!policy(r,item.item()))return false;
    // 004a09f0 -> 004df6e0: first empty slot on this page, duplicates allowed.
    notice.clear();
    for(unsigned i=0;i<slots;++i)if(assignments[page*slots+i].empty())return bind("hotbar:"+std::to_string(i),item.item(),r);
    return true; // Full page: handled without replacing a shortcut or consuming.
  }
  // PgUp/PgDn (004dfa30/004dfa50) step and clamp; F1-F8 (004dfa70) select directly.
  void change_page(bool next){page=next?std::min(page+1,pages-1):(page?page-1:0);}
  void select_page(unsigned p){if(p<pages)page=p;}
  bool begin_drag(unsigned slot,const n3e::WorldState&w){
    if(slot>=slots||assignments[page*slots+slot].empty())return false;
    drag=Drag{slot,page,w.world.self(),w.world.session()};return true;
  }
  bool drag_valid(const n3e::WorldState&w)const{
    if(!drag||!w.connected||drag->page!=page||drag->self!=w.world.self()||drag->session!=w.world.session())return false;
    for(const auto&e:w.world.entities())if(e.id()==w.world.self())return e.health()>0;
    return false;
  }
  void move(unsigned source,int target){
    if(source>=slots||target==int(source))return;
    auto item=assignments[page*slots+source];assignments[page*slots+source].clear();
    if(target>=0&&target<int(slots))assignments[page*slots+target]=item;
    save();
  }
  void clear(const std::string&key){int i=index(key);if(i>=0){assignments[page*slots+i].clear();save();}}
  std::optional<std::string> command(unsigned slot,const n3e::Release&r,const n3e::WorldState&w)const{
    if(slot>=slots||!w.connected)return {};
    bool alive=false;for(const auto&e:w.world.entities())if(e.id()==w.world.self())alive=e.health()>0;
    if(!alive)return {};
    const auto&item=assignments[page*slots+slot];if(!policy(r,item))return {};
    for(int i=0;i<w.bag.slots_size();++i)if(w.bag.slots(i).instance()&&w.bag.slots(i).quantity()&&w.bag.slots(i).item()==item)return "/use "+std::to_string(i+1);
    return {};
  }
  void begin(const std::string&item,const std::string&request,const n3e::Release&r,double now){
    if(timers.contains(item))return;
    if(auto p=policy(r,item);p&&p->cooldown_ms)timers[item]={now,p->cooldown_ms/1000.,request,false,-1};
  }
  void tick(const n3e::WorldState&w,double now){
    if(!w.connected){timers.clear();return;}
    for(auto it=timers.begin();it!=timers.end();){auto&t=it->second;bool remove=false;
      if(!t.confirmed)for(const auto&reply:w.bag_results)if(reply.first==t.request){
        if(reply.second=="consumed")t.confirmed=true;
        else if(reply.second!="use_pending")remove=true;
      }
      if(!t.confirmed&&now-t.start>10)remove=true;
      if(t.confirmed&&now>=t.start+t.duration){if(++t.flash>=3)remove=true;}
      if(remove)it=timers.erase(it);else ++it;
    }
  }
  void skill_cooldowns(const n3e::Release&r,const n3e::WorldState&w,double now){
    for(const auto&c:w.world.skill_cooldowns())if(auto s=skill(r,c.skill());s&&s->cooldown_ms){
      auto request="skill:"+std::to_string(c.ready_tick());auto it=timers.find(c.skill());
      if(it!=timers.end()&&it->second.request==request)continue;
      double duration=s->cooldown_ms/1000.,remaining=std::max(0.,(double(c.ready_tick())-w.world.tick())*.05-std::max(0.,now-w.received));
      timers[c.skill()]={now-duration+remaining,duration,request,true,-1};
    }
  }
  void update(FeatureUI&ui,const n3e::Release&r,const n3e::WorldState&w)const{
    ui.values["hotbar_page"]=std::to_string(page+1);
    for(unsigned i=0;i<slots;++i){auto key="hotbar:"+std::to_string(i);const auto&item=assignments[page*slots+i];if(item.empty())continue;
      ui.items[key]=item;uint64_t count=0;
      if(auto s=skill(r,item)){
        ui.tooltips[key]={{s->label,0xffffff},{"Level "+std::to_string(s->level)+" - "+r.skills->label,0xffff00},{"Mana: "+std::to_string(s->cost)+"   Cast: "+(std::to_string(s->cast_ms/1000)+"."+std::to_string((s->cast_ms%1000)/100))+"s",0xffffff},{"Click or press "+std::to_string(i+1)+" to cast",0xffffff}};
        continue;
      }
      for(const auto&s:w.bag.slots())if(s.item()==item)count+=s.quantity();
      ui.values["count:"+key]=std::to_string(count);
      ui.tooltips[key]=item_tooltip(r,item,uint32_t(std::min<uint64_t>(count,UINT32_MAX)),0,0,false,false,false,ui.viewer(),"Click or press "+std::to_string(i+1)+" to use");
    }
  }
};

// Covered polygon for the binary's clockwise reveal. Its edge motion uses sine
// interpolation (004e0f50); the fan is clipped to the icon rectangle by construction.
inline std::vector<std::array<float,2>> cooldown_polygon(float remaining){
  float elapsed=1-std::clamp(remaining,0.f,1.f);
  if(elapsed>=1)return {};
  constexpr float pi=3.14159265358979323846f,root2=1.4142135623730951f;
  auto wave=[&](float t){return .5f*root2*std::sin(t*2*pi);};
  std::array<float,2> edge;
  if(elapsed<.125f)edge={.5f+wave(elapsed),0};
  else if(elapsed<.375f)edge={1,.5f+wave(elapsed-.25f)};
  else if(elapsed<.625f)edge={.5f-wave(elapsed-.5f),1};
  else if(elapsed<.875f)edge={0,.5f-wave(elapsed-.75f)};
  else edge={.5f+wave(elapsed-1),0};
  std::vector<std::array<float,2>> points{{.5f,.5f},edge};
  const std::array<std::array<float,2>,5> corners{{{1,0},{1,1},{0,1},{0,0},{.5f,0}}};
  const float times[5]={.125f,.375f,.625f,.875f,1};
  for(unsigned i=0;i<5;++i)if(elapsed<times[i])points.push_back(corners[i]);
  return points;
}
