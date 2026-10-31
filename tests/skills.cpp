#include "assets/assets.h"
#include "render/skill_reach.h"
#include <iostream>
#include <cstdio>
#include <algorithm>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
static void check(bool ok,const char*what){if(!ok)throw std::runtime_error(what);}
int main(int argc,char**argv){try{
  if(argc!=2)return 2;
  auto p=n3e::load_skills(argv[1]);
  if(p.entries.size()!=2||p.entries[0].cost!=5||p.entries[1].cast_ms!=1500)throw std::runtime_error("skill values");
  std::cout<<"reach start="<<p.reach.start<<" hold="<<p.reach.hold<<" planar="<<p.reach.planar<<"\n";
  std::cout<<"notice='"<<p.notice<<"'\n";
  // PQ-466 (D-234): the client's start-limit hint, the server's acceptance
  // form (range + radii + start, 3-D, inclusive), and the notice's one %s.
  const auto&s=p.entries[1];const float limit=n3e::skill_start_limit(s,p.reach,2.f);
  check(limit==s.range+2.f+p.reach.start,"skill start limit");
  check(!n3e::skill_too_far({0,0,0},{limit,0,0},limit),"skill limit is inclusive");
  check(n3e::skill_too_far({0,0,0},{0,limit*1.0001f,0},limit),"skill limit is 3-D");
  check(!n3e::skill_too_far({1,1,1},{1+limit*.6f,1,1+limit*.79f},limit),"skill limit measures from the caster");
  check(n3e::skill_notice("%s is too far",s.label)==s.label+" is too far"&&n3e::skill_notice("Too far","x")=="Too far"&&
        n3e::skill_notice("","x").empty(),"skill notice format");
  std::cout<<"limit="<<limit<<" formatted='"<<n3e::skill_notice(p.notice,s.label)<<"'\n";
  // PQ-469 (D-235): N3K4's failed line and colour, and the record that names
  // which of the client's own skill actions the server refused out_of_range.
  {char color[16];std::snprintf(color,sizeof color,"%08x",p.failed_color);
   std::cout<<"failed='"<<p.failed<<"' color="<<color<<" failed_formatted='"<<n3e::skill_notice(p.failed,s.label)<<"'\n";}
  // PQ-479 (D-243): N3K5's refusal lines as loaded.
  for(const auto&l:p.refusals){char color[16];std::snprintf(color,sizeof color,"%08x",l.color);
   std::cout<<"refusal status="<<l.status<<" target="<<l.target<<" text='"<<l.text<<"' color="<<color<<"\n";}
  struct Outcome{uint64_t number,seq;std::string status;};
  using Line=n3e::SkillFailures::Line;
  n3e::SkillFailures f;f.send(3,1);f.send(5,0);
  std::vector<Outcome> got{{1,3,"cast_pending"},{2,4,"out_of_range"},{3,5,"out_of_range"},{4,3,"out_of_range"}};
  check(f.refused(got)==std::vector<Line>{{0,-1},{1,-1}},"refused: only the client's own skills, oldest first (a melee seq 4 is none)");
  check(f.refused(got).empty()&&f.seen==4,"each outcome is read once");
  got.push_back({5,3,"out_of_range"});
  check(f.refused(got).empty(),"a sent skill answers at most once");
  for(uint64_t seq=10;seq<10+n3e::SkillFailures::kept+1;++seq)f.send(seq,1);
  check(f.sent.size()==n3e::SkillFailures::kept&&f.sent.front().seq==11,"the record keeps the newest sent skills");
  f.reset();check(f.sent.empty()&&!f.seen,"a new connection starts the record again");
  check(f.refused(std::vector<Outcome>{{1,11,"out_of_range"}}).empty()&&f.seen==1,"after a reset nothing old answers");
  // PQ-471 (D-242): of the server's skill refusals only out_of_range matches a
  // -103 refusal (Ebenezer 0046e707), the one code on which 1298's 00586fa0
  // posts text 0xfa4. The others have no -103 counterpart: Ebenezer answers
  // them -100 or 0, drops them with no packet, or has no such refusal. With no
  // refusal lines (N3K2-N3K4) none of them posts a line.
  const char*statuses[]={"wrong_class","level_required","actor_dead","target_dead","invalid_target",
                         "insufficient_resource","weapon_required","cooldown","stale_target","stale_session",
                         "stale_action","combat_pending","skill_unavailable","cast_timeout","interrupted",
                         "target_pending","settlement_capacity","contributor_capacity"};
  for(const char*status:statuses){
    n3e::SkillFailures g;g.send(1,1);
    check(g.refused(std::vector<Outcome>{{1,1,status}}).empty()&&g.sent.size()==1,"no other skill refusal posts the failed line");
    check(g.refused(std::vector<Outcome>{{1,1,status},{2,1,"out_of_range"}})==std::vector<Line>{{1,-1}},
          "an out_of_range for the same action after it still posts once");}
  // PQ-479 (D-243): N3K5's refusal lines, Moradon's mapping (ko_skills.py):
  // 1298 posts its own text for the class, MP and need-item refusals it makes
  // before it sends a cast (0057f7f0) and text 0xfa2 for Ebenezer's -100 to a
  // casting phase (00586fa0): a low level, or an NPC that died on the server
  // first. Each posts only as the server's first answer to the action (its
  // acceptance), and target_dead only on an NPC; every other status, and
  // every refusal after the acceptance, posts nothing.
  {std::vector<n3e::SkillRefusal> lines{{"wrong_class",0,"class",0xffffff00},{"insufficient_resource",0,"mp",0xffffff00},
                                        {"weapon_required",0,"item",0xffffff00},{"level_required",0,"failed",0xffff3b3b},
                                        {"target_dead",2,"failed",0xffff3b3b}};
   auto posted=[&](const char*status,bool npc,bool accepted){
     n3e::SkillFailures g;g.send(7,1,npc);std::vector<Outcome> o;
     if(accepted)o.push_back({1,7,"cast_pending"});
     o.push_back({o.size()+1,7,status});auto r=g.refused(o,lines);
     check(r.size()<=1,"at most one line per action");return r.empty()?-2:r[0].skill==1?r[0].line:-3;};
   for(bool npc:{false,true}){
     check(posted("wrong_class",npc,false)==0&&posted("insufficient_resource",npc,false)==1&&
           posted("weapon_required",npc,false)==2&&posted("level_required",npc,false)==3,"an acceptance refusal posts its line");
     check(posted("target_dead",npc,false)==(npc?4:-2),"target_dead posts only on an NPC (Ebenezer drops a dead player silently)");
     check(posted("out_of_range",npc,false)==-1&&posted("out_of_range",npc,true)==-1,"out_of_range keeps the failed line");
     for(const char*status:statuses){
       check(posted(status,npc,true)==-2,"a refusal after the acceptance posts no refusal line");
       const bool listed=std::any_of(lines.begin(),lines.end(),[&](const auto&l){return l.status==status;});
       if(!listed)check(posted(status,npc,false)==-2,"a status without a line posts nothing");}}
   // A refusal line answers its action once; the record still names a later
   // out_of_range of another action, and a melee action posts nothing.
   n3e::SkillFailures g;g.send(1,0,true);g.send(2,1,true);
   check(g.refused(std::vector<Outcome>{{1,1,"level_required"},{2,1,"level_required"},{3,3,"level_required"},{4,2,"cast_pending"},{5,2,"out_of_range"}},lines)==
         std::vector<Line>{{0,3},{1,-1}},"each action posts once, in order");
   check(g.sent.empty(),"answered actions leave the record");}
  {// PQ-481 (D-245): the recipient of a press as 1298's skill start 005819e0
   // picks it. Kind 1 (1298's type 2) goes to a player the client sees,
   // whatever its health (00582bdf), else to the caster (00582b7b, 00582c16).
   // Kind 2 (type 7) holds a press with no target (00582e97) and, hinted, one
   // on a target the client does not see, sees dead (PQ-479: 00582ea3,
   // 00582eac) or sees is not an NPC (006164c0 at 00582ebc).
   struct Seen{uint64_t i;uint32_t h;bool n;uint64_t id()const{return i;}uint32_t health()const{return h;}bool npc()const{return n;}};
   const std::vector<Seen> seen{{1,50,false},{7,0,true},{8,40,true},{5,0,false},{6,30,false}};
   using H=n3e::SkillHold;
   auto at=[&](uint32_t kind,bool hint,uint64_t target){auto r=n3e::skill_recipient(kind,hint,seen,uint64_t{1},target);return std::pair{r.id,r.hold};};
   for(bool hint:{true,false}){
     check(at(1,hint,0)==std::pair{uint64_t{1},H::none},"a player skill with no target goes to the caster");
     check(at(1,hint,6)==std::pair{uint64_t{6},H::none},"a player skill goes to a live player target");
     check(at(1,hint,5)==std::pair{uint64_t{5},H::none},"a player skill goes to a dead player target (no fallback to the caster)");
     check(at(1,hint,8)==std::pair{uint64_t{1},H::none}&&at(1,hint,7)==std::pair{uint64_t{1},H::none},"a player skill on an NPC goes to the caster");
     check(at(1,hint,9)==std::pair{uint64_t{1},H::none},"a player skill on a target the client does not see goes to the caster");
     check(at(1,hint,1)==std::pair{uint64_t{1},H::none},"a player skill on the caster goes to the caster");
     check(at(2,hint,0).second==H::no_target,"an NPC skill with no target is held, hinted or not");}
   check(at(2,true,8)==std::pair{uint64_t{8},H::none},"an NPC skill goes to a live NPC");
   check(at(2,true,7).second==H::dead,"a dead NPC target holds a hinted NPC skill");
   check(at(2,true,9).second==H::unseen,"a target the client does not see holds a hinted NPC skill");
   check(at(2,true,6).second==H::not_npc&&at(2,true,1).second==H::not_npc,"a player target or the caster holds a hinted NPC skill");
   check(at(2,true,5).second==H::dead,"the state test comes before the hostility test (00582ea3 before 00582ebc)");
   for(uint64_t t:{5,6,7,9})check(at(2,false,t)==std::pair{t,H::none},"an unchecked NPC skill with a target is sent");
   for(auto h:{H::none,H::no_target,H::unseen,H::dead,H::not_npc})check(std::string(n3e::skill_hold_name(h)).size()>2,"each hold has a name");}
  std::cout<<"PASS skill policy cross-language load\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
