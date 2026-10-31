#pragma once
#include "feature_ui.h"
#include <array>
#include <limits>

// One immutable operation per slot; list refreshes leave holes instead of
// moving another reward under a held pointer. The server still authorizes claims.
struct LootUI {
  uint64_t encounter=0, pressed=0, pending=0, response=0;
  uint64_t session=0, entity=0;
  std::array<n3e::LootDrop,6> slots;
  float x=0,y=0;
  // Window lifetime is independent of an already submitted durable claim.
  // Keep polling that operation until its result, even after movement/expiry.
  void close(){encounter=pressed=0;for(auto&d:slots)d.Clear();}
  void context(const n3e::WorldState&w){
    if(!w.connected||session!=w.world.session()||entity!=w.world.self()){
      close();pending=0;response=w.claim_responses;
      session=w.world.session();entity=w.world.self();
    }
  }
  bool open(const n3e::WorldState&w,float radius,float px,float py,uint64_t requested=0,bool strict=false){
    context(w);if(!w.connected)return false;
    for(const auto&e:w.world.entities())if(e.id()==w.world.self()&&!e.health())return false;
    const n3e::LootDrop*nearest=nullptr;float best=radius*radius;
    for(const auto&d:w.loot.drops()){
      if(requested&&d.encounter()!=requested)continue;
      float distance=std::pow(d.x()-w.predicted[0],2)+std::pow(d.y()-w.predicted[1],2)+std::pow(d.z()-w.predicted[2],2);
      if(distance<=best&&(!strict||distance<radius*radius)){best=distance;nearest=&d;}
    }
    if(!nearest)return false;
    auto id=nearest->encounter();close();encounter=id;x=px;y=py;
    unsigned slot=0;for(const auto&d:w.loot.drops())if(d.encounter()==id&&slot<slots.size())slots[slot++]=d;
    return true;
  }
  void sync(const n3e::WorldState&w,float radius,bool strict=false){
    context(w);if(!w.connected)return;
    if(response!=w.claim_responses){response=w.claim_responses;if(w.claim.operation()==pending&&w.claim.status()!="pending")pending=0;}
    for(const auto&e:w.world.entities())if(e.id()==w.world.self()&&!e.health()){close();return;}
    bool any=false;
    for(auto&d:slots){
      if(!d.operation())continue;
      if(std::none_of(w.loot.drops().begin(),w.loot.drops().end(),[&](const auto&current){return current.operation()==d.operation()&&current.encounter()==d.encounter()&&current.item()==d.item()&&current.quantity()==d.quantity();})){d.Clear();continue;}
      float distance=std::pow(d.x()-w.predicted[0],2)+std::pow(d.y()-w.predicted[1],2)+std::pow(d.z()-w.predicted[2],2);
      if(distance>radius*radius||(strict&&distance==radius*radius)){close();return;}any=true;
    }
    if(!any)close();
  }
  static int index(const std::string&key){return key.size()==6&&key.starts_with("loot:")&&key[5]>='0'&&key[5]<='5'?key[5]-'0':-1;}
  void down(const std::string&key){auto i=index(key);pressed=i>=0&&!pending?slots[i].operation():0;}
  const n3e::LootDrop*up(const std::string&key){auto i=index(key);auto held=pressed;pressed=0;if(i<0||!held||pending||slots[i].operation()!=held)return nullptr;pending=held;return &slots[i];}
  void values(FeatureUI&ui,const n3e::Release&r)const{
    for(unsigned i=0;i<slots.size();++i){const auto&d=slots[i];if(!d.operation())continue;auto key="loot:"+std::to_string(i);
      ui.items[key]=d.item();ui.values[key]=d.kind()==1?"Coins":FeatureUI::label(r,d.item());
      if(d.quantity()>1)ui.values["count:"+key]=std::to_string(d.quantity());
      if(d.kind()==1)ui.tooltips[key]={{"Coins",0xffff00},{"Quantity: "+std::to_string(d.quantity()),0xffffff}};
      else {uint32_t durability=0;if(r.inventory)for(const auto&item:r.inventory->items)if(item.id==d.item())durability=item.durability;
        ui.tooltips[key]=item_tooltip(r,d.item(),d.quantity(),durability,0,false,false,false,ui.viewer());}
    }
  }
};
