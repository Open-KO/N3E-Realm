#include "assets/world_lod.h"
#include "assets/character_lod.h"
#include <iostream>
#include <stdexcept>
using namespace n3e;
void check(bool ok) { if(!ok) throw std::runtime_error("LOD assertion"); }
int main(int argc,char **argv) {
  try {
    if(argc==2) {
      Release release;release.root=argv[1];release.render_detail=true;
      Scene skeleton;skeleton.scale={1,1,1};skeleton.attachment=0;
      Node node{};node.parent=-1;node.s={1,1,1};node.q={0,0,0,1};
      skeleton.nodes.push_back(node);Joint joint{};joint.node=0;
      for(int i=0;i<4;++i)joint.inverse[i*5]=1;
      skeleton.joints.push_back(joint);
      auto detail=load_render_detail(release,skeleton);
      check(detail.levels.size()==4 && detail.attachments.size()==1);
      check(detail.textures[0][0].pixels[0]==255 && detail.textures[0][1].pixels[1]==255);
      auto a=character_lod::initial(detail),b=character_lod::initial(detail);
      character_lod::update(a[0],0);
      check(a[0].part.progressive.vertices==4 && b[0].part.progressive.vertices==3);
      character_lod::update(a[0],101);
      check(a[0].part.progressive.vertices==3 && a[0].indices==b[0].indices);
      for(auto &level:detail.levels)check(level.scene.skin(skeleton.nodes).size()==48);
      std::cout<<"PASS detail native mips, four skinned levels and independent reversible attachments\n";
      return 0;
    }
    if(argc==3) {
      auto world=load_world(load_release(argv[1]));
      for(auto &chunk:world.chunks) for(auto &part:chunk.parts) if(part.kind==1) {
        // Exercise approach, retreat, exact endpoints and reappearance. Output
        // topology hashes for comparison with an independent Python oracle.
        std::vector<float> metrics{0.f,400.f,100.f,50.f,200.f,0.f};
        const auto &controls=part.progressive.controls;
        for(size_t j=0;j<controls.size();++j) {
          float d=controls[j].distance;
          metrics.insert(metrics.end(),{std::nextafter(d,-INFINITY),d,std::nextafter(d,INFINITY)});
          if(j) for(int k=1;k<4;++k)
            metrics.push_back(float(double(controls[j-1].distance)+(double(d)-controls[j-1].distance)*k/4));
        }
        auto reverse=metrics;
        metrics.insert(metrics.end(),reverse.rbegin(),reverse.rend());
        for(float metric: metrics) {
          if(auto target=world_lod::budget(part.progressive,metric))
            world_lod::refine(part,chunk.indices,*target);
          uint64_t hash=1469598103934665603ull;
          for(uint32_t i=0;i<part.progressive.indices;++i) {
            check(chunk.indices[part.levels[0].first+i]>=part.progressive.base &&
                  chunk.indices[part.levels[0].first+i]<part.progressive.base+part.progressive.vertices);
            hash=(hash^(chunk.indices[part.levels[0].first+i]-part.progressive.base))*1099511628211ull;
          }
          std::cout<<part.progressive.vertices<<" "<<part.progressive.indices<<" "<<hash<<"\n";
        }
      }
      return 0;
    }
    ProgressiveMesh p;
    RenderDetail detail;detail.thresholds={{{6,18,32,128},{4,12,21,85},{2.66f,8,14.21f,56.8f},{1.77f,5.33f,9.48f,37.9f}}};
    detail.workload={30,60,100};
    for(unsigned row=0;row<4;++row)for(int i=0;i<4;++i){
      float threshold=detail.thresholds[row][i];
      check(character_lod::level(detail,std::nextafter(threshold,-INFINITY),row)==i);
      check(character_lod::level(detail,threshold,row)==(i==3?-1:i+1));
    }
    for(unsigned cost:{0u,29u,30u,59u,60u,99u,100u,1000u})
      check(character_lod::row(detail,cost)==unsigned(cost>=30)+unsigned(cost>=60)+unsigned(cost>=100));
    p.controls={{10,24},{110,6}};
    check(world_lod::budget(p,35)==20); // 24 + trunc(-4.5), NOT trunc(19.5)
    check(world_lod::budget(p,10)==24);
    check(world_lod::budget(p,0)==24);
    check(!world_lod::budget(p,110));
    check(world_lod::budget(p,111)==6);
    p.controls={{0,7}};
    check(!world_lod::budget(p,0));check(world_lod::budget(p,1)==7);
    WorldPart part{}; part.levels={{0,0,9}};
    auto &q=part.progressive;
    q.vertices=3;q.indices=3;q.maximum=5;
    q.splits={{3,1,1,0,0,0},{3,1,1,1,1,0}};q.edits={1,4};
    std::vector<uint32_t> ix={0,0,2,0,0,2,0,1,2};
    check(world_lod::refine(part,ix,4));
    check(q.vertices==5 && q.indices==9 && ix[1]==3 && ix[4]==4);
    check(world_lod::refine(part,ix,3));
    check(q.vertices==3 && q.indices==3 && ix[1]==0 && ix[4]==0);
    check(!world_lod::refine(part,ix,3));
    // A zero-vertex split must not run when target == current.
    q.splits.insert(q.splits.begin(),{0,0,0,0,1,0});
    check(!world_lod::refine(part,ix,3));
    TerrainDetail t{{-256,0,256},32,3.f/512,.6f,2,3,16};
    V eye{-256,0,256};
    check(world_lod::terrain_level(t,2,0,eye,256)==1);
    check(world_lod::terrain_level(t,3,0,eye,256)==2);
    check(world_lod::terrain_level(t,6,0,eye,256)==3);
    part.patch_x=3;part.patch_z=0;
    check(world_lod::terrain_variant(t,part,eye,256)==2); // level 2, refined left edge
    part.patch_x=6;
    check(world_lod::terrain_variant(t,part,eye,256)==32); // level 3, all midpoints
    auto visible=[](V c,float radius,bool radial) {
      return world_lod::sphere_visible(c,radius,{0,0,0},{1,0,0},{0,1,0},{0,0,1},.05f,100,1,1,radial);
    };
    check(visible({0,0,-50},1,true));
    check(!visible({0,0,5},1,true));
    check(visible({90,0,-90},1,false));
    check(!visible({90,0,-90},1,true)); // radial gate differs from depth alone
    check(visible({51,0,-50},1,true));
    check(!visible({52,0,-50},1,true)); // normalized side-plane sphere radius
    std::cout<<"PASS world LOD arithmetic, endpoints, grouped split/collapse and terrain selection\n";
    // PQ-394 (D-212): a texture sequence restarts at 0 when it reaches the
    // count, dropping the remainder (1298's 004429b0), where a wrap would keep
    // it; the frame is the index's integer part; the frame time is bounded.
    check(world_lod::sequence_advance(0,.05f,10,16)==.5f);
    check(world_lod::sequence_advance(15.5f,.1f,10,16)==0);       // 16.5 -> 0, not 0.5
    check(world_lod::sequence_advance(15.f,.1f,10,16)==0);        // exactly the count -> 0
    check(world_lod::sequence_advance(14.5f,.1f,10,16)==15.5f);
    check(world_lod::sequence_frame(15.99f,16)==15 && world_lod::sequence_frame(0.99f,16)==0);
    {
      // 16 frames at 10 fps with a 1/60 s frame: after each reset the cycle
      // starts again at frame 0, and a frame is held for 6 advances, 5 or 7
      // where the float32 sum crosses a frame early or late. The counts are
      // a float32 replay's (Python struct, PQ-394 evidence).
      float index=0; uint32_t resets=0, changes=0, last=0, held=0, shortest=1000, longest=0;
      for(int i=0;i<1000;++i) {
        float next=world_lod::sequence_advance(index,1.f/60,10,16);
        if(next<index) { ++resets; check(next==0); }
        auto k=world_lod::sequence_frame(next,16);
        if(k!=last) { ++changes; if(i>100){shortest=std::min(shortest,held);longest=std::max(longest,held);} held=0; last=k; }
        ++held; index=next;
      }
      check(resets==10 && changes==166 && shortest==5 && longest==7);
    }
    check(world_lod::sequence_seconds(0)==1.f/30 && world_lod::sequence_seconds(.001)==1.f/30 &&
          world_lod::sequence_seconds(1.0)==1.f/30 && world_lod::sequence_seconds(5)==1.f/30 &&
          world_lod::sequence_seconds(.02)==.02f && world_lod::sequence_seconds(.999)==.999f);
    std::cout<<"PASS world texture sequences (D-212): restart at 0 dropping the remainder, integer frames, "
               "bounded frame time\n";
  }catch(const std::exception &e){std::cerr<<e.what()<<"\n";return 1;}
}
