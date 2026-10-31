#include "render/target_marker.h"
#include "render/effects.h"
#include <iostream>
#include <stdexcept>
void check(bool b){if(!b)throw std::runtime_error("target marker regression");}
bool near(float a,float b){return std::abs(a-b)<.0001f;}
int main(){try{
  n3e::TargetMarker m{2,1.3f,.1f,{{{1,2},{2,3}}},{}};
  n3e::TargetMarkerPart p{};p.mode=0;
  p.vertices={{{-.5f,0,-.5f,0,1,0,0,0}},{{.5f,0,-.5f,0,1,0,1,0}},{{0,0,.5f,0,1,0,0,1}}};p.indices={0,1,2};
  // Synthetic sloped terrain y=x+2z, not a flat fallback at the actor's y.
  n3e::Scene ground;ground.collision=n3e::Collision(std::vector<n3e::V>{{-20,-60,-20},{20,-20,-20},{20,60,20},{-20,-60,-20},{20,60,20},{-20,20,20}});
  auto v=n3e::target_marker_vertices(m,p,true,1,{1,99,2},{0,0,10},ground);
  check(v.size()==24&&near(v[0],-1)&&near(v[2],0));
  check(near(v[1],(1-1.95f)+2*(2-1.95f)+.1f));
  p.mode=1;p.pivot={0,1,0};p.vertices[0]={1,0,0,0,0,1,0,0};
  auto front=n3e::target_marker_vertices(m,p,false,1,{0,5,0},{0,20,10},ground);
  auto side=n3e::target_marker_vertices(m,p,false,1,{0,5,0},{10,20,0},ground);
  auto back=n3e::target_marker_vertices(m,p,false,1,{0,5,0},{0,20,-10},ground);
  check(near(front[0],2)&&near(front[2],0)&&near(front[1],7.6f));
  check(near(side[0],0)&&near(side[2],-2)&&near(side[3],.5f));
  check(near(back[0],-2)&&near(back[2],0)&&near(back[5],-.5f));
  // PQ-296: an actor drawn at scale s gets the symbol at s times its profile
  // on both axes (005c4e20 -> 0045a1d0, 00459ff0: radius and height times
  // +0x90): the footprint, the upright height and the ground sample spacing.
  auto size=n3e::target_marker_size(m,true,2.5f);check(near(size[0],2*2*2.5f)&&near(size[1],1.3f*3*2.5f));
  auto big=n3e::target_marker_vertices(m,p,false,2.5f,{0,5,0},{0,20,10},ground);
  check(near(big[0],2*2.5f)&&near(big[2],0)&&near(big[1],5+2.6f*2.5f)&&near(big[5],1/5.f));
  p.mode=0;p.pivot={0,0,0};
  auto ring=n3e::target_marker_vertices(m,p,true,1,{1,99,2},{0,0,10},ground),wide=n3e::target_marker_vertices(m,p,true,2,{1,99,2},{0,0,10},ground);
  for(int k=0;k<3;++k){check(near(wide[k*8]-1,2*(ring[k*8]-1))&&near(wide[k*8+2]-2,2*(ring[k*8+2]-2)));
    // Ground samples at the scaled height spacing (x*vertical, z*vertical).
    float x=p.vertices[k][0]*1.3f*3*2,z=p.vertices[k][2]*1.3f*3*2;check(near(wide[k*8+1],ground.ground_height(1+x,2+z)+.1f));}
  ground.collision={};check(n3e::target_marker_vertices(m,p,true,1,{0,0,0},{0,0,1},ground).empty());
  // PQ-235 ground source: an N3W2 world's marker follows the native heightfield
  // without the object triangles; without one it is refused. An N3W1 world
  // keeps its terrain parts; no world keeps the collision surface.
  n3e::Collision::Terrain t;t.width=t.depth=3;t.ox=t.oz=-4;t.spacing=4;t.heights={0,0,0,0,2,0,0,0,0};
  std::vector<n3e::V> roof{{-3,9,-3},{-3,9,3},{3,9,-3}};
  n3e::Collision mixed(t,roof),soup(roof);
  check(near(mixed.ground_height(-1,-1),9));
  auto streamed=n3e::target_marker_ground(mixed,true,nullptr);
  check(streamed.has_terrain()&&streamed.triangles()==8&&near(streamed.ground_height(-1,-1),1)&&near(streamed.ground_height(0,0),2));
  bool refused=false;try{n3e::target_marker_ground(soup,true,nullptr);}catch(const std::runtime_error&){refused=true;}check(refused);
  n3e::WorldMesh world;world.chunks.emplace_back();auto&chunk=world.chunks.back();
  for(auto v:std::vector<n3e::V>{{-4,1,-4},{-4,1,4},{4,1,-4},{9,7,9},{9,7,10},{10,7,9}}){std::vector<float> f(n3e::WORLD_FLOATS,0);f[0]=v[0];f[1]=v[1];f[2]=v[2];chunk.vertices.insert(chunk.vertices.end(),f.begin(),f.end());}
  chunk.indices={0,1,2,3,4,5};
  n3e::WorldPart terrain{};terrain.kind=2;terrain.levels={{0,0,3},{1,0,0}};n3e::WorldPart object{};object.levels={{0,3,3}};
  chunk.parts={terrain,object};
  auto parts=n3e::target_marker_ground(mixed,false,&world);
  check(parts.triangles()==1&&near(parts.ground_height(-2,-2),1)&&!std::isfinite(parts.ground_height(9.2f,9.2f)));
  check(n3e::target_marker_ground(mixed,false,nullptr).triangles()==mixed.triangles());
  // PQ-380: a part's alpha-list key is the linear eye distance to the part
  // matrix's translation (00443090): the position plus the pivot at the
  // symbol's scale (X/Z horizontal, Y vertical), whatever the part's mode
  // and the ground under it; and it sorts with the effect draws (one list).
  {
    n3e::TargetMarkerPart arrow{};arrow.mode=1;arrow.pivot={.5f,1,-.25f};
    n3e::TargetMarkerPart ring{};ring.mode=0;ring.pivot={.5f,1,-.25f};
    // NPC at scale 2: horizontal 2 x 2 x 2 = 8, vertical 1.3 x 3 x 2 = 7.8.
    n3e::V at{1,99,2},eye{4,90,-30};
    n3e::V point{1+.5f*8,99+7.8f,2-.25f*8};
    float want=n3e::eye_distance(point,eye);
    check(near(n3e::target_marker_key(m,arrow,true,2,at,eye),want)&&near(n3e::target_marker_key(m,ring,true,2,at,eye),want));
    check(std::abs(n3e::target_marker_key(m,arrow,true,2,at,eye)-want*want)>1); // linear, not squared
    // The player profile scales by its own bounds (1, 2): horizontal 2 x 1, vertical 1.3 x 2.
    check(near(n3e::target_marker_key(m,arrow,false,1,{0,0,0},{0,0,0}),std::sqrt(1*1+2.6f*2.6f+.5f*.5f)));
    // An effect 3 m behind the part and one 3 m in front: the part draws
    // between them, far to near, as an external draw of the pass.
    n3e::TargetMarkerPart upright{};upright.mode=1;upright.pivot={0,.5f,0};
    n3e::TargetMarker unit{2,1.3f,.1f,{{{1,1},{2,4/1.3f}}},{}};
    float key=n3e::target_marker_key(unit,upright,true,1,{0,0,0},{0,2,10});check(near(key,10));
    std::vector<n3e::EffectMesh> meshes{{0,5,6,0x101,13,{0}},{0,5,6,0x101,7,{0}}};
    n3e::EffectPlayer none;std::vector<const n3e::EffectInstance*> links;std::vector<float> keys{key};
    auto draws=n3e::effect_draws(none,links,meshes,0,{0,2,10},{1,0,0},{0,1,0},1,keys);
    check(draws.size()==3&&draws[0].mesh==&meshes[0]&&draws[1].external==0&&draws[2].mesh==&meshes[1]);
  }
  std::cout<<"PASS PQ-380 target marker part keys: linear eye distance to the scaled pivot, sorted between the effects behind and in front\n";
  std::cout<<"PASS target marker ground: N3W2 native heightfield without objects, refusal without one, N3W1 terrain parts, collision without a world\n";
  std::cout<<"PASS target terrain lift/sample spacing, model bounds, camera quadrants, upright anchor and absent surface\n";
  std::cout<<"PASS target marker at the actor's drawn scale: footprint, upright height, normals and ground sample spacing x2 and x2.5\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
