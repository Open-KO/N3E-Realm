#pragma once
#include <charconv>
#include <string_view>
namespace n3e {
struct BagCommand {
  enum Kind { use, none, invalid, list, swap, retry, shop, buy, sell, repair, repairgear, equipment, equip, unequip, gearswap } kind=none;
  unsigned source=0, destination=0, quantity=0;
};
inline BagCommand parse_bag(std::string_view text) {
  if(text=="/bag") return {BagCommand::list};
  if(text=="/retry") return {BagCommand::retry};
  if(text=="/equipment") return {BagCommand::equipment};
  if(text=="/shop") return {BagCommand::shop};
  if(text.starts_with("/use")||text.starts_with("/repair")) {
    bool use=text.starts_with("/use");
    bool gear=text.starts_with("/repairgear");text.remove_prefix(use?4:gear?11:7);if(text.empty()||text.front()!=' ')return {BagCommand::invalid};
    while(!text.empty()&&text.front()==' ')text.remove_prefix(1);
    unsigned slot=0;auto [end,error]=std::from_chars(text.data(),text.data()+text.size(),slot);
    if(error!=std::errc{}||end!=text.data()+text.size()||slot<1||slot>64)return {BagCommand::invalid};
    return {use?BagCommand::use:gear?BagCommand::repairgear:BagCommand::repair,slot-1};
  }
  if(text.starts_with("/buy")||text.starts_with("/sell")) {
    bool buy=text.starts_with("/buy");text.remove_prefix(buy?4:5);
    unsigned values[3]{};int count=buy?3:2;
    for(int i=0;i<count;++i) {
      if(text.empty()||text.front()!=' ')return {BagCommand::invalid};
      while(!text.empty()&&text.front()==' ')text.remove_prefix(1);
      auto [end,error]=std::from_chars(text.data(),text.data()+text.size(),values[i]);
      if(error!=std::errc{}||values[i]<1||values[i]>(i==count-1?9999u:64u))return {BagCommand::invalid};
      text.remove_prefix(end-text.data());
    }
    if(!text.empty())return {BagCommand::invalid};
    if(buy)return {BagCommand::buy,values[1]-1,values[0]-1,values[2]};
    return {BagCommand::sell,values[0]-1,0,values[1]};
  }
  auto kind=BagCommand::swap;
  if(text.starts_with("/equip")){kind=BagCommand::equip;text.remove_prefix(6);}
  else if(text.starts_with("/unequip")){kind=BagCommand::unequip;text.remove_prefix(8);}
  else if(text.starts_with("/gearswap")){kind=BagCommand::gearswap;text.remove_prefix(9);}
  else if(text.starts_with("/swap"))text.remove_prefix(5);else return {};
  unsigned slots[2]{};
  for(auto &slot:slots) {
    if(text.empty() || text.front()!=' ') return {BagCommand::invalid};
    while(!text.empty() && text.front()==' ') text.remove_prefix(1);
    auto [end,error]=std::from_chars(text.data(),text.data()+text.size(),slot);
    if(error!=std::errc{} || slot<1 || slot>64) return {BagCommand::invalid};
    text.remove_prefix(end-text.data());
  }
  if(!text.empty() || ((kind==BagCommand::swap||kind==BagCommand::gearswap)&&slots[0]==slots[1])) return {BagCommand::invalid};
  return {kind,slots[0]-1,slots[1]-1};
}
}
