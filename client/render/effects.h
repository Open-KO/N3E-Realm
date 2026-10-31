#pragma once
#include "assets/assets.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <deque>
#include <map>
#include <optional>

namespace n3e {
// PQ-342: one N3E4 rule's state on a tail link (ParticleThinning). The 2233
// particle tick (00592900) sets its live count each tick from the camera's
// distance to the bundle and emits (00592740) only while the live particles
// are at most that count, from a pool of `count` (005901b0, 00590570,
// 005915e0); live ones are never cut, and the render (0058e880) draws none at
// a count of 0. The cook writes every emission as a candidate; this keeps which
// ones the link took.
struct ThinState {
  size_t next=0;          // the first sample not yet decided
  uint32_t alive=0;       // taken candidates with a record in sample next - 1
  int64_t target=0;       // the live count at the last advance
  float distance=0;       // and the camera distance it came from
  uint32_t carried=0;     // the earlier links' taken live ones it counted
  std::vector<uint8_t> taken; // per birth sample
};
// 00592900 (assembly 005929ac-00592a37): the count within `near`, else
// trunc(count x (far - d) / far), negative past far.
inline int64_t thin_target(const ParticleThinning&r,float distance){
  if(!std::isfinite(distance))distance=1e9f;
  if(distance<r.near)return r.count;
  return int64_t((double(r.far)-distance)/r.far*r.count);
}
inline long birth_sample(float birth,uint32_t rate){return std::lround(double(birth)*rate);}
struct EffectInstance {
  const EffectClip* clip;
  uint64_t actor;
  double start;
  float scale=1,stop=10;
  V offset{};
  std::deque<std::pair<float,V>> positions;
  int joint=-1;
  std::string tag;
  // PQ-342: one per clip rule; kept by the draw pass, which decides each
  // sample's candidates as it reaches it (thin_advance).
  mutable std::vector<ThinState> thin;
  // PQ-342: the links of one 2233 tail copy share its pool and live list:
  // links with the same group count each other's taken live particles.
  const void*group=nullptr;
  // PQ-376 (D-200): each camera-facing quad sorts on its own (quad_sort_point),
  // as 1298's alpha particle part queues each spark (004840b0); otherwise the
  // instance's batches sort by its newest point.
  bool quad_keys=false;
  // PQ-423 (D-220): a ranged cast effect turns every record about its anchor
  // by the actor's drawn facing (`heading`, kept by tick), as 1298's self FX
  // turns its parts from +Z to the caster's +Z (00477590, 0048f700).
  bool turn=false;
  float heading=0;
  // PQ-417 (D-222): a ranged flight (1298's flying FX, move type 0: the
  // tick 00477590 moves the bundle by its direction x frame time x its
  // velocity, and 0048f700 turns each part from +Z to the direction, pitch
  // included). Its anchor leaves `from` along the unit `dir` at `speed` and
  // halts at `reach` (negative: not yet arrived); every record turns by
  // `rotation` (row-major), the shortest turn from the model's forward (-z,
  // KO's +Z) to `dir`. The flight ends at `stop`, when it arrives.
  // PQ-445: `request` is the shot's request sequence (0: none); `pending`
  // marks the local archer's own flight launched at its predicted release
  // and not yet confirmed by the server's release event.
  struct Flight {V from{},dir{0,0,-1};float speed=0,reach=-1,launch=0;std::array<float,9> rotation{1,0,0,0,1,0,0,0,1};
                 uint64_t target=0;std::string hit;int hit_joint=-1;uint64_t request=0;bool pending=false;};
  std::optional<Flight> flight;
  V turned(const float*record) const {
    if(flight){const auto&m=flight->rotation;float x=record[0]*scale,y=record[1]*scale,z=record[2]*scale;
      return {m[0]*x+m[1]*y+m[2]*z,m[3]*x+m[4]*y+m[5]*z,m[6]*x+m[7]*y+m[8]*z};}
    if(!turn)return {record[0]*scale,record[1]*scale,record[2]*scale};
    float c=std::cos(heading),s=std::sin(heading),x=record[0]*scale,z=record[2]*scale;
    return {x*c+z*s,record[1]*scale,-x*s+z*c};
  }
  V position(float age) const {
    if(flight){float d=std::max(0.f,age)*flight->speed;if(flight->reach>=0)d=std::min(d,flight->reach);
      return {flight->from[0]+flight->dir[0]*d,flight->from[1]+flight->dir[1]*d,flight->from[2]+flight->dir[2]*d};}
    auto it=std::lower_bound(positions.begin(),positions.end(),age,[](const auto&p,float a){return p.first<a;});
    if(it==positions.begin())return it->second;
    if(it==positions.end())return positions.back().second;
    const auto&before=*std::prev(it);float blend=(age-before.first)/(it->first-before.first);
    V result{};for(unsigned k=0;k<3;++k)result[k]=before.second[k]+(it->second[k]-before.second[k])*blend;
    return result;
  }
};
// PQ-417 (D-222): the shortest turn from the model's forward (n3e's -z,
// KO's +Z after the cook's z reflection) to the unit `dir`, row-major: 1298's
// 0048f700 turns a part from +Z to the bundle direction about their cross
// product, about (0, 1, 0) when that is zero (by pi when they are opposite).
// Rodrigues: R v = v cos t + (k x v) sin t + k (k . v)(1 - cos t).
inline std::array<float,9> flight_rotation(V dir){
  float c=-dir[2],kx=dir[1],ky=-dir[0],s=std::sqrt(kx*kx+ky*ky); // (0, 0, -1) x dir
  if(s<1e-6f)return c>0?std::array<float,9>{1,0,0,0,1,0,0,0,1}:std::array<float,9>{-1,0,0,0,1,0,0,0,-1};
  kx/=s;ky/=s;float t=1-c;
  return {c+kx*kx*t, kx*ky*t, ky*s,
          kx*ky*t, c+ky*ky*t, -kx*s,
          -ky*s, kx*s, c};
}
// PQ-417 (D-222): the distance along the ray from `o` (unit `d`) to where it
// first enters a box of eight corners (pick_attack.h's order and KO's twelve
// outward triangles, 004482c0), or a negative value when it does not; from
// inside the box the entry is 0. Each front face is tested as 004495c0 does.
inline float ray_box_entry(V o,V d,const std::array<V,8>&box){
  static constexpr uint8_t tris[36]={0,1,2,0,2,3,1,4,7,1,7,2,4,5,6,4,6,7,5,0,3,5,3,6,5,4,1,5,1,0,3,2,7,3,7,6};
  auto sub=[](V a,V b){return V{a[0]-b[0],a[1]-b[1],a[2]-b[2]};};
  auto dot=[](V a,V b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];};
  auto cross=[](V a,V b){return V{a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};};
  float best=-1;bool inside=true;
  for(size_t i=0;i<36;i+=3){
    V a=box[tris[i]],b=box[tris[i+1]],c=box[tris[i+2]],e1=sub(b,a),e2=sub(c,a),n=cross(e1,e2);
    if(dot(n,sub(o,a))>0)inside=false;   // in front of an outward face
    if(dot(n,d)>-1e-4f)continue;
    V p=cross(d,e2);float det=dot(e1,p);if(det<1e-4f)continue;
    V t=sub(o,a);float u=dot(t,p);if(u<0||u>det)continue;
    V q=cross(t,e1);float v=dot(d,q);if(v<0||u+v>det)continue;
    float at=dot(e2,q)/det;if(at>=0&&(best<0||at<best))best=at;
  }
  return inside?0:best;
}
// PQ-417 (D-222): whether flight `i` has arrived by `now` against the
// target's current box (null: none drawn); if so it halts there, ends, and
// `on_box` says whether it met the box. It arrives where the ray from its
// start first enters the box, or, when the ray does not meet the box, at
// its launch distance (1298's 0047a8d0 stops a moving bundle on its
// collision with the actor's box, 0045c2c0).
inline bool flight_arrive(EffectInstance&i,double now,const std::array<V,8>*box,bool&on_box){
  if(!i.flight||i.flight->reach>=0)return false;
  auto&f=*i.flight;float travelled=float(std::max(0.,now-i.start))*f.speed,at=-1;on_box=false;
  if(box)if(float t=ray_box_entry(f.from,f.dir,*box);t>=0){on_box=true;if(travelled>=t)at=t;}
  if(!on_box&&travelled>=f.launch)at=f.launch;
  if(at<0)return false;
  f.reach=at;i.stop=std::min(i.stop,at/f.speed);return true;
}
struct EffectPlayer {
  std::deque<EffectInstance> active;
  bool start(const Effects&data,const std::string&key,uint64_t actor,V position,V offset,float scale,double now,float stop=10){
    auto it=data.clips.find(key);if(it==data.clips.end()||!std::isfinite(scale)||scale<=0||scale>100||!std::isfinite(now)||!std::isfinite(stop)||stop<=0)return false;
    if(active.size()==64)active.pop_front();
    active.push_back({&it->second,actor,now,it->second.scaled?scale:1,stop,offset,{{0,position}},-1,{},{},nullptr});return true;
  }
  void tick(double now,const std::map<uint64_t,V>&positions,const std::map<std::pair<uint64_t,int>,V>&joints={},
            const std::map<uint64_t,float>&headings={}){
    for(auto it=active.begin();it!=active.end();){
      float age=float(now-it->start);
      if(it->turn)if(auto h=headings.find(it->actor);h!=headings.end())it->heading=h->second;
      if(age>=float(it->clip->frames.size())/it->clip->rate){it=active.erase(it);continue;}
      // A flight's anchor is its own (position); it has only triangle
      // records (no particle tails), so it goes once it has ended.
      if(it->flight){if(age>=it->stop)it=active.erase(it);else ++it;continue;}
      if(age<0){if(auto p=positions.find(it->actor);p!=positions.end())it->positions.front().second=p->second;++it;continue;}
      const V*position=nullptr;
      if(it->joint>=0){auto p=joints.find({it->actor,it->joint});if(p!=joints.end())position=&p->second;}
      else{auto p=positions.find(it->actor);if(p!=positions.end())position=&p->second;}
      if(position&&age>it->positions.back().first){
        // At most one position per sample interval, with enough history for the
        // complete clip. Particles keep their birth position when actors move.
        if(it->positions.size()>1&&int(age*it->clip->rate)==int(it->positions.back().first*it->clip->rate))it->positions.back()={age,*position};
        else if(it->positions.size()<602)it->positions.push_back({age,*position});
      }
      ++it;
    }
  }
};
// PQ-342: decides the candidates of every sample up to `age` with the
// target at camera distance `distance` to the link's bundle: a candidate born
// at sample j is taken when the taken ones alive at sample j - 1, with
// `carried[k]` more of rule k from the earlier links of the same tail copy
// (2233's one live list, +0x448), are at most the target and fewer than the
// pool, and it was born before the link's stop.
inline void thin_advance(const EffectInstance&i,float age,float distance,const uint32_t*carried=nullptr){
  const auto&rules=i.clip->thinning;
  if(rules.empty()||age<0||i.clip->frames.empty())return;
  if(i.thin.size()!=rules.size()){i.thin.assign(rules.size(),{});for(auto&s:i.thin)s.taken.assign(i.clip->frames.size(),0);}
  size_t frame=std::min(size_t(age*i.clip->rate),i.clip->frames.size()-1);
  for(size_t k=0;k<rules.size();++k){
    const auto&rule=rules[k];auto&s=i.thin[k];
    s.target=thin_target(rule,distance);s.distance=distance;s.carried=carried?carried[k]:0;
    for(;s.next<=frame;++s.next){
      const auto&batches=i.clip->frames[s.next];
      bool born=false;
      for(const auto&b:batches)if(rule.applies(b))
        for(size_t n=10;n<b.records.size();n+=11)
          if(birth_sample(b.records[n],i.clip->rate)==long(s.next)&&b.records[n]<i.stop)born=true;
      uint32_t live=s.alive+s.carried;
      if(born&&int64_t(live)<=s.target&&live<rule.count)s.taken[s.next]=1;
      uint32_t alive=0;
      for(const auto&b:batches)if(rule.applies(b))
        for(size_t n=10;n<b.records.size();n+=11){
          auto j=birth_sample(b.records[n],i.clip->rate);
          alive+=j>=0&&size_t(j)<s.taken.size()&&s.taken[size_t(j)];
        }
      s.alive=alive;
    }
  }
}
// Advances every link of `links` at `now` (one frame), the camera at `eye`,
// in order, so that a link counts the taken live candidates of the links
// before it in its group (a tail chain lists its older link first).
template<class Links>
inline void thin_links(const Links&links,double now,V eye){
  std::map<const void*,std::vector<uint32_t>> groups;
  for(const EffectInstance*i:links){
    const auto&rules=i->clip->thinning;float age=float(now-i->start);
    if(rules.empty()||i->positions.empty()||age<0||age*i->clip->rate>=float(i->clip->frames.size()))continue;
    float d=0;for(unsigned k=0;k<3;++k){float x=i->positions.back().second[k]+i->offset[k]-eye[k];d+=x*x;}
    std::vector<uint32_t>*sum=nullptr;
    if(i->group){sum=&groups[i->group];sum->resize(rules.size(),0);}
    thin_advance(*i,age,std::sqrt(d),sum?sum->data():nullptr);
    if(sum)for(size_t k=0;k<rules.size();++k)(*sum)[k]+=i->thin[k].alive;
  }
}
// The draw pass's advance: every instance it draws, the player's effects
// (no group: each its own one-link chain) and the appearance tail links, so
// no instance of a ruled clip is drawn undecided.
template<class Links>
inline void thin_all(const EffectPlayer&player,const Links&tails,double now,V eye){
  std::vector<const EffectInstance*> all;
  for(const auto&i:player.active)all.push_back(&i);
  for(const EffectInstance*i:tails)all.push_back(i);
  thin_links(all,now,eye);
}
// `first` and `count` select records of the batch (PQ-376: one quad's draw).
inline std::vector<float> effect_vertices(const EffectInstance&i,const EffectBatch&batch,float age,V right,V up,
                                          size_t first=0,size_t count=SIZE_MAX){
  std::vector<float> out;
  // PQ-342: a thinned batch draws only the candidates its link took, and
  // nothing at a target of 0 (0058e880) or before the link has decided them.
  const ThinState*thin=nullptr;bool thinned=false;
  for(size_t k=0;k<i.clip->thinning.size();++k)if(i.clip->thinning[k].applies(batch)){
    thinned=true;if(k<i.thin.size())thin=&i.thin[k];break;}
  if(thinned&&(!thin||thin->target==0))return out;
  auto vertex=[&](V p,float u,float v,const float*color){out.insert(out.end(),{p[0],p[1],p[2],u,v,color[0],color[1],color[2],color[3]});};
  unsigned stride=batch.kind?11:9;
  size_t end=count>=batch.records.size()/stride?batch.records.size():std::min(batch.records.size(),(first+count)*stride);
  for(size_t n=first*stride;n<end;n+=stride){
    const float*record=batch.records.data()+n;
    float birth=batch.kind?record[10]:-1;
    if((birth>=0&&birth>=i.stop)||(birth<0&&age>=i.stop))continue;
    if(thinned){auto j=birth_sample(birth,i.clip->rate);if(j<0||size_t(j)>=thin->next||!thin->taken[size_t(j)])continue;}
    V anchor=i.position(birth>=0?birth:age),p{},r=i.turned(record);
    for(unsigned k=0;k<3;++k)p[k]=anchor[k]+i.offset[k]+r[k];
    if(!batch.kind){vertex(p,record[3],record[4],record+5);continue;}
    float c=std::cos(record[5]),s=std::sin(record[5]);
    constexpr float corners[6][2]={{0,0},{0,1},{1,1},{0,0},{1,1},{1,0}};
    for(const auto&uv:corners){
      float x=(uv[0]-.5f)*record[3]*i.scale,y=(.5f-uv[1])*record[4]*i.scale;
      V v{};for(unsigned k=0;k<3;++k)v[k]=p[k]+right[k]*(c*x-s*y)+up[k]*(s*x+c*y);
      vertex(v,uv[0],uv[1],record+6);
    }
  }
  return out;
}
inline float eye_distance(V p,V eye){float d=0;for(unsigned k=0;k<3;++k)d+=(p[k]-eye[k])*(p[k]-eye[k]);return std::sqrt(d);}
// PQ-376 (D-200): a camera-facing quad record's sort point, 1298's
// (v0 + v1 + v2) x 0.3333 (004840b0) in its corner order: the particle part's
// template (00482820) is (-0.5, 0.5) UV (0, 0), (0.5, 0.5) UV (1, 0),
// (0.5, -0.5) UV (1, 1), then (-0.5, -0.5) UV (0, 1), the corners
// effect_vertices builds for those UVs. Their mean offset is (w / 6, h / 6),
// turned by the record's angle in the camera plane. The anchor is the one
// effect_vertices takes: the birth point, or the point at `age` for a
// following quad (birth -1).
inline V quad_sort_point(const EffectInstance&i,const float*record,float age,V right,V up){
  float birth=record[10];
  V anchor=i.position(birth>=0?birth:age),p{};
  float c=std::cos(record[5]),s=std::sin(record[5]),x=record[3]*i.scale/6,y=record[4]*i.scale/6;
  V r=i.turned(record);
  for(unsigned k=0;k<3;++k)p[k]=anchor[k]+i.offset[k]+r[k]+right[k]*(c*x-s*y)+up[k]*(s*x+c*y);
  return p;
}
// One draw of the effect pass (PQ-211, PQ-376): a batch of an instance (all
// its records, or one quad of a quad-keyed instance) or an appearance mesh,
// with its sort key, a linear eye distance.
struct EffectMesh {
  uint32_t texture, source_blend, destination_blend, flags;
  float distance; // the sort key, a linear eye distance; the pass draws far to near
  std::vector<float> vertices;
};
// `external` (PQ-379, D-201) is an index into the pass's other draws (the
// world's alpha parts), drawn by the caller; SIZE_MAX for an effect draw.
struct EffectDraw {
  const EffectInstance*instance;const EffectBatch*batch;const EffectMesh*mesh;
  float age,key;size_t record=0,records=SIZE_MAX,external=SIZE_MAX;
};
// Every draw of the pass at `now`, far to near (stable: ties keep this order,
// the player's effects, then the links, then the meshes, then the external
// draws). An instance's frame is drawn as one draw per batch keyed by its
// newest point, but a quad-keyed instance's camera-facing batches are drawn
// one quad each, keyed by quad_sort_point. A mesh whose texture is past
// `textures` is skipped. `external_keys` are the keys of the caller's own
// draws (PQ-379: 1298 sorts world shape parts with flag 1 into the same list,
// 00443090), each a linear eye distance; they join the order as draws whose
// `external` is their index.
template<class Links,class Meshes,class Keys=std::vector<float>>
inline std::vector<EffectDraw> effect_draws(const EffectPlayer&player,const Links&instances,const Meshes&meshes,
                                            double now,V eye,V right,V up,size_t textures,const Keys&external_keys={}){
  std::vector<EffectDraw> draws;
  auto add=[&](const EffectInstance&i){
    float age=float(now-i.start);if(age<0)return;
    auto frame=size_t(age*i.clip->rate);if(frame>=i.clip->frames.size())return;
    float key=eye_distance(i.position(age),eye);
    for(const auto&batch:i.clip->frames[frame]){
      if(i.quad_keys&&batch.kind==1){
        for(size_t n=0;n<batch.records.size()/11;++n)
          draws.push_back({&i,&batch,nullptr,age,eye_distance(quad_sort_point(i,batch.records.data()+n*11,age,right,up),eye),n,1});
      }else draws.push_back({&i,&batch,nullptr,age,key});
    }
  };
  for(const auto&i:player.active)add(i);
  for(const EffectInstance*i:instances)add(*i);
  for(const auto&m:meshes)if(m.texture<textures&&!m.vertices.empty())draws.push_back({nullptr,nullptr,&m,0,m.distance});
  size_t k=0;for(float key:external_keys)draws.push_back({nullptr,nullptr,nullptr,0,key,0,SIZE_MAX,k++});
  std::stable_sort(draws.begin(),draws.end(),[](const auto&a,const auto&b){return a.key>b.key;});
  return draws;
}
}
