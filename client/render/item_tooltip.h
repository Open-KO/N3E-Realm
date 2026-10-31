#pragma once
#include "assets/assets.h"
#include "network/world.h"
#include <algorithm>
#include <string>
#include <vector>

// A tooltip's first line is centred; so are the item head's lines (2233
// 005aa8e0 sets style 0x800000 on each of them).
struct ItemTooltipLine {std::string text;uint32_t color=0xffffff;bool centred=false;};
using ItemTooltip=std::vector<ItemTooltipLine>;
// D-194 (PQ-354): `token` in `text` replaced by the viewer's character name, as
// 2233's 004aad90 replaces "<selfname>", but only with a name the server
// accepts (1-24 ASCII letters, digits, '_' or '-'; else the text is kept), each
// occurrence once, left to right, continuing after the inserted name (2233
// searches again from inside it: BINARY-POLICY "Self-name token correction"),
// and the result cut at 128 bytes.
inline std::string self_named(const std::string&text,const std::string&token,const std::string&viewer){
  constexpr size_t limit=128;
  auto valid=!viewer.empty()&&viewer.size()<=24&&viewer.find_first_not_of(
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")==std::string::npos;
  if(token.empty()||!valid)return text;
  std::string out;size_t at=0;
  for(size_t found;out.size()<limit&&(found=text.find(token,at))!=std::string::npos;at=found+token.size())
    out.append(text,at,found-at).append(viewer);
  if(out.size()<limit)out.append(text,at,std::string::npos);
  if(out.size()>limit)out.resize(limit);
  return out;
}
inline ItemTooltip item_tooltip(const n3e::Release&r,const std::string&item,
    uint32_t quantity,uint32_t durability,uint32_t coins,bool buying,bool selling,bool repairing,
    const std::string&viewer={},const std::string&activation_hint="Right-click to add to hotbar"){
  ItemTooltip lines;
  if(!r.inventory)return lines;
  auto found=std::find_if(r.inventory->items.begin(),r.inventory->items.end(),[&](const auto&i){return i.id==item;});
  if(found==r.inventory->items.end())return lines;
  auto add=[&](std::string label,uint32_t value,uint32_t color=0xffffff){lines.push_back({std::move(label)+std::to_string(value),color});};
  // The head (N3IH, D-194): the label in the head's name colour, the token
  // replaced by the viewer's name, then the head's lines, centred. Without a
  // head file or a head for the item, the label alone in yellow, as before.
  const n3e::ItemHead*head=nullptr;
  if(r.item_heads)if(auto h=r.item_heads->heads.find(item);h!=r.item_heads->heads.end())head=&h->second;
  lines.push_back({r.item_heads?self_named(found->label,r.item_heads->token,viewer):found->label,head?head->name_color:0xffff00u,true});
  if(head)for(const auto&line:head->lines)lines.push_back({line.text,line.color,true});
  if(quantity>1)add("Quantity: ",quantity);
  if(auto stats=r.item_stats.find(item);stats!=r.item_stats.end()){
    const char*names[]={"Attack: ","Defense: ","Health bonus: ","Resource bonus: ","Accuracy bonus: ","Evasion bonus: ","Strength bonus: ","Stamina bonus: ","Dexterity bonus: ","Intelligence bonus: ","Magic bonus: "};
    for(unsigned i=0;i<11;++i)if(stats->second[i])add(names[i],stats->second[i],i<2?0xffffff:0x80ff00);
  }
  for(const auto&c:r.consumables)if(c.item==item){
    if(c.health)add("Restores HP: ",c.health,0x80ff00);
    if(c.resource)add("Restores MP: ",c.resource,0x80ff00);
    lines.push_back({activation_hint,0xffffff});
  }
  if(found->durability)lines.push_back({"Durability: "+std::to_string(durability)+" / "+std::to_string(found->durability),durability?0xffffffu:0xff3c3cu});
  if(r.equipment)for(const auto&i:r.equipment->items)if(i.id==item){
    const auto&gear=*r.equipment;
    if(i.race)add("Required race: ",i.race,i.race==gear.race?0xffffff:0xff3c3c);
    if(i.title)add("Required title: ",i.title,i.title<=gear.title?0xffffff:0xff3c3c);
    const char*names[]={"Required strength: ","Required stamina: ","Required dexterity: ","Required intelligence: ","Required magic: "};
    for(unsigned j=0;j<5;++j)if(i.attributes[j])add(names[j],i.attributes[j],i.attributes[j]<=gear.attributes[j]?0xffffff:0xff3c3c);
  }
  if(r.commerce)for(const auto&p:r.commerce->items)if(p.item==item){
    add("Weight: ",p.weight);
    if(buying)add("Buy price: ",p.price,p.price<=coins?0xffffff:0xff3c3c);
    if(selling)add("Sell price: ",std::max(1u,p.price/p.divisor));
    if(repairing&&r.commerce->repair){const auto&policy=*r.commerce->repair;
      if(std::find(policy.items.begin(),policy.items.end(),item)!=policy.items.end())
        if(auto cost=policy.cost(p.price,durability,found->durability))add("Repair price: ",*cost,*cost<=coins?0xffffff:0xff3c3c);
    }
  }
  if(lines.size()>30)lines.resize(30);
  return lines;
}
// Binary 004d5f70: cursor+26 or left, above or below, then bottom clamp.
// Clamp both axes as well: the legacy right-edge test omits the cursor offset.
inline std::array<float,4> tooltip_rectangle(float x,float y,float width,float height,int w,int h,float gap){
  width=std::min(width,float(w));height=std::min(height,float(h));
  float left=x+gap+width<w?x+gap:x-width;
  float top=y-height>0?y-height:y+height<h?y:h-height;
  left=std::clamp(left,0.f,std::max(0.f,w-width));top=std::clamp(top,0.f,std::max(0.f,h-height));
  return {left,top,left+width,top+height};
}
