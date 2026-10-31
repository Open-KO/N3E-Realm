#pragma once
#include "assets/assets.h"
#include "item_tooltip.h"
#include "network/world.h"
#include <algorithm>
#include <map>
#include <optional>
#include <string>

// Package HUD keys name reusable controls; no legacy file names or item IDs here.
struct FeatureUI {
  struct Prompt {std::string title,prefix,value;unsigned mode=0;uint64_t bag=0,bank=0;std::optional<std::string> shop;};
  static constexpr unsigned offer_page_size=24,offer_page_count=12;
  unsigned bag_page=0,bank_page=0,friend_page=0,offer_page=0;
  std::string shop_id;
  std::string selected,selection,friend_name,member_name;
  unsigned index=0,offer=0;uint64_t serial=0;
  std::optional<Prompt> prompt;
  std::map<std::string,std::string> values;
  std::map<std::string,std::string> items;
  std::map<std::string,ItemTooltip> tooltips;
  std::map<std::string,float> meters;
  std::map<std::string,uint32_t> colors;
  static std::string label(const n3e::Release&r,const std::string&id){
    if(r.inventory)for(const auto&i:r.inventory->items)if(i.id==id)return i.label;
    return id;
  }
  void clear(){drag.reset();selected.clear();selection.clear();friend_name.clear();member_name.clear();serial=0;prompt.reset();}
  void sync_shop(const n3e::Shop*shop){
    const auto id=shop?shop->id:std::string{};
    if(id!=shop_id){
      shop_id=id;offer_page=0;
      if(selected=="offer"){selected.clear();selection.clear();serial=0;prompt.reset();}
    }
  }
  void ask(const n3e::WorldState&w,std::string title,std::string prefix,std::string value="",unsigned mode=0){
    prompt=Prompt{std::move(title),std::move(prefix),std::move(value),mode,w.bag.revision(),w.storage.revision(),std::nullopt};
  }
  std::optional<std::string> confirm(const n3e::WorldState&w,const std::string&input,const n3e::Shop*shop=nullptr){
    if(!prompt)return std::nullopt;
    if(prompt->bag!=w.bag.revision()||prompt->bank!=w.storage.revision()||(prompt->shop&&(!shop||shop->id!=*prompt->shop))){
      selection="Inventory changed. Select again.";prompt.reset();return std::nullopt;
    }
    if(prompt->mode==1&&(input.empty()||input.size()>10||input.find_first_not_of("0123456789")!=std::string::npos||input.find_first_not_of('0')==std::string::npos)){
      selection="Enter a positive quantity";return std::nullopt;
    }
    auto result=prompt->prefix+(prompt->mode==2?std::string{}:input);prompt.reset();return result;
  }
  // mode 0 text, 1 quantity, 2 confirmation only. No command text comes from UIF.
  bool act(const std::string&a,const n3e::Release&r,const n3e::WorldState&w,const n3e::Shop*shop,bool bank,bool trading){
    sync_shop(shop);
    auto num=[](unsigned n){return std::to_string(n+1);};
    if(a=="bag_prev"||a=="bag_next"){unsigned max=(std::max(1u,w.bag.capacity())-1)/28;bag_page=a=="bag_prev"?(bag_page?bag_page-1:0):std::min(max,bag_page+1);return true;}
    if(a=="bank_prev"||a=="bank_next"){unsigned max=(std::max(1u,w.storage.capacity())-1)/24;bank_page=a=="bank_prev"?(bank_page?bank_page-1:0):std::min(max,bank_page+1);return true;}
    if(a=="friend_prev"||a=="friend_next"){friend_page=a=="friend_prev"?(friend_page?friend_page-1:0):std::min(2u,friend_page+1);return true;}
    if(a=="offer_prev"||a=="offer_next"){
      offer_page=a=="offer_prev"?(offer_page?offer_page-1:0):std::min(offer_page_count-1,offer_page+1);
      if(selected=="offer"){selected.clear();selection.clear();serial=0;prompt.reset();}
      return true;
    }
    auto colon=a.find(':');
    if(colon!=std::string::npos){
      auto kind=a.substr(0,colon);unsigned slot=0;
      auto digits=a.substr(colon+1);if(digits.empty()||digits.size()>3||!std::all_of(digits.begin(),digits.end(),[](char c){return c>='0'&&c<='9';}))return true;
      slot=std::stoul(digits);
      if(kind=="friend"){unsigned ix=friend_page*8+slot;for(const auto&f:w.friends.entries())if(f.slot()==ix){friend_name=f.name();selection=friend_name;}return true;}
      if(kind=="member"){if(slot<unsigned(w.party.members_size())){member_name=w.party.members(slot).name();selection=member_name;}return true;}
      if(kind=="offer"){
        selected.clear();selection.clear();serial=0;
        if(slot>=offer_page_size)return true;
        slot+=offer_page*offer_page_size;
        if(shop&&slot<shop->items.size()){
          offer=slot;selection=label(r,shop->items[slot]);
          if(r.commerce)for(const auto&i:r.commerce->items)if(i.item==shop->items[slot])selection+=" | buy "+std::to_string(i.price);
          selected="offer";
        }return true;
      }
      if(kind!="bag"&&kind!="gear"&&kind!="bank")return true;
      slot+=kind=="bag"?bag_page*28:kind=="bank"?bank_page*24:0;
      const auto&dest=kind=="bag"?w.bag.slots():kind=="gear"?w.bag.equipment():w.storage.slots();
      if(slot>=unsigned(dest.size()))return true;
      const auto&source=selected=="bag"?w.bag.slots():selected=="gear"?w.bag.equipment():w.storage.slots();
      bool valid=serial&&index<unsigned(source.size())&&source[index].instance()==serial;
      if(valid&&(kind!=selected||slot!=index)&&(!trading||kind=="gear")){
        std::string cmd,title;unsigned mode=2;
        if(selected=="bag"&&kind=="bag"){cmd="/swap ";title="Move item";}
        if(selected=="bag"&&kind=="gear"){cmd="/equip ";title="Equip item";}
        if(selected=="gear"&&kind=="bag"){cmd="/unequip ";title="Unequip item";}
        if(selected=="gear"&&kind=="gear"){cmd="/gearswap ";title="Move equipment";}
        if(bank&&selected=="bag"&&kind=="bank"){cmd="/deposit ";title="Deposit quantity";mode=1;}
        if(bank&&selected=="bank"&&kind=="bag"){cmd="/withdraw ";title="Withdraw quantity";mode=1;}
        if(bank&&selected=="bank"&&kind=="bank"){cmd="/bankmove ";title="Move stored item";}
        if(!cmd.empty()){ask(w,title,cmd+num(index)+" "+num(slot)+(mode==1?" ":""),mode==1?"1":"",mode);selected.clear();serial=0;return true;}
      }
      selected=kind;index=slot;serial=dest[slot].instance();selection=serial?label(r,dest[slot].item())+" | quantity "+std::to_string(dest[slot].quantity())+" | durability "+std::to_string(dest[slot].durability()):"Empty slot "+num(slot);return true;
    }
    if(a=="deposit_coins"||a=="withdraw_coins"){ask(w,a=="deposit_coins"?"Deposit coins":"Withdraw coins",a=="deposit_coins"?"/bankcoins ":"/takecoins ","1",1);return true;}
    if(a=="buy"){
      if(shop&&selected=="offer"&&offer<shop->items.size()){
        unsigned destination=w.bag.capacity();
        for(int i=0;i<w.bag.slots_size();++i)if(!w.bag.slots(i).instance()){destination=i;break;}
        if(destination==w.bag.capacity()){selection="No empty bag slot";return true;}
        ask(w,"Buy quantity","/buy "+num(offer)+" "+num(destination)+" ","1",1);
      }else selection="Select an offer first";
      return true;
    }
    if(a=="sell"||a=="repair"||a=="unequip"){
      const auto&records=selected=="gear"?w.bag.equipment():w.bag.slots();
      if((selected!="gear"&&selected!="bag")||!serial||index>=unsigned(records.size())||records[index].instance()!=serial){selection="Select an item first";return true;}
      if(a=="sell"&&selected=="bag")ask(w,"Sell quantity","/sell "+num(index)+" ","1",1);
      if(a=="repair"){
        if(!r.commerce||!r.commerce->repair||!r.inventory)return true;
        const auto&policy=*r.commerce->repair;const auto&item=records[index];uint32_t price=0,maximum=0;
        if(std::find(policy.items.begin(),policy.items.end(),item.item())==policy.items.end()){selection="This item cannot be repaired";return true;}
        for(const auto&i:r.inventory->items)if(i.id==item.item())maximum=i.durability;
        for(const auto&i:r.commerce->items)if(i.item==item.item())price=i.price;
        if(auto cost=policy.cost(price,item.durability(),maximum))ask(w,"Repair for "+std::to_string(*cost)+" coins",(selected=="gear"?"/repairgear ":"/repair ")+num(index),"",2);
      }
      if(a=="unequip"&&selected=="gear"){
        for(int i=0;i<w.bag.slots_size();++i)if(!w.bag.slots(i).instance()){ask(w,"Unequip item","/unequip "+num(index)+" "+num(i),"",2);break;}
      }return true;
    }
    if(a=="friend_add"||a=="friend_remove"||a=="invite"||a=="kick"){
      ask(w,a=="friend_add"?"Add friend":a=="friend_remove"?"Remove friend":a=="invite"?"Invite player":"Remove party member",
          a=="friend_add"?"/friend ":a=="friend_remove"?"/unfriend ":a=="invite"?"/invite ":"/kick ",a=="kick"?member_name:friend_name);return true;
    }
    if(a=="accept"||a=="decline"||a=="leave"||a=="disband"){ask(w,"Confirm party action","/"+a,"",2);return true;}
    return false;
  }
  struct Slot {std::string kind;unsigned index;};
  std::optional<Slot> slot(const std::string&key)const{
    auto colon=key.find(':');if(colon==std::string::npos)return {};
    auto kind=key.substr(0,colon),digits=key.substr(colon+1);
    unsigned count=kind=="bag"?28:kind=="gear"?16:kind=="bank"||kind=="offer"?24:0;
    if(digits.empty()||digits.size()>3||digits.find_first_not_of("0123456789")!=std::string::npos)return {};
    unsigned i=std::stoul(digits);if(i>=count)return {};
    return Slot{kind,i+(kind=="bag"?bag_page*28:kind=="bank"?bank_page*24:kind=="offer"?offer_page*24:0)};
  }
  std::optional<std::string> right_click(const std::string&key,const n3e::Release&r,const n3e::WorldState&w){
    if(drag||prompt||!w.connected)return {};
    auto source=slot(key);if(!source)return {};
    auto num=[](unsigned n){return std::to_string(n+1);};
    if(source->kind=="gear"){
      if(!r.equipment)return {};
      if(source->index>=unsigned(w.bag.equipment_size())||!w.bag.equipment(source->index).instance())return {};
      for(int i=0;i<w.bag.slots_size();++i)if(!w.bag.slots(i).instance())return "/unequip "+num(source->index)+" "+num(i);
      selection="No empty bag slot";return {};
    }
    if(source->kind!="bag"||source->index>=unsigned(w.bag.slots_size()))return {};
    const auto&record=w.bag.slots(source->index);
    if(!r.equipment)return {};
    auto item=std::find_if(r.equipment->items.begin(),r.equipment->items.end(),[&](const auto&i){return i.id==record.item();});
    if(!record.instance()||item==r.equipment->items.end())return {};
    // Ordered package slots: prefer a free compatible slot; an equipped item
    // blocking that slot is replaced in its own compatible slot when possible.
    int destination=-1;
    for(int i=0;i<w.bag.equipment_size();++i)if(item->slots&(1u<<i)){
      if(destination<0)destination=i;
      if(w.bag.equipment(i).instance())continue;
      int blocker=-1;
      for(int j=0;j<w.bag.equipment_size();++j)if(w.bag.equipment(j).instance()){
        for(const auto&other:r.equipment->items)if(other.id==w.bag.equipment(j).item()&&(other.blocks&(1u<<i)))blocker=j;
      }
      destination=blocker>=0&&(item->slots&(1u<<blocker))?blocker:i;break;
    }
    if(destination<0)return {};
    selected.clear();serial=0;
    return "/equip "+num(source->index)+" "+num(destination);
  }
  struct Drag {
    Slot source;std::string key,item,shop;
    uint32_t panel;unsigned bag_page,bank_page,offer_page;
    uint64_t serial,bag,bank,session,self;
  };
  std::optional<Drag> drag;
  bool begin_drag(const std::string&key,uint32_t panel,const n3e::WorldState&w,const n3e::Shop*shop){
    sync_shop(shop);auto source=slot(key);if(!source||prompt||!w.connected)return false;
    if((panel!=1&&panel!=3&&panel!=4)||(source->kind=="gear"&&panel!=1)||(source->kind=="offer"&&panel!=3)||(source->kind=="bank"&&panel!=4))return false;
    std::string item;uint64_t instance=0;
    if(source->kind=="offer"){
      if(!shop||source->index>=shop->items.size())return false;
      item=shop->items[source->index];
    }else{
      const auto&records=source->kind=="bag"?w.bag.slots():source->kind=="gear"?w.bag.equipment():w.storage.slots();
      if(source->index>=unsigned(records.size())||!records[source->index].instance())return false;
      item=records[source->index].item();instance=records[source->index].instance();
    }
    drag=Drag{*source,key,item,shop_id,panel,bag_page,bank_page,offer_page,instance,w.bag.revision(),w.storage.revision(),w.world.session(),w.world.self()};
    return true;
  }
  bool drag_valid(const n3e::WorldState&w,const n3e::Shop*shop)const{
    if(!drag||prompt||!w.connected)return false;
    const auto&d=*drag;
    if(d.session!=w.world.session()||d.self!=w.world.self()||d.bag!=w.bag.revision()||d.bank!=w.storage.revision()||d.bag_page!=bag_page||d.bank_page!=bank_page||d.offer_page!=offer_page)return false;
    if(d.panel==3&&d.shop!=(shop?shop->id:std::string{}))return false;
    if(d.source.kind=="offer")return shop&&d.source.index<shop->items.size()&&shop->items[d.source.index]==d.item;
    const auto&records=d.source.kind=="bag"?w.bag.slots():d.source.kind=="gear"?w.bag.equipment():w.storage.slots();
    return d.source.index<unsigned(records.size())&&records[d.source.index].instance()==d.serial&&records[d.source.index].item()==d.item;
  }
  // A drop produces a command or a quantity prompt, never an optimistic mutation.
  std::optional<std::string> drop(const std::string&key,uint32_t panel,const n3e::Release&r,const n3e::WorldState&w,const n3e::Shop*shop){
    if(!drag_valid(w,shop)){drag.reset();return {};}
    auto d=*drag;drag.reset();auto target=slot(key);
    if(!target||panel!=d.panel||(target->kind==d.source.kind&&target->index==d.source.index))return {};
    const auto&from=d.source.kind;const auto&to=target->kind;
    if((to=="bag"&&target->index>=unsigned(w.bag.slots_size()))||(to=="gear"&&target->index>=unsigned(w.bag.equipment_size()))||(to=="bank"&&target->index>=unsigned(w.storage.slots_size())))return {};
    std::string cmd,title;bool quantity=false;
    if(from=="bag"&&to=="bag"){cmd="/swap";title="Move item";}
    if(panel==1){
      if(from=="bag"&&to=="gear")cmd="/equip";
      if(from=="gear"&&to=="bag")cmd="/unequip";
      if(from=="gear"&&to=="gear")cmd="/gearswap";
    }
    if(panel==4){
      if(from=="bag"&&to=="bank"){cmd="/deposit";title="Deposit quantity";quantity=true;}
      if(from=="bank"&&to=="bag"){cmd="/withdraw";title="Withdraw quantity";quantity=true;}
      if(from=="bank"&&to=="bank")cmd="/bankmove";
    }
    if(panel==3){
      if(from=="offer"&&to=="bag"){cmd="/buy";title="Buy quantity";quantity=true;}
      if(from=="bag"&&to=="offer"){cmd="/sell";title="Sell quantity";quantity=true;}
    }
    if(cmd.empty())return {};
    auto prefix=cmd+" "+std::to_string(d.source.index+1);
    if(cmd!="/sell")prefix+=" "+std::to_string(target->index+1);
    selected.clear();serial=0;selection.clear();
    if(quantity){
      bool stack=false;if(r.inventory)for(const auto&i:r.inventory->items)if(i.id==d.item)stack=i.stack>1;
      prefix+=" ";
      if(stack&&from!="offer"){
        const auto&records=from=="bag"?w.bag.slots():w.storage.slots();
        stack=records[d.source.index].quantity()>1;
      }
      if(stack){ask(w,title,prefix,"1",1);if(panel==3)prompt->shop=d.shop;return {};}
      prefix+="1";
    }
    return prefix;
  }
  // The viewer's own character name (the self entity's, set by update()), for
  // an item tooltip's self-name token (N3IH, D-194).
  std::string viewer()const{auto it=values.find("name");return it==values.end()?std::string{}:it->second;}
  void update(const n3e::Release&r,const n3e::WorldState&w,const n3e::Shop*shop,bool trading=false){
    sync_shop(shop);
    values.clear();items.clear();meters.clear();colors.clear();tooltips.clear();
    auto put=[&](const std::string&key,auto number){values[key]=std::to_string(number);};
    values["unsupported"]="--";values["selection"]=selection+"\n"+w.bag_status+" | "+w.storage_status+" | "+w.party_status;
    put("coins",w.bag.coins());put("bank_coins",w.storage.coins());put("bank_page",bank_page+1);put("friend_page",friend_page+1);
    put("offer_page",offer_page+1);
    uint64_t weight=0;if(r.commerce)for(const auto* records:{&w.bag.slots(),&w.bag.equipment()})for(const auto&s:*records)for(const auto&i:r.commerce->items)if(i.item==s.item())weight+=uint64_t(s.quantity())*i.weight;
    values["weight"]=std::to_string(weight)+" / "+std::to_string(w.world.stats().carry_limit());
    put("level",w.world.inventory().level());put("xp",w.world.inventory().xp());put("attack",w.world.stats().attack());put("defense",w.world.stats().defense());
    if(r.equipment)put("race",r.equipment->race);
    if(r.skills)values["class"]=r.skills->label;
    const char*attrs[]={"strength","stamina","dexterity","intelligence","magic"};
    for(int i=0;i<std::min(5,w.world.stats().attributes_size());++i)put(attrs[i],w.world.stats().attributes(i));
    for(const auto&e:w.world.entities())if(e.id()==w.world.self()){
      values["name"]=e.name();values["health"]=std::to_string(e.health())+" / "+std::to_string(w.world.max_health());values["resource"]=std::to_string(e.resource())+" / "+std::to_string(w.world.max_resource());
    }
    auto slots=[&](const auto&records,const std::string&prefix,unsigned start,unsigned count){
      for(unsigned i=0;i<count;++i){unsigned j=start+i;if(j>=unsigned(records.size()))continue;const auto&s=records[j];
        auto key=prefix+std::to_string(i);
        std::string text=std::to_string(j+1);if(s.instance()){auto name=label(r,s.item());auto space=name.find_last_of(' ');if(space!=std::string::npos)name=name.substr(space+1);text=name.substr(0,6)+"\nx"+std::to_string(s.quantity());
          items[key]=s.item();tooltips[key]=item_tooltip(r,s.item(),s.quantity(),s.durability(),w.bag.coins(),false,trading&&prefix=="bag:",trading&&prefix!="bank:",viewer());if(s.quantity()>1)values["count:"+key]=std::to_string(s.quantity());
        }
        values[key]=text;
      }
    };
    slots(w.bag.slots(),"bag:",bag_page*28,28);slots(w.storage.slots(),"bank:",bank_page*24,24);slots(w.bag.equipment(),"gear:",0,16);
    if(shop)for(unsigned i=0;i<offer_page_size&&offer_page*offer_page_size+i<shop->items.size();++i){auto key="offer:"+std::to_string(i);auto item=shop->items[offer_page*offer_page_size+i];auto name=label(r,item);auto space=name.find_last_of(' ');if(space!=std::string::npos)name=name.substr(space+1);values[key]=name.substr(0,6);items[key]=item;uint32_t durability=0;if(r.inventory)for(const auto&d:r.inventory->items)if(d.id==item)durability=d.durability;tooltips[key]=item_tooltip(r,item,1,durability,w.bag.coins(),true,false,false,viewer());}
    for(const auto&f:w.friends.entries())if(f.slot()>=friend_page*8&&f.slot()<friend_page*8+8){auto key="friend:"+std::to_string(f.slot()-friend_page*8);values[key]=f.name();colors[key]=0xffaaaaaa;for(const auto&p:w.friend_presence.entries())if(p.name()==f.name()&&p.online())colors[key]=p.in_party()?0xffff7070:0xff70ff70;}
    for(int i=0;i<w.party.members_size()&&i<8;++i){const auto&m=w.party.members(i);auto ix=std::to_string(i);values["member:"+ix]=(m.character()==w.party.leader()?"*":"")+m.name();meters["member_hp:"+ix]=float(m.health())/std::max(1u,m.max_health());meters["member_mp:"+ix]=float(m.resource())/std::max(1u,m.max_resource());}
    if(w.party.invitation())values["selection"]=w.party.inviter_name()+" invites you. Accept or Decline.";
  }
};
