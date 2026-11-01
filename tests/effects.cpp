#include "render/effects.h"
#include "render/appearance_effects.h"
#include "render/options.h"
#include "render/equipment_glow.h"
#include "render/attached_characters.h"
#include "render/animation.h"
#include <cmath>
#include <cstdio>
#include <fstream>
#include <set>
#include <unistd.h>
#include <iostream>
#include <stdexcept>
void need(bool value){if(!value)throw std::runtime_error("effect check");}
bool near(float a,float b,float tolerance=1e-4f){return std::abs(a-b)<tolerance;}
// PQ-211: an N3E2 appearance effect on a one-joint skeleton. Three copies of one
// triangle (KO 00415910: as placed, and two turned copies moved +v and -v),
// two tails, a two-second tail clip.
void appearance(n3e::Effects effects){
  n3e::Scene skeleton{};skeleton.scale={1,1,1};
  skeleton.nodes.push_back(n3e::Node{-1,{0,0,0},{1,1,1},{0,0,0,1}});
  n3e::M identity{};for(int i=0;i<4;++i)identity[i*5]=1;
  skeleton.joints.push_back(n3e::Joint{0,identity});
  effects.textures.assign(3,n3e::EffectTexture{1,1,{255,255,255,255}});
  n3e::EffectBatch spark{1,0,5,6,199,{0,0,0,.1f,.1f,0,1,1,1,1,0}};
  n3e::EffectClip tail{false,30,{}};for(int i=0;i<60;++i)tail.frames.push_back({spark});
  effects.clips.emplace("tail",tail);
  n3e::AppearanceEffect e;e.key=2;e.joint=0;e.frames={0,1,2};e.fps=10;e.phase_steps=1;e.phase_step=0;
  e.source_blend=3;e.destination_blend=2;e.flags=455;
  std::vector<std::array<float,5>> triangle{{0,0,0,0,0},{1,0,0,1,0},{0,1,0,0,1}};
  e.copies={{0,0,triangle},{1,1,triangle},{-1,2,triangle}};
  e.jitter_rate=1.2f;e.jitter_amplitude=.035f;e.jitter={n3e::V{0,0,0},n3e::V{0,0,1}};
  e.tail_box={n3e::V{0,0,0},n3e::V{1,0,0},n3e::V{0,2,0},n3e::V{0,0,3}};
  e.tail_low=.25f;e.tail_steps=50;e.tail_step=.01f;e.tails=2;e.tail_clip="tail";e.trace_color=0xffffff00;
  effects.appearance.push_back(e);
  std::vector<n3e::AppearanceRule> rules{{"demo:item/shield",1},{"demo:item/blade",0},{"demo:item/other",0}};
  n3e::AppearanceEffects fx;fx.build(effects,skeleton);
  need(fx.models.size()==1&&fx.models.at(2).indices.size()==9+7);
  // The first key per slot: key 3 shares key 2's slot and is not drawn.
  need((n3e::AppearanceEffects::selected(rules,std::vector<uint32_t>{3,2,1})==std::vector<uint32_t>{3,1}));
  auto pose=skeleton.nodes;pose[0].t={0,1,0};
  std::vector<n3e::EffectMesh> meshes;std::vector<const n3e::EffectInstance*> tails;
  // Not equipped (key 1 has no effect, key 3 shadows key 2): nothing drawn.
  need(fx.draw(7,rules,std::vector<uint32_t>{1,3,2},pose,{10,0,20},0,100,{0,0,0},meshes,tails).empty()&&meshes.empty()&&tails.empty());
  need(fx.retire().empty());
  auto started=fx.draw(7,rules,std::vector<uint32_t>{2},pose,{10,0,20},0,100,{0,0,0},meshes,tails);
  need(started==std::vector<uint32_t>{2}&&meshes.size()==3&&tails.size()==2);
  // t=0: frac 0 gives offset -amplitude along +z; copy 1 moves -0.035, copy 2 +0.035.
  need(meshes[0].vertices.size()==27&&near(meshes[0].vertices[0],10)&&near(meshes[0].vertices[1],1)&&near(meshes[0].vertices[2],20));
  need(near(meshes[1].vertices[2],20-.035f)&&near(meshes[2].vertices[2],20+.035f));
  need(meshes[0].texture==0&&meshes[1].texture==1&&meshes[2].texture==2&&meshes[0].source_blend==3&&meshes[0].destination_blend==2&&meshes[0].flags==455);
  need(near(meshes[0].vertices[3+9],1)&&meshes[0].vertices[5]==1&&meshes[0].vertices[8]==1); // UV, white tint
  // Tail links start inside the box's 25..74 % (x 0..1, y 0..2, z 0..3) about the posed joint.
  for(auto*t:tails){auto p=t->positions.front().second;need(p[0]>=10.25f-1e-4f&&p[0]<=10.74f+1e-4f&&p[1]>=1.5f-1e-4f&&p[1]<=2.48f+1e-4f&&p[2]>=20.75f-1e-4f&&p[2]<=22.22f+1e-4f);}
  need(fx.retire().empty());
  // t=0.5 s: frame 5 (+0, +1, +2), offset (frac(0.6) x 2 - 1) x 0.035 = 0.007.
  meshes.clear();tails.clear();
  need(fx.draw(7,rules,std::vector<uint32_t>{2},pose,{10,0,20},0,100.5,{0,0,0},meshes,tails).empty());
  need(meshes[0].texture==2&&meshes[1].texture==0&&meshes[2].texture==1);
  need(near(meshes[1].vertices[2],20+.007f)&&near(meshes[2].vertices[2],20-.007f));
  // Heading pi/2 turns model x onto -z, as the body is drawn.
  meshes.clear();tails.clear();fx.draw(7,rules,std::vector<uint32_t>{2},pose,{10,0,20},float(M_PI/2),100.5,{0,0,0},meshes,tails);
  need(near(meshes[0].vertices[9],10)&&near(meshes[0].vertices[11],19));
  // Each tail adds one random point per sample interval.
  auto points=tails[0]->positions.size();
  meshes.clear();tails.clear();fx.draw(7,rules,std::vector<uint32_t>{2},pose,{10,0,20},0,100.52,{0,0,0},meshes,tails);
  need(tails[0]->positions.size()==points);
  meshes.clear();tails.clear();fx.draw(7,rules,std::vector<uint32_t>{2},pose,{10,0,20},0,100.54,{0,0,0},meshes,tails);
  need(tails[0]->positions.size()==points+1);
  // At half the clip (1 s) a new link starts and the old one stops emitting.
  meshes.clear();tails.clear();fx.draw(7,rules,std::vector<uint32_t>{2},pose,{10,0,20},0,101,{0,0,0},meshes,tails);
  need(tails.size()==4&&near(tails[0]->stop,1)&&tails[1]->stop==10);
  // At the clip's end the first link is gone.
  meshes.clear();tails.clear();fx.draw(7,rules,std::vector<uint32_t>{2},pose,{10,0,20},0,102,{0,0,0},meshes,tails);
  need(tails.size()==4&&tails[0]->start==101);
  // Not drawn for a frame: retired, then started afresh.
  need(fx.retire().empty());
  auto gone=fx.retire();need(gone.size()==1&&gone[0]==std::pair<uint64_t,uint32_t>{7,2}&&fx.states.empty());
  meshes.clear();tails.clear();
  need(fx.draw(7,rules,std::vector<uint32_t>{2},pose,{10,0,20},0,103,{0,0,0},meshes,tails)==std::vector<uint32_t>{2});
  // A phase of (rand % steps) x step seconds shifts the frame for each weapon.
  effects.appearance[0].phase_steps=1000;effects.appearance[0].phase_step=.01f;fx.build(effects,skeleton);
  std::set<uint32_t> first;
  for(uint64_t actor=1;actor<=20;++actor){meshes.clear();tails.clear();fx.draw(actor,rules,std::vector<uint32_t>{2},pose,{},0,5,{},meshes,tails);first.insert(meshes[0].texture);}
  need(first.size()>1);
  std::cout<<"PASS appearance effects: three textured copies with their jitter, frame steps and heading, tails in the box, chained links, first key per slot and retirement\n";
}
// PQ-376 (D-200): 1298's alpha-list keys. With an N3E5 sort record a copy
// sorts by the eye distance to the sort origin moved by its jitter plus the
// bias (00415910) and each tail quad on its own by the eye distance to the
// centroid of its first three corners (004840b0; corner order 00482820:
// UV (0, 0), (1, 0), (1, 1), (0, 1)); without one, n3e's order: a copy by its
// vertex centroid, a link's batch by its newest point. All keys are linear.
void alpha_keys(n3e::Effects effects){
  n3e::Scene skeleton{};skeleton.scale={1,1,1};
  skeleton.nodes.push_back(n3e::Node{-1,{0,0,0},{1,1,1},{0,0,0,1}});
  n3e::M identity{};for(int i=0;i<4;++i)identity[i*5]=1;
  skeleton.joints.push_back(n3e::Joint{0,identity});
  effects.textures.assign(3,n3e::EffectTexture{1,1,{255,255,255,255}});
  // Three sparks of one batch, at different offsets, sizes and angles.
  n3e::EffectBatch spark{1,0,5,6,455,{0,0,4,.6f,.3f,float(M_PI/2),1,1,1,1,0,
                                      0,1,2.5f,.2f,.2f,0,1,1,1,1,0,
                                      1,0,-3,.4f,.1f,.3f,1,1,1,1,0}};
  n3e::EffectClip tail{false,30,{}};for(int i=0;i<60;++i)tail.frames.push_back({spark});
  effects.clips.emplace("tail",tail);
  n3e::AppearanceEffect e;e.key=1;e.joint=0;e.frames={0,1,2};e.fps=10;e.phase_steps=1;e.phase_step=0;
  e.source_blend=5;e.destination_blend=6;e.flags=455;
  std::vector<std::array<float,5>> triangle{{0,0,0,0,0},{1,0,0,1,0},{0,1,0,0,1}};
  e.copies={{0,0,triangle},{1,1,triangle},{-1,2,triangle}};
  e.jitter_rate=1.2f;e.jitter_amplitude=.035f;e.jitter={n3e::V{0,0,0},n3e::V{0,0,1}};
  e.tail_box={n3e::V{0,0,0},n3e::V{0,0,0},n3e::V{0,0,0},n3e::V{0,0,0}};  // every point at the origin
  e.tail_low=.25f;e.tail_steps=50;e.tail_step=.01f;e.tails=1;e.tail_clip="tail";e.trace_color=0;
  e.sorted=true;e.sort_origin={0,0,2};e.sort_bias=1.5f;
  effects.appearance.push_back(e);
  std::vector<n3e::AppearanceRule> rules{{"demo:item/blade",0}};
  n3e::V eye{0,0,10},right{1,0,0},up{0,1,0};
  auto pose=skeleton.nodes;
  for(bool sorted:{true,false}){
    effects.appearance[0].sorted=sorted;
    n3e::AppearanceEffects fx;fx.build(effects,skeleton);
    std::vector<n3e::EffectMesh> meshes;std::vector<const n3e::EffectInstance*> tails;
    fx.draw(7,rules,std::vector<uint32_t>{1},pose,{0,0,0},0,100,eye,meshes,tails);
    need(meshes.size()==3&&tails.size()==1&&tails[0]->quad_keys==sorted);
    // t=0: the jitter offset is -0.035 along +z: copy 1 at z -0.035, copy 2 at +0.035.
    if(sorted){
      need(near(meshes[0].distance,8+1.5f)&&near(meshes[1].distance,8.035f+1.5f)&&near(meshes[2].distance,7.965f+1.5f));
    }else{
      float d=std::sqrt(1.f/9+1.f/9+100);  // the triangle's centroid (1/3, 1/3, 0)
      need(near(meshes[0].distance,d));
    }
    n3e::EffectPlayer player;
    auto draws=n3e::effect_draws(player,tails,meshes,100.01,eye,right,up,effects.textures.size());
    if(!sorted){
      // One draw for the link's batch, keyed by its newest point (the
      // origin, 10), between the copies at their centroids (10.046, 10.011
      // and 9.976 with the jitter).
      need(draws.size()==4&&draws[2].mesh==nullptr&&near(draws[2].key,10)&&draws[2].records==SIZE_MAX);
      need(draws[0].mesh==&meshes[1]&&draws[1].mesh==&meshes[0]&&draws[3].mesh==&meshes[2]);
      continue;
    }
    // Three copies and three quads: the quad at z -3 (key 13.04) first, then
    // the copies (9.465..9.535), then the quads at z 2.5 (7.57) and z 4 (6).
    need(draws.size()==6);
    need(draws[0].batch&&draws[0].record==2&&draws[0].records==1);
    need(draws[1].mesh==&meshes[1]&&draws[2].mesh==&meshes[0]&&draws[3].mesh==&meshes[2]);
    need(draws[4].record==1&&draws[5].record==0);
    for(size_t k=1;k<draws.size();++k)need(draws[k-1].key>=draws[k].key);
    // Each quad's key is the eye distance to the mean of its corners UV
    // (0, 0), (1, 0), (1, 1) as effect_vertices builds them.
    for(const auto&d:draws){
      if(!d.batch)continue;
      auto v=n3e::effect_vertices(*d.instance,*d.batch,d.age,right,up,d.record,d.records);
      need(v.size()==54);
      n3e::V mean{};int found=0;
      for(auto uv:{std::array<float,2>{0,0},{1,0},{1,1}})
        for(size_t j=0;j<v.size();j+=9)if(near(v[j+3],uv[0])&&near(v[j+4],uv[1])){for(int a=0;a<3;++a)mean[a]+=v[j+a]/3;++found;break;}
      need(found==3&&near(d.key,n3e::eye_distance(mean,eye)));
    }
    // The first quad, turned pi/2: its three-corner mean is off its centre by
    // (w / 6, h / 6) turned, (-0.05, 0.1, 0).
    auto point=n3e::quad_sort_point(*draws[5].instance,spark.records.data(),draws[5].age,right,up);
    need(near(point[0],-.05f)&&near(point[1],.1f)&&near(point[2],4));
  }
  // A following quad (birth -1) sorts at the anchor of its draw's age, as
  // effect_vertices places it; a born one at its birth point.
  n3e::EffectInstance moving{&effects.clips.at("tail"),1,0,1,10,{},{{0,{0,0,0}},{1,{5,0,0}}}};
  const float following[11]{0,0,0,.6f,.6f,0,1,1,1,1,-1},born[11]{0,0,0,.6f,.6f,0,1,1,1,1,0};
  need(near(n3e::quad_sort_point(moving,following,1,right,up)[0],5.1f)&&near(n3e::quad_sort_point(moving,born,1,right,up)[0],.1f));
  std::cout<<"PASS N3E5 alpha-list keys (PQ-376): copies at the sort origin moved by their jitter plus the bias, each tail quad at its first three corners' mean, one far-to-near list of linear keys; without a record each copy at its centroid and each link at its newest point\n";
}
// PQ-341: a 2233 weapon effect tail, a 20 s clip (two 10 s links) whose first
// half carries a triangle batch (a mesh part: birth -1) and whose second half
// is empty but for finishing quads. Links restart every 10 s; a link's
// triangles stand at its newest box point and stop with it; drawn at 60 Hz,
// a link keeps one point per sample interval, at most 601 in its 20 s.
void long_tail(n3e::Effects effects){
  n3e::Scene skeleton{};skeleton.scale={1,1,1};
  skeleton.nodes.push_back(n3e::Node{-1,{0,0,0},{1,1,1},{0,0,0,1}});
  n3e::M identity{};for(int i=0;i<4;++i)identity[i*5]=1;
  skeleton.joints.push_back(n3e::Joint{0,identity});
  effects.textures.assign(2,n3e::EffectTexture{1,1,{255,255,255,255}});
  n3e::EffectBatch mesh{0,1,5,2,455,{0,0,0,0,0,1,1,1,1, 1,0,0,1,0,1,1,1,1, 0,1,0,0,1,1,1,1,1}};
  n3e::EffectBatch spark{1,0,5,2,455,{0,0,0,.1f,.1f,0,1,1,1,1,9.9f}};
  n3e::EffectClip tail{false,30,{}};
  for(int i=0;i<600;++i)tail.frames.push_back(i<300?std::vector<n3e::EffectBatch>{mesh}:i<310?std::vector<n3e::EffectBatch>{spark}:std::vector<n3e::EffectBatch>{});
  effects.clips.emplace("long",tail);
  n3e::AppearanceEffect e;e.key=1;e.joint=0;e.frames={0};e.fps=10;e.phase_steps=1;e.phase_step=0;
  e.source_blend=5;e.destination_blend=2;e.flags=455;
  e.jitter_rate=1.2f;e.jitter_amplitude=.035f;e.jitter={n3e::V{0,0,0},n3e::V{0,0,1}};
  e.tail_box={n3e::V{0,0,0},n3e::V{1,0,0},n3e::V{0,2,0},n3e::V{0,0,3}};
  e.tail_low=.25f;e.tail_steps=50;e.tail_step=.01f;e.tails=2;e.tail_clip="long";e.trace_color=0xffff00ff;
  effects.appearance.push_back(e);
  std::vector<n3e::AppearanceRule> rules{{"demo:item/bow",1}};
  n3e::AppearanceEffects fx;fx.build(effects,skeleton);
  auto pose=skeleton.nodes;
  size_t most=0;
  for(int step=0;step<=60*25;++step){
    double now=200+step/60.;
    std::vector<n3e::EffectMesh> meshes;std::vector<const n3e::EffectInstance*> tails;
    fx.draw(3,rules,std::vector<uint32_t>{1},pose,{0,0,0},0,now,{0,0,0},meshes,tails);
    for(const auto*t:tails){
      most=std::max(most,t->positions.size());
      float age=float(now-t->start);auto frame=size_t(age*t->clip->rate);
      if(frame>=t->clip->frames.size())continue;
      for(const auto&batch:t->clip->frames[frame]){
        auto v=n3e::effect_vertices(*t,batch,age,{1,0,0},{0,1,0});
        if(batch.kind)continue;
        // Triangles only before the link's stop, at its newest point.
        need(age<t->stop?v.size()==27:v.empty());
        if(!v.empty()){auto p=t->positions.back().second;need(near(v[0],p[0])&&near(v[1],p[1])&&near(v[2],p[2])&&near(v[9],p[0]+1));}
      }
    }
    // A new link every 10 s: one per chain until then, two after.
    if(step==60*5)need(tails.size()==2);
    if(step==60*15)need(tails.size()==4&&near(tails[0]->stop,10)&&tails[1]->stop==10);
  }
  need(most>590&&most<=601);
  std::cout<<"PASS appearance effect long tail (PQ-341): 20 s clip, links every 10 s, triangles at the newest point until the stop, at most 601 points a link\n";
}
void options(){
  auto file=std::filesystem::temp_directory_path()/("n3e-options-"+std::to_string(::getpid())+".ini");
  auto write=[&](const std::string&text){std::ofstream(file)<<text;};
  need(ClientOptions::load(file.string()+".missing").weapon_effects);
  write("[Screen]\nEffectVisible=0\n");need(ClientOptions::load(file).weapon_effects);
  write("[weaponeffect]\n effectvisible = 0 ; off\n");need(!ClientOptions::load(file).weapon_effects);
  write("[WeaponEffect]\nEffectVisible=off\n");need(!ClientOptions::load(file).weapon_effects); // no leading integer: 0
  write("[WeaponEffect]\nEffectVisible=2\nEffectVisible=0\n");need(ClientOptions::load(file).weapon_effects); // first key wins
  write("[WeaponEffect]\nEffectVisible=0\n"+std::string(70000,';'));need(ClientOptions::load(file).weapon_effects); // oversized: defaults
  std::filesystem::remove(file);
  need(ClientOptions::load(file.string()+".missing").equipment_glow);
  write("[Addition2233]\nEquipmentGlow=0\n");need(!ClientOptions::load(file).equipment_glow&&ClientOptions::load(file).weapon_effects);
  write("[WeaponEffect]\nEffectVisible=0\n");need(ClientOptions::load(file).equipment_glow);
  std::filesystem::remove(file);
  // PQ-328: 2233's own [Effect] Wing (009e0883, default 1).
  need(ClientOptions::load(file.string()+".missing").wing);
  write("[effect]\nwing=0\n");need(!ClientOptions::load(file).wing&&ClientOptions::load(file).equipment_glow);
  write("[Effect]\nWing=1\n[Addition2233]\nEquipmentGlow=0\n");need(ClientOptions::load(file).wing);
  std::filesystem::remove(file);
  // RQ-071 (Q70): 1298's [Sound] Effect (0064b9b0, default 1) silences every
  // sound; [Sound] Bgm (zone music only) and [Effect] (2233's Wing) do not.
  need(ClientOptions::load(file.string()+".missing").sound);
  write("[sound]\neffect=0\n");need(!ClientOptions::load(file).sound&&ClientOptions::load(file).wing);
  write("[Sound]\nBgm=0\n[Effect]\nEffect=0\nWing=0\n");need(ClientOptions::load(file).sound&&!ClientOptions::load(file).wing);
  write("[Sound]\nEffect=1\nBgm=0\nDistance=20\n");need(ClientOptions::load(file).sound);
  std::filesystem::remove(file);
  std::cout<<"PASS client options: WeaponEffect.EffectVisible, Addition2233.EquipmentGlow, Effect.Wing and Sound.Effect default on, case-blind names, leading-integer values, bounded file\n";
}
// PQ-315: the N3E3 equipment glow. The KO cook writes 0056ea30's pulse as rise
// 1 s, hold to 3 s, fall to 5 s, period 5.5 s (2233 constants 00b96e14 3.0,
// 00b96dd8 5.0, 00b96e1c 5.5, 00b91540 3.0, 00b8fab8 0.5).
void glow(){
  n3e::AppearanceGlow pulse{};pulse.key=1;pulse.color={1,1,1};pulse.modulate=2;pulse.wave=n3e::AppearanceGlow::PULSE;
  pulse.rise=1;pulse.hold=3;pulse.fall=5;pulse.period=5.5f;
  auto at=[&](double t){return n3e::EquipmentGlow::intensity(pulse,t);};
  // 0056ea30: i = t to 1 s, held to 3 s, 1 - (t - 3) x 0.5 to 5 s, then 0
  // until the timer restarts past 5.5 s.
  need(near(at(0),0)&&near(at(.25),.25f)&&near(at(1),1)&&near(at(2),1)&&near(at(3),1));
  need(near(at(3.5),.75f)&&near(at(4),.5f)&&near(at(5),0)&&near(at(5.25),0));
  need(near(at(5.75),.25f)&&near(at(5.5+4),.5f)&&near(at(11+2),1)); // repeats every 5.5 s
  n3e::AppearanceGlow steady{};steady.key=2;steady.color={.5f,.25f,1};steady.modulate=1;
  need(near(n3e::EquipmentGlow::intensity(steady,0),1)&&near(n3e::EquipmentGlow::intensity(steady,77),1));
  n3e::Effects effects;effects.glow={pulse,steady};
  n3e::EquipmentGlow g;g.build(effects);
  bool started=false;
  // One clock per actor, from its first draw: actor 7 at 10 s, actor 8 at 12 s.
  need(!g.shade(7,3,10,&started)); // a key with no record: none, but the clock starts
  auto a=g.shade(7,1,10,&started);need(a&&started&&near(a->intensity,0)&&near(a->modulate,2));
  auto b=g.shade(8,1,12,&started);need(b&&started&&near(b->intensity,0));
  a=g.shade(7,1,12.5,&started);need(a&&!started&&near(a->intensity,1)&&near(a->emissive[0],1));
  b=g.shade(8,1,12.5,&started);need(b&&near(b->intensity,.5f)&&near(b->emissive[2],.5f));
  auto c=g.shade(8,2,12.5,&started);need(c&&started&&near(c->modulate,1)&&near(c->emissive[0],.5f)&&near(c->emissive[1],.25f)&&near(c->emissive[2],1));
  need(g.retire().empty());
  // Actor 8 drawn without key 1 (unequipped): its pair ends, its clock stays.
  need(g.shade(8,2,13,&started)&&!started);g.shade(7,1,13);
  auto gone=g.retire();need(gone.size()==1&&gone[0]==std::make_pair(uint64_t(8),uint32_t(1)));
  b=g.shade(8,1,13.5,&started);need(b&&started&&near(b->intensity,1)); // t 1.5 s on actor 8's clock
  // Actor 7 not drawn for a frame (out of view): its clock restarts with it.
  g.shade(8,1,14);g.retire();g.shade(8,1,14.5);
  need(g.retire().size()==0&&!g.clocks.contains(7));
  a=g.shade(7,1,20,&started);need(a&&started&&near(a->intensity,0));
  need(g.sample(7,1,20,.5)&&!g.sample(7,1,20.25,.5)&&g.sample(7,1,20.5,.5));
  std::cout<<"PASS equipment glow: 0056ea30's pulse (rise 1 s, hold to 3 s, fall to 5 s, repeat at 5.5 s), steady 1, emissive colour x intensity, modulate, one clock per actor, pair and clock retirement\n";
}
// PQ-328: N3AT attached characters. The KO cook writes 00569590's timer as rise
// 1 s, hold to 3 s, fall to 5 s, restart past 5.5 s (2233 floats 00b96d78 3.0,
// 00b96d7c 5.0, 00b96d80 5.5; doubles 00b91540 3.0, 00b8fab8 0.5) on one clock
// per wearer that every attached slot advances.
void attached(){
  n3e::Attachments a;a.per_attachment=true;a.rise=1;a.hold=3;a.fall=5;a.period=5.5f;a.color={1,1,1};
  n3e::Attachment wing;wing.key=2;wing.group=0;wing.flags=n3e::Attachment::OPTIONAL|n3e::Attachment::EMISSIVE;wing.modulate=2;
  n3e::Attachment fairy;fairy.key=3;fairy.group=1;fairy.modulate=2; // KO column 3 = 0: part 0 at 2x, no emissive
  n3e::Attachment other_wing=wing;other_wing.key=4;
  a.entries={wing,fairy,other_wing};
  n3e::AttachedCharacters c;c.build(a);
  // One per group, the last key in the list winning; in group order.
  need(c.resolve(std::vector<uint32_t>{}).empty()&&c.resolve(std::vector<uint32_t>{1,9}).empty());
  need((c.resolve(std::vector<uint32_t>{3,2})==std::vector<size_t>{0,1}));
  need((c.resolve(std::vector<uint32_t>{2,4})==std::vector<size_t>{2})&&(c.resolve(std::vector<uint32_t>{4,2})==std::vector<size_t>{0}));
  // The KO accumulator, one attachment: i = t to 1 s, kept to 3 s, falling to
  // 0 at 5 s, kept, restart past 5.5 s (00569590).
  auto one=[&](double now){return c.advance(7,{0},now).at(0);};
  need(near(one(0).intensity,0)&&near(one(.5).intensity,.5f)&&near(one(1).intensity,1));
  auto s=one(2);need(near(s.intensity,1)&&near(s.emissive[0],1)&&near(s.modulate,2));
  need(near(one(4).intensity,.5f)&&near(one(5).intensity,0)&&near(one(5.25).intensity,0));
  need(near(float(c.clocks.at(7).t),5.25f));one(5.75);need(near(float(c.clocks.at(7).t),0)&&near(one(6.25).intensity,.5f));
  // KO keeps the last value between 1 and 3 s: a step from .9 to 2 keeps .9.
  n3e::AttachedCharacters::Clock k;n3e::AttachedCharacters::step(k,a,.9);n3e::AttachedCharacters::step(k,a,1.1);
  need(near(k.intensity,.9f)&&near(float(k.t),2));
  // Both slots advance the one clock (00569590's loop), so the pulse runs twice
  // as fast: after 0.5 s the first slot sees 0.75 and the second 1.0 (t 0.5 + 0.25 x 2).
  c.build(a);c.advance(8,{0,1},10);
  auto both=c.advance(8,{0,1},10.25);
  need(both.size()==2&&near(both[0].intensity,.25f)&&near(both[1].intensity,.5f));
  both=c.advance(8,{0,1},10.5);need(near(both[0].intensity,.75f)&&near(both[1].intensity,1)&&near(float(c.clocks.at(8).total),1));
  need(near(both[0].emissive[0],.75f)&&near(both[1].emissive[0],0)&&near(both[1].modulate,2)); // no emissive on the fairy
  // Once per frame when the package says so.
  a.per_attachment=false;c.build(a);c.advance(8,{0,1},10);both=c.advance(8,{0,1},10.5);
  need(near(both[0].intensity,.5f)&&near(both[1].intensity,.5f));a.per_attachment=true;
  // A wearer drawn with no attachment keeps its clock but does not advance it.
  c.build(a);c.advance(9,{0},0);c.advance(9,{0},.5);c.advance(9,{},1.5);need(near(float(c.clocks.at(9).t),.5f));
  need(near(c.advance(9,{0},1.75).at(0).intensity,.75f));
  // Pairs end when not drawn; a wearer not drawn loses its clock.
  need(c.draw(9,0)&&!c.draw(9,0));need(c.retire().empty());
  c.advance(9,{},2);auto gone=c.retire();need(gone.size()==1&&gone[0]==std::make_pair(uint64_t(9),size_t(0))&&c.clocks.contains(9));
  c.retire();need(!c.clocks.contains(9));
  // The wearer's pose state picks the attached clip: idle, walk, attack, death.
  int expect[]={0,1,2,3,1,1,0,0,0,0};
  for(int pose=0;pose<10;++pose)need(n3e::AttachedCharacters::clip_state(pose)==expect[pose]);
  std::cout<<"PASS attached characters: one per group (last key wins), 00569590's timer (rise 1 s, kept, fall to 0 at 5 s, restart past 5.5 s) on one clock per wearer advanced by each attachment (twice as fast with two), emissive only where flagged, modulate, clip per wearer state, pair and clock retirement\n";
}
// PQ-342: an N3E4 camera-distance rule (2233 00592900). A candidate is born
// every sample for 40 samples and lives 5 (birth j has records in samples
// j..j+4); the pool holds 3, near 10 m, far 30 m.
size_t thin_drawn(const n3e::EffectInstance&i,size_t frame){
  size_t n=0;
  for(const auto&b:i.clip->frames[frame])n+=n3e::effect_vertices(i,b,(frame+.5f)/30,{1,0,0},{0,1,0}).size()/54;
  return n;
}
void thinning(){
  n3e::EffectClip clip{false,30,{}};
  for(int j=0;j<60;++j){
    n3e::EffectBatch b{1,0,5,2,199,{}},other{1,1,5,2,199,{}};
    for(int k=std::max(0,j-4);k<=std::min(j,39);++k){
      b.records.insert(b.records.end(),{0,0,0,.1f,.1f,0,1,1,1,1,float(k)/30});
      other.records.insert(other.records.end(),{0,0,0,.1f,.1f,0,1,1,1,1,float(k)/30});
    }
    clip.frames.push_back({b,other});
  }
  clip.thinning.push_back(n3e::ParticleThinning{0,5,2,199,3,10,30});
  const auto&rule=clip.thinning[0];
  // The target: the pool within near (exclusive), trunc(pool x (far - d) / far)
  // from it on, 0 in the band around far, negative past it.
  need(n3e::thin_target(rule,9.99f)==3&&n3e::thin_target(rule,10)==2&&n3e::thin_target(rule,20)==1
       &&n3e::thin_target(rule,29)==0&&n3e::thin_target(rule,31)==0&&n3e::thin_target(rule,40)==-1);
  auto link=[&]{return n3e::EffectInstance{&clip,1,0,1,10,{},{{0,{0,0,0}}},-1,{},{},nullptr};};
  auto run=[&](n3e::EffectInstance&i,size_t from,size_t to,float d,std::vector<size_t>&out){
    for(size_t f=from;f<to;++f){n3e::thin_advance(i,(f+.5f)/30,d);out.push_back(thin_drawn(i,f));}
  };
  // Within near: the pool alone. Three taken, then one each time one dies.
  auto a=link();std::vector<size_t> full;run(a,0,60,5,full);
  // (Each count adds the other batch's 1, 2, 3, 4, then 5 candidates.)
  need((std::vector<size_t>(full.begin(),full.begin()+12)==std::vector<size_t>{1+1,2+2,3+3,3+4,3+5,2+5,2+5,2+5,3+5,3+5,3+5,2+5}));
  // At 20 m the target is 1: taken while at most 1 is alive, so 2 at a time.
  auto b=link();std::vector<size_t> mid;run(b,0,60,20,mid);
  need(*std::max_element(mid.begin(),mid.end())==2+5&&mid[0]==1+1&&mid[1]==2+2&&mid[2]==2+3);
  // In the band around far the target is 0: candidates are still taken (0 alive
  // is at most 0) but none is drawn, by either batch of the rule; the other
  // texture's batch is not the rule's and draws all its candidates.
  auto c=link();std::vector<size_t> band;run(c,0,10,29,band);
  need((band==std::vector<size_t>{0+1,0+2,0+3,0+4,0+5,0+5,0+5,0+5,0+5,0+5})&&c.thin[0].alive==1);
  // Past far nothing is taken; what was taken before is drawn till it dies.
  auto e=link();std::vector<size_t> away;run(e,0,10,5,away);away.clear();run(e,10,20,40,away);
  need(e.thin[0].target==-1&&away[0]==3+5&&away[4]==0+5&&away[9]==0+5);
  // A candidate born at or after the link's stop is never taken (and, as in
  // every batch, not drawn: the other's count falls with the rule's).
  auto g=link();g.stop=.19f;std::vector<size_t> stopped;run(g,0,12,5,stopped);
  need((std::vector<size_t>(stopped.begin(),stopped.begin()+8)==std::vector<size_t>{1+1,2+2,3+3,3+4,3+5,2+5,1+4,0+3})&&!g.thin[0].taken[6]);
  // Undecided (never advanced): a thinned batch draws nothing.
  auto h=link();need(thin_drawn(h,0)==1);
  // A handover (one 2233 tail copy, one live list): the older link stops at
  // 0.5 s and a new one starts; the new link counts the older one's taken
  // live candidates, so together they never draw more than the pool, and the
  // new link takes its first only as the older one's die.
  int group=0;
  auto older=link(),newer=link();older.stop=.5f;newer.start=.5;older.group=newer.group=&group;
  std::vector<const n3e::EffectInstance*> chain{&older,&newer};
  size_t most=0,first_new=0,at_handover=0;
  auto rule_drawn=[&](const n3e::EffectInstance&i,double now){
    float age=float(now-i.start);if(age<0||!i.thin.size())return size_t(0);
    auto f=size_t(age*30);if(f>=i.clip->frames.size())return size_t(0);
    return n3e::effect_vertices(i,i.clip->frames[f][0],age,{1,0,0},{0,1,0}).size()/54;};
  for(int f=0;f<36;++f){
    double now=(f+.5)/30;n3e::thin_links(chain,now,{5,0,0});
    size_t a=rule_drawn(older,now),b=rule_drawn(newer,now);most=std::max(most,a+b);
    if(f==15)at_handover=a;
    if(b&&!first_new)first_new=size_t(f);
  }
  need(most==3&&at_handover>=2&&first_new>15&&newer.thin[0].carried==0&&older.thin[0].alive==0);
  // A ruled clip a player effect plays (a skill's cast or target effect may
  // name any clip): the draw pass's advance decides it too, as its own chain,
  // so its particles are drawn.
  n3e::Effects ruled;ruled.clips.emplace("ruled",clip);
  n3e::EffectPlayer player;need(player.start(ruled,"ruled",4,{0,0,0},{},1,0));
  std::vector<const n3e::EffectInstance*> none;
  n3e::thin_all(player,none,(2+.5)/30,{5,0,0});
  const auto&cast=player.active.front();
  need(cast.thin.size()==1&&cast.thin[0].target==3&&rule_drawn(cast,(2+.5)/30)==3);
  std::cout<<"PASS N3E4 particle distance rule (PQ-342): the pool within near, trunc(pool x (far - d) / far) from near on (2 at near, 1 at 20 m, 0 near far, -1 past it), a candidate taken while the taken live ones are at most that and fewer than the pool, none drawn at 0, none taken past far while the taken ones live on, none after the stop, other batches untouched, and across a link handover the two links of a tail copy share the pool; a player effect playing a ruled clip is decided and drawn\n";
}
// The cross-language check (tests/ko_fx.py): `effects.bin --thin clip
// sample:distance ...` plays one link of the clip from sample 0, the camera at
// each distance from its sample on, and prints each sample's drawn births per
// rule.
int thin_run(int argc,char**argv){
  auto effects=n3e::load_effects(argv[1]);
  const auto&clip=effects.clips.at(argv[3]);
  std::vector<std::pair<size_t,float>> steps;
  for(int a=4;a<argc;++a){std::string s=argv[a];auto c=s.find(':');steps.push_back({std::stoul(s.substr(0,c)),std::stof(s.substr(c+1))});}
  n3e::EffectInstance i{&clip,1,0,1,10,{},{{0,{0,0,0}}},-1,{},{}};
  for(size_t f=0;f<clip.frames.size();++f){
    float d=0;for(const auto&[at,dist]:steps)if(f>=at)d=dist;
    float age=(f+.5f)/clip.rate;n3e::thin_advance(i,age,d);
    for(size_t k=0;k<clip.thinning.size();++k){
      std::cout<<"THIN rule="<<k<<" sample="<<f<<" target="<<i.thin[k].target<<" drawn=";
      const char*sep="";
      for(const auto&b:clip.frames[f]){
        if(!clip.thinning[k].applies(b))continue;
        auto one=b;one.records.clear();
        for(size_t n=0;n<b.records.size();n+=11){
          one.records.assign(b.records.begin()+n,b.records.begin()+n+11);
          if(!n3e::effect_vertices(i,one,age,{1,0,0},{0,1,0}).empty()){std::cout<<sep<<n3e::birth_sample(b.records[n+10],clip.rate);sep=",";}
        }
      }
      std::cout<<"\n";
    }
  }
  return 0;
}
// PQ-317: N3AT skeletal plugs (2233 CN3ChrTypePlug). The map is what the KO
// cook writes from 0042df00 for the Moradon player's clips (idle 0, walk 1,
// run 2, death 8 -> plug clip 0 looped; attack 87, ready 86 and every combat
// clip -> 1 once; the skill animations 16 and 17 -> 5 once), with the bow's
// plug clips 0, 1 and 5 in model slots 0, 1 and 2.
void skeletal_plugs(){
  using P=n3e::PlugClip;using S=n3e::AttachedCharacters::PlugState;
  n3e::Attachment bow;bow.key=5;bow.group=2;bow.flags=n3e::Attachment::PLUG;
  bow.clip_map={{P::STATE,0,0,false},{P::STATE,4,0,false},{P::STATE,1,0,false},{P::STATE,3,0,false},
                {P::STATE,2,1,true},{P::STATE,6,1,true},{P::COMBAT,0,1,true},{P::SKILL,17,2,true}};
  auto next=[&](uint32_t kind,uint32_t id,S s){return n3e::AttachedCharacters::plug_clip(bow,kind,id,s);};
  // It starts on slot 0, looped (00449d78), whatever the first clip has no row for.
  need((next(P::STATE,9,S{})==S{0,false})&&(next(P::STATE,0,S{})==S{0,false}));
  // A new slot restarts with the row's once flag; the same slot keeps playing,
  // and so does a clip with no row (00432760).
  S s=next(P::STATE,2,S{0,false});need((s==S{1,true}));
  need((next(P::STATE,6,s)==s)&&(next(P::COMBAT,0,s)==s)&&(next(P::STATE,7,s)==s)&&(next(P::COMBAT,5,s)==s));
  need((next(P::STATE,4,s)==S{0,false})&&(next(P::SKILL,17,s)==S{2,true})&&(next(P::SKILL,16,s)==s));
  // A row for the playing slot with another once flag does not restart it.
  n3e::Attachment odd=bow;odd.clip_map={{P::STATE,0,1,false}};
  need((n3e::AttachedCharacters::plug_clip(odd,P::STATE,0,S{1,true})==S{1,true}));
  // A plug neither takes nor advances the wearer's pulse: with the wing on
  // the same wearer the clock runs once per frame for the wing alone.
  n3e::Attachments a;a.per_attachment=true;a.rise=1;a.hold=3;a.fall=5;a.period=5.5f;a.color={1,1,1};
  n3e::Attachment wing;wing.key=2;wing.group=0;wing.flags=n3e::Attachment::EMISSIVE;wing.modulate=2;
  a.entries={wing,bow};
  n3e::AttachedCharacters c;c.build(a);
  c.advance(4,{0,1},0);auto shades=c.advance(4,{0,1},.5);
  need(shades.size()==2&&near(shades[0].intensity,.5f)&&near(shades[1].intensity,0)&&near(shades[1].emissive[0],0)&&near(shades[1].modulate,1));
  need(near(float(c.clocks.at(4).total),.5f)&&near(float(c.clocks.at(4).drawn),.5f));
  // With the plug alone the pulse stays still while the drawn time runs.
  c.build(a);c.advance(6,{1},0);c.advance(6,{1},.75);
  need(near(float(c.clocks.at(6).total),0)&&near(float(c.clocks.at(6).t),0)&&near(float(c.clocks.at(6).drawn),.75f));
  // The clip player: slot 0 loops on its own clock, a once slot holds its
  // end (0042e070), and the same slot is not restarted.
  n3e::Scene one{};one.scale={1,1,1};one.nodes.push_back(n3e::Node{-1,{0,0,0},{1,1,1},{0,0,0,1}});
  one.tracks.push_back(n3e::Track{0,0,{{0,{0,0,0,0}},{1,{1,0,0,0}}}});
  std::vector<n3e::Scene> scenes(4,one);std::array<n3e::Clip,4> clips{};for(auto&k:clips)k.duration=1;
  AnimationPlayer player;float t=-1;
  player.update(scenes,clips.data(),0,0,10,10,false,0);
  player.update(scenes,clips.data(),0,0,11.25,11.25,false,0);player.evaluate(scenes,clips.data(),11.25,&t);
  need(near(t,.25f)&&near(player.current[0].t[0],.25f));  // looped past one length, not restarted
  player.update(scenes,clips.data(),1,0,11.5,11.5,false,AnimationPlayer::HOLD);
  player.update(scenes,clips.data(),1,0,13,13,false,AnimationPlayer::HOLD);player.evaluate(scenes,clips.data(),13,&t);
  need(near(t,1)&&near(player.current[0].t[0],1));  // played once from 11.5, held at its end
  // The placement: rows to a column-major matrix, composed after the joint.
  const std::array<float,12> rows{0,-2,0,.1f, 2,0,0,.2f, 0,0,2,.3f};
  auto m=n3e::multiply(n3e::placement_matrix({1,0,0,1, 0,1,0,0, 0,0,1,0}),n3e::placement_matrix(rows));
  std::vector<float> v{1,0,0, 0,0,1, 0,0};n3e::transform_skinned(v,m,1);
  need(near(v[0],1.1f)&&near(v[1],2.2f)&&near(v[2],.3f)&&near(v[5],1));
  std::cout<<"PASS skeletal plugs: slot 0 looped first, a new slot restarts with its once flag, the same slot or an unmapped clip keeps playing, no pulse taken or advanced, once clips hold their end, the placement after the joint\n";
}
// PQ-379 (D-201): the caller's external draws (the world's alpha parts, as
// 1298's 00443090 queues them into the same list) join the effect pass's
// far-to-near order by their keys, each as a draw naming its index; ties keep
// the effect draws first, then the external ones in their order.
void external_keys(){
  n3e::EffectPlayer player;std::vector<const n3e::EffectInstance*> tails;
  std::vector<n3e::EffectMesh> meshes{{0,5,6,1,10,{0,0,0,0,0,1,1,1,1}},{0,5,6,1,5,{0,0,0,0,0,1,1,1,1}}};
  std::vector<float> keys{12,7,3,10};
  auto draws=n3e::effect_draws(player,tails,meshes,0,{0,0,0},{1,0,0},{0,1,0},1,keys);
  need(draws.size()==6);
  const size_t none=SIZE_MAX;
  std::vector<std::pair<const n3e::EffectMesh*,size_t>> order{{nullptr,0},{&meshes[0],none},{nullptr,3},{nullptr,1},{&meshes[1],none},{nullptr,2}};
  for(size_t i=0;i<draws.size();++i)need(draws[i].mesh==order[i].first&&draws[i].external==order[i].second);
  need(n3e::effect_draws(player,tails,meshes,0,{0,0,0},{1,0,0},{0,1,0},1).size()==2);
  std::cout<<"PASS PQ-379 external draws (world alpha parts) sort far to near with the effect draws, ties after them\n";
}
// PQ-423 (D-220): a ranged cast effect turns its records about its joint by
// the caster's facing, kept by tick from the headings (1298 00477590 sets a
// self FX's direction from the caster's +Z, 0048f700 turns its mesh from +Z
// to it); other instances ignore the headings. A model-space point (x, z)
// turns to (x cos h + z sin h, -x sin h + z cos h), as the joints do.
void cast_turn(){
  n3e::Effects effects;
  n3e::EffectBatch tri{0,0,5,6,199,{1,2,-3,0,0,1,1,1,1, 1,2,-3,0,0,1,1,1,1, 1,2,-3,0,0,1,1,1,1}};
  effects.clips.emplace("arrow",n3e::EffectClip{false,30,{{tri},{tri},{tri}}});
  n3e::EffectPlayer player;
  need(player.start(effects,"arrow",7,{10,0,10},{},1,0)&&player.start(effects,"arrow",7,{10,0,10},{},1,0));
  player.active[0].turn=true;player.active[0].joint=12;player.active[1].joint=12;
  const float h=0.5f;
  player.tick(.05,{{7,{0,0,0}}},{{{7,12},{4,5,6}}},{{7,h}});
  need(near(player.active[0].heading,h)&&player.active[1].heading==0);
  auto v=n3e::effect_vertices(player.active[0],tri,.05f,{1,0,0},{0,1,0});
  need(v.size()==27&&near(v[0],4+1*std::cos(h)-3*std::sin(h))&&near(v[1],7)&&near(v[2],6-1*std::sin(h)-3*std::cos(h)));
  auto still=n3e::effect_vertices(player.active[1],tri,.05f,{1,0,0},{0,1,0});
  need(near(still[0],5)&&near(still[1],7)&&near(still[2],3));   // not turned
  player.tick(.06,{},{{{7,12},{4,5,6}}},{{7,-1.f}});need(near(player.active[0].heading,-1));
  player.active[0].stop=.05f;need(n3e::effect_vertices(player.active[0],tri,.06f,{1,0,0},{0,1,0}).empty());
  std::cout<<"PASS PQ-423 cast effects: records turned about the joint by the caster's facing (kept each tick), others unturned, nothing after the stop\n";
}
// PQ-417 (D-222): a ranged flight. Its anchor leaves its start along the
// unit direction at its speed (1298 00477590, move type 0); every record
// turns by the shortest turn from the model's forward (n3e's -z, KO's +Z)
// to the direction, pitch included (0048f700), which for a level direction
// is the facing turn a cast effect uses; it ends where the ray first enters
// the target's box (0047a8d0 -> 0045c2c0), or at its launch distance when
// the ray misses the box, and is gone once it has ended.
void flights(){
  auto mul=[](const std::array<float,9>&m,n3e::V v){return n3e::V{m[0]*v[0]+m[1]*v[1]+m[2]*v[2],m[3]*v[0]+m[4]*v[1]+m[5]*v[2],m[6]*v[0]+m[7]*v[1]+m[8]*v[2]};};
  auto unit=[](n3e::V v){float l=std::sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]);return n3e::V{v[0]/l,v[1]/l,v[2]/l};};
  for(n3e::V d:{n3e::V{0,0,-1},n3e::V{0,0,1},n3e::V{1,0,0},unit({1,-.5f,-2}),unit({-3,2,1}),n3e::V{0,1,0},n3e::V{0,-1,0},unit({1e-8f,0,1})}){
    auto m=n3e::flight_rotation(d);auto f=mul(m,{0,0,-1});
    for(int k=0;k<3;++k)need(near(f[k],d[k]));                                  // the forward goes to the direction
    for(int a=0;a<3;++a)for(int b=0;b<3;++b){float dot=m[a]*m[b]+m[3+a]*m[3+b]+m[6+a]*m[6+b];need(near(dot,a==b?1.f:0.f));}
    float det=m[0]*(m[4]*m[8]-m[5]*m[7])-m[1]*(m[3]*m[8]-m[5]*m[6])+m[2]*(m[3]*m[7]-m[4]*m[6]);need(near(det,1));
    auto axis=mul(m,{d[1],-d[0],0});                                              // the turn's axis stays put
    if(std::hypot(d[0],d[1])>1e-3f)for(int k=0;k<3;++k)need(near(axis[k],d[1]*(k==0)-d[0]*(k==1)));
  }
  auto opposite=n3e::flight_rotation({0,0,1});need(near(opposite[0],-1)&&near(opposite[4],1)&&near(opposite[8],-1));  // about y by pi
  for(float h:{.3f,2.5f,-1.2f}){                                                  // level: the cast effect's facing turn
    n3e::EffectInstance cast{};cast.turn=true;cast.heading=h;cast.scale=1;
    n3e::EffectInstance fly{};fly.scale=1;fly.flight=n3e::EffectInstance::Flight{};fly.flight->rotation=n3e::flight_rotation({-std::sin(h),0,-std::cos(h)});
    const float record[3]={.3f,.7f,-.9f};auto a=cast.turned(record),b=fly.turned(record);
    for(int k=0;k<3;++k)need(near(a[k],b[k]));
  }
  // A box 1 m each way about (0, 1, -20): from (0, 1, 0) along -z the ray
  // enters it at 19 m; from inside, at 0; along +x it misses.
  // The corner order of pick_attack.h's box_corners (KO's 004482c0).
  auto corners=[](n3e::V lo,n3e::V hi){return std::array<n3e::V,8>{{{lo[0],hi[1],lo[2]},{hi[0],hi[1],lo[2]},{hi[0],lo[1],lo[2]},{lo[0],lo[1],lo[2]},
                                                                    {hi[0],hi[1],hi[2]},{lo[0],hi[1],hi[2]},{lo[0],lo[1],hi[2]},{hi[0],lo[1],hi[2]}}};};
  auto box=corners({-1,0,-21},{1,2,-19});
  need(near(n3e::ray_box_entry({0,1,0},{0,0,-1},box),19)&&near(n3e::ray_box_entry({0,1,-20},{0,0,-1},box),0));
  need(n3e::ray_box_entry({0,1,0},{1,0,0},box)<0&&n3e::ray_box_entry({0,1,0},{0,0,1},box)<0);
  auto pitched=unit({0,-1,-20});need(near(n3e::ray_box_entry({0,2,0},pitched,box),19*std::sqrt(401.f)/20,1e-3f));
  n3e::Effects effects;
  n3e::EffectBatch tri{0,0,5,6,199,{0,0,-.9f,0,0,1,1,1,1, .02f,0,0,0,0,1,1,1,1, -.02f,0,0,0,0,1,1,1,1}};
  effects.clips.emplace("arrow",n3e::EffectClip{false,30,std::vector<std::vector<n3e::EffectBatch>>(300,{tri})});
  n3e::EffectPlayer player;need(player.start(effects,"arrow",7,{0,1,0},{},1,10));
  auto&i=player.active.back();i.flight=n3e::EffectInstance::Flight{{0,1,0},{0,0,-1},77,-1,20,n3e::flight_rotation({0,0,-1}),9,"",-1};
  auto at=i.position(.1f);need(near(at[2],-7.7f)&&near(at[1],1));               // start + dir x speed x age
  player.tick(10.1,{{7,{50,50,50}}});need(near(player.active.back().position(.1f)[2],-7.7f));  // the actor's moves do not move it
  bool on_box=false;
  need(!n3e::flight_arrive(player.active.back(),10.2,&box,on_box)&&on_box);        // 15.4 m: not yet in the box
  need(n3e::flight_arrive(player.active.back(),10.25,&box,on_box)&&on_box);         // 19.25 m: entered it at 19
  auto&f=player.active.back();need(near(f.flight->reach,19)&&near(f.stop,19.f/77)&&near(f.position(1)[2],-19));
  need(n3e::effect_vertices(f,tri,19.f/77+.001f,{1,0,0},{0,1,0}).empty());
  need(!n3e::flight_arrive(f,10.3,&box,on_box));                                   // once
  player.tick(10.26,{});need(player.active.empty());                               // gone once ended
  need(player.start(effects,"arrow",7,{0,1,0},{},1,10));                           // the target moved off the line: the launch distance
  player.active.back().flight=n3e::EffectInstance::Flight{{0,1,0},{1,0,0},77,-1,20,n3e::flight_rotation({1,0,0}),9,"",-1};
  need(!n3e::flight_arrive(player.active.back(),10.25,&box,on_box)&&!on_box);
  need(n3e::flight_arrive(player.active.back(),10.27,&box,on_box)&&!on_box&&near(player.active.back().flight->reach,20));
  need(player.start(effects,"arrow",7,{0,1,0},{},1,10));                           // no box drawn: the launch distance
  player.active.back().flight=n3e::EffectInstance::Flight{{0,1,0},{0,0,-1},77,-1,20,n3e::flight_rotation({0,0,-1}),9,"",-1};
  need(n3e::flight_arrive(player.active.back(),10.27,nullptr,on_box)&&near(player.active.back().flight->reach,20));
  // Drawn: a record turned to a pitched direction at its anchor.
  need(player.start(effects,"arrow",7,{0,1,0},{},1,10));
  auto d=unit({1,-1,-4});auto&g=player.active.back();g.flight=n3e::EffectInstance::Flight{{0,2,0},d,10,-1,30,n3e::flight_rotation(d),9,"",-1};
  auto v=n3e::effect_vertices(g,tri,.5f,{1,0,0},{0,1,0});
  need(v.size()==27);for(int k=0;k<3;++k)need(near(v[k],(k==1?2.f:0.f)+d[k]*5+d[k]*.9f,1e-4f));  // the tip .9 m ahead along the direction
  std::cout<<"PASS PQ-417 flights: the anchor moves from its start along the direction at the speed; records turn from -z to the direction "
             "(pitch included; the facing turn when level, about y by pi when opposite); it ends where the ray enters the target's box, "
             "else at the launch distance, once, and is gone after\n";
}
int main(int argc,char**argv){try{
  if(argc==2){auto effects=n3e::load_effects(argv[1]);std::cout<<"PASS effects clips="<<effects.clips.size()<<" textures="<<effects.textures.size()<<"\n";return 0;}
  if(argc>=4&&std::string(argv[2])=="--thin")return thin_run(argc,argv);
  n3e::Effects effects;
  n3e::EffectBatch quad{1,0,5,6,199,{0,1,0,2,2,0,1,1,1,1,0}};
  effects.clips.emplace("sample",n3e::EffectClip{true,30,{{quad},{quad},{quad}}});
  n3e::EffectPlayer player;
  need(!player.start(effects,"missing",1,{},{},1,10));
  need(player.start(effects,"sample",1,{3,0,4},{},2,10));
  player.tick(10.02,{{1,{7,0,4}}});
  auto vertices=n3e::effect_vertices(player.active.front(),quad,.02,{1,0,0},{0,1,0});
  need(vertices.size()==54&&vertices[0]==1&&vertices[1]==4&&vertices[2]==4); // birth-anchored, scaled
  quad.records[10]=-1;
  vertices=n3e::effect_vertices(player.active.front(),quad,.02,{1,0,0},{0,1,0});
  need(std::abs(vertices[0]-5)<.001); // following quads use current anchor
  player.active.front().stop=.01;
  need(n3e::effect_vertices(player.active.front(),quad,.02,{1,0,0},{0,1,0}).empty());
  quad.records[10]=0;
  need(!n3e::effect_vertices(player.active.front(),quad,.02,{1,0,0},{0,1,0}).empty()); // stop lets old particles retire
  for(int i=0;i<100;++i)player.start(effects,"sample",1,{},{},1,10);
  need(player.active.size()==64);
  player.tick(11,{});need(player.active.empty());
  std::cout<<"PASS effect birth anchors, scale, stop tails and bounded lifetime/instances\n";
  appearance(effects);
  long_tail(effects);
  alpha_keys(effects);
  external_keys();
  options();
  glow();
  attached();
  skeletal_plugs();
  thinning();
  cast_turn();
  flights();
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
