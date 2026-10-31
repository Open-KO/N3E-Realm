#pragma once
#include "assets/assets.h"
#include <algorithm>
#include <cmath>
#include <map>
#include <optional>
#include <set>

struct Nameplate {
  uint64_t entity;
  std::string text;
  int x,y,width;
  unsigned font;
  uint32_t color;
  bool info=false; // the NPC info line above a name (PQ-177)
};
// The capability under which the client shows the NPC info line (PQ-177): the
// engine's inspection capability (CONTRACTS C-05), read only from the set the
// server projects in Registry.capabilities.
inline constexpr const char*inspect_capability="server.inspect";
// The name display the package's names_toggle action flips (PQ-014; KO: O,
// 005c6990 flips the byte 006d42e4, initially 1). While it is off, names of the
// classes the package lists stay hidden (KO: self 0046b5a0 and other players
// 0046ea90 return early; NPC names, 00459820, ignore the flag). Session state:
// KO never saves it. `party`: another player in the local player's party, whose
// name stays drawn when the package's party policy says so (PQ-166; 0046ea90
// returns early only while other-player +0x7dc, the party marker, is 0; the
// self callback 0046b5a0 never reads the local player's marker +0x7ec).
struct NameDisplay {
  n3e::NameDisplayPolicy policy;
  bool shown=policy.shown;
  void toggle(){shown=!shown;}
  bool visible(bool npc,bool self,bool party=false)const{
    uint32_t cls=npc?n3e::NameDisplayPolicy::npcs:self?n3e::NameDisplayPolicy::self:n3e::NameDisplayPolicy::players;
    return shown||!(policy.hides&cls)||(party&&!npc&&!self&&policy.party&&policy.party->while_hidden);
  }
};
// Other players' label lifetime (PQ-169). KO's player-manager tick 00470900
// measures each other player's 3-D distance from the local player's position
// (005c41b1 passes a copy of [00818794]+0x98, not the camera) and builds the
// label (slot +0x14, 0046e840) below 10.0 (006a425c), frees it (00456b40) above
// 20.0 (006a4260) and leaves it alone in between; party members (+0x7dc) are
// refreshed whatever the distance. Without the name font the name callback
// (0046ea90) draws nothing, so the camera draw limit applies only on top.
// Radii, measuring point and exempt classes are package data
// (NameLifetimePolicy); without a policy every other player keeps a label.
// Session state: forgotten when the player leaves view or the session changes.
// Each label also keeps the classes its player had when it was last refreshed
// (KO slot +0x14, 0046e840, which sets the name colour from the party marker):
// the acquire branch below refreshes it. KO's member removal (0051bf60) clears
// the marker without a refresh, so a removed member's colour stays until the
// next one; the end of the local player's party (0051c030: the local player
// leaves, disbanding, zone entry) refreshes every member (party_ended).
struct NameLifetime {
  enum Change {none,acquired,released};
  std::optional<n3e::NameLifetimePolicy> policy;
  std::map<uint64_t,uint32_t> labels;
  // One measurement of a remote player. `exempt` holds the classes it belongs
  // to (NameLifetimePolicy::party, ...). KO's comparisons: FCOMP/TEST AH,1
  // at 004709db acquires unless distance >= acquire, so a NaN acquires;
  // TEST AH,0x41 at 004709fd releases only when distance > release. With
  // `band` (the NPC loop, PQ-174) TEST AH,1 at 00470bec releases only when
  // distance < release, so at `release` or farther the label stays.
  Change update(uint64_t entity,float distance,uint32_t exempt){
    if(!policy)return none;
    bool acquire=(exempt&policy->exempt)||!(distance>=policy->acquire);
    if(acquire){auto [it,made]=labels.try_emplace(entity,exempt);it->second=exempt;return made?acquired:none;}
    if(policy->band?distance<policy->release:distance>policy->release)return labels.erase(entity)?released:none;
    return none;
  }
  // Drop a label whatever the distance (KO: a dead NPC, PQ-174).
  Change release(uint64_t entity){return policy&&labels.erase(entity)?released:none;}
  bool labelled(uint64_t entity)const{return !policy||labels.count(entity)!=0;}
  // The classes at the label's last refresh; without a policy, `current`.
  uint32_t refreshed(uint64_t entity,uint32_t current)const{
    if(!policy)return current;
    auto it=labels.find(entity);return it==labels.end()?0:it->second;
  }
  void party_ended(){for(auto&label:labels)label.second&=~uint32_t(n3e::NameLifetimePolicy::party);}
  template<class Present> void forget_absent(Present present){std::erase_if(labels,[&](const auto&label){return !present(label.first);});}
  void clear(){labels.clear();}
};
// NPC label lifetime (PQ-174). KO's manager tick 00470900 walks the NPC map
// (head [00818790]+0x2c, filled by NPC-in 005cd620, which builds no name font).
// Per NPC, in order: an NPC in state 5 (+0x2fc, dead and lying) moves to the
// corpse map, whose loop frees its font every tick (00470b25, 00470c67); an NPC
// whose looks row byte +0x14c (NPC_Looks.tbl column 36) is 1 gets slot +0x14
// (00465070 -> 00456830, builds the font once) every tick (00470baa); otherwise
// the font is built below 10.0 of the local player's position (00470bc6) and
// freed (00456b40) while 10.0 <= d < 20.0 (00470be0), and left alone at 20.0
// or farther. The NPC name callback 00459820 draws nothing without the font and
// skips the 48 m camera limit for the flagged NPCs (00459856). The policy's
// `range` carries the radii and the band rule; `always` the flag; `drop_dead`
// the state-5 release, which n3e maps to the final death pose (the death clip
// has played; KO enters state 5 when its dying clip ends, 00457e57).
// Without a policy every NPC keeps a label.
//
// The operator info line (PQ-177) lives with the label. KO's label refresh
// (slot +0x14, 00465070) sets it while the local authority byte +0x4a4 is 0
// and otherwise jumps past it (0046509e -> 00465177) without clearing it; it
// goes only when the labels are freed (00456b40, which frees +0x2f0 with the
// name) or the NPC is released (00455e40). The manager tick refreshes a flagged
// NPC every tick (00470bc1) and any other below 10.0 (00470bdb). Here a refresh
// is every measurement that takes the acquire branch (every one without a
// policy); `inspect` is whether the projected capability set holds the
// inspection capability at that refresh. A line once set therefore stays
// after revocation until the label is dropped or the NPC leaves view.
//
// Per-template presentation (PQ-253): KO reads the flag from each NPC's own
// looks row (+0x274, set by 0045dda0), so an NPC is `always` when the package
// policy says so for every NPC or its looks entry says so for itself
// (NpcLooks::name_always), whether or not the package has a lifetime policy.
struct NpcNameLifetime {
  std::optional<n3e::NpcNameLifetimePolicy> policy;
  NameLifetime range; // its one exempt class is `always`
  std::set<uint64_t> info;
  explicit NpcNameLifetime(std::optional<n3e::NpcNameLifetimePolicy> p={}):policy(p){
    if(p){auto r=p->range;r.exempt=1u;range.policy=r;}
  }
  // One measurement of an NPC. `dead`: its death presentation has finished;
  // `looks_always`: its looks entry keeps its name at any range.
  NameLifetime::Change update(uint64_t entity,float distance,bool dead,bool inspect=false,bool looks_always=false){
    if(!policy){if(inspect)info.insert(entity);return NameLifetime::none;}
    if(dead&&policy->drop_dead){info.erase(entity);return range.release(entity);}
    bool always=policy->always||looks_always;
    bool refresh=always||!(distance>=policy->range.acquire);
    auto change=range.update(entity,distance,always?1u:0u);
    if(change==NameLifetime::released)info.erase(entity);
    if(refresh&&inspect)info.insert(entity);
    return change;
  }
  bool labelled(uint64_t entity)const{return !policy||range.labels.count(entity)!=0;}
  // The info line is drawn only with the name (00459820 returns before any
  // line without the name font).
  bool informed(uint64_t entity)const{return labelled(entity)&&info.count(entity)!=0;}
  bool beyond_distance(bool looks_always=false)const{return looks_always||(policy&&policy->always);}
  template<class Present> void forget_absent(Present present){
    range.forget_absent(present);std::erase_if(info,[&](uint64_t id){return !present(id);});
  }
  void clear(){range.clear();info.clear();}
};
inline unsigned name_glyph(unsigned char c){return c>=32&&c<=126?c-32:'?'-32;}
inline int name_width(const n3e::NameFont&font,const std::string&text){
  float width=0;for(unsigned char c:text)width+=font.advances[name_glyph(c)];
  return int(std::round(width));
}
// The NPC info line's plate (PQ-177): 00459820 stacks each line its own height
// plus 5 px above the one before (00459e1c-00459e2b: EDI += -5 - height; the
// clan line, absent in n3e, would sit between) and centres it on the same
// projected x (00459e2d-00459e34), in the info font, which 00456bb0 creates
// with the NPC name font's height 12 and flag 1 (bold). Here: the style's gap
// and the NPC font, above the NPC's name plate.
inline Nameplate info_plate(const n3e::NameplateStyle&style,const Nameplate&name,std::string text,uint32_t color){
  const auto&font=style.fonts[1];int width=name_width(font,text);
  int centre=name.x+name.width/2;
  return Nameplate{name.entity,std::move(text),centre-width/2,name.y-int(style.gap)-int(font.height),width,1u,color,true};
}
// An actor's drawn scale (PQ-272, D-179): an NPC's template percent on the
// wire (Entity.scale), 0 meaning 100; KO's NPC-in multiplies the record's
// sSize by 0.01 (005cdd82-005cdd8c).
template<class E> float drawn_scale(const E&e){return e.npc()&&e.scale()?float(e.scale())*.01f:1.f;}
// The NPC label height without a nameplate style (the demo HUD's fixed 0.65 m).
constexpr float legacy_npc_label_height=.65f;
// `scale` is the actor's drawn scale (PQ-272): KO's NPC name callback places
// the name at y + h x s + 0.1 x h x s (00459820, s = actor +0x90, the scale
// NPC-in sets through 0041f800), so the height and its padding both scale.
inline n3e::V name_anchor(const n3e::NameplateStyle&style,bool npc,n3e::V position,float root_y,bool seated,float scale=1){
  float height=style.profiles[npc].height*scale;
  position[1]+=height*(1+style.padding);
  if(seated)position[1]+=root_y-height*style.seated_fraction;
  return position;
}
// The camera distance limit of a name class (PQ-173): the package's per-class
// limit, otherwise the style's. KO's other-player callback 0046ea90 picks 33.0
// (006a4250) over 48.0 (006a40dc) in zone key 0x140; self (0046b5a0) and NPC
// (00459820) names always use 48.0.
inline float name_distance(const n3e::NameplateStyle&style,const n3e::NameDisplayPolicy&names,bool npc,bool self){
  return names.distance[npc?2:self?0:1].value_or(style.distance);
}
// `beyond_distance` lifts the camera distance limit (PQ-166: party members,
// 0046ea90); `color` replaces the style colour; `limit` replaces the style's
// distance (name_distance).
inline std::optional<Nameplate> nameplate(const n3e::NameplateStyle&style,uint64_t entity,
    std::string text,bool npc,bool self,n3e::V position,n3e::V eye,n3e::V projected,int w,int h,
    bool beyond_distance=false,std::optional<uint32_t> color={},std::optional<float> limit={}){
  if(text.empty()||text.size()>128||w<=0||h<=0)return {};
  float distance2=0;for(unsigned i=0;i<3;++i){float d=position[i]-eye[i];distance2+=d*d;}
  float distance=limit.value_or(style.distance);
  if(!std::isfinite(distance2)||(!beyond_distance&&distance2>=distance*distance))return {};
  for(auto v:projected)if(!std::isfinite(v))return {};
  if(projected[2]<=0)return {};
  const auto&font=style.fonts[npc];int width=name_width(font,text);
  // Reject offscreen coordinates before converting them to integers. Partially
  // visible names remain clipped by the viewport, not arbitrary HUD margins.
  if(projected[0]<-width||projected[0]>w+width||projected[1]<0||projected[1]>h+font.height+style.gap)return {};
  int x=int(projected[0])-width/2,y=int(projected[1])-int(font.height)-int(style.gap);
  if(x+width<0||x>w||y+int(font.height)<0||y>h)return {};
  return Nameplate{entity,std::move(text),x,y,width,unsigned(npc),color.value_or(style.colors[npc?2:self?0:1])};
}
