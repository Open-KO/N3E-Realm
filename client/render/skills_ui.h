#pragma once
#include "hotbar.h"

struct SkillsUI {
  unsigned selected=0;
  bool open=false;
  struct Drag {unsigned index;uint64_t self,session;};
  std::optional<Drag> drag, right_press;
  static int index(const std::string&key){return key.size()==7&&key.starts_with("skill:")&&key[6]>='0'&&key[6]<='5'?key[6]-'0':-1;}
  void update(FeatureUI&ui,const n3e::Release&r,const n3e::WorldState&w)const{
    if(!r.skills)return;
    for(unsigned i=0;i<r.skills->entries.size();++i){
      const auto&s=r.skills->entries[i];auto key="skill:"+std::to_string(i);
      ui.items[key]=s.id;ui.values["skill_name:"+std::to_string(i)]=s.label;
      ui.tooltips[key]={{s.label,0xffffff},{"Level "+std::to_string(s.level)+" - "+r.skills->label,w.world.inventory().level()>=s.level?0xffff00u:0xff4444u},{"Mana: "+std::to_string(s.cost),0xffffff},{"Drag to hotbar or right-click to register",0xffffff},{"Double-click to cast",0xffffff}};
    }
    const auto&s=r.skills->entries[std::min(size_t(selected),r.skills->entries.size()-1)];
    ui.values["skill_page"]="1";ui.values["skill_info"]=s.label+(s.target==1?": restore "+std::to_string(s.amount)+" HP":": magic attack");
    ui.values["skill_cost"]="Mana: "+std::to_string(s.cost)+"   Cast: "+(std::to_string(s.cast_ms/1000)+"."+std::to_string((s.cast_ms%1000)/100))+"s";
    ui.values["skill_requirement"]="Requires level "+std::to_string(s.level)+" "+r.skills->label;
    if(w.world.inventory().level()<s.level)ui.values["skill_requirement"]+=" (locked)";
  }
};
