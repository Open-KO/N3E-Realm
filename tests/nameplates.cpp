#include "render/nameplates.h"
#include <iostream>
#include <stdexcept>
void check(bool v){if(!v)throw std::runtime_error("nameplate regression");}
int main(){try{
  n3e::NameplateStyle s{};s.distance=48;s.padding=.1f;s.gap=5;s.seated_fraction=.5f;s.colors={1,2,3};s.profiles={{{2,0},{.75f,0}}};
  for(auto&font:s.fonts){font.height=18;font.top=7;font.advances.fill(8);font.advances['i'-32]=3;font.advances['W'-32]=15;}
  check(name_width(s.fonts[0],"WiWi")==36&&name_width(s.fonts[0],"iiii")==12);
  auto anchor=name_anchor(s,false,{3,10,4},.4f,false);check(std::abs(anchor[1]-12.2f)<1e-5);
  auto sitting=name_anchor(s,false,{3,10,4},.4f,true);check(std::abs(sitting[1]-11.6f)<1e-5);
  auto npc=name_anchor(s,true,{0,0,0},0,false);check(std::abs(npc[1]-.825f)<1e-5);
  // PQ-272: a drawn scale multiplies the height and its padding (KO 00459820:
  // y + h x s + 0.1 x h x s); at scale 2 the 0.75 m NPC height stands 1.65 m up.
  auto big=name_anchor(s,true,{1,2,3},0,false,2.f);check(std::abs(big[1]-3.65f)<1e-5&&big[0]==1&&big[2]==3);
  auto small=name_anchor(s,true,{0,0,0},0,false,.55f);check(std::abs(small[1]-.825f*.55f)<1e-5);
  auto label=nameplate(s,7,"WiWi",false,true,{0,0,0},{0,0,10},{320,200,10},640,480);
  check(label&&label->entity==7&&label->text=="WiWi"&&label->x==302&&label->y==177&&label->color==1&&label->font==0);
  auto mob=nameplate(s,8,"Worm",true,false,{0,0,0},{0,0,10},{320,200,10},640,480);
  check(mob&&mob->font==1&&mob->color==3);
  check(nameplate(s,7,"Wi",false,false,{0,0,0},{0,0,47.99f},{320,200,10},640,480).has_value());
  check(!nameplate(s,7,"Wi",false,false,{0,0,0},{0,0,48},{320,200,10},640,480));
  check(!nameplate(s,7,"Wi",false,false,{0,0,0},{0,0,10},{320,200,-10},640,480));
  check(!nameplate(s,7,"Wi",false,false,{0,0,0},{0,0,10},{NAN,200,10},640,480));
  check(!nameplate(s,7,"Wi",false,false,{0,0,0},{0,0,10},{1e20f,200,10},640,480));
  check(nameplate(s,7,"Wi",false,false,{0,0,0},{0,0,10},{0,100,10},640,480).has_value());
  check(!nameplate(s,7,std::string(129,'W'),false,false,{0,0,0},{0,0,10},{320,200,10},640,480));
  check(name_glyph('\n')==unsigned('?'-32));
  // PQ-169 label lifetime (KO 00470900: build below 10.0, free above 20.0).
  {
    using L=NameLifetime;using P=n3e::NameLifetimePolicy;
    L none;check(none.labelled(5)&&none.update(5,500,0)==L::none&&none.labelled(5));
    L life{P{P::self,10,20,P::party},{}};
    check(!life.labelled(5));
    check(life.update(5,25,0)==L::none&&!life.labelled(5));       // first seen far: no label
    check(life.update(5,15,0)==L::none&&!life.labelled(5));       // approaching through the band: still none
    check(life.update(5,10,0)==L::none&&!life.labelled(5));       // exactly 10 is not below 10
    check(life.update(5,9.99f,0)==L::acquired&&life.labelled(5));
    check(life.update(5,2,0)==L::none&&life.labelled(5));
    check(life.update(5,19,0)==L::none&&life.labelled(5));        // leaving through the band: kept
    check(life.update(5,20,0)==L::none&&life.labelled(5));        // exactly 20 is not above 20
    check(life.update(5,20.01f,0)==L::released&&!life.labelled(5));
    check(life.update(5,12,0)==L::none&&!life.labelled(5));       // coming back: waits for 10
    check(life.update(5,NAN,0)==L::acquired&&life.labelled(5));   // KO: an unordered compare acquires
    check(life.update(5,NAN,0)==L::none&&life.labelled(5));
    check(life.update(6,400,P::party)==L::acquired&&life.labelled(6)); // party: any range
    check(life.update(6,400,0)==L::released&&!life.labelled(6));       // left the party far away
    L unexempt{P{P::self,10,20,0},{}};
    check(unexempt.update(6,400,P::party)==L::none&&!unexempt.labelled(6)); // exemption is package data
    life.update(7,1,0);check(life.labelled(5)&&life.labelled(7));
    life.forget_absent([](uint64_t id){return id==7;});check(!life.labelled(5)&&life.labelled(7));
    check(life.update(5,15,0)==L::none&&!life.labelled(5));       // re-entered view in the band: no label
    life.clear();check(!life.labelled(7));
  }
  // PQ-174 NPC label lifetime (KO 00470900 NPC loop: build below 10.0, free
  // while 10.0 <= d < 20.0, keep at 20.0 or farther; NPC_Looks column 36 = 1
  // refreshed at any range; state 5 moves the NPC to the corpse map).
  {
    using L=NameLifetime;using P=n3e::NameLifetimePolicy;using N=n3e::NpcNameLifetimePolicy;
    NpcNameLifetime none;check(none.labelled(5)&&none.update(5,500,true)==L::none&&none.labelled(5)&&!none.beyond_distance());
    NpcNameLifetime npc{N{P{P::self,10,20,0,true},false,true}};
    check(!npc.labelled(5)&&!npc.beyond_distance());
    check(npc.update(5,15,false)==L::none&&!npc.labelled(5));         // entered view in the band: no name (NPC-in builds none)
    check(npc.update(5,10,false)==L::none&&!npc.labelled(5));         // exactly 10 is not below 10
    check(npc.update(5,9.99f,false)==L::acquired&&npc.labelled(5));
    check(npc.update(5,10,false)==L::released&&!npc.labelled(5));     // 10 <= d < 20 frees it: no hysteresis
    check(npc.update(5,5,false)==L::acquired);
    check(npc.update(5,19.99f,false)==L::released);                   // just inside 20: freed
    check(npc.update(5,5,false)==L::acquired);
    check(npc.update(5,20,false)==L::none&&npc.labelled(5));          // a jump to exactly 20: kept (TEST AH,1 at 00470bec)
    check(npc.update(5,400,false)==L::none&&npc.labelled(5));         // stale far label, KO's jump case
    check(npc.update(5,15,false)==L::released&&!npc.labelled(5));     // the next sample in the band frees it
    check(npc.update(5,25,false)==L::none&&!npc.labelled(5));         // beyond 20 without a label: nothing to keep
    check(npc.update(5,NAN,false)==L::acquired);                      // an unordered compare acquires
    check(npc.update(5,2,true)==L::released&&!npc.labelled(5));       // dead (state 5): freed even close by
    check(npc.update(5,2,true)==L::none&&!npc.labelled(5));           // and never rebuilt while dead
    check(npc.update(5,2,false)==L::acquired);                        // alive again (respawn): rebuilt below 10
    NpcNameLifetime keep{N{P{P::self,10,20,0,true},false,false}};
    check(keep.update(6,2,false)==L::acquired&&keep.update(6,2,true)==L::none&&keep.labelled(6)); // drop_dead is package data
    NpcNameLifetime flagged{N{P{P::self,10,20,0,true},true,true}};
    check(flagged.beyond_distance());
    check(flagged.update(7,400,false)==L::acquired&&flagged.labelled(7)); // column 36 = 1: any range
    check(flagged.update(7,15,false)==L::none&&flagged.labelled(7));
    check(flagged.update(7,400,true)==L::released&&!flagged.labelled(7)); // state 5 before the flag test (00470b25)
    NpcNameLifetime beyond{N{P{P::camera,10,20,0,false},false,false}};
    check(beyond.update(8,5,false)==L::acquired&&beyond.update(8,20,false)==L::none&&beyond.update(8,20.01f,false)==L::released); // the player rule
    npc.update(9,1,false);npc.forget_absent([](uint64_t id){return id==9;});check(!npc.labelled(5)&&npc.labelled(9));
    npc.clear();check(!npc.labelled(9));
    // The flagged NPC's name is drawn beyond the camera limit, as the party's.
    check(!nameplate(s,8,"Wi",true,false,{0,0,0},{0,0,60},{320,200,10},640,480,false));
    check(nameplate(s,8,"Wi",true,false,{0,0,0},{0,0,60},{320,200,10},640,480,flagged.beyond_distance()).has_value());
    // PQ-253: the flag per looks entry (KO reads it from each NPC's own looks
    // row, +0x274 -> +0x14c). One policy without the package-wide flag: an NPC
    // whose looks entry sets it keeps its name at any range and past the camera
    // limit, its neighbour with another looks follows the radii, and the flag
    // never outlives state 5.
    NpcNameLifetime looks{N{P{P::self,10,20,0,true},false,true}};
    check(!looks.beyond_distance()&&looks.beyond_distance(true));
    check(looks.update(10,400,false,false,true)==L::acquired&&looks.labelled(10));  // flagged looks: any range
    check(looks.update(10,15,false,false,true)==L::none&&looks.labelled(10));       // not freed in the band
    check(looks.update(11,400,false,false,false)==L::none&&!looks.labelled(11));    // other looks: the radii
    check(looks.update(11,15,false,false,false)==L::none&&!looks.labelled(11));
    check(looks.update(10,400,true,false,true)==L::released&&!looks.labelled(10));  // state 5 first (00470b25)
    check(looks.update(12,400,false,true,true)==L::acquired&&looks.informed(12));   // the info line follows the name
    NpcNameLifetime unmanaged;  // no lifetime policy: every NPC keeps a label; the flag still lifts the camera limit
    check(unmanaged.update(13,400,false,false,true)==L::none&&unmanaged.labelled(13)&&unmanaged.beyond_distance(true)&&
          !unmanaged.beyond_distance(false));
  }
  // PQ-166 party names (KO other-player +0x7dc: 0046ea90 draws while O hides
  // names and skips the 48 m limit unless Zones.tbl column 23 is 0; 0046e840
  // colours the name 0xffffff00 on each refresh).
  {
    using P=n3e::NameDisplayPolicy;using L=NameLifetime;using C=n3e::NameLifetimePolicy;
    P policy{true,P::self|P::players,std::nullopt,n3e::PartyNamePolicy{true,true,0xffff00u}};
    NameDisplay names{policy};names.toggle();
    check(!names.visible(false,false)&&names.visible(false,false,true));     // a hidden player's name stays for a party member
    check(!names.visible(false,true,true)&&names.visible(true,false,true));  // never the local player's (0046b5a0); NPCs as before
    P no_keep=policy;no_keep.party->while_hidden=false;NameDisplay plain{no_keep};plain.toggle();
    check(!plain.visible(false,false,true));                                 // the exception is package data
    P none=policy;none.party.reset();NameDisplay old{none};old.toggle();
    check(!old.visible(false,false,true));                                   // no party policy: the toggle hides them
    // Beyond the camera limit only when the policy lifts it; colour replaced.
    check(!nameplate(s,7,"Wi",false,false,{0,0,0},{0,0,60},{320,200,10},640,480));
    auto far=nameplate(s,7,"Wi",false,false,{0,0,0},{0,0,400},{320,200,10},640,480,true,0xffff00u);
    check(far&&far->color==0xffff00u);
    auto near=nameplate(s,7,"Wi",false,false,{0,0,0},{0,0,10},{320,200,10},640,480,false,std::nullopt);
    check(near&&near->color==2);
    check(!nameplate(s,7,"Wi",false,false,{NAN,0,0},{0,0,10},{320,200,10},640,480,true,0xffff00u)); // still finite only
    // The colour follows the label's last refresh (0046e840): a member is
    // refreshed every frame; a removed member keeps the party colour between
    // the radii (0051bf60 clears the marker without a refresh) until refreshed
    // inside acquire, or until the local player's party ends (0051c030).
    L life{C{C::self,10,20,C::party},{}};
    check(life.update(9,15,C::party)==L::acquired&&(life.refreshed(9,C::party)&C::party));
    check(life.update(9,15,0)==L::none&&(life.refreshed(9,0)&C::party));     // removed at 15 m: still the party colour
    check(life.update(9,9,0)==L::none&&!(life.refreshed(9,0)&C::party));     // refreshed inside 10 m: ordinary
    check(life.update(9,15,C::party)==L::none&&(life.refreshed(9,C::party)&C::party));
    life.party_ended();check(!(life.refreshed(9,0)&C::party)&&life.labelled(9)); // party ended: refreshed, label kept
    check(!life.refreshed(10,C::party));                                     // no label, nothing refreshed
    L open{std::nullopt,{}};check(open.refreshed(9,C::party)==C::party&&!open.refreshed(9,0)); // no lifetime: current membership
  }
  // PQ-173 camera limit by class (KO 0046ea90: 33.0, 006a4250, for other
  // players in zone key 0x140; self 0046b5a0 and NPC 00459820 keep 48.0).
  {
    using P=n3e::NameDisplayPolicy;
    P plain{};check(name_distance(s,plain,false,false)==48&&name_distance(s,plain,true,false)==48&&name_distance(s,plain,false,true)==48);
    P zone{};zone.distance[1]=33;
    float player=name_distance(s,zone,false,false),npc_limit=name_distance(s,zone,true,false),self_limit=name_distance(s,zone,false,true);
    check(player==33&&npc_limit==48&&self_limit==48);
    check(nameplate(s,7,"Wi",false,false,{0,0,0},{0,0,32.99f},{320,200,10},640,480,false,std::nullopt,player).has_value());
    check(!nameplate(s,7,"Wi",false,false,{0,0,0},{0,0,33},{320,200,10},640,480,false,std::nullopt,player));   // 33 is not below 33
    check(!nameplate(s,7,"Wi",false,false,{0,0,0},{0,0,40},{320,200,10},640,480,false,std::nullopt,player));
    check(nameplate(s,8,"Wi",true,false,{0,0,0},{0,0,40},{320,200,10},640,480,false,std::nullopt,npc_limit).has_value());
    check(nameplate(s,1,"Wi",false,true,{0,0,0},{0,0,40},{320,200,10},640,480,false,std::nullopt,self_limit).has_value());
    check(nameplate(s,7,"Wi",false,false,{0,0,0},{0,0,40},{320,200,10},640,480,true,0xffff00u,player).has_value()); // beyond_distance still skips it
    P wide{};wide.distance[2]=60;check(nameplate(s,8,"Wi",true,false,{0,0,0},{0,0,55},{320,200,10},640,480,false,std::nullopt,name_distance(s,wide,true,false)).has_value());
  }
  // PQ-177 NPC info line (KO 00465070 sets it at each label refresh while the
  // local authority byte is 0 and never clears it, 0046509e -> 00465177; the
  // labels' release 00456b40 frees it with the name; 00459820 draws it 5 px
  // plus its height above the name, centred).
  {
    using L=NameLifetime;using P=n3e::NameLifetimePolicy;using N=n3e::NpcNameLifetimePolicy;
    NpcNameLifetime npc{N{P{P::self,10,20,0,true},false,true}};
    check(npc.update(1,5,false,false)==L::acquired&&npc.labelled(1)&&!npc.informed(1));   // no capability: never set
    for(int i=0;i<3;++i)npc.update(1,5,false,false);check(!npc.informed(1));
    check(npc.update(2,15,false,true)==L::none&&!npc.informed(2));                       // no refresh in the band: no line, no name
    check(npc.update(2,25,false,true)==L::none&&!npc.informed(2));                       // nor at 20 m or farther
    check(npc.update(1,5,false,true)==L::none&&npc.informed(1));                         // a refresh with the capability sets it
    check(npc.update(1,5,false,false)==L::none&&npc.informed(1));                        // revoked: refresh skips, the line stays
    check(npc.update(1,25,false,false)==L::none&&npc.informed(1));                       // kept far with the label
    check(npc.update(1,15,false,false)==L::released&&!npc.informed(1)&&!npc.labelled(1));// freed with the label (00456b40)
    check(npc.update(1,5,false,false)==L::acquired&&!npc.informed(1));                   // rebuilt without the capability: none
    check(npc.update(1,5,false,true)==L::none&&npc.informed(1));
    check(npc.update(1,5,true,true)==L::released&&!npc.informed(1));                     // dead: dropped with the name, not set again
    check(npc.update(1,5,true,true)==L::none&&!npc.informed(1));
    npc.update(3,1,false,true);npc.update(4,1,false,true);
    npc.forget_absent([](uint64_t id){return id==4;});check(!npc.informed(3)&&npc.informed(4)); // left view
    npc.clear();check(!npc.informed(4));                                                 // new session
    NpcNameLifetime flagged{N{P{P::self,10,20,0,true},true,true}};
    check(flagged.update(5,400,false,true)==L::acquired&&flagged.informed(5));          // looks flag: refreshed at any range
    check(flagged.update(5,400,false,false)==L::none&&flagged.informed(5));             // and kept after revocation
    NpcNameLifetime none;                                                                // no policy: every measurement refreshes
    check(none.update(6,500,false,false)==L::none&&!none.informed(6));
    check(none.update(6,500,false,true)==L::none&&none.informed(6));
    check(none.update(6,500,false,false)==L::none&&none.informed(6));                   // revoked: kept while in view
    none.forget_absent([](uint64_t){return false;});check(!none.informed(6));
    // Text: the package's line with its one {id} replaced; validation.
    n3e::NpcInfoPolicy info{0x00ff00u,"ID({id}) : TYPE(0)"};
    check(n3e::npc_info_line(info,1234)=="ID(1234) : TYPE(0)");
    check(n3e::npc_info_text_valid("{id}")&&n3e::npc_info_text_valid(std::string(60,'x')+"{id}"));
    for(const char*bad:{"","ID","{id}{id}","{id}}","{ID}","{id}\n"})check(!n3e::npc_info_text_valid(bad));
    check(!n3e::npc_info_text_valid(std::string(61,'x')+"{id}")&&!n3e::npc_info_text_valid("{id}\xe9"));
    // Placement: the NPC font, gap plus its height above the name, centred on
    // the name's projected x.
    auto name=nameplate(s,8,"Worm",true,false,{0,0,0},{0,0,10},{320,200,10},640,480);
    check(name.has_value());
    auto line=info_plate(s,*name,n3e::npc_info_line(info,8),info.color);
    check(line.info&&!name->info&&line.font==1&&line.color==0x00ff00u&&line.entity==8);
    check(line.y==name->y-5-18&&line.width==name_width(s.fonts[1],"ID(8) : TYPE(0)"));
    check(line.x==320-line.width/2&&name->x+name->width/2==320);
  }
  std::cout<<"PASS proportional mixed-case names, centering, model/seated/drawn-scale anchors, self/NPC styles, distance boundary, partial viewport and hostile projections, other-player label lifetime hysteresis and exemptions, party names under the toggle, beyond the camera limit and in the refreshed colour, per-class camera limits, NPC label band, stale far case, looks flag and dead release, NPC info line set only with the projected capability, kept after revocation until the label goes, stacked above the name\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
