#include "assets/assets.h"
#include "assets/input_names.h"
#include <algorithm>
#include <bit>
#include <cmath>
#include <fstream>
#include <limits>
#include <memory>
#include <openssl/evp.h>
#include <openssl/sha.h>
#include <set>
#include <tuple>
#include <stdexcept>
namespace n3e {
namespace {
constexpr size_t WORLD_ASSET_BOUND = 32 * 1024 * 1024;
// N3W2 (PQ-231, D-159): the chunked encoding for worlds that do not fit N3W1.
constexpr size_t CHUNKED_WORLD_BOUND = 384u * 1024 * 1024;
void need(bool b, const char *why) {
  if (!b)
    throw std::runtime_error(why);
}
struct Reader {
  std::vector<unsigned char> b;
  size_t p = 0;
  explicit Reader(const std::filesystem::path &path,
                  size_t limit = 16 * 1024 * 1024) {
    auto n = std::filesystem::file_size(path);
    need(n <= limit, "asset file bound");
    b.resize(n);
    std::ifstream f(path, std::ios::binary);
    f.read((char *)b.data(), n);
    need(bool(f), "asset read");
  }
  // `n` bytes of an open file from `offset`: one N3W2 chunk body or header (PQ-232).
  Reader(std::istream &in, uint64_t offset, size_t n) {
    b.resize(n);
    in.clear();
    in.seekg(std::streamoff(offset));
    in.read((char *)b.data(), std::streamsize(n));
    need(bool(in), "asset read");
  }
  uint32_t u() {
    need(p + 4 <= b.size(), "truncated cooked data");
    uint32_t x = 0;
    for (int i = 0; i < 4; ++i)
      x |= uint32_t(b[p++]) << (8 * i);
    return x;
  }
  float f() {
    float x = std::bit_cast<float>(u());
    need(std::isfinite(x) && std::abs(x) <= 1e6, "cooked finite bound");
    return x;
  }
  template <size_t N> std::array<float, N> floats() {
    std::array<float, N> x;
    for (auto &v : x)
      v = f();
    return x;
  }
  uint32_t count(uint32_t max, uint32_t min = 1) {
    auto n = u();
    need(n >= min && n <= max, "cooked count");
    return n;
  }
  std::string raw(size_t n) {
    need(p + n <= b.size(), "cooked byte length");
    std::string s((char *)b.data() + p, n);
    p += n;
    return s;
  }
  std::string str() { return raw(count(200)); }
  void magic(const char *m) { need(raw(4) == m, "cooked magic/version"); }
  void end() { need(p == b.size(), "cooked trailing bytes"); }
};
std::string sha(const std::vector<unsigned char> &b) {
  unsigned char d[32];
  SHA256(b.data(), b.size(), d);
  return std::string((char *)d, 32);
}
// (size, SHA-256, first four bytes) of a file read in 1 MiB blocks.
std::tuple<uint64_t, std::string, std::string> hash_file(const std::filesystem::path &path, uint64_t limit) {
  auto n = std::filesystem::file_size(path);
  need(n <= limit, "asset file bound");
  std::ifstream f(path, std::ios::binary);
  need(bool(f), "asset read");
  std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> ctx(EVP_MD_CTX_new(), EVP_MD_CTX_free);
  need(ctx && EVP_DigestInit_ex(ctx.get(), EVP_sha256(), nullptr) == 1, "asset hash");
  std::vector<char> block(1 << 20);
  std::string head;
  uint64_t done = 0;
  while (done < n) {
    auto k = size_t(std::min<uint64_t>(block.size(), n - done));
    f.read(block.data(), std::streamsize(k));
    need(bool(f), "asset read");
    if (head.size() < 4) head.append(block.data(), std::min<size_t>(k, 4 - head.size()));
    need(EVP_DigestUpdate(ctx.get(), block.data(), k) == 1, "asset hash");
    done += k;
  }
  unsigned char d[32];
  unsigned int length = 0;
  need(EVP_DigestFinal_ex(ctx.get(), d, &length) == 1 && length == 32, "asset hash");
  return {n, std::string((char *)d, 32), head};
}
std::string hex(const std::string &b) {
  std::string s;
  for (unsigned char x : b) {
    s += "0123456789abcdef"[x >> 4];
    s += "0123456789abcdef"[x & 15];
  }
  return s;
}
M identity() {
  M m{};
  m[0] = m[5] = m[10] = m[15] = 1;
  return m;
}
M mul(const M &a, const M &b) {
  M o{};
  for (int c = 0; c < 4; c++)
    for (int r = 0; r < 4; r++)
      for (int k = 0; k < 4; k++)
        o[c * 4 + r] += a[k * 4 + r] * b[c * 4 + k];
  return o;
}
V point(const M &m, V p) {
  V v{};
  for (int r = 0; r < 3; r++) {
    v[r] = m[12 + r];
    for (int k = 0; k < 3; k++)
      v[r] += m[k * 4 + r] * p[k];
  }
  return v;
}
V norm(V v) {
  float l = std::sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
  need(l > 1e-10, "zero normal");
  for (auto &x : v)
    x /= l;
  return v;
}
V normal(const M &m, V n) {
  V a{m[0], m[1], m[2]}, b{m[4], m[5], m[6]}, c{m[8], m[9], m[10]};
  auto cross = [](V x, V y) {
    return V{x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2],
             x[0] * y[1] - x[1] * y[0]};
  };
  V bc = cross(b, c), ca = cross(c, a), ab = cross(a, b);
  float det = a[0] * bc[0] + a[1] * bc[1] + a[2] * bc[2];
  need(std::abs(det) > 1e-10, "singular skin matrix");
  V v;
  for (int i = 0; i < 3; i++)
    v[i] = (bc[i] * n[0] + ca[i] * n[1] + ab[i] * n[2]) / det;
  return norm(v);
}
M trs(const Node &n) {
  auto [x, y, z, w] = n.q;
  M m = {1 - 2 * (y * y + z * z),
         2 * (x * y + z * w),
         2 * (x * z - y * w),
         0,
         2 * (x * y - z * w),
         1 - 2 * (x * x + z * z),
         2 * (y * z + x * w),
         0,
         2 * (x * z + y * w),
         2 * (y * z - x * w),
         1 - 2 * (x * x + y * y),
         0,
         n.t[0],
         n.t[1],
         n.t[2],
         1};
  for (int c = 0; c < 3; c++)
    for (int r = 0; r < 3; r++)
      m[c * 4 + r] *= n.s[c];
  return m;
}
Q interpolate(Q a, Q b, float t, bool rotation) {
  float d = 0;
  for (int i = 0; i < 4; i++)
    d += a[i] * b[i];
  if (rotation && d < 0) {
    d = -d;
    for (auto &x : b)
      x = -x;
  }
  Q q{};
  if (rotation && d < .9995f) {
    float angle = std::acos(std::clamp(d, -1.f, 1.f));
    for (int i = 0; i < 4; i++)
      q[i] = (a[i] * std::sin((1 - t) * angle) + b[i] * std::sin(t * angle)) /
             std::sin(angle);
  } else
    for (int i = 0; i < 4; i++)
      q[i] = a[i] + (b[i] - a[i]) * t;
  if (rotation) {
    float l = 0;
    for (auto x : q)
      l += x * x;
    need(l > 1e-10, "quaternion");
    for (auto &x : q)
      x /= std::sqrt(l);
  }
  return q;
}
} // namespace
std::optional<uint32_t> RepairPolicy::cost(uint32_t price,uint32_t current,uint32_t maximum) const {
  if(maximum<=1||current>maximum)return {};
  double value=((double(price)-offset)*double(linear)+std::pow(double(price),power))*double(maximum-current)/double(maximum);
  if(!std::isfinite(value)||value<0||value>2147483647)return {};
  return uint32_t(std::trunc(double(uint32_t(std::trunc(value)))*double(multiplier)));
}
Skills load_skills(const std::filesystem::path&path){
  Reader r(path);auto version=r.raw(4);need(version=="N3K2"||version=="N3K3"||version=="N3K4"||version=="N3K5","skill magic");Skills p{r.str(),r.str(),{},{},{},{},0,{}};
  p.reach.start=r.f();p.reach.hold=r.f();auto plane=r.count(1,0);p.reach.planar=plane==1;
  need(p.reach.start>=0&&p.reach.start<=50&&p.reach.hold>=0&&p.reach.hold<=50,"skill reach");
  // PQ-466 (D-234) notice; PQ-469 (D-235) the failed line, bounded the same way.
  auto line=[&](const char*what){auto text=r.str();auto format=text.find('%');
    need(text.size()<=96&&std::all_of(text.begin(),text.end(),[](char c){return c>=' '&&c<='~';})&&
         (format==std::string::npos||(text.compare(format,2,"%s")==0&&text.find('%',format+2)==std::string::npos)),what);
    return text;};
  if(version!="N3K2")p.notice=line("skill notice");
  if(version=="N3K4"||version=="N3K5"){p.failed=line("skill failed line");p.failed_color=r.u();need(p.failed_color>>24,"skill failed colour");}
  // PQ-479 (D-243): N3K5's acceptance refusal lines, bounded as the server
  // bounds them: 1-8, one per status ([a-z][a-z_]{0,31}, not out_of_range).
  if(version=="N3K5"){
    auto count=r.count(8);std::set<std::string> statuses;
    for(unsigned i=0;i<count;++i){
      SkillRefusal line_;line_.status=r.str();
      need(!line_.status.empty()&&line_.status.size()<=32&&line_.status[0]>='a'&&line_.status[0]<='z'&&
           std::all_of(line_.status.begin(),line_.status.end(),[](char c){return (c>='a'&&c<='z')||c=='_';})&&
           line_.status!="out_of_range"&&statuses.insert(line_.status).second,"skill refusal line");
      line_.target=r.count(2,0);line_.text=line("skill refusal line");line_.color=r.u();need(line_.color>>24,"skill refusal colour");
      p.refusals.push_back(std::move(line_));
    }
  }
  auto count=r.count(32);std::set<std::string> seen;
  for(unsigned i=0;i<count;++i){
    Skill s;s.id=r.str();s.label=r.str();s.character_class=r.str();
    s.level=r.count(100);s.cost=r.count(100000,0);s.cast_ms=r.count(10000,50);s.cooldown_ms=r.count(60000,0);
    s.target=r.count(2);s.amount=r.count(5000);s.survival=r.count(100,0);s.attribute=r.count(4,0);s.resistance=r.count(200,0);s.animation=r.count(31,0);s.range=r.f();
    need(seen.insert(s.id).second&&!s.label.empty()&&s.character_class==p.archetype&&s.label.size()<=80&&s.range>0&&s.range<=50,"skill bounds");
    auto n=r.count(64,0);for(unsigned j=0;j<n;++j)s.weapons.push_back(r.str());
    s.cast_effect=r.str();s.target_effect=r.str();n=r.count(2);
    for(unsigned j=0;j<n;++j){auto joint=int(r.count(128,0))-1;need(std::find(s.cast_joints.begin(),s.cast_joints.end(),joint)==s.cast_joints.end(),"skill duplicate joint");s.cast_joints.push_back(joint);}
    s.target_joint=int(r.count(128,0))-1;p.entries.push_back(std::move(s));
  }
  r.end();return p;
}
Audio load_audio(const std::filesystem::path& path) {
  Reader r(path);auto version=r.raw(4);need(version=="N3AU"||version=="N3A2","audio magic");
  need(r.u()==48000,"audio rate");Audio result;
  auto count=r.count(128);size_t total=0;
  for(unsigned i=0;i<count;++i){
    SoundClip clip;clip.maximum=r.count(16);auto frames=r.count(480000);
    total+=frames;need(total<=6*48000*10,"audio decoded bound");
    auto raw=r.raw(frames*2);clip.samples.reserve(frames);
    for(unsigned j=0;j<frames;++j){uint16_t bits=uint8_t(raw[j*2])|(uint16_t(uint8_t(raw[j*2+1]))<<8);clip.samples.push_back(std::bit_cast<int16_t>(bits)/32768.f);}
    result.clips.push_back(std::move(clip));
  }
  count=r.count(1024,0);
  for(unsigned i=0;i<count;++i){auto key=r.str();auto index=r.u();need(index<result.clips.size()&&result.bindings.emplace(key,index).second,"audio binding");}
  count=r.count(128,0);
  for(unsigned i=0;i<count;++i){auto style=r.u(),variant=r.u();need(style<=32&&variant>=1&&variant<=4,"audio timing selector");
    auto n=r.count(2,0);std::vector<float> markers;
    for(unsigned j=0;j<n;++j){auto t=r.f();need(t>=0&&t<=10,"audio marker");markers.push_back(t);}
    need(result.timings.emplace(std::pair{style,variant},markers).second,"duplicate audio timing");
  }
  if(version=="N3A2"){ // PQ-013: positional policy, bounds as tools/assetc/audio_spatial.py
    auto&s=result.spatial;s.listener=r.u();
    s.effect_distance=r.f();s.effect_distance_min=r.f();s.effect_distance_max=r.f();s.cutoff=r.f();s.reference=r.f();
    auto in=[](float v,float lo,float hi){return std::isfinite(v)&&v>=lo&&v<=hi;};
    need(s.listener<=1&&in(s.cutoff,5,512)&&in(s.reference,.1f,32)&&s.reference<s.cutoff
         &&(s.effect_distance==0?s.effect_distance_min==0&&s.effect_distance_max==0
            :in(s.effect_distance_min,1,512)&&in(s.effect_distance_max,1,512)
             &&s.effect_distance_min<=s.effect_distance&&s.effect_distance<=s.effect_distance_max),"audio spatial bounds");
  }
  r.end();return result;
}
Effects load_effects(const std::filesystem::path& path) {
  Reader r(path);auto magic=r.raw(4);need(magic=="N3EF"||magic=="N3E2"||magic=="N3E3"||magic=="N3E4"||magic=="N3E5","cooked magic/version");Effects effects;
  auto textures=r.count(256);size_t pixels=0,records=0;
  for(unsigned i=0;i<textures;++i){
    EffectTexture t{r.count(512),r.count(512),{}};
    pixels+=size_t(t.width)*t.height;need(pixels<=4*1024*1024,"effect texture budget");
    auto bytes=r.raw(size_t(t.width)*t.height*4);t.pixels.assign(bytes.begin(),bytes.end());
    effects.textures.push_back(std::move(t));
  }
  auto clips=r.count(64);
  for(unsigned i=0;i<clips;++i){
    auto name=r.str();need(!effects.clips.contains(name),"duplicate effect clip");
    auto scaled=r.count(1,0);EffectClip clip{bool(scaled),r.count(60),{}};
    // At most 20 s (PQ-341: a 2233 weapon effect tail of two 10 s links, the
    // shortest that holds whole cycles of its meshes).
    auto frames=r.count(600);need(frames<=clip.rate*20,"effect duration bound");
    for(unsigned j=0;j<frames;++j){
      std::vector<EffectBatch> frame;auto batches=r.count(128,0);
      for(unsigned k=0;k<batches;++k){
        EffectBatch batch{r.count(1,0),r.u(),r.count(10),r.count(10),r.u(),{}};
        need(batch.texture<textures&&!(batch.flags&~0x7ffu),"effect material bounds");
        auto n=r.count(8192);records+=n;need(records<=500000,"effect record budget");
        need(batch.kind||n%3==0,"effect triangle count");
        auto stride=batch.kind?11u:9u;
        for(unsigned a=0;a<n;++a){
          for(unsigned b=0;b<stride;++b){
            float value=r.f();
            if(b<3)need(std::abs(value)<=1000,"effect position bounds");
            unsigned color=batch.kind?6:5;
            if(b>=color&&b<color+4)need(value>=0&&value<=1,"effect color bounds");
            if(batch.kind&&b==10)need(value==-1||(value>=0&&value<=float(j)/clip.rate+.001f),"effect birth time");
            if(batch.kind&&(b==3||b==4))need(value>=0&&value<=100,"effect quad size");
            batch.records.push_back(value);
          }
        }
        frame.push_back(std::move(batch));
      }
      clip.frames.push_back(std::move(frame));
    }
    effects.clips.emplace(name,std::move(clip));
  }
  auto bindings=r.count(128,0);
  for(unsigned i=0;i<bindings;++i){
    Effects::Binding b{r.count(3),r.str(),r.count(4,0),r.count(129,0),{}};
    auto n=r.count(8);for(unsigned j=0;j<n;++j){auto key=r.str();need(effects.clips.contains(key),"unknown bound effect");b.clips.push_back(key);}
    effects.bindings.push_back(std::move(b));
  }
  // N3E2 (PQ-211): effects on equipped appearance keys. The key is checked
  // against N3V1 by load_release and the joint against the skeleton by
  // load_render_detail.
  // N3E3 (PQ-315) is N3E2 with 0..16 effects, then the glow section below.
  // N3E4 (PQ-342) is N3E3 with 0..16 glows, then the particle distance rules.
  // N3E5 (PQ-376, D-200) is N3E4 with 0..64 rules, then the sort records.
  if(magic!="N3EF"){
    auto n=r.count(16,magic=="N3E2"?1:0);std::set<uint32_t> keys;size_t vertices=0;
    auto point=[&]{auto p=r.floats<3>();for(float x:p)need(std::abs(x)<=1000,"appearance effect position");return V{p[0],p[1],p[2]};};
    for(unsigned i=0;i<n;++i){
      AppearanceEffect e;e.key=r.count(128);need(keys.insert(e.key).second,"duplicate appearance effect");e.joint=r.count(255,0);
      auto frames=r.count(64);for(unsigned j=0;j<frames;++j){e.frames.push_back(r.u());need(e.frames.back()<textures,"appearance effect frame");}
      e.fps=r.f();need(e.fps>0&&e.fps<=120,"appearance effect rate");
      e.phase_steps=r.count(10000);e.phase_step=r.f();need(e.phase_step>=0&&e.phase_steps*e.phase_step<=10,"appearance effect phase");
      e.source_blend=r.count(10);e.destination_blend=r.count(10);e.flags=r.u();need(!(e.flags&~0x7ffu),"appearance effect flags");
      auto copies=r.count(4,0);
      for(unsigned j=0;j<copies;++j){
        AppearanceEffect::Copy c;c.jitter=r.f();need(std::abs(c.jitter)<=1,"appearance effect jitter weight");
        c.frame_offset=r.count(frames-1,0);auto count=r.count(3072,3);need(count%3==0,"appearance effect triangles");
        vertices+=count;need(vertices<=8192,"appearance effect vertex budget");
        for(unsigned k=0;k<count;++k){auto v=r.floats<5>();for(int a=0;a<3;++a)need(std::abs(v[a])<=1000,"appearance effect position");
          need(std::abs(v[3])<=1024&&std::abs(v[4])<=1024,"appearance effect UV");c.vertices.push_back(v);}
        e.copies.push_back(std::move(c));
      }
      e.jitter_rate=r.f();e.jitter_amplitude=r.f();need(e.jitter_rate>=0&&e.jitter_rate<=100&&e.jitter_amplitude>=0&&e.jitter_amplitude<=1,"appearance effect jitter");
      for(auto&p:e.jitter)p=point();
      for(auto&p:e.tail_box)p=point();
      e.tail_low=r.f();e.tail_steps=r.count(10000);e.tail_step=r.f();
      need(e.tail_low>=0&&e.tail_step>=0&&e.tail_low+(e.tail_steps-1)*e.tail_step<=1+1e-4f,"appearance effect tail range");
      // '' without tails (the N3E2 contract); PQ-339's skeletal plug effect is
      // the first to carry none, so the name may be empty here.
      e.tails=r.count(4,0);e.tail_clip=r.raw(r.count(200,0));
      need(e.tails?effects.clips.contains(e.tail_clip):e.tail_clip.empty(),"appearance effect tail clip");
      e.trace_color=r.u();
      effects.appearance.push_back(std::move(e));
    }
  }
  // N3E3 (PQ-315): an emissive glow on equipped appearance keys' geometry.
  // The key is checked against N3V1 by load_release.
  if(magic=="N3E3"||magic=="N3E4"||magic=="N3E5"){
    auto n=r.count(16,magic=="N3E3"?1:0);std::set<uint32_t> keys;
    for(unsigned i=0;i<n;++i){
      AppearanceGlow g;g.key=r.count(128);need(keys.insert(g.key).second,"duplicate appearance glow");
      for(auto&c:g.color){c=r.f();need(c>=0&&c<=1,"appearance glow colour");}
      g.modulate=r.f();need(g.modulate==1||g.modulate==2||g.modulate==4,"appearance glow modulate");
      g.wave=r.count(1,0);g.rise=r.f();g.hold=r.f();g.fall=r.f();g.period=r.f();
      need(g.wave==AppearanceGlow::STEADY?g.rise==0&&g.hold==0&&g.fall==0&&g.period==0
           :g.rise>0&&g.rise<=g.hold&&g.hold<=g.fall&&g.fall<=g.period&&g.period<=60,"appearance glow timing");
      effects.glow.push_back(g);
    }
  }
  // N3E4 (PQ-342): camera-distance particle rules on appearance tail clips,
  // as tools/assetc/appearance_effects.py writes them. Only an appearance
  // tail link carries the state the rule needs, so no binding may play the
  // clip; each candidate is known by its birth sample alone.
  if(magic=="N3E4"||magic=="N3E5"){
    auto n=r.count(64,magic=="N3E4"?1:0);std::set<std::pair<std::string,std::array<uint32_t,4>>> seen;
    for(unsigned i=0;i<n;++i){
      auto name=r.str();ParticleThinning t;
      t.texture=r.u();t.source_blend=r.count(10);t.destination_blend=r.count(10);t.flags=r.u();t.count=r.count(1024);
      t.near=r.f();t.far=r.f();
      bool tail=std::any_of(effects.appearance.begin(),effects.appearance.end(),[&](const auto&e){return e.tails&&e.tail_clip==name;});
      bool bound=std::any_of(effects.bindings.begin(),effects.bindings.end(),[&](const auto&b){return std::find(b.clips.begin(),b.clips.end(),name)!=b.clips.end();});
      need(tail&&!bound,"appearance tail particle rule clip");
      need(t.texture<textures&&!(t.flags&~0x7ffu),"appearance tail particle rule material");
      need(seen.insert({name,{t.texture,t.source_blend,t.destination_blend,t.flags}}).second,"duplicate appearance tail particle rule");
      auto in=[](float v){return std::isfinite(v)&&v>0&&v<=1000;};
      need(in(t.near)&&in(t.far),"appearance tail particle rule distance");
      auto&clip=effects.clips.at(name);bool found=false;
      for(const auto&frame:clip.frames){
        std::set<long> births;
        for(const auto&b:frame){
          if(!t.applies(b))continue;found=true;
          for(size_t k=10;k<b.records.size();k+=11){
            float x=b.records[k]*float(clip.rate);long sample=std::lround(x);
            need(b.records[k]>=0&&std::abs(x-float(sample))<=1e-3f&&births.insert(sample).second,"appearance tail particle rule candidates");
          }
        }
      }
      need(found,"appearance tail particle rule batch");
      clip.thinning.push_back(t);
    }
  }
  // N3E5 (PQ-376, D-200): 1298's alpha-list keys (00415910, 004840b0) on
  // appearance effects, as tools/assetc/appearance_effects.py writes them: a
  // sort origin rigid to the effect's joint and the copies' bias.
  if(magic=="N3E5"){
    auto n=r.count(16);std::set<uint32_t> keys;
    for(unsigned i=0;i<n;++i){
      auto key=r.count(128);need(keys.insert(key).second,"duplicate appearance effect sort");
      auto e=std::find_if(effects.appearance.begin(),effects.appearance.end(),[&](const auto&a){return a.key==key;});
      need(e!=effects.appearance.end(),"appearance effect sort key");
      auto p=r.floats<3>();for(float x:p)need(std::isfinite(x)&&std::abs(x)<=1000,"appearance effect sort origin");
      float bias=r.f();need(std::isfinite(bias)&&bias>=0&&bias<=1000,"appearance effect sort bias");
      e->sorted=true;e->sort_origin={p[0],p[1],p[2]};e->sort_bias=bias;
    }
  }
  r.end();return effects;
}
// N3PF (PQ-316): seven f32 in tools/assetc/postprocess.py's order and bounds.
PostProcess load_postprocess(const std::filesystem::path &path){
  Reader r(path);r.magic("N3PF");PostProcess pp;
  pp.threshold=r.f();pp.bloom=r.f();pp.exposure=r.f();pp.saturation=r.f();pp.lift=r.f();pp.adapt_rate=r.f();pp.blur_variance=r.f();r.end();
  auto in=[](float x,float lo,float hi){return x>=lo&&x<=hi;};
  need(in(pp.threshold,0,1)&&in(pp.bloom,0,4)&&in(pp.exposure,0,16)&&in(pp.saturation,0,4)&&in(pp.lift,0,4)
       &&in(pp.adapt_rate,0,100)&&in(pp.blur_variance,0,16)&&pp.blur_variance>0,"postprocess bounds");
  return pp;
}
Release load_release(const std::filesystem::path &root) {
  Reader r(root / "release.bin");
  r.magic("N3R1");
  need(r.u() == 1, "incompatible schema");
  auto engine = r.u(), protocol = r.u();
  // Engines 38 (PQ-253), 39 (PQ-265: N3MM looks models with render
  // states) and 40 (PQ-283: N3NI / N3MI looks models with influence tables)
  // add client presentation only and keep wire 30; so do 41 (PQ-272) and
  // 42 (spec 11: front-end.bin).
  need(engine >= 1 && engine <= 42 &&
           (engine >= 38 ? protocol == 30
            : engine >= 15 ? protocol == engine-7
            : engine >= 13 ? protocol == 7
            : engine == 12  ? protocol == 6
            : engine >= 9 ? protocol == engine - 5
            : engine == 8   ? protocol >= 1 && protocol <= 3
            : engine == 7 ? protocol == 3
            : engine >= 3 ? protocol >= 1 && protocol <= 2
                          : protocol == engine),
       "incompatible schema/engine/protocol");
  Release result{r.str(), r.str(), hex(sha(r.b)), root};
  result.protocol = protocol;

  need(!result.game.empty() && result.game.size() <= 32 &&
           result.game.find_first_not_of(
               "abcdefghijklmnopqrstuvwxyz0123456789_-") == std::string::npos,
       "game ID");
  auto count = r.count(256);
  std::set<std::string> files;
  for (uint32_t i = 0; i < count; i++) {
    auto name = r.str();
    need(name.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789_.-") ==
                 std::string::npos &&
             name != "." && name != "..",
         "release path");
    need(files.insert(name).second, "duplicate asset");
    auto size = r.u();
    auto hash = r.raw(32);
    auto path = std::filesystem::canonical(root / name);
    auto base = std::filesystem::canonical(root);
    need(path.parent_path() == base, "asset containment");
    // The static world asset is map sized; everything else keeps the 16 MiB
    // bound. Both are fixed limits, not a blanket increase.
    if (name == "world.bin") {
      // Hashed in blocks, never held whole: a streamed world's memory is its
      // resident chunks (PQ-232), not the file.
      auto [bytes, digest, magic] = hash_file(path, CHUNKED_WORLD_BOUND);
      need(bytes == size && digest == hash, "asset size/hash mismatch");
      // N3W3 (PQ-379, D-201): N3W2 with alpha parts; N3W4 (PQ-382, D-202):
      // N3W3 with the opaque part bits; N3W5 (PQ-388, D-203): N3W4 with
      // single-layer unlit vertices.
      result.world_chunked = world_chunk_magic(magic);
      need((magic == "N3W1" && bytes <= WORLD_ASSET_BOUND) || result.world_chunked, "world asset magic/size");
      continue;
    }
    // An N3W2 world's textures (N3WT, PQ-233), up to 384 MiB of pixels: hashed
    // in blocks too; load_world_textures reads them once at start.
    if (name == "world-textures.bin") {
      auto [bytes, digest, magic] = hash_file(path, WORLD_TEXTURES_BOUND);
      need(bytes == size && digest == hash, "asset size/hash mismatch");
      need(magic == "N3WT", "world texture magic");
      continue;
    }
    // N3WO (PQ-387, D-204): up to 256 MiB of pixels, hashed in blocks too.
    if (name == "world-overlay.bin") {
      auto [bytes, digest, magic] = hash_file(path, WORLD_OVERLAY_BOUND);
      need(bytes == size && digest == hash, "asset size/hash mismatch");
      need(magic == "N3WO", "world overlay magic");
      continue;
    }
    Reader f(path, name == "render-detail.bin" ? 128 * 1024 * 1024 : name == "front-end.bin" ? kFrontEndFile : 16 * 1024 * 1024);
    need(f.b.size() == size && sha(f.b) == hash, "asset size/hash mismatch");
  }
  r.end();
  need((engine >= 9 || files.contains("animation.bin") == (engine == 8)) && (engine<30 || files.contains("animation.bin")),
       "animation compatibility");
  if (files.erase("animation.bin")) {
    Reader a(root / "animation.bin");
    auto version = a.raw(4);
    need(version == "N3A1" || version == "N3A2" || version == "N3A3", "animation magic");
    int count = version=="N3A3" ? 14 : version == "N3A1" ? 11 : 7;
    need((count==14)==(engine>=30),"rest animation compatibility");
    result.animation.emplace(count);
    for (int i = 0; i < count; ++i) {
      auto &clip = (*result.animation)[i];
      clip.duration = a.f();
      clip.blend = a.f();
      auto loop = a.u();
      clip.loop_blend = loop;
      clip.markers = a.floats<2>();
      need(clip.duration >= .001f && clip.duration <= 3600 && clip.blend >= 0 &&
               clip.blend <= 2 && loop <= 1 &&
               (!(i==2||i==3||(count==14?(i==7||i==9||i==12||i==13):(i==9||i==10))) || !loop),
           "animation bounds");
      for (float marker : clip.markers)
        need(marker == -1 || (marker >= 0 && marker <= clip.duration),
             "animation marker");
    }
    a.end();
    if (count >= 11) for (const char *name :
         {"npc-idle.bin", "npc-walk.bin", "npc-attack.bin", "npc-death.bin"})
      need(files.erase(name) == 1, "NPC animation set");
    if(count==14)for(const char *name:{"player-sit-down.bin","player-sit-idle.bin","player-stand-up.bin"})need(files.erase(name)==1,"rest animation set");
    need(files.contains("hud.bin") && files.contains("player-run.bin") &&
             files.contains("player-backward.bin") &&
             files.contains("player-ready.bin"),
         "player animation set");
  }
  bool has_camera = files.contains("camera.bin");
  need(engine >= 4 || files.contains("camera.bin") == (engine == 3),
       "camera compatibility");
  need(engine >= 5 || files.contains("melee.bin") == (engine == 4), "melee compatibility");
  need(engine >= 6 || files.contains("damage.bin") == (engine == 5), "damage compatibility");
  need(engine >= 7 || files.contains("npc.bin") == (engine == 6), "npc compatibility");
  need(engine >= 9 || (engine == 8 ? files.contains("life.bin") == (protocol == 3)
                    : files.contains("life.bin") == (engine == 7)),
       "life compatibility");
  need(engine < 10 || files.contains("life.bin"), "loot requires durable life policy");
  need(files.contains("progression.bin") == (engine >= 9), "progression compatibility");
  std::string progression_item,drop_currency;
  struct DropItem {std::string id;uint32_t quantity,durability;};
  std::vector<DropItem> drop_items;
  uint32_t progression_capacity = 0, progression_starting = 0;
  if (files.erase("progression.bin")) {
    Reader p(root / "progression.bin");
    auto progression_magic=p.raw(4);
    unsigned progression_version=progression_magic=="N3P5"?5:progression_magic=="N3P4"?4:progression_magic=="N3P3"?3:progression_magic=="N3P2"?2:progression_magic=="N3P1"?1:0;
    need(progression_version && (engine>=29 || progression_magic == (engine==28?"N3P5":engine==27?"N3P4":engine==26?"N3P3":engine==25?"N3P2":"N3P1")) && p.u() == 1 && p.u() == (files.contains("stats.bin")?2u:1u), "progression policy");
    auto curve = p.str(); progression_item = p.str();
    need(curve.starts_with(result.game + ":") && curve.size() <= 128 && progression_item.size() <= 128, "progression namespace");
    need(p.str() == "original synthetic", "progression origin");
    p.str(); need(p.u() > 0, "progression revision");
    uint64_t previous = 0;
    result.thresholds.emplace();
    for (int i = 0; i < 10; ++i) {
      uint64_t low = p.u(), high = p.u(), value = low | (high << 32);
      need(value <= INT64_MAX && (i == 0 ? value == 0 : value > previous), "progression thresholds");
      previous = value;
      (*result.thresholds)[i] = value;
    }
    progression_capacity = p.u(); progression_starting = p.u();
    auto level = p.u(), xp = p.u(); auto radius = p.f(), claim = p.f(); auto ttl = p.u();result.claim_radius=claim;
    need(progression_capacity >= 1 && progression_capacity <= 64 && progression_starting <= progression_capacity && level >= 1 && level <= 10 && xp >= 1 && xp <= 1000000 && radius >= 1 && radius <= 100 && claim >= .5 && claim <= 10 && ttl >= 10 && ttl <= 600, "progression bounds");
    if(progression_version>=2){
      auto bonus=p.u(); auto read_double=[&](){uint64_t lo=p.u(),hi=p.u(),bits=lo|(hi<<32);return std::bit_cast<double>(bits);};
      auto minimum=read_double(),maximum=read_double();auto gap=p.u();
      need(bonus<=8&&std::isfinite(minimum)&&std::isfinite(maximum)&&minimum>=0&&minimum<=1&&maximum>=1&&maximum<=10&&gap<=100&&std::floor(radius)==radius,"party reward bounds");
      for(unsigned i=0;i<10;++i){auto xp=p.u();need(xp>0&&xp<=INT32_MAX&&(i==9||(*result.thresholds)[i+1]-(*result.thresholds)[i]==xp),"party reward level table");}
    }
    if(progression_version>=3){auto radius=p.u();need(radius>=1&&radius<=100,"party loot radius");}
    if(progression_version>=4){
      drop_currency=p.str();auto base=p.u(),lo=p.u(),hi=p.u(),event=p.u(),party=p.u(),maximum=p.u(),overflow=p.u(),pickup=p.u(),cap=p.u();
      need(!drop_currency.empty()&&drop_currency.size()<=129&&base<=INT32_MAX/100&&lo<=hi&&hi<=100&&event<=32767&&party<=100&&maximum>=1&&maximum<=32766&&overflow>=1&&overflow<=maximum&&pickup<=100&&cap>=1&&cap<=32766&&double(base)*(1.+double(event)*.01)*(1.+7.*(double(party)/100.))<=INT32_MAX,"coin generation bounds");
    }
    if(progression_version>=5){
      p.u();p.u();p.u();auto bound=p.u(),event=p.u();auto unit=p.f(),premium=p.f();
      need(bound>=1&&bound<=32767&&event<=255&&unit>=0&&unit<=1&&premium>=0&&premium<=1,"item drop policy");
      auto count=p.count(64);std::set<std::string> seen;
      for(unsigned i=0;i<count;++i){DropItem d{p.str(),p.u(),p.u()};
        need(d.id.starts_with(result.game+":")&&d.id.size()>result.game.size()+1&&d.id.size()<=result.game.size()+97&&d.id[result.game.size()+1]>='a'&&d.id[result.game.size()+1]<='z'&&d.id.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789_/-",result.game.size()+1)==std::string::npos&&seen.insert(d.id).second&&d.quantity>=1&&d.quantity<=9999&&d.durability<=65535,"drop item");drop_items.push_back(d);}
      auto rows=p.count(6);
      for(unsigned i=0;i<rows;++i){auto chance=p.u(),penalty=p.u(),premium=p.u(),group=p.u(),slots=p.count(30);
        need(chance<=10000&&penalty<=10000&&premium<=1&&group<=1&&(group||slots==1),"drop row");
        for(unsigned j=0;j<slots;++j){auto slot=p.u();need(slot<=count&&(group||slot>0),"drop slot");}}
    }
    p.end();
  }
  std::optional<uint32_t> npc_corpse;
  if (files.erase("life.bin")) {
    Reader l(root / "life.bin");
    need(l.raw(4) == "N3L1" && l.u() == 1, "life model");
    auto player = l.u(), corpse = l.u(), respawn = l.u();
    need(player <= 1200 && corpse <= 1200 && respawn >= 1 && respawn <= 12000 && corpse <= respawn, "life timer");
    l.end();
    npc_corpse = corpse;
    result.requested_respawn = true;
  }
  std::set<std::string> template_looks; // N3N3 templates' looks keys (PQ-253)
  if (files.erase("npc.bin")) {
    Reader n(root / "npc.bin");
    auto magic = n.raw(4);
    auto model = n.u();
    // N3N3 (PQ-249, engine 37) is N3N2 with a template table: acquisition moves
    // into each template and every slot names one.
    // N3N4 (PQ-272, D-179, engine 41) is N3N3 with a drawn scale per template;
    // an engine 41 package's templates are N3N4. Engine 42 adds only the
    // front end (spec 11, Q59), so it keeps whichever table it has.
    bool scaled = magic == "N3N4" && model == 4;
    bool templated = (magic == "N3N3" && model == 3) || scaled;
    bool reference = (magic == "N3N2" && model == 2) || templated;
    need((magic == "N3N1" && model == 1) || (reference && engine >= (templated ? 37u : 36u)), "npc model");
    need(scaled ? engine >= 41 : engine != 41, "npc scale compatibility");
    for (int i = 0; i < 6; ++i) {
      auto ticks = n.u();
      need(ticks >= (i == 1 ? 0u : 1u) && ticks <= (i == 3 || i == 4 ? 12000u : 1200u), "npc timer");
    }
    uint32_t templates = 0;
    if (reference) {
      // The server owns behavior; the client only validates the bounded layout.
      for (int i = 0; i < (templated ? 3 : 4); ++i) need(n.u() <= 1, "npc reference flag");
      auto percent = n.u(), interval = n.u(), divisor = n.u(), tries = n.u();
      need(percent >= 100 && percent <= 300 && interval <= 12000 && divisor >= 1 && divisor <= 1000 &&
               tries >= 1 && tries <= 500, "npc reference bound");
      if (templated) {
        auto rule_id = [&](const std::string &id) {
          return id.starts_with(result.game + ":") && id.size() <= 128 &&
                 std::all_of(id.begin(), id.end(), [](char c) {
                   return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == ':' || c == '/' || c == '-';
                 });
        };
        templates = n.count(256);
        std::set<std::string> names;
        for (uint32_t i = 0; i < templates; ++i) {
          auto name = n.str(), looks = n.str();
          need(rule_id(name) && rule_id(looks) && names.insert(name).second, "npc template key");
          template_looks.insert(looks);
          auto health = n.u(), level = n.u(), xp = n.u(), damage = n.u();
          auto attack = n.u(), defense = n.u(), accuracy = n.u(), evasion = n.u();
          auto ticks = n.u(), acquisition = n.u();
          // PQ-252 (D-165): the reference rows' iExp (0-50,000,000), sDamage
          // (0, attack within 10,000) and the shorts sAc, sHitRate, sEvadeRate.
          need(health >= 1 && health <= 2000000 && level >= 1 && level <= 255 && xp <= 50000000 &&
                   damage <= 100000 && attack <= 10000 && defense <= 32767 && accuracy <= 32767 &&
                   evasion <= 32767 && ticks >= 1 && ticks <= 1200 && acquisition <= 1,
               "npc template bound");
          auto speed = n.f(), attack_range = n.f(), search = n.f(), tracing = n.f();
          // PQ-251 (D-164): the reference rows' bounds; speed 0 never moves.
          need(speed >= 0.f && speed <= 12.f && attack_range >= .05f && attack_range <= 64.f && search >= .05f &&
                   search <= 64.f && tracing >= .05f && tracing <= 64.f && search <= tracing,
               "npc template range");
          // PQ-272: the drawn scale in percent (KO sSize), 1-1000.
          if (scaled) {
            auto scale = n.u();
            need(scale >= 1 && scale <= 1000, "npc template scale");
          }
        }
      }
      auto slots = n.u();
      need(slots >= 1 && slots <= MAX_SPAWNS, "npc slots");
      for (uint32_t i = 0; i < slots; ++i) {
        int32_t area[4];
        for (auto &v : area) {
          v = static_cast<int32_t>(n.u());
          need(v >= -256 && v <= 256, "npc slot area");
        }
        need(area[0] <= 0 && area[1] <= 0 && area[2] >= 0 && area[3] >= 0, "npc slot area");
        auto respawn = n.u();
        // Reference slots require the life policy; a slot may not respawn before corpse removal.
        need(npc_corpse && respawn >= 1 && respawn <= 12000 && respawn >= *npc_corpse, "npc slot respawn");
        if (templated) need(n.u() < templates, "npc slot template");
      }
    }
    n.end();
  }
  // N3LK (PQ-253, D-166, engine 38): per-template NPC presentation. Exactly
  // the templates' looks keys, each entry with its model npc-looks-<i>.bin;
  // the models' atlases and bytes stay inside fixed budgets.
  // PQ-317 (D-187): an engine 38+ package without NPC templates (the Moradon
  // additions package) carries no looks table; with templates it must.
  need(files.contains("npc-looks.bin") == (engine >= 38 && !template_looks.empty()), "npc looks compatibility");
  if (files.erase("npc-looks.bin")) {
    need(!template_looks.empty(), "npc looks require npc templates");
    Reader k(root / "npc-looks.bin");
    k.magic("N3LK");
    auto entries = k.count(MAX_NPC_LOOKS);
    std::set<std::string> keys;
    for (uint32_t i = 0; i < entries; ++i) {
      NpcLooks looks;
      looks.key = k.str();
      need(looks.key.starts_with(result.game + ":") && looks.key.size() <= 128 &&
               looks.key.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789_:/-") == std::string::npos &&
               keys.insert(looks.key).second,
           "npc looks key");
      auto flags = k.u();
      need(flags <= 1, "npc looks flags");
      looks.name_always = flags == 1;
      for (size_t c = 0; c < looks.clips.size(); ++c) {
        auto &clip = looks.clips[c];
        clip.duration = k.f();
        clip.blend = k.f();
        auto loop = k.u();
        clip.loop_blend = loop == 1;
        clip.markers = k.floats<2>();
        need(clip.duration >= .001f && clip.duration <= 3600 && clip.blend >= 0 && clip.blend <= 2 && loop <= 1 &&
                 !((c == 2 || c == 3) && loop),
             "npc looks clip bounds");
        for (float marker : clip.markers)
          need(marker == -1 || (marker >= 0 && marker <= clip.duration), "npc looks clip marker");
      }
      result.npc_looks.push_back(std::move(looks));
    }
    k.end();
    need(keys == template_looks, "npc looks must cover exactly the templates' looks keys");
    uint64_t texels = 0, bytes = 0;
    for (uint32_t i = 0; i < entries; ++i) {
      auto name = "npc-looks-" + std::to_string(i) + ".bin";
      need(files.erase(name) == 1, "npc looks model");
      bytes += std::filesystem::file_size(root / name);
      std::ifstream model(root / name, std::ios::binary);
      unsigned char head[12];
      model.read(reinterpret_cast<char *>(head), sizeof head);
      const std::string magic(reinterpret_cast<char *>(head), 4);
      need(bool(model) && (magic == "N3NM" || (engine >= 39 && magic == "N3MM") ||
                           (engine >= 40 && (magic == "N3NI" || magic == "N3MI"))),
           "npc looks model magic");
      result.npc_looks[i].materials = magic == "N3MM" || magic == "N3MI";
      result.npc_looks[i].influences = magic == "N3NI" || magic == "N3MI";
      uint32_t size[2];
      for (int d = 0; d < 2; ++d)
        size[d] = uint32_t(head[4 + 4 * d]) | uint32_t(head[5 + 4 * d]) << 8 | uint32_t(head[6 + 4 * d]) << 16 |
                  uint32_t(head[7 + 4 * d]) << 24;
      need(size[0] >= 1 && size[0] <= 1024 && size[1] >= 1 && size[1] <= 1024, "npc looks atlas size");
      texels += uint64_t(size[0]) * size[1] * (result.npc_looks[i].materials ? 4 : 3);
    }
    need(texels <= NPC_LOOKS_TEXTURE_BYTES && bytes <= NPC_LOOKS_MODEL_BYTES, "npc looks byte budget");
  }
  bool has_damage=files.contains("damage.bin");
  if (files.erase("damage.bin")) {
    Reader d(root / "damage.bin");
    need(d.raw(4) == "N3D1" && d.u() == 1, "damage model");
    for (int side = 0; side < 2; ++side) {
      need(d.u() <= 10000 && d.u() <= 10000, "damage stats");
      auto accuracy = d.u(), evasion = d.u();
      need(accuracy >= 1 && accuracy <= 10000 && evasion >= 1 && evasion <= 10000, "damage rates");
    }
    d.end();
  }
  if (files.erase("melee.bin")) {
    Reader m(root / "melee.bin");
    need(m.raw(4) == "N3M1", "melee magic");
    MeleeConfig cfg;
    cfg.actor_radius = m.f();
    cfg.target_radius = m.f();
    cfg.reach = m.f();
    cfg.facing_dot = m.f();
    m.end();
    need(cfg.valid(), "melee bounds");
    result.melee = cfg;
  }
  if (files.erase("camera.bin")) {
    Reader camera(root / "camera.bin");
    auto version = camera.raw(4);
    need(version == "N3V1" || version == "N3V2", "camera magic");
    auto &c = result.camera;
    c.pitch = camera.f();
    c.pitch_min = camera.f();
    c.pitch_max = camera.f();
    c.distance = camera.f();
    c.distance_min = camera.f();
    c.distance_max = camera.f();
    c.focus_height = camera.f();
    c.focus_scale = camera.f();
    c.yaw_per_pixel = camera.f();
    c.pitch_per_pixel = camera.f();
    c.zoom_per_step = camera.f();
    c.clearance = camera.f();
    c.turn_rate = camera.f();
    c.hold_delay = camera.f();
    c.facing_relative = camera.u();
    if (version == "N3V2") {
      c.drag_distance = camera.u();
      c.distance_per_pixel = camera.f();
      c.key_pitch_rate = camera.f();
      c.edge_yaw_rate = camera.f();
    }
    need(c.valid(), "camera policy bounds");
    camera.end();
  }
  if (files.contains("player-ready.bin")) {
    need(engine >= 4 && result.melee && files.contains("hud.bin"), "ready pose compatibility");
    files.erase("player-ready.bin");
    result.ready_pose = true;
  }
  if (files.contains("hud.bin")) {
    result.presentation = true;
    for (const auto *name : {"hud.bin", "player-idle.bin", "player-walk.bin",
                             "player-attack.bin", "player-death.bin"})
      need(files.erase(name) == 1, "incomplete presentation");
    if (files.contains("player-run.bin") ||
        files.contains("player-backward.bin")) {
      need(protocol >= 2 && files.erase("player-run.bin") == 1 &&
               files.erase("player-backward.bin") == 1,
           "incomplete locomotion presentation");
      result.locomotion = true;
    }
  }
  if(files.erase("target-marker.bin")) {
    need(engine>=33 && result.presentation && result.melee,"target marker compatibility");
    Reader r(root/"target-marker.bin", 8*1024*1024);r.magic("N3TM");
    TargetMarker marker{r.f(),r.f(),r.f(),{}, {}};
    need(marker.diameter_scale>0 && marker.diameter_scale<=10 && marker.height_scale>0 && marker.height_scale<=10 && marker.ground_lift>=0 && marker.ground_lift<=1,"marker scale bounds");
    for(auto& b:marker.bounds){b=r.floats<2>();for(auto v:b)need(v>.001f&&v<=100,"marker model bounds");}
    auto count=r.count(8);
    for(unsigned i=0;i<count;++i){
      TargetMarkerPart part{};part.mode=r.u();need(part.mode<=1,"marker part mode");
      part.pivot=r.floats<3>();for(auto v:part.pivot)need(std::abs(v)<=10,"marker pivot bounds");
      part.width=r.count(512);part.height=r.count(512);
      auto pixels=r.raw(size_t(part.width)*part.height*4);part.texture.assign(pixels.begin(),pixels.end());
      auto vertices=r.count(1024,3);
      for(unsigned j=0;j<vertices;++j){
        auto v=r.floats<8>();for(auto x:v)need(std::abs(x)<=10,"marker vertex bounds");
        need(v[3]*v[3]+v[4]*v[4]+v[5]*v[5]>.5f,"marker normal");part.vertices.push_back(v);
      }
      auto indices=r.count(3072,3);need(indices%3==0,"marker triangles");
      for(unsigned j=0;j<indices;++j){auto k=r.u();need(k<vertices,"marker index");part.indices.push_back(k);}
      marker.parts.push_back(std::move(part));
    }
    r.end();result.target_marker=std::move(marker);
  }
  if(files.erase("effects.bin")){
    need(engine>=33&&result.presentation,"effects compatibility");
    result.effects=load_effects(root/"effects.bin");
  }
  if(files.erase("postprocess.bin")){
    need(engine>=33&&result.presentation,"postprocess compatibility");
    result.postprocess=load_postprocess(root/"postprocess.bin");
  }
  if(files.erase("audio.bin")){
    need(engine>=33&&result.presentation,"audio compatibility");
    result.audio=load_audio(root/"audio.bin");
  }
  // Spec 11: hashed above; read whole by load_front_end when the window opens.
  if(files.erase("front-end.bin")){
    need(engine>=42&&result.presentation,"front end compatibility");
    result.front_end=true;
  }
  result.loot_model=files.erase("loot-model.bin")!=0;
  need(!result.loot_model||(engine>=10&&result.presentation&&result.thresholds),"loot model requires durable loot presentation");
  if(files.erase("pick.bin")){
    Reader k(root/"pick.bin");k.magic("N3PK");auto&pick=result.pick;
    auto box=k.u();pick.min_extent=k.f();pick.pad=k.f();pick.mesh_lod=k.u();k.end();
    need(box<=1&&pick.min_extent>=0&&pick.min_extent<=4&&pick.pad>=0&&pick.pad<=4&&pick.mesh_lod<=3,"pick policy bounds");
    pick.joints=box==1;
  }
  if(files.erase("loot-policy.bin")){
    need(result.loot_model,"loot policy requires loot model");
    Reader p(root/"loot-policy.bin");p.magic("N3LP");auto radius=p.f();p.end();
    need(radius>0&&radius<=100,"loot open radius");result.loot_open_radius=radius;
  }
  need((files.erase("editing.bin") != 0) == (engine >= 11), "editing compatibility");
  // Engine 12 adds the static world asset and retains wire 6. It builds on the
  // engine 11 editing contract rather than replacing it.
  result.world = files.erase("world.bin") != 0;
  bool exploration = files.erase("exploration.bin") != 0;
  bool lod = files.erase("world-lod.bin") != 0;
  // N3W2 carries its own parts: exploration without world-lod.bin (engine 13 on).
  need(result.world_chunked ? engine >= 13 && exploration && !lod
       : engine >= 15 ? lod == exploration && (!exploration || result.world)
                   : result.world == (engine >= 12) && exploration == (engine >= 13) && lod == exploration,
       "world/exploration compatibility");
  result.world_textures = files.erase("world-textures.bin") != 0;
  need(result.world_textures == result.world_chunked, "world textures compatibility");
  // N3WO (PQ-387, D-204) draws over the world's terrain: a world and exploration.
  result.world_overlay = files.erase("world-overlay.bin") != 0;
  need(!result.world_overlay || (result.world && exploration), "world overlay compatibility");
  result.render_detail = files.erase("render-detail.bin") != 0;
  need(engine >= 15 ? !result.render_detail || exploration : result.render_detail == (engine == 14), "render detail compatibility");
  if (result.render_detail) {
    need(result.presentation, "render detail requires player presentation");
    // N3D3 (PQ-348, D-191): N3D2 with a render state per appearance entry.
    Reader d(root / "render-detail.bin", 128*1024*1024);
    const auto detail_magic=d.raw(4);
    need(engine>=29?detail_magic=="N3D2"||detail_magic=="N3D3":detail_magic=="N3D1","cooked magic/version");
    result.camera.fov=d.f(); result.camera.near_plane=d.f(); result.camera.far_plane=d.f();
    need(result.camera.fov>=.2f && result.camera.fov<=2.5f && result.camera.near_plane>=.01f &&
         result.camera.near_plane<=2 && result.camera.far_plane>=10 && result.camera.far_plane<=1000, "projection bounds");
  }
  if (exploration) {
    Reader x(root / "exploration.bin"); x.magic("N3X1");
    Exploration policy{x.f(), x.f(), x.f(), x.floats<3>()}; x.end();
    need(policy.multiplier >= 1 && policy.multiplier <= 10 &&
         policy.fog_start >= 0 && policy.fog_start < policy.fog_end && policy.fog_end <= 1000,
         "exploration bounds");
    for (float c : policy.fog_color) need(c >= 0 && c <= 1, "fog colour");
    result.exploration = policy;
  }
  if(engine>=11) {
    Reader e(root/"editing.bin");need(e.raw(4)=="N3T1","editing magic");auto n=e.u();need(n>0&&n<=128,"editing count");std::set<std::string> keys;std::set<std::pair<unsigned,unsigned>> slots;
    for(uint32_t i=0;i<n;++i){EditProperty p;p.key=e.str();p.kind=e.u();p.target=e.u();p.initial=e.f();p.min=e.f();p.max=e.f();
      need(p.key.starts_with(result.game+":")&&p.key.size()<=128&&std::all_of(p.key.begin(),p.key.end(),[](unsigned char c){return std::isalnum(c)||std::string("_:.-").find(c)!=std::string::npos;})&&keys.insert(p.key).second&&slots.insert({p.kind,p.target}).second&&p.kind<=10&&p.target<MAX_SPAWNS&&p.min<=p.initial&&p.initial<=p.max,"editing property");
      float lo=0,hi=1;
      if(p.kind==1||p.kind==2||p.kind==3||p.kind==7||p.kind==8){lo=-1000;hi=1000;}
      else if(p.kind==4){lo=-3.141593f;hi=3.141593f;}else if(p.kind==5){lo=.05f;hi=10;}else if(p.kind==6){hi=0;}else if(p.kind==9){hi=1200;}else if(p.kind==10){lo=1;hi=12000;}
      need(p.min==lo&&p.max==hi&&((p.kind!=0&&p.kind<9)||p.target==0)&&(!(p.kind>=1&&p.kind<=6)||p.target<8)&&(!(p.kind==6||p.kind>=9)||std::floor(p.initial)==p.initial),"editing policy");
      result.editing.push_back(p);}
    e.end();need(slots.contains({0,0}),"lighting required");
    for(auto[k,t]:slots)if(k>=1&&k<=6)for(unsigned j=1;j<=6;++j)need(slots.contains({j,t}),"incomplete decoration");
  }
  bool has_inventory=files.erase("inventory.bin")!=0;need(engine>=23||has_inventory==(engine>=15),"inventory compatibility");
  if(has_inventory) {
    Reader b(root / "inventory.bin"); b.magic("N3I1");
    InventoryPolicy p{b.u(), b.str(), b.u(), b.u(), {}};
    auto identity = [&](const std::string &s) {
      auto prefix = result.game + ":";
      return s.starts_with(prefix) && s.size() > prefix.size() && s.size() <= prefix.size()+96 &&
        s[prefix.size()] >= 'a' && s[prefix.size()] <= 'z' &&
        s.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789_/-",prefix.size()) == std::string::npos;
    };
    need(p.capacity>=1 && p.capacity<=64 && identity(p.currency) && p.limit>=1 && p.limit<=2147483647 && p.coins<=p.limit, "inventory bounds");
    auto n=b.u(); need(n>=1 && n<=64,"item count"); std::set<std::string> ids;
    uint32_t initial=0; bool reward=false;
    for(uint32_t i=0;i<n;++i) {
      ItemDefinition item{b.str(),b.str(),b.u(),b.u(),b.u()};
      need(identity(item.id) && ids.insert(item.id).second && !item.label.empty() && item.label.size()<=64 &&
           std::all_of(item.label.begin(),item.label.end(),[](unsigned char c){return c>=32 && c<=126;}) &&
           item.stack>=1 && item.stack<=9999 && item.durability<=65535 && item.starting<=item.stack,"item definition");
      initial += item.starting>0;
      if(item.id==progression_item) { reward=true; need(item.stack==1 && item.starting==0 && item.durability==0,"reward definition"); }
      p.items.push_back(item);
    }
    b.end(); need(reward && initial<p.capacity && initial+progression_capacity<=p.capacity,"inventory starting capacity");
    result.inventory=std::move(p);
  }
  // N3IH (PQ-354, D-194): item tooltip heads, client presentation over the
  // inventory's items; the bounds are tools/assetc/item_heads.py's.
  if(files.erase("item-heads.bin")){
    need(engine>=33&&result.presentation&&result.inventory.has_value(),"item heads compatibility");
    Reader h(root/"item-heads.bin");h.magic("N3IH");
    ItemHeads heads;heads.token=h.raw(h.count(32,0));
    need(std::all_of(heads.token.begin(),heads.token.end(),[](unsigned char c){return c>=33&&c<=126;}),"item heads token");
    auto n=h.count(64,0);need(n||!heads.token.empty(),"item heads count");
    auto defined=[&](const std::string&id){return std::any_of(result.inventory->items.begin(),result.inventory->items.end(),[&](const auto&i){return i.id==id;});};
    for(uint32_t i=0;i<n;++i){
      auto item=h.raw(h.count(128));ItemHead head{h.u(),{}};
      need(defined(item)&&!heads.heads.contains(item),"item head item");
      need(head.name_color<=0xffffffu,"item head colour");
      auto lines=h.count(4,0);
      for(uint32_t j=0;j<lines;++j){ItemHeadLine line{h.raw(h.count(64)),0};line.color=h.u();
        need(std::all_of(line.text.begin(),line.text.end(),[](unsigned char c){return c>=32&&c<=126;})&&line.color<=0xffffffu,"item head line");
        head.lines.push_back(std::move(line));}
      heads.heads.emplace(std::move(item),std::move(head));
    }
    h.end();result.item_heads=std::move(heads);
  }
  bool has_commerce=files.erase("commerce.bin")!=0;need((engine>=23||has_commerce==(engine>=16))&&(!has_commerce||has_inventory),"commerce compatibility");
  if(has_commerce) {
    Reader r(root/"commerce.bin");r.magic("N3O1");
    CommercePolicy p{r.u(),r.u(),r.u(),r.u(),{}, {}};
    need(p.weight_limit>=1&&p.weight_limit<=2147483647&&p.max_quantity>=1&&p.max_quantity<=9999&&p.bulk_price<=2147483647&&p.bulk_quantity>=1&&p.bulk_quantity<=p.max_quantity,"commerce bounds");
    auto n=r.u();need(n==result.inventory->items.size(),"commerce coverage");std::set<std::string> ids;
    auto defined=[&](const std::string &id){return std::any_of(result.inventory->items.begin(),result.inventory->items.end(),[&](const auto&i){return i.id==id;});};
    for(unsigned j=0;j<n;++j) {
      ItemPrice i{r.str(),r.u(),r.u(),r.u()};need(ids.insert(i.item).second&&defined(i.item)&&i.weight<=1000000&&i.price>=1&&i.price<=2147483647&&i.divisor>=1&&i.divisor<=10000,"commerce item");p.items.push_back(i);
    }
    n=r.u();need(n>=1&&n<=64,"shop count");ids.clear();
    for(unsigned j=0;j<n;++j) {
      Shop shop;shop.id=r.str();shop.label=r.str();shop.position=r.floats<3>();shop.radius=r.f();auto remote=r.u();auto count=r.u();
      const auto prefix=result.game+":";
      need(shop.id.starts_with(prefix)&&shop.id.size()>prefix.size()&&shop.id.size()<=prefix.size()+96&&shop.id[prefix.size()]>='a'&&shop.id[prefix.size()]<='z'&&shop.id.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789_/-",prefix.size())==std::string::npos&&ids.insert(shop.id).second&&
        !shop.label.empty()&&shop.label.size()<=64&&std::all_of(shop.label.begin(),shop.label.end(),[](unsigned char c){return c>=32&&c<=126;})&&std::all_of(shop.position.begin(),shop.position.end(),[](float v){return std::abs(v)<=1000;})&&shop.radius>=.5f&&shop.radius<=20&&remote<=1&&count>=1&&count<=64,"shop bounds");
      shop.remote_sell=remote!=0;std::set<std::string> offers;
      for(unsigned k=0;k<count;++k){auto item=r.str();need(item!=progression_item&&defined(item)&&offers.insert(item).second,"shop offer");shop.items.push_back(item);}
      p.shops.push_back(shop);
    }
    r.end();result.commerce=std::move(p);
  }
  bool has_repair=files.erase("repair.bin")!=0;need((engine>=23||has_repair==(engine>=17))&&(!has_repair||has_commerce),"repair compatibility");
  if(has_repair) {
    Reader r(root/"repair.bin");r.magic("N3J1");auto low=r.u(),high=r.u();
    RepairPolicy p{std::bit_cast<double>(uint64_t(low)|(uint64_t(high)<<32)),r.f(),r.u(),r.f(),{}};auto n=r.u();
    need(std::isfinite(p.power)&&p.power>=.01&&p.power<=1&&p.linear>=0&&p.linear<=1&&p.offset<=1000000&&p.multiplier>=0&&p.multiplier<=1&&n>=1&&n<=64,"repair bounds");std::set<std::string> items;
    for(unsigned j=0;j<n;++j){auto id=r.str();need(items.insert(id).second&&std::any_of(result.inventory->items.begin(),result.inventory->items.end(),[&](const auto&i){return i.id==id&&i.durability>1;}),"repair item");p.items.push_back(id);}
    r.end();result.commerce->repair=std::move(p);
  }
  bool has_equipment=files.erase("equipment.bin")!=0;need((engine>=23||has_equipment==(engine>=18))&&(!has_equipment||has_repair),"equipment compatibility");
  if(has_equipment){
    Reader r(root/"equipment.bin");r.magic("N3Q1");EquipmentPolicy p;p.race=r.u();p.title=r.u();for(auto &a:p.attributes)a=r.u();auto n=r.u();
    need(p.race<=255&&p.title<=255&&std::all_of(p.attributes.begin(),p.attributes.end(),[](auto a){return a<=255;})&&n>=1&&n<=16,"equipment bounds");
    std::set<std::string> names;
    for(unsigned j=0;j<n;++j){auto name=r.str();need(!name.empty()&&name.size()<=32&&std::all_of(name.begin(),name.end(),[](unsigned char c){return c>=32&&c<=126;})&&names.insert(name).second,"equipment slot");p.slots.push_back(name);}
    auto mask=(1u<<n)-1;auto count=r.u();need(count>=1&&count<=64,"equipment count");names.clear();
    for(unsigned j=0;j<count;++j){EquipmentItem i;i.id=r.str();i.slots=r.u();i.blocks=r.u();i.title=r.u();i.race=r.u();for(auto&a:i.attributes)a=r.u();auto swap=r.u();
      need(names.insert(i.id).second&&std::any_of(result.inventory->items.begin(),result.inventory->items.end(),[&](const auto&d){return d.id==i.id&&d.stack==1;})&&i.slots&&((i.slots|i.blocks)&~mask)==0&&(i.slots&i.blocks)==0&&i.title<=255&&i.race<=255&&std::all_of(i.attributes.begin(),i.attributes.end(),[](auto a){return a<=255;})&&swap<=1,"equipment definition");i.swappable=swap;p.items.push_back(i);
    }r.end();result.equipment=std::move(p);
  }
  for(const auto& d:drop_items){need(bool(result.inventory),"drop inventory");const auto& items=result.inventory->items;
    need(std::any_of(items.begin(),items.end(),[&](const auto& i){return i.id==d.id&&i.stack>=d.quantity&&i.durability==d.durability;}),"drop inventory definition");}
  need(drop_currency.empty()||(result.inventory&&result.inventory->currency==drop_currency&&result.inventory->limit<=2100000000),"coin inventory currency");
  bool has_stats=files.erase("stats.bin")!=0;need((engine>=23||has_stats==(engine>=19))&&(!has_stats||has_equipment),"stats compatibility");
  result.equipment_stats=has_stats;
  if(has_stats) {
    need(has_damage,"stats require damage");
    Reader r(root/"stats.bin");r.magic("N3Y1");
    std::array<unsigned,13> v;unsigned j=0;
    for(unsigned hi:{15,15,1,1,100,100,255,100,100,255,255,1000,10000}){v[j]=r.u();need(v[j]<=hi,"stats integer");++j;}
    need(v[0]!=v[1]&&v[0]<result.equipment->slots.size()&&v[1]<result.equipment->slots.size()&&v[7]&&v[8],"stats hand/divisor");
    for(float hi:{1,1,10,1,1,10,10,1,100}){auto f=r.f();need(f>=0&&f<=hi,"stats coefficient");}
    bool resource_polynomial=false;
    for(unsigned k=0;k<3;++k){auto coefficient=r.f();if(k>0&&coefficient!=0)resource_polynomial=true;double linear;
      if(k==0){auto lo=r.u(),hi=r.u();linear=std::bit_cast<double>(uint64_t(lo)|(uint64_t(hi)<<32));}else linear=r.f();
      auto divisor=r.u(),base=r.u(),attribute=r.u(),offset=r.u();
      need(coefficient>=0&&coefficient<=1&&std::isfinite(linear)&&linear>=0&&linear<=1&&divisor>=1&&divisor<=100&&base<=10000&&attribute<=4&&offset<=255,"stats polynomial");
    }
    need(resource_polynomial,"resource polynomial missing");
    auto valid_id=[&](const std::string &id){auto prefix=result.game+":";if(!id.starts_with(prefix))return false;auto s=id.substr(prefix.size());return !s.empty()&&s.size()<=96&&s[0]>='a'&&s[0]<='z'&&std::all_of(s.begin(),s.end(),[](char c){return (c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'||c=='/'||c=='-';});};
    auto n=r.count(32);std::set<std::string> categories,items;
    for(unsigned k=0;k<n;++k){auto id=r.str();auto coefficient=r.f();auto dex=r.u(),offhand=r.u();need(valid_id(id)&&categories.insert(id).second&&coefficient>=0&&coefficient<=1&&dex<=1&&offhand<=2,"stats category");}
    n=r.u();need(n==result.equipment->items.size(),"stats coverage");
    for(unsigned k=0;k<n;++k){auto id=r.str(),category=r.str();need(items.insert(id).second&&categories.contains(category)&&std::any_of(result.equipment->items.begin(),result.equipment->items.end(),[&](const auto&i){return i.id==id;}),"stats item");
      unsigned index=0;auto&bonuses=result.item_stats[id];
      for(unsigned hi:{10000,10000,10000,10000,1000,1000,255,255,255,255,255}){auto value=r.u();need(value<=hi,"stats bonus");bonuses[index++]=value;}
    }r.end();
  }

  bool has_wear=files.erase("wear.bin")!=0;need((engine>=23||has_wear==(engine>=20))&&(!has_wear||has_stats),"wear compatibility");
  if(has_wear){
    Reader r(root/"wear.bin");r.magic("N3U1");auto low=r.u(),high=r.u();double scale=std::bit_cast<double>(uint64_t(low)|(uint64_t(high)<<32));auto n=r.u();
    need(std::isfinite(scale)&&scale>0&&scale<=1&&n==result.equipment->items.size(),"wear bounds");std::set<std::string> seen;
    for(unsigned j=0;j<n;++j){auto id=r.str();auto attack=r.u(),defense=r.u();auto def=std::find_if(result.equipment->items.begin(),result.equipment->items.end(),[&](const auto&i){return i.id==id;});need(def!=result.equipment->items.end()&&seen.insert(id).second&&((attack|defense)&~def->slots)==0,"wear masks/reference");}r.end();
  }
  bool has_combat=files.erase("combat-animation.bin")!=0;
  need(has_combat==(engine>=31),"combat animation compatibility");
  if(has_combat){
    need(result.inventory&&result.equipment,"combat equipment required");
    Reader a(root/"combat-animation.bin");a.magic(engine>=32?"N3A5":"N3A4");CombatAnimation policy;
    auto n=a.count(64);uint64_t bytes=0;
    for(unsigned i=0;i<n;++i){
      auto name="combat-"+std::to_string(i)+".bin";need(files.erase(name)==1,"combat clip missing");
      bytes+=std::filesystem::file_size(root/name);need(bytes<=32*1024*1024,"combat clip byte budget");
      Clip clip;clip.duration=a.f();clip.blend=a.f();auto loop=a.u();clip.loop_blend=loop;clip.markers=a.floats<2>();
      need(clip.duration>=.001f&&clip.duration<=3600&&clip.blend>=0&&clip.blend<=2&&loop<=1,"combat clip bounds");
      for(auto m:clip.markers)need(m==-1||(m>=0&&m<=clip.duration),"combat marker");
      policy.clips.push_back(clip);
    }
    auto np=a.count(32);std::set<unsigned> used;
    for(unsigned j=0;j<np;++j){
      CombatProfile profile;profile.ready=a.u();need(profile.ready<n,"combat ready");used.insert(profile.ready);
      auto na=a.count(4);std::set<unsigned> seen;
      for(unsigned k=0;k<na;++k){auto i=a.u();need(i<n&&!policy.clips[i].loop_blend&&seen.insert(i).second,"combat attack");profile.attacks.push_back(i);used.insert(i);}
      if(engine>=32){profile.interval_ms=a.u();profile.moving=a.u();need(profile.interval_ms>=50&&profile.interval_ms<=60000&&profile.moving<n&&!policy.clips[profile.moving].loop_blend,"combat motion bounds");used.insert(profile.moving);}
      policy.profiles.push_back(profile);
    }
    need(used.size()==n,"unused combat clip");
    auto ns=a.count(4);std::vector<unsigned> slots;std::set<unsigned> slot_set;
    for(unsigned i=0;i<ns;++i){auto s=a.u();need(s<result.equipment->slots.size()&&slot_set.insert(s).second,"combat selector slot");slots.push_back(s);}
    auto nr=a.count(256);std::set<std::vector<unsigned>> rows;bool empty=false;
    for(unsigned i=0;i<nr;++i){std::vector<unsigned> key;
      for(auto slot:slots){auto item=a.u();need(item<=result.inventory->items.size(),"combat item index");key.push_back(item);
        if(item){const auto&id=result.inventory->items[item-1].id;need(std::any_of(result.equipment->items.begin(),result.equipment->items.end(),[&](const auto&g){return g.id==id&&(g.slots&(1u<<slot));}),"combat equipment mapping");}}
      auto profile=a.u();need(profile>=1&&profile<=np&&rows.insert(key).second,"combat row");
      empty|=std::all_of(key.begin(),key.end(),[](auto i){return i==0;});
    }
    need(empty,"combat empty fallback");
    if(engine>=32){auto count=a.count(63);std::set<unsigned> seen;for(unsigned i=0;i<count;++i){auto node=a.u();need(node>0&&node<64&&seen.insert(node).second,"combat upper mask");policy.upper_nodes.push_back(node);}}
    a.end();result.combat_animation=std::move(policy);
  }
  // N3RB (PQ-416, D-216) / N3RC (PQ-420, D-217): ranged basic attacks on N3A5
  // profiles, added to the melee radii; the bounds are
  // tools/assetc/ranged_attack.py's. A cast time stretches the profile's one
  // attack clip (which no other profile or role uses) to it, as 1298's
  // 00461ab0 sets the clip's rate to its frames over the cast time.
  if(files.erase("ranged-attack.bin")){
    need(result.combat_animation&&!result.combat_animation->upper_nodes.empty()&&result.melee,"ranged attack compatibility");
    Reader g(root/"ranged-attack.bin");auto magic=g.raw(4);need(magic=="N3RB"||magic=="N3RC"||magic=="N3RD"||magic=="N3RE"||magic=="N3RF"||magic=="N3RG"||magic=="N3RH","ranged attack magic");
    // N3RD (PQ-421, D-218): per entry an ammo item (0, or a 1-based inventory
    // index that does not wear) and count (0 without, else 1 to its stack
    // limit), then the ammo notice; the server removes the ammo in the
    // strike's durable commit, so the package carries the wear policy.
    // N3RE (PQ-422, D-219): N3RD with, per entry after the ammo count, a hit
    // kind (0 the basic attack's damage, 1 a type-2 skill hit) and its hit
    // rate (1-1000), add damage (0-300) and add damage plus (0-10000), all 0
    // for kind 0. The server resolves the damage; the client only checks it.
    // N3RF (PQ-423, D-220): N3RE with, per entry after the skill hit, the
    // cast effect: a key of 0-64 printable bytes (an effects clip with only
    // triangle records; a key needs a cast time), then 0 joints without a
    // key, else 1-2 distinct joints, each index + 1 (0: the actor) up to 128.
    // N3RG (PQ-417, D-222): N3RF with, per entry after the cast effect, the
    // flight: a key of 0-64 printable bytes (an effects clip with only
    // triangle records; a key needs a cast time), its source joint (index +
    // 1, 0: the actor, up to 128) and speed (1-1000 m/s), a hit key (an
    // effects clip) and joint, and a release audio key; without a flight key
    // every field is 0 or empty.
    // N3RH (PQ-467, D-233): N3RG with, per entry after the flight, the hold:
    // f32 distance (0: none, else 0.5-200 m) and u32 plane (0 3-D, 1 the
    // ground plane; 0 without a hold). Only the server checks it (1298's
    // client does not check the range after the cast starts); the client
    // bounds it.
    bool hold=magic=="N3RH";
    bool flight=magic=="N3RG"||hold,effect=magic=="N3RF"||flight,ammo=magic=="N3RD"||magic=="N3RE"||effect,skill=magic=="N3RE"||effect;bool any_ammo=false;
    auto n=g.count(32);std::set<uint32_t> seen;auto&combat=*result.combat_animation;
    for(uint32_t i=0;i<n;++i){
      auto profile=g.u();RangedAttack ranged;ranged.reach=g.f();ranged.range=g.f();ranged.cast_ms=magic!="N3RB"?g.u():0;
      need(profile>=1&&profile<=combat.profiles.size()&&seen.insert(profile).second,"ranged attack profile");
      need(ranged.range>=.5f&&ranged.range<=100&&ranged.reach>=0&&ranged.reach<=ranged.range,"ranged attack bounds");
      if(ranged.cast_ms){
        need(ranged.cast_ms>100&&ranged.cast_ms<=10000,"ranged cast time");
        const auto&own=combat.profiles[profile-1];need(own.attacks.size()==1,"ranged cast clip");
        uint32_t clip=own.attacks[0];
        for(size_t k=0;k<combat.profiles.size();++k){const auto&o=combat.profiles[k];
          need(o.ready!=clip&&(k+1==profile||(std::find(o.attacks.begin(),o.attacks.end(),clip)==o.attacks.end()&&o.moving!=clip)),"ranged cast clip");}
        auto&c=combat.clips[clip];need(c.markers[0]>=0,"ranged cast clip");
        // The server's landing (combat_animation.rs landing_ticks), bounded the same way.
        double land=std::ceil((double(c.blend)+double(c.markers[0])*(ranged.cast_ms/1000.)/double(c.duration))*20.);
        need(land>=1&&land<=double((own.interval_ms+49)/50),"ranged cast landing");
        c.stretch=float(ranged.cast_ms/1000.)/c.duration;c.duration=ranged.cast_ms/1000.f;
        for(auto&m:c.markers)if(m>=0)m*=c.stretch;
      }
      if(ammo){
        auto item=g.u(),count=g.u();
        if(!item)need(count==0,"ranged ammo count");
        else{
          need(item<=result.inventory->items.size()&&result.inventory->items[item-1].durability==0,"ranged ammo item");
          const auto&def=result.inventory->items[item-1];need(count>=1&&count<=def.stack,"ranged ammo count");
          ranged.ammo=def.id;ranged.ammo_count=count;any_ammo=true;
        }
      }
      if(skill){
        auto kind=g.u(),hit_rate=g.u(),add_damage=g.u(),plus=g.u();
        need(kind==0?(hit_rate==0&&add_damage==0&&plus==0):(kind==1&&hit_rate>=1&&hit_rate<=1000&&add_damage<=300&&plus<=10000),"ranged skill hit");
      }
      if(effect){
        auto key=g.raw(g.count(64,0));need(std::all_of(key.begin(),key.end(),[](unsigned char c){return c>=32&&c<=126;})&&(key.empty()||ranged.cast_ms),"ranged cast effect");
        auto joints=g.count(key.empty()?0:2,key.empty()?0:1);std::set<uint32_t> seen;
        for(uint32_t j=0;j<joints;++j){auto joint=g.count(128,0);need(seen.insert(joint).second,"ranged cast effect joints");ranged.cast_joints.push_back(int(joint)-1);}
        if(!key.empty()){
          need(result.effects&&result.effects->clips.contains(key),"ranged cast effect missing");
          for(const auto&frame:result.effects->clips.at(key).frames)for(const auto&b:frame)need(b.kind==0,"ranged cast effect records");
        }
        ranged.cast_effect=std::move(key);
      }
      if(flight){
        auto printable_key=[&](){auto k=g.raw(g.count(64,0));need(std::all_of(k.begin(),k.end(),[](unsigned char c){return c>=32&&c<=126;}),"ranged flight key");return k;};
        auto key=printable_key();auto joint=g.u();auto speed=g.f();auto hit=printable_key();auto hit_joint=g.u();auto release=printable_key();
        if(key.empty())need(joint==0&&speed==0&&hit.empty()&&hit_joint==0&&release.empty(),"ranged flight");
        else{
          need(ranged.cast_ms&&joint<=128&&speed>=1&&speed<=1000&&hit_joint<=128&&(!hit.empty()||hit_joint==0),"ranged flight");
          need(result.effects&&result.effects->clips.contains(key),"ranged flight missing");
          for(const auto&frame:result.effects->clips.at(key).frames)for(const auto&b:frame)need(b.kind==0,"ranged flight records");
          need(hit.empty()||result.effects->clips.contains(hit),"ranged flight hit missing");
          ranged.flight=std::move(key);ranged.flight_joint=int(joint)-1;ranged.flight_speed=speed;
          ranged.hit=std::move(hit);ranged.hit_joint=int(hit_joint)-1;ranged.release=std::move(release);
        }
      }
      if(hold){
        auto distance=g.f();auto plane=g.u();
        need(distance==0?plane==0:(distance>=.5f&&distance<=200&&plane<=1),"ranged hold");
      }
      combat.profiles[profile-1].ranged=ranged;
    }
    auto printable=[](const std::string&t){return std::all_of(t.begin(),t.end(),[](unsigned char c){return c>=32&&c<=126;});};
    auto notice=g.raw(g.count(96,0));
    need(printable(notice),"ranged attack notice");
    if(ammo){auto line=g.raw(g.count(96,0));need(printable(line),"ranged attack notice");result.combat_animation->ammo_notice=std::move(line);}
    need(!any_ammo||has_wear,"ranged ammo compatibility");
    g.end();result.combat_animation->ranged_notice=std::move(notice);
  }
  bool has_consumables=files.erase("consumables.bin")!=0;
  need((files.erase("skills.bin")!=0)==(engine>=34),"skill compatibility");
  if(engine>=34){
    result.skills=load_skills(root/"skills.bin");std::set<unsigned> clips;
    need(result.skills->archetype.starts_with(result.game+":")&&!result.skills->label.empty()&&result.skills->label.size()<=80,"skill class");
    for(const auto&s:result.skills->entries){
      need(s.id.starts_with(result.game+":")&&std::all_of(s.weapons.begin(),s.weapons.end(),[&](const auto&id){return result.inventory&&std::any_of(result.inventory->items.begin(),result.inventory->items.end(),[&](const auto&i){return i.id==id;});}),"skill references");
      need(result.effects&&result.effects->clips.contains(s.cast_effect)&&result.effects->clips.contains(s.target_effect),"skill effects missing");
      if(clips.insert(s.animation).second)need(files.erase("player-skill-"+std::to_string(s.animation)+".bin"),"skill animation missing");
    }
  }
  need(has_consumables==(engine>=33),"consumable compatibility");
  if(has_consumables){Reader a(root/"consumables.bin");a.magic("N3X1");auto n=a.count(64);std::set<unsigned> seen;
    need(result.inventory.has_value(),"consumable inventory");
    for(unsigned j=0;j<n;++j){auto i=a.u();need(i>0&&i<=result.inventory->items.size()&&seen.insert(i).second,"consumable item");
      const auto&item=result.inventory->items[i-1];Consumable c{item.id,a.u(),a.u(),a.u(),a.u()};
      need(item.durability==0&&c.health<=100000&&c.resource<=100000&&c.health+c.resource>0&&c.delay_ms<=2000&&c.cooldown_ms>=50&&c.cooldown_ms<=60000,"consumable bounds");result.consumables.push_back(c);
    }a.end();
  }
  result.rest=files.erase("rest.bin")!=0;
  need(result.rest==(engine>=30),"rest compatibility");
  if(result.rest){Reader a(root/"rest.bin");a.magic("N3E1");auto interval=a.u(),cooldown=a.u(),n=a.count(255);
    need(interval>=1&&interval<=12000&&cooldown<=1200,"rest bounds");
    for(unsigned i=0;i<n;++i){auto hp=a.u(),num=a.u(),den=a.u(),add=a.u();need(hp<=100000&&num<=100000&&den>=1&&den<=100000&&add<=100000,"rest level");}a.end();}
  bool has_appearance=files.erase("appearance.bin")!=0;
  need(has_appearance==(engine>=29)&&(!has_appearance||(result.equipment&&result.render_detail)),"appearance compatibility");
  if(has_appearance){
    Reader a(root/"appearance.bin");a.magic("N3V1");auto n=a.count(128);std::set<std::pair<std::string,uint32_t>> seen;
    for(unsigned k=0;k<n;++k){AppearanceRule rule{a.str(),a.u()};
      need(rule.slot<result.equipment->slots.size()&&std::any_of(result.equipment->items.begin(),result.equipment->items.end(),[&](const auto&i){return i.id==rule.item&&(i.slots&(1u<<rule.slot));})&&seen.insert({rule.item,rule.slot}).second,"appearance mapping");result.appearance.push_back(rule);}
    a.end();
  }
  // N3AT (PQ-328, D-186): attached characters on N3V1 keys, models in the
  // looks formats; the model meshes are checked when they load.
  if(files.erase("attachments.bin")){
    need(engine>=38&&has_appearance,"attachment compatibility");
    Reader t(root/"attachments.bin");t.magic("N3AT");Attachments a;
    auto flags=t.u();need(flags<=1,"attachment flags");a.per_attachment=flags==1;
    a.rise=t.f();a.hold=t.f();a.fall=t.f();a.period=t.f();
    need(a.rise>0&&a.rise<=a.hold&&a.hold<=a.fall&&a.fall<=a.period&&a.period<=60,"attachment clock");
    for(auto&c:a.color){c=t.f();need(c>=0&&c<=1,"attachment colour");}
    auto n=t.count(MAX_ATTACHMENTS);std::set<uint32_t> keys;
    for(uint32_t i=0;i<n;++i){
      Attachment e;e.key=t.u();need(e.key>=1&&e.key<=result.appearance.size()&&keys.insert(e.key).second,"attachment appearance key");
      e.joint=t.u();e.scale=t.f();e.group=t.u();e.flags=t.u();e.modulate=t.f();e.lit=t.u();
      need(e.joint<64&&e.scale>=.01f&&e.scale<=100&&e.group<MAX_ATTACHMENT_GROUPS&&e.flags<=7&&
           (e.modulate==1||e.modulate==2||e.modulate==4)&&e.lit%3==0,"attachment entry bounds");
      for(size_t c=0;c<e.clips.size();++c){auto&clip=e.clips[c];clip.duration=t.f();clip.blend=t.f();auto loop=t.u();
        clip.loop_blend=loop==1;clip.markers=t.floats<2>();
        need(clip.duration>=.001f&&clip.duration<=3600&&clip.blend>=0&&clip.blend<=2&&loop<=1&&!((c==2||c==3)&&loop),"attachment clip bounds");
        for(float marker:clip.markers)need(marker==-1||(marker>=0&&marker<=clip.duration),"attachment clip marker");}
      // PQ-317 (D-187): a skeletal plug's placement and clip map. It is never
      // optional, lit or emissive (2233 draws it always, with no pulse).
      if(e.flags&Attachment::PLUG){
        need(e.flags==Attachment::PLUG&&e.lit==0&&e.modulate==1,"attachment plug flags");
        e.placement=t.floats<12>();
        for(float v:e.placement)need(std::abs(v)<=100,"attachment plug placement");
        const auto&m=e.placement;
        const float det=m[0]*(m[5]*m[10]-m[6]*m[9])-m[1]*(m[4]*m[10]-m[6]*m[8])+m[2]*(m[4]*m[9]-m[5]*m[8]);
        need(std::abs(det)>=1e-6f,"attachment plug placement");
        auto rows=t.count(MAX_PLUG_CLIPS);need(rows>=1,"attachment plug clip map");std::set<std::pair<uint32_t,uint32_t>> seen;
        for(uint32_t r=0;r<rows;++r){PlugClip c;c.kind=t.u();c.id=t.u();c.slot=t.u();auto once=t.u();c.once=once==1;
          need(c.kind<=PlugClip::SKILL&&(c.kind!=PlugClip::STATE||c.id<=9)&&c.slot<4&&once<=1&&seen.insert({c.kind,c.id}).second,
               "attachment plug clip map");
          // The ids name the package's own combat clips and skill animations.
          need(c.kind!=PlugClip::COMBAT||(result.combat_animation&&c.id<result.combat_animation->clips.size()),"attachment plug combat clip");
          need(c.kind!=PlugClip::SKILL||(result.skills&&std::any_of(result.skills->entries.begin(),result.skills->entries.end(),
               [&](const auto&s){return s.animation==c.id;})),"attachment plug skill animation");
          e.clip_map.push_back(c);}
      }
      a.entries.push_back(e);
    }
    t.end();
    uint64_t texels=0,bytes=0;
    for(uint32_t i=0;i<n;++i){
      auto name="attachment-"+std::to_string(i)+".bin";
      need(files.erase(name)==1,"attachment model");
      bytes+=std::filesystem::file_size(root/name);
      std::ifstream model(root/name,std::ios::binary);unsigned char head[12];
      model.read(reinterpret_cast<char*>(head),sizeof head);
      const std::string magic(reinterpret_cast<char*>(head),4);
      need(bool(model)&&(magic=="N3NM"||(engine>=39&&magic=="N3MM")||(engine>=40&&(magic=="N3NI"||magic=="N3MI"))),"attachment model magic");
      auto&e=a.entries[i];e.materials=magic=="N3MM"||magic=="N3MI";e.influences=magic=="N3NI"||magic=="N3MI";
      uint32_t size[2];
      for(int d=0;d<2;++d)size[d]=uint32_t(head[4+4*d])|uint32_t(head[5+4*d])<<8|uint32_t(head[6+4*d])<<16|uint32_t(head[7+4*d])<<24;
      need(size[0]>=1&&size[0]<=1024&&size[1]>=1&&size[1]<=1024,"attachment atlas size");
      texels+=uint64_t(size[0])*size[1]*(e.materials?4:3);
    }
    need(texels<=ATTACHMENT_TEXTURE_BYTES&&bytes<=ATTACHMENT_MODEL_BYTES,"attachment byte budget");
    result.attachments=std::move(a);
  }
  // N3E2 appearance effects name N3V1 keys (PQ-211).
  if(result.effects)for(const auto&e:result.effects->appearance)need(e.key<=result.appearance.size(),"appearance effect key");
  // N3E3 appearance glows name N3V1 keys too (PQ-315).
  if(result.effects)for(const auto&g:result.effects->glow)need(g.key<=result.appearance.size(),"appearance glow key");
  bool has_storage=files.erase("storage.bin")!=0;need((engine>=23||has_storage==(engine>=21))&&(!has_storage||has_wear),"storage compatibility");
  if(has_storage){
    Reader r(root/"storage.bin");r.magic("N3B1");StoragePolicy p{r.u(),r.u(),{}};auto n=r.u();
    need(p.capacity>=1&&p.capacity<=192&&p.coin_limit>=1&&p.coin_limit<=2100000000&&n>=1&&n<=64,"storage bounds");std::set<std::string> seen;
    for(unsigned j=0;j<n;++j){auto id=r.str(),label=r.str();V pos{r.f(),r.f(),r.f()};auto radius=r.f();auto remote=r.u(),fee=r.u();
      need((id.starts_with(result.game+":")&&id.size()>result.game.size()+1&&id.size()<=result.game.size()+97&&id[result.game.size()+1]>='a'&&id[result.game.size()+1]<='z'&&id.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789_/-",result.game.size()+1)==std::string::npos)&&seen.insert(id).second&&label.size()<=64&&std::all_of(label.begin(),label.end(),[](unsigned char c){return c>=32&&c<=126;})&&std::abs(pos[0])<=1000&&std::abs(pos[1])<=1000&&std::abs(pos[2])<=1000&&radius>=.5f&&radius<=20&&remote<=1&&fee<=2100000000,"storage service");
      p.services.push_back({id,label,pos,radius,remote!=0,fee});
    }r.end();result.storage=std::move(p);
  }
  bool has_credential=files.erase("storage-auth.bin")!=0;need((engine>=23||has_credential==(engine==22))&&(!has_credential||has_storage),"storage credential compatibility");
  if(has_credential){
    Reader r(root/"storage-auth.bin");r.magic("N3K1");auto lo=r.u(),hi=r.u(),comparison=r.u();auto alphabet=r.str();auto n=r.u();
    need(comparison<=1&&lo>=1&&lo<=hi&&hi<=128&&!alphabet.empty()&&alphabet.size()<=94&&n<=400&&std::all_of(alphabet.begin(),alphabet.end(),[](unsigned char c){return c>=33&&c<=126;})&&std::adjacent_find(alphabet.begin(),alphabet.end(),[](char a,char b){return a>=b;})==alphabet.end(),"storage credential bounds");
    std::set<std::string> seen;for(unsigned i=0;i<n;++i){auto word=r.str();need(!word.empty()&&word.size()<=64&&seen.insert(word).second&&std::all_of(word.begin(),word.end(),[](unsigned char c){return c>=32&&c<=126&&!(c>='a'&&c<='z');}),"storage credential word");}
    r.end();result.storage_auth=true;
  }
  bool has_party=files.erase("party.bin")!=0;need(has_party==(engine>=24),"party compatibility");
  if(has_party){Reader r(root/"party.bin");r.magic("N3Z1");PartyPolicy p{};p.capacity=r.u();p.name_bytes=r.u();
    auto real=[&](){uint64_t bits=r.u();bits|=uint64_t(r.u())<<32;return std::bit_cast<double>(bits);};p.minimum=real();p.maximum=real();p.gap=r.u();p.repeat_ticks=r.u();
    need(p.capacity>=2&&p.capacity<=8&&p.name_bytes>=1&&p.name_bytes<=24&&std::isfinite(p.minimum)&&std::isfinite(p.maximum)&&p.minimum>=0&&p.minimum<=1&&p.maximum>=1&&p.maximum<=10&&p.gap<=100&&p.repeat_ticks<=1200,"party policy");r.end();result.party=p;}
  bool has_friends=files.erase("friends.bin")!=0;need(engine>=24||has_friends==(engine==23),"friends compatibility");
  if(has_friends){Reader r(root/"friends.bin");r.magic("N3F1");FriendPolicy p{r.u(),r.u(),r.u()};need(p.capacity>=1&&p.capacity<=24&&p.name_bytes>=1&&p.name_bytes<=24&&p.refresh_ticks>=1&&p.refresh_ticks<=1200,"friend policy");r.end();result.friends=p;}


  if(files.erase("input.bin")){
    // Package input map (PQ-009, D-136). Every name must be in the engine's
    // vocabulary; a reserved key or a duplicate binding is refused, as is a
    // mouse gesture on a held action or with the typing flag (PQ-011).
    Reader r(root/"input.bin");auto magic=r.raw(4);need(magic=="N3I1"||magic=="N3I2"||magic=="N3I3"||magic=="N3I4"||magic=="N3I5"||magic=="N3I6"||magic=="N3I7"||magic=="N3I8","input map magic");
    std::vector<InputBinding> bindings(r.count(input::max_bindings));
    std::set<std::tuple<std::string,std::string,uint32_t,uint32_t>> seen;
    for(auto&b:bindings){
      b.action=r.str();b.key=r.str();b.require=r.u();b.forbid=r.u();b.flags=r.u();
      auto action=input::find(input::action_names,b.action);
      need(action&&input::find(input::key_names,b.key)&&!input::reserved(b.key)&&
           !(input::mouse(b.key)&&(input::held(input::Action(*action))||(b.flags&input::typing)))&&
           !(b.require&~input::all_modifiers)&&!(b.forbid&~input::all_modifiers)&&!(b.require&b.forbid)&&!(b.flags&~input::all_flags)&&
           seen.emplace(b.action,b.key,b.require,b.forbid).second,"input binding");
    }
    if(magic!="N3I1"){
      // Name display (PQ-014): bit 0 shown at start, bits 1-3 the classes the
      // toggle hides (self, other players, NPCs); at least one class.
      auto word=r.u();need(!(word&~0xfu)&&(word>>1),"input name display");
      result.names={(word&1)!=0,word>>1,std::nullopt,std::nullopt,{}};
    }
    // N3I4 (PQ-166): a u32 lifetime flag (0 or 1) and, when 1, the N3I3 record;
    // then the party-name flags and colour. N3I5 (PQ-173): the lifetime flag
    // and record, a u32 party flag (0 or 1) and, when 1, the party record, then
    // the per-class camera distance limits. N3I6 (PQ-174): the N3I5 layout,
    // whose class mask may be 0, then the NPC label lifetime record. N3I7
    // (PQ-177): the N3I5 layout, whose class mask may be 0, a u32 NPC lifetime
    // flag (0 or 1) and, when 1, the N3I6 record, then the NPC info line.
    // N3I8 (PQ-178): the N3I7 layout with a u32 flag (0 or 1) before the NPC
    // info line, present when 1, then the operator chat colour.
    bool n3i8=magic=="N3I8",n3i7=magic=="N3I7"||n3i8,n3i6=magic=="N3I6",limits=magic=="N3I5"||n3i6||n3i7;
    bool has_lifetime=magic=="N3I3",has_party=magic=="N3I4";
    if(magic=="N3I4"||limits){auto flag=r.u();need(flag<=1,"input name lifetime flag");has_lifetime=flag==1;}
    if(has_lifetime){
      // Other-player label lifetime (PQ-169): measuring point, acquire and
      // release radii (0 < acquire <= release <= 1000) and the exempt classes.
      NameLifetimePolicy l;l.from=r.u();l.acquire=r.f();l.release=r.f();l.exempt=r.u();
      need(l.from<=NameLifetimePolicy::camera&&std::isfinite(l.acquire)&&std::isfinite(l.release)&&
           l.acquire>0&&l.acquire<=l.release&&l.release<=1000&&!(l.exempt&~NameLifetimePolicy::all_exempt),"input name lifetime");
      result.names.lifetime=l;
    }
    if(limits){auto flag=r.u();need(flag<=1,"input party names flag");has_party=flag==1;}
    if(has_party){
      // Bit 0 drawn while the toggle hides players, bit 1 beyond the camera
      // distance limit, bit 2 colour set; an unset colour is 0.
      auto flags=r.u(),color=r.u();
      need(!(flags&~7u)&&color<=0xffffffu&&((flags&4)||!color),"input party names");
      result.names.party=PartyNamePolicy{(flags&1)!=0,(flags&2)!=0,(flags&4)?std::optional<uint32_t>(color):std::nullopt};
    }
    if(limits){
      // Class mask (bits 0-2 self, other players, NPCs; at least one in N3I5,
      // possibly none in N3I6), then one limit per set bit in that order:
      // finite, 0 < limit <= 1000.
      auto mask=r.u();need((mask||n3i6||n3i7)&&!(mask&~7u),"input name distance classes");
      for(unsigned i=0;i<3;++i)if(mask&(1u<<i)){
        float limit=r.f();need(std::isfinite(limit)&&limit>0&&limit<=1000,"input name distance");
        result.names.distance[i]=limit;
      }
    }
    bool has_npc_lifetime=n3i6;
    if(n3i7){auto flag=r.u();need(flag<=1,"input npc name lifetime flag");has_npc_lifetime=flag==1;}
    if(has_npc_lifetime){
      // NPC label lifetime (PQ-174): measuring point, acquire and release radii
      // (0 < acquire <= release <= 1000) and flags (bit 0 band release, bit 1
      // always named beyond the camera limit, bit 2 dropped once dead).
      NpcNameLifetimePolicy n;n.range.from=r.u();n.range.acquire=r.f();n.range.release=r.f();auto flags=r.u();
      need(n.range.from<=NameLifetimePolicy::camera&&std::isfinite(n.range.acquire)&&std::isfinite(n.range.release)&&
           n.range.acquire>0&&n.range.acquire<=n.range.release&&n.range.release<=1000&&!(flags&~7u),"input npc name lifetime");
      n.range.band=(flags&1)!=0;n.always=(flags&2)!=0;n.drop_dead=(flags&4)!=0;
      result.names.npc_lifetime=n;
    }
    bool has_npc_info=n3i7;
    if(n3i8){auto flag=r.u();need(flag<=1,"input npc info line flag");has_npc_info=flag==1;}
    if(has_npc_info){
      // NPC info line (PQ-177): u32 colour (0xRRGGBB) and the text, 1-64
      // printable ASCII bytes with exactly one `{id}`, at most one state
      // placeholder (PQ-186) and no other brace.
      NpcInfoPolicy info;info.color=r.u();info.text=r.str();
      need(info.color<=0xffffffu&&npc_info_text_valid(info.text),"input npc info line");
      result.names.npc_info=std::move(info);
    }
    if(n3i8){
      // Operator chat colour (PQ-178): 0xRRGGBB for a line the server marks.
      auto color=r.u();need(color<=0xffffffu,"input operator chat colour");
      result.names.operator_chat=color;
    }
    r.end();result.input=std::move(bindings);
  }
  need(files == std::set<std::string>{"collision.bin", "recipe.json",
                                      "scene.bin", "gameplay.bin"},
       "release asset set");
  Reader rules(root / "gameplay.bin");
  auto magic = rules.raw(4);
  need(magic == "N3G1" || magic == "N3G2" || magic == "N3G3", "gameplay magic");
  need(protocol >= 3 || (magic == "N3G3") == (protocol == 2), "movement compatibility");
  rules.str(); auto rule_item = rules.str(); rules.str();
  need(engine < 9 || progression_item == rule_item, "progression item");
  uint32_t resource = 0, cost = 0, cooldown = 0;
  for (int i = 0; i < 15; ++i) {
    auto v = rules.u();
    if (engine >= 9 && i == 10) need(v == progression_capacity, "progression capacity");
    if (engine >= 9 && i == 11) need(v == progression_starting, "progression starting");
    if (i == 1)
      resource = v;
    if (i == 3)
      cost = v;
    if (i == 4)
      cooldown = v;
    if (i == 6)
      result.npc_health = v;
  }
  need(result.npc_health >= 1 && result.npc_health <= 100000, "NPC health");
  need(resource >= 1 && resource <= 100000 && cost <= resource &&
           (cost > 0 || result.melee),
       "action cost");
  need(cooldown >= 1 && cooldown <= 1200, "action interval");
  if (result.melee)
    result.melee->cooldown_ticks = cooldown;
  if (magic == "N3G3") {
    MovementConfig cfg;
    cfg.walk = rules.f();
    for (int i = 0; i < 7; ++i)
      rules.f();
    float cell = rules.f();
    need(cell >= 1 && cell <= 64, "interest bounds");
    auto count = rules.count(MAX_SPAWNS);
    for (uint32_t i = 0; i < count; ++i) {
      rules.f();
      rules.f();
    }
    cfg.run = rules.f();
    cfg.backward = rules.f();
    cfg.radius = rules.f();
    cfg.height = rules.f();
    cfg.step_height = rules.f();
    need(cfg.valid(), "movement policy bounds");
    rules.end();
    result.movement = cfg;
  }
  need(!result.exploration || result.movement.has_value(), "turbo requires movement");
  need(!result.locomotion || result.movement.has_value(), "locomotion requires movement");
  if (!has_camera)
    result.camera.facing_relative = result.movement.has_value();
  return result;
}
bool MeleeConfig::valid() const {
  auto b = [](float v, float lo, float hi) {
    return std::isfinite(v) && v >= lo && v <= hi;
  };
  return b(actor_radius, .1f, 5) && b(target_radius, .1f, 5) &&
         b(reach, 0, 5) && b(facing_dot, 0, .99f);
}
bool CameraConfig::valid() const {
  auto b = [](float v, float lo, float hi) {
    return std::isfinite(v) && v >= lo && v <= hi;
  };
  return b(pitch_min, .05f, 1.4f) && b(pitch_max, pitch_min, 1.4f) &&
         b(pitch, pitch_min, pitch_max) && b(distance_min, .5f, 32) &&
         b(distance_max, distance_min, 32) &&
         b(distance, distance_min, distance_max) && b(focus_height, 0, 3) &&
         b(focus_scale, 0, 1) && b(yaw_per_pixel, .0001f, .05f) &&
         b(pitch_per_pixel, .0001f, .05f) && b(zoom_per_step, .01f, 4) &&
         b(clearance, .1f, .5f) && b(turn_rate, .1f, 6.3f) &&
         b(hold_delay, 0, 1) && facing_relative <= 1 && drag_distance <= 1 &&
         b(distance_per_pixel, .0001f, .5f) && b(key_pitch_rate, 0, 6.3f) &&
         b(edge_yaw_rate, 0, 6.3f);
}
bool MovementConfig::valid() const {
  auto bounded = [](float v, float lo, float hi) {
    return std::isfinite(v) && v >= lo && v <= hi;
  };
  return bounded(walk, .01f, 6) && bounded(run, .01f, 6) &&
         bounded(backward, .01f, 6) && bounded(radius, .1f, 1) &&
         bounded(height, .5f, 3) && bounded(step_height, .05f, .5f) &&
         backward <= walk && walk <= run && step_height < height;
}
float MovementConfig::speed(uint32_t mode) const {
  need(mode <= 2, "invalid movement mode");
  return mode == 0 ? walk : mode == 1 ? run : backward;
}
Hud load_hud(const Release &release) {
  need(release.presentation, "missing presentation");
  Reader r(release.root / "hud.bin");
  auto magic = r.raw(4);
  need(magic == "N3H1" || magic == "N3H2" || magic == "N3H3" || magic == "N3H4" || magic == "N3H5" || magic == "N3H6" || magic == "N3H7" || magic == "N3H8" || magic == "N3H9" || magic == "N3HA" || magic == "N3HB" || magic == "N3HC" || magic == "N3HD" || magic == "N3HE", "HUD magic/version");
  // N3HE (PQ-217) is the N3HB layout with a panel word per record (0, or 15 for
  // the overview map) and N3HD's overview map block: a zone package's map
  // without the feature dialogs.
  bool basic_overview=magic=="N3HE";
  bool overview=magic=="N3HD"||basic_overview;
  bool movable=magic=="N3HC"||magic=="N3HD";
  bool names=magic=="N3H9"||magic=="N3HA"||movable;
  bool hotbar=magic=="N3H8"||names;
  bool tooltips=magic=="N3H7" || hotbar;
  bool portraits = magic == "N3H6" || tooltips;
  bool icons = magic == "N3H5" || portraits;
  bool controls = magic != "N3H1";
  bool dialogs = magic == "N3H4" || icons;
  bool measured = magic == "N3H3" || magic == "N3HB" || basic_overview || dialogs;
  Hud h; h.dialogs=dialogs; h.hotbar=hotbar;
  // N3HA wraps the N3H9 layout and N3HB the N3H3 layout behind a scale policy;
  // N3HC is N3HA plus persistent HUD panels 11-14 and a draggable panel table;
  // N3HD adds an overview map on toggled panel 15.
  if(magic=="N3HA"||magic=="N3HB"||movable||basic_overview){auto policy=r.u();need(policy<=1,"HUD scale policy");h.pixel_scale=policy==1;}
  h.font = r.u();
  h.target_health = r.f();
  h.level_xp = r.f();
  need(h.target_health > 0 && h.level_xp > 0, "HUD maxima");
  // Imported HUD metadata may predate the current gameplay rules.
  h.target_health = float(release.npc_health);
  auto nt = r.count(dialogs ? 64 : 16);
  for (uint32_t i = 0; i < nt; ++i) {
    HudTexture t{r.count(1024), r.count(1024), {}};
    auto pixels = r.raw(t.width * t.height * 4);
    t.pixels.assign(pixels.begin(), pixels.end());
    h.textures.push_back(std::move(t));
  }
  need(h.font < nt && h.textures[h.font].width == 256 &&
           h.textures[h.font].height == 128,
       "HUD font atlas");
  if (measured) {
    h.font_advance = r.f(); h.font_height = r.u(); h.font_top = r.u();
    need(h.font_advance >= 1 && h.font_advance <= 16 &&
         h.font_height >= 1 && h.font_height <= 20 && h.font_top <= 20 &&
         h.font_top + h.font_height <= 20, "HUD font metrics");
  }
  if (controls) {
    auto nc = r.count(dialogs ? 512 : 256, 0);
    for (uint32_t i = 0; i < nc; ++i) {
      HudControl c{r.u(), r.u(), r.u(), r.u()};
      need(c.parent <= i && c.visibility <= (release.rest?5u:3u) && c.selection <= 3 && c.enabled <= 1,
           "HUD control");
      h.controls.push_back(c);
    }
  }
  auto nr = r.count(dialogs ? 4096 : 2048);
  const std::set<std::string> bindings = {"",
                                          "health",
                                          "resource",
                                          "xp",
                                          "target_health",
                                          "health_text",
                                          "resource_text",
                                          "xp_text",
                                          "position",
                                          "target_name",
                                          "player_name",
                                          "combat",
                                          "chat",
                                          "chat_input",
                                          "strike",
                                          "inventory", "equipment", "party", "features",
                                          "exit",
                                          "walk",
                                          "run",
                                          "unavailable", "rest", "skills",
                                          // PQ-408: the message line's scroll bar (N3HS).
                                          "message_up", "message_down", "message_track", "message_thumb"};
  for (uint32_t i = 0; i < nr; ++i) {
    HudRecord q;
    q.kind = r.u();
    q.anchor = r.floats<2>();
    q.rect = r.floats<4>();
    q.texture = r.u();
    q.uv = r.floats<4>();
    q.binding = r.raw(r.count(200, 0));
    q.text = r.raw(r.count(200, 0));
    q.color = r.u();
    q.target = r.u();
    q.align = r.u();
    if (controls) {
      q.control = r.u();
      q.states = r.u();
      need(q.control <= h.controls.size() && q.states >= 1 && q.states <= 15 &&
               (q.control || q.states == 15) && (q.kind != 2 || q.states == 15),
           "HUD control record");
    }
    if (measured) {
      q.text_flags = r.u();
      need(q.text_flags <= 7 && (q.text_flags & 6) != 6 &&
           (!(q.text_flags & 6) || (q.text_flags & 1)) &&
           (q.kind == 1 || q.text_flags == 0), "HUD text flags");
      if (q.kind == 1) for (float a : q.rect)
        need(a == std::trunc(a), "HUD text integer rectangle");
    }
    need(q.kind <= 2 && q.texture < nt && q.target <= 1 && q.align <= 2 &&
             (bindings.contains(q.binding) || (overview && ((q.binding=="minimap"&&q.kind==0)||(q.binding=="toggle_minimap"&&q.kind==2))) || (portraits && q.binding=="portrait") || (icons && (q.binding=="item" || q.binding=="item_label")) || (dialogs && (q.binding=="value" || q.binding=="action" || q.binding=="meter"))),
         "HUD record");
    for (float a : q.anchor)
      need(a >= 0 && a <= 1, "HUD anchor");
    for (float a : q.rect)
      need(std::abs(a) <= 16384, "HUD coordinate");
    for (float a : q.uv)
      need(a >= 0 && a <= 1, "HUD UV");
    need(q.rect[0] <= q.rect[2] && q.rect[1] <= q.rect[3] &&
             q.uv[0] <= q.uv[2] && q.uv[1] <= q.uv[3],
         "HUD rectangle");
    if(basic_overview){q.panel=r.u();need((q.panel==0||q.panel==15)&&(q.binding!="minimap"||q.panel==15),"HUD panel");}
    if(dialogs){q.panel=r.u();need(q.panel<=(movable?15u:release.skills?10u:tooltips?9u:8u)&&(q.binding!="minimap"||q.panel==15),"HUD panel");
      if(q.binding=="value"||q.binding=="action"||q.binding=="meter"||q.binding=="item"||q.binding=="item_label"||q.binding=="portrait"){
        need(!q.text.empty()&&q.text.size()<=64&&std::all_of(q.text.begin(),q.text.end(),[](unsigned char c){return (c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'||c==':';}),"HUD feature key");
        need(q.kind==((q.binding=="value"||q.binding=="item_label")?1u:q.binding=="action"?2u:0u),"HUD feature kind");
      }
    }
    h.records.push_back(std::move(q));
  }
  if(icons){
    auto count=r.count(256,0);auto prefix=release.game+":";
    for(uint32_t i=0;i<count;++i){
      auto item=r.str();HudIcon icon{r.u(),r.floats<4>()};
      need(item.starts_with(prefix)&&item.size()>prefix.size()&&item.size()<=prefix.size()+96&&
           item[prefix.size()]>='a'&&item[prefix.size()]<='z'&&
           item.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789_/-",prefix.size())==std::string::npos,"HUD icon namespace");
      need(icon.texture<nt&&icon.texture!=h.font,"HUD icon texture");
      for(float v:icon.uv)need(v>=0&&v<=1,"HUD icon UV");
      need(icon.uv[0]<icon.uv[2]&&icon.uv[1]<icon.uv[3],"HUD icon rectangle");
      need(h.item_icons.emplace(item,icon).second,"HUD duplicate item icon");
    }
  }
  if(portraits){
    auto count=r.count(8,0);
    for(uint32_t i=0;i<count;++i){
      auto key=r.str();HudPortrait view{r.f(),r.f(),r.f()};
      need(!key.empty()&&key.size()<=64&&key.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789_")==std::string::npos,"HUD portrait key");
      need(std::abs(view.yaw)<=180&&std::abs(view.pitch)<=80&&view.framing>=1&&view.framing<=4,"HUD portrait view");
      need(h.portraits.emplace(key,view).second,"HUD duplicate portrait");
    }
    for(const auto&q:h.records)if(q.binding=="portrait")need(h.portraits.contains(q.text),"HUD missing portrait");
  }
  if(tooltips){
    HudTooltip t{{r.u(),r.floats<4>()},r.f(),r.f(),r.f(),{}};
    need(t.background.texture<nt&&t.background.texture!=h.font,"tooltip texture");
    for(auto uv:t.background.uv)need(uv>=0&&uv<=1,"tooltip UV");
    need(t.background.uv[0]<t.background.uv[2]&&t.background.uv[1]<t.background.uv[3]&&t.width_padding>=16&&t.width_padding<=100&&t.height_padding>=8&&t.height_padding<=100&&t.gap>=0&&t.gap<=100,"tooltip layout");
    auto count=r.count(30);float previous=-1;
    for(unsigned i=0;i<count;++i){auto row=r.floats<2>();need(row[0]>=0&&row[0]>previous&&row[1]>row[0]&&row[1]<=768,"tooltip row");previous=row[0];t.rows.push_back(row);}
    h.tooltip=std::move(t);
  }
  if(hotbar){
    auto count=r.count(64,0);
    for(unsigned i=0;i<count;++i){
      auto item=r.str();HudIcon icon{r.u(),r.floats<4>()};
      need(std::any_of(release.consumables.begin(),release.consumables.end(),[&](const auto&c){return c.item==item;})||(release.skills&&std::any_of(release.skills->entries.begin(),release.skills->entries.end(),[&](const auto&s){return s.id==item;})),"HUD shortcut action");
      need(icon.texture<nt&&icon.texture!=h.font,"HUD action texture");
      for(float v:icon.uv)need(v>=0&&v<=1,"HUD action UV");
      need(icon.uv[0]<icon.uv[2]&&icon.uv[1]<icon.uv[3],"HUD action rectangle");
      need(h.action_icons.emplace(item,icon).second,"HUD duplicate action");
    }
    h.cooldown_color=r.u();
    for(auto &frame:h.cooldown_frames){frame=r.u();need(frame<nt&&frame!=h.font,"HUD cooldown texture");}
  }
  if(names){
    NameplateStyle n{r.f(),r.f(),r.f(),r.f(),{r.u(),r.u(),r.u()},{},{}};
    need(n.distance>0&&n.distance<=1000&&n.padding>=0&&n.padding<=1&&n.gap>=0&&n.gap<=32&&n.seated_fraction>=0&&n.seated_fraction<=1,"nameplate policy");
    for(auto&font:n.fonts){
      font.texture=r.u();font.height=r.u();font.top=r.u();
      need(font.texture<nt&&font.texture!=h.font&&h.textures[font.texture].width==512&&h.textures[font.texture].height==192,"nameplate atlas");
      need(font.height>=1&&font.height<=32&&font.top+uint64_t(font.height)<=32,"nameplate font metrics");
      for(auto&advance:font.advances){advance=r.f();need(advance>0&&advance<=28,"nameplate advance");}
    }
    for(auto&profile:n.profiles){profile.height=r.f();profile.root=r.u();need(profile.height>0&&profile.height<=100&&profile.root<64,"nameplate model");}
    for(unsigned i=0;i<2;++i){
      auto model=load_scene(release,i?"scene.bin":"player-idle.bin");
      auto root=n.profiles[i].root;
      need(root<model.nodes.size()&&model.nodes[root].parent==-1&&
           std::any_of(model.joints.begin(),model.joints.end(),[&](const auto&joint){return joint.node==root;}),"nameplate root joint");
    }
    h.nameplates=std::move(n);
  }
  if(movable){
    auto count=r.count(8,0);std::set<uint32_t> panels;std::map<uint32_t,unsigned> keys;
    for(unsigned i=0;i<count;++i){
      HudMovable m{r.u(),r.u(),r.floats<2>(),r.floats<4>(),r.floats<4>(),r.u(),{}};m.key=r.raw(r.count(32,0));
      need(m.panel>=1&&m.panel<=15&&m.panel!=8&&m.panel!=9&&panels.insert(m.panel).second&&m.group<=15&&m.snap<=32,"HUD movable panel");
      for(float a:m.anchor)need(a>=0&&a<=1,"HUD movable anchor");
      for(float a:m.handle)need(std::abs(a)<=16384,"HUD movable coordinate");
      for(float a:m.bounds)need(std::abs(a)<=16384,"HUD movable coordinate");
      need(m.handle[0]<m.handle[2]&&m.handle[1]<m.handle[3]&&m.bounds[0]<m.bounds[2]&&m.bounds[1]<m.bounds[3]&&
           m.handle[0]>=m.bounds[0]&&m.handle[1]>=m.bounds[1]&&m.handle[2]<=m.bounds[2]&&m.handle[3]<=m.bounds[3],"HUD movable handle");
      need(m.key.find_first_not_of("abcdefghijklmnopqrstuvwxyz_")==std::string::npos,"HUD movable key");
      // One saved position per group: the other members follow it rigidly.
      if(!m.key.empty())need(++keys[m.group]==1,"HUD movable group key");
      h.movables.push_back(std::move(m));
    }
    for(const auto&q:h.records)need(q.panel<11||panels.contains(q.panel)||(overview&&q.panel==15),"HUD persistent panel");
    need(!panels.contains(15),"HUD minimap panel is not draggable");
  }
  if(overview){
    HudMinimap m{r.u(),r.floats<2>(),r.f(),r.f(),r.f(),r.f(),r.f(),{}};
    for(auto&c:m.colors)c=r.u();
    need(m.texture<nt&&m.texture!=h.font&&std::abs(m.origin[0])<=65536&&std::abs(m.origin[1])<=65536&&
         m.extent>0&&m.extent<=65536&&m.zoom>=1&&m.zoom<=64&&m.arrow_ratio>0&&m.arrow_ratio<=1&&
         m.marker_inner>0&&m.marker_inner<=m.marker_outer&&m.marker_outer<=16,"HUD minimap");
    need(std::count_if(h.records.begin(),h.records.end(),[&](const auto&q){return q.binding=="minimap"&&q.texture==m.texture;})==1&&
         std::count_if(h.records.begin(),h.records.end(),[](const auto&q){return q.binding=="minimap";})==1,"HUD minimap image");
    h.minimap=m;
  }
  // PQ-407 (D-210): an optional message block after every other part, in any
  // HUD version; a HUD without one keeps one row in its text record's colour.
  if(r.p<r.b.size()){
    need(r.raw(4)=="N3HM","HUD trailing data");
    HudMessages m{r.u(),r.u(),r.u()};
    need(m.rows>=1&&m.rows<=16,"HUD message rows");
    need(std::any_of(h.records.begin(),h.records.end(),[](const auto&q){return q.kind==1&&q.binding=="combat";}),"HUD message line");
    // PQ-408 (D-211): an optional scroll block after it.
    if(r.p<r.b.size()){
      need(r.raw(4)=="N3HS","HUD trailing data");
      HudMessageScroll s{r.u(),r.u(),r.u(),r.u(),r.f()};
      need(s.records>=1&&s.records<=1024&&s.lines>=m.rows&&s.lines<=4096&&s.line_step>=1&&s.line_step<=64&&
           s.page_step>=1&&s.page_step<=64&&s.repeat>0&&s.repeat<=10,"HUD message scroll");
      m.scroll=s;
    }
    h.messages=m;
  }
  // The scroll bar's records: one each with a scroll block, none without.
  {
    auto one=[&](const char*binding,uint32_t kind)->const HudRecord*{
      const HudRecord*found=nullptr;size_t n=0;
      for(const auto&q:h.records)if(q.binding==binding){found=&q;++n;}
      need(h.messages&&h.messages->scroll?n==1&&found->kind==kind:n==0,"HUD message scroll records");
      return found;
    };
    one("message_up",2);one("message_down",2);
    auto track=one("message_track",2);auto thumb=one("message_thumb",0);
    if(track)need(thumb->panel==track->panel&&thumb->anchor==track->anchor&&thumb->rect[1]>=track->rect[1]&&
                  thumb->rect[3]<=track->rect[3]&&thumb->rect[3]-thumb->rect[1]>0&&
                  thumb->rect[3]-thumb->rect[1]<track->rect[3]-track->rect[1],"HUD message thumb");
  }
  r.end();
  return h;
}
namespace {
// What a part may reference: the vertex count, parents and index list of the
// file (N3W1 with N3L1-3) or chunk (N3W2) that holds it.
struct PartScope {
  std::string version;  // N3L1 .. N3L5 or N3W2 .. N3W6
  uint32_t vertices;
  const std::vector<WorldParent> &parents;
  std::vector<uint32_t> &indices;
  const TerrainDetail *terrain;  // null: no terrain policy, so no kind-2 parts
  std::set<std::pair<uint32_t,uint32_t>> &patches;
  uint64_t &split_work;
  float slots = 0;  // the world's texture count, for N3W6 sequence slots
};
// `unlit` (N3W5, D-203): a vertex's second slot may be WORLD_UNLIT_VERTEX, a
// single-layer unlit vertex; every other slot names a texture below `slots`.
void read_world_vertices(Reader &r, uint32_t nv, float slots, std::vector<float> &out, bool unlit = false) {
  out.reserve(out.size() + size_t(nv) * WORLD_FLOATS);
  for (uint32_t i = 0; i < nv; i++) {
    auto point = r.floats<3>();
    auto n = r.floats<3>(); norm(n);
    auto uv = r.floats<4>();
    auto slot = r.floats<2>();
    // UVs are cell-local and tile, so they are bounded rather than clipped to
    // the unit square; the slots must name a cell that exists.
    for (float v : uv)
      need(std::abs(v) <= 1024, "world UV");
    for (int k = 0; k < 2; ++k)
      need((k == 1 && unlit && slot[1] == WORLD_UNLIT_VERTEX) ||
           (slot[k] >= 0 && slot[k] < slots && std::floor(slot[k]) == slot[k]), "world atlas slot");
    for (float v : {point[0], point[1], point[2], n[0], n[1], n[2], uv[0],
                    uv[1], uv[2], uv[3], slot[0], slot[1]})
      out.push_back(v);
  }
}
TerrainDetail read_terrain_policy(Reader &lod) {
  TerrainDetail t;
  t.origin=lod.floats<3>(); t.patch_size=lod.f(); t.far_factor=lod.f(); t.bias=lod.f();
  t.minimum=lod.count(64); t.band=lod.count(64); t.width=lod.count(256);
  need(t.patch_size>=.01f && t.patch_size<=1000 && t.far_factor>0 && t.far_factor<=1 &&
       t.bias>=0 && t.bias<1, "terrain detail policy");
  return t;
}
WorldParent read_world_parent(Reader &lod) {
  WorldParent p{lod.floats<3>(),lod.f(),lod.floats<3>(),lod.f()};
  need(p.distance_radius>=0 && p.distance_radius<=10000 && p.radius>=0 && p.radius<=10000,"parent bounds");
  return p;
}
// One part in the N3L1-5 layout. N3W2 parts are N3L3's plus kind 0 (plain
// distance levels, as N3L1/N3L2 parts are drawn). N3L4 and N3W3 (D-201) are
// N3L3 and N3W2 whose kind 0 and 1 parts may be alpha parts (flag bit 4),
// each followed by its alpha record. N3L5 and N3W4 (D-202) are N3L4 and N3W3
// whose kind 0 and 1 parts that are not alpha parts may set bit 5 (cut at
// zero) and bit 6 (unlit). N3W5 (D-203) has N3W4's parts. N3W6 (D-212) is
// N3W5 whose kind 0 and 1 parts may set bit 7, each followed (after its alpha
// record) by its texture-sequence record.
WorldPart read_world_part(Reader &lod, PartScope s) {
  const bool sequence_layout = s.version == "N3W6";
  const bool opaque_layout = s.version == "N3L5" || s.version == "N3W4" || s.version == "N3W5" || sequence_layout;
  const bool alpha_layout = opaque_layout || s.version == "N3L4" || s.version == "N3W3";
  const bool chunked = world_chunk_magic(s.version);
  const bool progressive = s.version == "N3L3" || alpha_layout || chunked;
  const auto nv = s.vertices;
  auto &indices = s.indices;
  WorldPart part{lod.floats<3>(),lod.f(),lod.f(),false,false,false,{}};
  auto flags = lod.u();
  part.no_fog = flags & 1; part.mirrored = flags & 2; part.radial_cull = flags & 4;
  part.two_sided=flags & 8;
  part.cut_zero=flags & WORLD_CUT_ZERO; part.unlit=flags & WORLD_UNLIT;
  need(part.radius >= 0 && part.radius <= 2000 && part.scale > 0 && part.scale <= 1000 && flags <= (sequence_layout ? 255u : opaque_layout ? 127u : alpha_layout ? 31u : progressive ? 15u : s.version == "N3L2" ? 7u : 1u), "world part bounds");
  // Neither opaque bit on an alpha part (its record states both); a terrain
  // patch's flags are exactly 2 (below).
  need(!((flags & WORLD_ALPHA_PART) && (flags & (WORLD_CUT_ZERO | WORLD_UNLIT))), "world alpha part opaque bits");
  auto levels = lod.count(65);
  float last = -1;
  for (uint32_t j = 0; j < levels; ++j) {
    float distance = lod.f(); auto count = lod.count(589824,0);
    need(distance > last && (j != 0 || distance == 0) && count % 3 == 0 &&
         indices.size()+count <= 2000000, "world LOD bounds");
    last = distance;
    part.levels.push_back({distance,uint32_t(indices.size()),count});
    for (uint32_t k=0;k<count;++k) { auto index=lod.u(); need(index<nv,"world LOD index"); indices.push_back(index); }
  }
  if(!progressive) return part;
  part.kind=lod.count(2,chunked ? 0 : 1);
  if(part.kind==2) {
    need(s.terrain && levels==33 && flags==2,"terrain detail variants");
    part.patch_x=lod.count(s.terrain->width-1,0); part.patch_z=lod.count(s.terrain->width-1,0);
    need(s.patches.emplace(part.patch_x,part.patch_z).second,"duplicate terrain patch");
  } else if(part.kind==1) {
    auto &p=part.progressive;
    part.parent=lod.u(); p.base=lod.u(); p.vertices=lod.u(); p.indices=lod.u();
    p.maximum=lod.count(65536);
    need(levels==1 && part.levels[0].count>0 && part.parent<s.parents.size() && p.base<=nv &&
         p.maximum<=nv-p.base && p.vertices<=p.maximum && p.indices<=part.levels[0].count &&
         p.indices%3==0,"progressive mesh bounds");
    auto controls=lod.count(4096,0); float last=-1;
    for(uint32_t j=0;j<controls;++j) {
      MeshControl c{lod.f(),lod.u()};
      need(c.distance>last && c.vertices>=p.vertices && c.vertices<=p.maximum,"progressive control");
      p.controls.push_back(c);last=c.distance;
    }
    uint32_t live_v=p.vertices,live_i=p.indices;
    auto splits=lod.count(65536,0);
    for(uint32_t j=0;j<splits;++j) {
      MeshSplit m{lod.u(),lod.u(),lod.u(),lod.u(),lod.u(),lod.u()};
      need(m.vertices<=p.maximum-live_v && m.indices<=part.levels[0].count-live_i &&
           m.indices%3==0 && m.grouped<=1 && m.target<p.maximum && (!m.changes || m.target<live_v) &&
           m.changes<=196608 && m.first<=196608,"progressive split");
      live_v+=m.vertices;live_i+=m.indices;p.splits.push_back(m);
      s.split_work+=uint64_t(m.changes)+1;
      need(s.split_work<=2000000,"progressive work bound");
    }
    need(live_v==p.maximum && live_i==part.levels[0].count,"progressive maxima");
    auto edits=lod.count(196608,0);
    for(uint32_t j=0;j<edits;++j) p.edits.push_back(lod.count(part.levels[0].count-1,0));
    for(auto &m:p.splits) need(m.first<=edits && m.changes<=edits-m.first,"progressive edit range");
    for(uint32_t j=0;j<part.levels[0].count;++j) {
      auto index=indices[part.levels[0].first+j];
      need(index>=p.base && index<p.base+p.maximum &&
           (j>=p.indices || index<p.base+p.vertices),"progressive stored index");
    }
    // Validate every newly activated index and the reverse program once,
    // outside rendering. Work is linear in the bounded records/edits.
    std::vector<uint32_t> trial(indices.begin()+part.levels[0].first,indices.end());
    live_v=p.vertices;live_i=p.indices;
    for(const auto &m:p.splits) {
      live_v+=m.vertices;
      for(uint32_t k=0;k<m.changes;++k) {
        auto &index=trial[p.edits[m.first+k]];
        need(index==p.base+m.target,"non-reversible progressive edit");
        index=p.base+live_v-1;
      }
      for(uint32_t k=live_i;k<live_i+m.indices;++k)
        need(trial[k]<p.base+live_v,"progressive activated index");
      live_i+=m.indices;
    }
  }
  if(flags & WORLD_ALPHA_PART) {
    // Kind 2 is refused above (its flags are exactly 2).
    WorldAlpha a;
    a.source=lod.count(10,1); a.destination=lod.count(10,1); a.state=lod.u();
    a.sort_point=lod.floats<3>();  // finite, within 1e6
    need((a.state & 1) && !(a.state & ~WORLD_ALPHA_STATES), "world alpha part state");
    part.alpha=a;
  }
  if(flags & WORLD_SEQUENCE_PART) {
    // Kind 2 is refused above (its flags are exactly 2).
    WorldSequence q;
    auto frames=lod.count(WORLD_SEQUENCE_FRAMES_MAX,WORLD_SEQUENCE_FRAMES_MIN);
    q.fps=lod.f();
    need(q.fps>0 && q.fps<=WORLD_SEQUENCE_FPS_MAX,"world sequence part fps");
    for(uint32_t j=0;j<frames;++j) {
      auto slot=lod.u();
      need(float(slot)<s.slots,"world sequence part slot");
      q.slots.push_back(float(slot));
    }
    part.sequence=std::move(q);
  }
  return part;
}
// The N3W1 atlas header; returns the number of atlas slots.
float read_world_atlas(Reader &r, WorldMesh &w) {
  w.width = r.count(2048);
  w.height = r.count(2048);
  need((w.width & (w.width - 1)) == 0 && (w.height & (w.height - 1)) == 0,
       "world atlas dimensions");
  w.cell = r.count(2048, 8);
  w.pad = r.count(w.cell / 4, 1);
  need(w.cell <= w.width && w.cell <= w.height, "world atlas cell");
  auto per_row = w.width / w.cell;
  float slots = float(per_row * (w.height / w.cell));
  auto tex = r.raw(size_t(w.width) * w.height * 4);
  w.texture.assign(tex.begin(), tex.end());
  return slots;
}
// The grid cell holding a terrain patch's centre (PQ-232): patch (x, z) spans
// [origin.x + x * size, +size] and [origin.z - (z + 1) * size, +size], as
// world_lod::terrain_level counts them. The writer assigns the patch there.
std::pair<int64_t,int64_t> patch_cell(const WorldTable &t, const TerrainDetail &d, uint32_t x, uint32_t z) {
  const double cx = double(d.origin[0]) + (double(x) + .5) * double(d.patch_size);
  const double cz = double(d.origin[2]) - (double(z) + .5) * double(d.patch_size);
  return {int64_t(std::floor((cx - t.ox) / t.size)), int64_t(std::floor((cz - t.oz) / t.size))};
}
// Upper bound of an N3W2 header with its table: magic, texture count, grid,
// policy, 64 x 64 entries.
constexpr size_t WORLD_INDEX_BOUND = 8 + 16 + 4 + 36 + 4 + 64 * 64 * 36;
}
WorldMesh load_world_index(const Release &release, WorldTable &t) {
  need(release.world && release.world_chunked, "missing chunked world asset");
  t = {};
  t.path = release.root / "world.bin";
  const auto file = std::filesystem::file_size(t.path);
  need(file <= CHUNKED_WORLD_BOUND, "asset file bound");
  std::ifstream in(t.path, std::ios::binary);
  need(bool(in), "asset read");
  Reader r(in, 0, size_t(std::min<uint64_t>(file, WORLD_INDEX_BOUND)));
  t.version = r.raw(4);
  need(world_chunk_magic(t.version), "world chunk magic");
  WorldMesh w;
  // The world's texture count (PQ-233): every vertex slot is below it, and it
  // is the count of the package's N3WT asset.
  const auto textures = r.count(WORLD_TEXTURES);
  {
    need(release.world_textures, "missing world textures");
    std::ifstream wt(release.root / "world-textures.bin", std::ios::binary);
    need(bool(wt), "asset read");
    Reader h(wt, 0, 8);
    h.magic("N3WT");
    need(h.u() == textures, "world texture count");
  }
  t.slots = float(textures);
  t.ox = r.f(); t.oz = r.f(); t.size = r.f();
  t.side = r.count(64);
  need(t.size >= 1 && t.size <= 4096, "world chunk grid");
  t.terrain = r.count(1, 0) != 0;
  if (t.terrain) w.terrain = read_terrain_policy(r);
  const auto count = r.count(t.side * t.side);
  uint64_t bytes = 0; int64_t previous = -1;
  std::vector<int32_t> slot(size_t(t.side) * t.side, -1);
  for (uint32_t i = 0; i < count; ++i) {
    WorldChunkEntry e;
    e.x = r.count(t.side - 1, 0); e.z = r.count(t.side - 1, 0);
    e.lo = r.floats<3>(); e.hi = r.floats<3>();
    e.offset = bytes; e.bytes = r.u();
    for (int a = 0; a < 3; ++a) need(e.lo[a] <= e.hi[a], "world chunk box");
    // Grid order, each cell at most once: the table is searchable by cell.
    int64_t index = int64_t(e.z) * t.side + e.x;
    need(index > previous, "world chunk order");
    previous = index; bytes += e.bytes;
    slot[size_t(index)] = int32_t(i);
    t.entries.push_back(e);
  }
  need(bytes == file - r.p, "world chunk table length");
  for (auto &e : t.entries) e.offset += r.p;
  // Every terrain patch belongs to the chunk of its centre's cell; a cell with
  // patches and no chunk leaves terrain uncovered.
  if (t.terrain)
    for (uint32_t z = 0; z < w.terrain.width; ++z)
      for (uint32_t x = 0; x < w.terrain.width; ++x) {
        auto [cx, cz] = patch_cell(t, w.terrain, x, z);
        need(cx >= 0 && cz >= 0 && cx < t.side && cz < t.side && slot[size_t(cz * t.side + cx)] >= 0, "terrain grid coverage");
        ++t.entries[size_t(slot[size_t(cz * t.side + cx)])].patches;
      }
  for (const auto &e : t.entries) {
    WorldChunk c; c.x = e.x; c.z = e.z; c.bounded = true; c.lo = e.lo; c.hi = e.hi; c.resident = false;
    w.chunks.push_back(std::move(c));
  }
  return w;
}
WorldChunk load_world_chunk(std::istream &file, const WorldTable &t, const TerrainDetail &terrain,
                            size_t index, uint64_t *work_out) {
  const auto &e = t.entries.at(index);
  need(e.bytes <= CHUNKED_WORLD_BOUND, "world chunk length");
  Reader r(file, e.offset, size_t(e.bytes));
  // A position belongs to its cell, closed and widened by a thousandth of a
  // cell for the producer's float rounding.
  auto in_cell = [&](const V &p) {
    const double eps = t.size * 1e-3;
    return p[0] >= t.ox + e.x * t.size - eps && p[0] <= t.ox + (e.x + 1) * t.size + eps &&
           p[2] >= t.oz + e.z * t.size - eps && p[2] <= t.oz + (e.z + 1) * t.size + eps;
  };
  WorldChunk c; c.x = e.x; c.z = e.z; c.bounded = true; c.lo = e.lo; c.hi = e.hi;
  const auto nv = r.count(196608);
  read_world_vertices(r, nv, t.slots, c.vertices, t.version == "N3W5" || t.version == "N3W6");
  const auto np = r.count(8192, 0);
  for (uint32_t i = 0; i < np; ++i) {
    c.parents.push_back(read_world_parent(r));
    need(in_cell(c.parents.back().position), "world parent cell");
  }
  const auto nparts = r.count(8192);
  uint64_t work = 0;
  std::set<std::pair<uint32_t,uint32_t>> patches;
  for (uint32_t i = 0; i < nparts; ++i) {
    auto part = read_world_part(r, {t.version, nv, c.parents, c.indices, t.terrain ? &terrain : nullptr, patches, work, t.slots});
    for (int a = 0; a < 3; ++a)
      need(double(part.center[a]) - part.radius >= e.lo[a] && double(part.center[a]) + part.radius <= e.hi[a], "world chunk box cover");
    // A progressive part lives with its parent, whose position is checked; a
    // terrain patch with the cell of its centre (patch_cell).
    if (part.kind == 2) {
      auto [cx, cz] = patch_cell(t, terrain, part.patch_x, part.patch_z);
      need(cx == e.x && cz == e.z, "world terrain patch cell");
    } else {
      need(part.kind == 1 || in_cell(part.center), "world part cell");
    }
    c.parts.push_back(std::move(part));
  }
  need(patches.size() == e.patches, "terrain grid coverage");
  need(r.p == e.bytes, "world chunk length");
  if (work_out) *work_out = work;
  return c;
}
WorldMesh load_world(const Release &release) {
  need(release.world, "missing world asset");
  if (release.world_chunked) {
    // Every chunk at once: the whole-world totals bind as well (PQ-231).
    WorldTable t;
    auto w = load_world_index(release, t);
    std::ifstream in(t.path, std::ios::binary);
    need(bool(in), "asset read");
    uint64_t vertices = 0, indices = 0, parts = 0, parents = 0, work = 0;
    for (size_t i = 0; i < t.entries.size(); ++i) {
      uint64_t chunk_work = 0;
      auto c = load_world_chunk(in, t, w.terrain, i, &chunk_work);
      vertices += c.vertices.size() / WORLD_FLOATS; parents += c.parents.size(); parts += c.parts.size();
      indices += c.indices.size(); work += chunk_work;
      need(vertices <= 4194304, "world vertex total");
      need(parents <= 65536, "world parent total");
      need(parts <= 65536, "world part total");
      need(indices <= 33554432 && work <= 16777216, "world index/work total");
      w.chunks[i] = std::move(c);
    }
    return w;
  }
  // A map-sized atlas and vertex buffer need a larger bound than an animated
  // scene. The caps below still bind every count before anything is allocated.
  Reader r(release.root / "world.bin", WORLD_ASSET_BOUND);
  r.magic("N3W1");
  WorldMesh w;
  float slots = read_world_atlas(r, w);
  w.chunks.emplace_back();
  auto &c = w.chunks.back();
  auto nv = r.count(196608);
  read_world_vertices(r, nv, slots, c.vertices);
  auto ni = r.count(589824);
  need(ni % 3 == 0, "world triangle count");
  for (uint32_t i = 0; i < ni; i++) {
    auto ix = r.u();
    need(ix < nv, "world index");
    c.indices.push_back(ix);
  }
  if (release.exploration) {
    Reader lod(release.root / "world-lod.bin");
    auto version = lod.raw(4);
    bool progressive = version == "N3L3" || version == "N3L4" || version == "N3L5";
    need(version == "N3L1" || version == "N3L2" || progressive, "world LOD version");
    if (progressive) {
      w.terrain=read_terrain_policy(lod);
      auto count=lod.count(8192,0);
      for(uint32_t i=0;i<count;++i) c.parents.push_back(read_world_parent(lod));
    }
    auto parts = lod.count(8192);
    c.indices.clear();
    uint64_t split_work=0;
    std::set<std::pair<uint32_t,uint32_t>> patches;
    for (uint32_t i = 0; i < parts; ++i)
      c.parts.push_back(read_world_part(lod,{version,nv,c.parents,c.indices,progressive ? &w.terrain : nullptr,patches,split_work}));
    if(progressive) need(patches.size()==size_t(w.terrain.width)*w.terrain.width,"terrain grid coverage");
    lod.end();
  }
  r.end();
  return w;
}
WorldTextures load_world_textures(const Release &release) {
  need(release.world_textures, "missing world textures");
  Reader r(release.root / "world-textures.bin", WORLD_TEXTURES_BOUND);
  r.magic("N3WT");
  WorldTextures t;
  const auto count = r.count(WORLD_TEXTURES);
  for (uint32_t i = 0; i < count; ++i) {
    const auto levels = r.count(WORLD_TEXTURE_LEVELS);
    std::vector<WorldTextureLevel> chain;
    uint32_t w = 0, h = 0;
    for (uint32_t j = 0; j < levels; ++j) {
      WorldTextureLevel m;
      m.width = r.count(2048);
      m.height = r.count(2048);
      // Power-of-two levels that halve, as N3D1's native textures; no
      // generated tail, so a chain may stop above 1 x 1.
      need((m.width & (m.width - 1)) == 0 && (m.height & (m.height - 1)) == 0 &&
           (!j || (m.width == std::max(1u, w / 2) && m.height == std::max(1u, h / 2) && (w > 1 || h > 1))),
           "world texture mip dimensions");
      w = m.width; h = m.height;
      const uint64_t bytes = uint64_t(w) * h * 4;
      t.pixels += bytes;
      need(t.pixels <= WORLD_TEXTURE_PIXELS, "world texture byte bound");
      need(bytes <= r.b.size() - r.p, "truncated cooked data");
      m.offset = r.p;
      r.p += size_t(bytes);
      chain.push_back(m);
    }
    t.chains.push_back(std::move(chain));
  }
  r.end();
  need(world_texture_banks(t, WORLD_TEXTURE_BANK_LAYERS).size() <= WORLD_TEXTURE_BANKS, "world texture bank bound");
  t.bytes = std::move(r.b);
  return t;
}
WorldOverlay load_world_overlay(const Release &release, const TerrainDetail &terrain) {
  need(release.world_overlay, "missing world overlay");
  Reader r(release.root / "world-overlay.bin", WORLD_OVERLAY_BOUND);
  r.magic("N3WO");
  WorldOverlay o;
  o.patch_tiles = r.u(); o.block_tiles = r.u(); o.window = r.u(); o.side = r.u();
  o.cell = r.u(); o.inset = r.u(); o.levels = r.u(); o.width = r.u();
  need(o.patch_tiles >= 1 && o.patch_tiles <= WORLD_OVERLAY_PATCH_TILES && o.block_tiles >= 1 &&
       o.block_tiles <= o.patch_tiles && o.patch_tiles % o.block_tiles == 0 &&
       o.per_patch() <= WORLD_OVERLAY_BLOCKS_PER_PATCH, "world overlay grid");
  need(o.window <= WORLD_OVERLAY_WINDOW && o.layers() <= WORLD_OVERLAY_LAYERS, "world overlay window");
  need(o.side >= 4 && o.side <= 256 && (o.side & (o.side - 1)) == 0 && uint64_t(o.block_tiles) * o.cell == o.side &&
       2 * uint64_t(o.inset) < o.cell, "world overlay texel layout");
  need(o.levels >= 1 && o.levels <= uint32_t(std::bit_width(o.side)), "world overlay levels");
  need(o.width >= 1 && o.width <= WORLD_OVERLAY_WIDTH, "world overlay width");
  // The grid is the terrain policy's: whole patches of patch_tiles tiles.
  need(terrain.patch_size > 0 && terrain.width > 0 &&
       uint64_t(o.width) * o.block_tiles == uint64_t(terrain.width) * o.patch_tiles,
       "world overlay grid differs from the terrain policy");
  const auto count = r.u();
  need(count >= 1 && count <= std::min<uint64_t>(uint64_t(o.width) * o.width, WORLD_OVERLAY_MAPS), "world overlay count");
  uint64_t size = 0;
  for (uint32_t k = 0; k < o.levels; ++k) size += uint64_t(o.side >> k) * (o.side >> k) * 4;
  need(count * size <= WORLD_OVERLAY_PIXELS && r.b.size() - r.p == count * (8 + size), "world overlay size");
  int64_t last = -1;
  for (uint32_t i = 0; i < count; ++i) {
    const auto bx = r.u(), bz = r.u();
    const int64_t key = int64_t(bz) * o.width + bx;
    need(bx < o.width && bz < o.width && key > last, "world overlay block order");
    last = key;
    o.maps.emplace(uint32_t(key), r.p);
    r.p += size_t(size);
  }
  r.end();
  o.bytes = std::move(r.b);
  return o;
}
std::vector<WorldTextureBank> world_texture_banks(const WorldTextures &textures, uint32_t layers) {
  need(layers >= 1, "world texture bank layers");
  std::map<std::array<uint32_t, 3>, std::vector<uint32_t>> groups;
  for (uint32_t i = 0; i < textures.chains.size(); ++i) {
    const auto &c = textures.chains[i];
    groups[{c[0].width, c[0].height, uint32_t(c.size())}].push_back(i);
  }
  std::vector<WorldTextureBank> banks;
  for (const auto &[key, ids] : groups)
    for (size_t at = 0; at < ids.size(); at += layers)
      banks.push_back({key[0], key[1], key[2],
                       std::vector<uint32_t>(ids.begin() + at, ids.begin() + std::min(ids.size(), at + layers))});
  return banks;
}
RenderDetail load_render_detail(const Release &release, const Scene &skeleton) {
  need(release.render_detail,"missing render detail");
  Reader r(release.root/"render-detail.bin",128*1024*1024);
  const auto magic=r.raw(4);const bool states=magic=="N3D3";
  need(release.appearance.empty()?magic=="N3D1":magic=="N3D2"||states,"cooked magic/version");
  r.floats<3>(); RenderDetail d;
  for(auto &row:d.thresholds) {
    float last=0;
    for(auto &v:row) { v=r.f(); need(v>last && v<=10000,"character thresholds"); last=v; }
  }
  uint32_t last=0;
  for(auto &v:d.workload) { v=r.count(100000); need(v>last,"character workload");last=v; }
  d.world_textures=r.count(1024);
  auto nt=r.count(1024);need(d.world_textures<=nt,"world texture subset");
  size_t total_bytes=0; std::set<std::array<uint32_t,3>> banks;
  for(uint32_t i=0;i<nt;++i) {
    TextureChain chain;auto levels=r.count(12);uint32_t w=0,h=0;
    for(uint32_t j=0;j<levels;++j) {
      TextureMip m; m.width=r.count(2048);m.height=r.count(2048);
      need((m.width&(m.width-1))==0 && (m.height&(m.height-1))==0 &&
           (!j || (m.width==std::max(1u,w/2) && m.height==std::max(1u,h/2) && (w>1 || h>1))),"native mip dimensions");
      w=m.width;h=m.height;size_t bytes=size_t(w)*h*4;total_bytes+=bytes;
      need(total_bytes<=112*1024*1024,"native texture budget");
      auto pixels=r.raw(bytes);m.pixels.assign(pixels.begin(),pixels.end());chain.push_back(std::move(m));
    }
    banks.insert({chain[0].width,chain[0].height,levels});
    need(banks.size()<=8,"native texture bank bound");d.textures.push_back(std::move(chain));
  }
  d.radius=r.f();need(d.radius>.001f && d.radius<=1000,"character radius");
  auto nl=r.count(4);need(nl==4,"character level count");
  size_t total_vertices=0,total_indices=0;
  auto mesh=[&]() {
    DetailMesh m; m.scene=skeleton;m.scene.vertices.clear();m.scene.indices.clear();
    m.scene.collision={};m.scene.tracks.clear();m.scene.texture.clear();
    auto nv=r.count(65536,0),ni=r.count(196608,0);
    need(ni%3==0 && ((nv==0)==(ni==0)),"detail geometry counts");
    total_vertices+=nv;total_indices+=ni;
    need(total_vertices<=262144 && total_indices<=786432,"detail geometry budget");
    for(uint32_t i=0;i<nv;++i) {
      Vertex v;v.p=r.floats<3>();v.n=r.floats<3>();norm(v.n);v.uv=r.floats<2>();
      for(float uv:v.uv)need(std::abs(uv)<=1024,"detail UV");
      for(auto &j:v.joints) { j=r.u();need(j<skeleton.joints.size(),"detail joint"); }
      v.weights=r.floats<4>();float sum=0;
      for(float w:v.weights){need(w>=0 && w<=1,"detail weight");sum+=w;}
      need(std::abs(sum-1)<.001f,"detail weight sum");
      auto slot=r.u();need(slot<nt,"detail texture slot");
      m.scene.vertices.push_back(v);m.slots.push_back(slot);
    }
    for(uint32_t i=0;i<ni;++i){auto ix=r.u();need(ix<nv,"detail index");m.scene.indices.push_back(ix);}
    for(size_t i=0;i<m.scene.indices.size();i+=3)need(m.slots[m.scene.indices[i]]==m.slots[m.scene.indices[i+1]]&&m.slots[m.scene.indices[i]]==m.slots[m.scene.indices[i+2]],"detail triangle material");
    return m;
  };
  for(uint32_t i=0;i<nl;++i)d.levels.push_back(mesh());
  need(!d.levels[0].scene.indices.empty(),"empty character base level");
  auto na=r.count(16,0);uint64_t work=0;
  for(uint32_t a=0;a<na;++a) {
    DetailAttachment attachment;attachment.mesh=mesh();auto &part=attachment.part;
    auto &p=part.progressive;const auto &indices=attachment.mesh.scene.indices;
    need(!indices.empty(),"empty attachment");part.levels={{0,0,uint32_t(indices.size())}};
    p.vertices=r.u();p.indices=r.u();p.maximum=attachment.mesh.scene.vertices.size();
    need(p.vertices>0 && p.vertices<=p.maximum && p.indices<=indices.size() && p.indices%3==0,"attachment minima");
    auto nc=r.count(4096,0);float distance=-1;
    for(uint32_t i=0;i<nc;++i){MeshControl c{r.f(),r.u()};need(c.distance>distance && c.vertices>=p.vertices && c.vertices<=p.maximum,"attachment controls");p.controls.push_back(c);distance=c.distance;}
    auto ns=r.count(65536,0);uint32_t v=p.vertices,n=p.indices;
    for(uint32_t i=0;i<ns;++i){MeshSplit s{r.u(),r.u(),r.u(),r.u(),r.u(),r.u()};
      need(s.vertices<=p.maximum-v && s.indices<=indices.size()-n && s.indices%3==0 &&
           s.grouped<=1 && s.target<p.maximum && (!s.changes || s.target<v),"attachment split");
      v+=s.vertices;n+=s.indices;work+=uint64_t(s.changes)+1;
      need(work<=2000000,"attachment work bound");p.splits.push_back(s);}
    need(v==p.maximum && n==indices.size(),"attachment maxima");
    auto ne=r.count(196608,0);for(uint32_t i=0;i<ne;++i)p.edits.push_back(r.count(indices.size()-1,0));
    auto trial=indices;v=p.vertices;n=p.indices;
    for(uint32_t i=0;i<n;++i)need(trial[i]<v,"attachment active index");
    for(auto &s:p.splits){need(s.first<=ne && s.changes<=ne-s.first,"attachment edits");v+=s.vertices;
      for(uint32_t i=0;i<s.changes;++i){auto &ix=trial[p.edits[s.first+i]];need(ix==s.target,"attachment reversible edit");ix=v-1;}
      for(uint32_t i=n;i<n+s.indices;++i)need(trial[i]<v,"attachment activated index");n+=s.indices;}
    d.attachments.push_back(std::move(attachment));
  }
  if(!release.appearance.empty()) {
    auto n=r.count(128);need(n==release.appearance.size(),"appearance geometry count");
    for(unsigned i=0;i<n;++i){AppearanceMesh a;auto count=r.count(16,0);std::set<uint32_t> seen;
      for(unsigned j=0;j<count;++j){auto slot=r.u();need(slot>=d.world_textures&&slot<nt&&seen.insert(slot).second,"appearance replacement");a.replaces.push_back(slot);}
      for(unsigned j=0;j<4;++j)a.levels.push_back(mesh());
      // PQ-317 (D-187): a skeletal plug's key draws no rigid mesh (2233's
      // CN3ChrTypePlug names none); every other key needs one.
      const bool plug=release.attachments&&std::any_of(release.attachments->entries.begin(),release.attachments->entries.end(),
        [&](const auto&e){return e.key==i+1&&(e.flags&Attachment::PLUG);});
      need(plug||!a.levels[0].scene.indices.empty(),"empty appearance");
      if(states){
        // The N3SM run's state bounds (PQ-265) without its unlit flag: flags
        // 1 blend, 2 double-sided; factors 0-9 only with blend; the reference
        // in [0, 1).
        AppearanceState st;st.flags=r.u();st.alpha_reference=r.f();st.source=r.u();st.destination=r.u();
        need(st.flags<=3&&std::isfinite(st.alpha_reference)&&st.alpha_reference>=0&&st.alpha_reference<1&&
             ((st.flags&MaterialRun::BLEND)?st.source<=9&&st.destination<=9:st.source==0&&st.destination==0),
             "appearance render state");
        a.state=st;
      }
      d.appearances.push_back(std::move(a));
    }
  }
  r.end();
  // N3E2 appearance effects are rigid to one joint of this skeleton (PQ-211).
  if(release.effects)for(const auto&e:release.effects->appearance)need(e.joint<skeleton.joints.size(),"appearance effect joint");
  return d;
}
// N3C1 soup or N3C2 heightfield plus objects (PQ-215); the same bounds as
// server/src/collision.rs, refusing anything else.
Collision load_collision(const std::filesystem::path &path) {
  Reader c(path);
  auto magic = c.raw(4);
  if (magic == "N3C1") {
    auto n = c.count(196608);
    need(n % 3 == 0, "collision triangles");
    std::vector<V> soup;
    soup.reserve(n);
    for (uint32_t i = 0; i < n; i++)
      soup.push_back(c.floats<3>());
    c.end();
    return Collision(std::move(soup));
  }
  need(magic == "N3C2", "collision magic");
  Collision::Terrain t;
  t.width = c.count(513, 2);
  t.depth = c.count(513, 2);
  t.ox = c.f();
  t.oz = c.f();
  t.spacing = c.f();
  auto extent = [&](uint32_t n) { return float(n - 1) * t.spacing; };
  need(t.spacing > 0 && t.spacing <= 100 && extent(t.width) <= 4096 && extent(t.depth) <= 4096 &&
           std::abs(t.ox + extent(t.width)) <= 1e6f && std::abs(t.oz + extent(t.depth)) <= 1e6f,
       "collision heightfield extent");
  t.diagonal = c.u();
  need(t.diagonal <= 2, "collision heightfield diagonal");
  t.heights.resize(size_t(t.width) * t.depth);
  for (auto &h : t.heights)
    h = c.f();
  auto n = c.count(393216, 0);
  need(n % 3 == 0, "collision triangles");
  std::vector<V> objects;
  objects.reserve(n);
  for (uint32_t i = 0; i < n; i++)
    objects.push_back(c.floats<3>());
  c.end();
  return Collision(std::move(t), std::move(objects));
}
// N3S1's parts (PQ-253: N3NM repeats the track list once per clip). `atlas`
// is the largest side: 2048 for the front end's models only (spec 11).
static void read_scene_head(Reader &r, Scene &s, uint32_t atlas = 1024) {
  s.width = r.count(atlas);
  s.height = r.count(atlas);
  auto tex = r.raw(s.width * s.height * s.channels);
  s.texture.assign(tex.begin(), tex.end());
  auto nn = r.count(128);
  for (uint32_t i = 0; i < nn; i++) {
    Node n;
    n.parent = std::bit_cast<int32_t>(r.u());
    n.t = r.floats<3>();
    n.q = r.floats<4>();
    n.s = r.floats<3>();
    need(n.parent >= -1 && n.parent < int(nn), "node parent");
    float len = 0;
    for (float v : n.q)
      len += v * v;
    need(std::abs(len - 1) < 1e-4, "node rotation");
    for (float v : n.s)
      need(v > 0, "node scale");
    s.nodes.push_back(n);
  }
  for (uint32_t i = 0; i < nn; i++) {
    std::set<int> seen;
    for (int j = i; j != -1; j = s.nodes[j].parent)
      need(seen.insert(j).second, "node cycle");
  }
  auto nj = r.count(64);
  for (uint32_t i = 0; i < nj; i++) {
    Joint j{r.u(), r.floats<16>()};
    need(j.node < nn, "joint node");
    s.joints.push_back(j);
  }
}
static void read_scene_tracks(Reader &r, const Scene &s, std::vector<Track> &out) {
  auto nt = r.count(384, 0);
  std::set<std::pair<uint32_t, uint32_t>> channels;
  for (uint32_t i = 0; i < nt; i++) {
    Track t{r.u(), r.u(), {}};
    need(t.node < s.nodes.size() && t.path < 3 && channels.insert({t.node, t.path}).second,
         "animation channel");
    auto nk = r.count(4096, 2);
    for (uint32_t k = 0; k < nk; k++) {
      Key key{r.f(), r.floats<4>()};
      need((k == 0 ? key.time == 0 : key.time > t.keys.back().time) &&
               key.time <= 3600,
           "key time");
      if (t.path == 1) {
        float l = 0;
        for (auto v : key.value)
          l += v * v;
        need(std::abs(l - 1) < 1e-4, "key rotation");
      }
      if (t.path == 2)
        for (int c = 0; c < 3; c++)
          need(key.value[c] > 0, "key scale");
      t.keys.push_back(key);
    }
    out.push_back(t);
  }
}
// `influences`: an N3NI / N3MI model, whose influence table follows the
// vertices (PQ-283, D-176; tools/assetc/gltf.py N3SI).
static void read_scene_tail(Reader &r, Scene &s, bool influences = false) {
  auto nv = r.count(65536);
  std::vector<float> sums;
  sums.reserve(nv);
  for (uint32_t i = 0; i < nv; i++) {
    Vertex v;
    v.p = r.floats<3>();
    v.n = r.floats<3>();
    v.uv = r.floats<2>();
    for (auto &j : v.joints) {
      j = r.u();
      need(j < s.joints.size(), "vertex joint");
    }
    v.weights = r.floats<4>();
    float sum = 0;
    for (auto w : v.weights) {
      need(w >= 0, "negative weight");
      sum += w;
    }
    sums.push_back(sum);
    norm(v.n);
    s.vertices.push_back(v);
  }
  if (influences) {
    // Vertices in strictly increasing order, each with 1-60 further
    // influences (64 in all), on skin joints, with weights above 0.
    auto entries = r.count(nv);
    int64_t last = -1;
    for (uint32_t e = 0; e < entries; ++e) {
      auto vertex = r.u();
      need(vertex < nv && int64_t(vertex) > last, "influence vertex");
      last = vertex;
      auto n = r.count(60);
      auto &v = s.vertices[vertex];
      v.first_influence = uint32_t(s.influences.size());
      v.influences = n;
      for (uint32_t k = 0; k < n; ++k) {
        Influence influence{r.u(), r.f()};
        need(influence.joint < s.joints.size(), "influence joint");
        need(std::isfinite(influence.weight) && influence.weight > 0, "influence weight");
        sums[vertex] += influence.weight;
        s.influences.push_back(influence);
      }
    }
  }
  for (float sum : sums)
    need(std::abs(sum - 1) < 1e-4, "weight sum");
  auto ni = r.count(196608);
  need(ni % 3 == 0, "triangle count");
  for (uint32_t i = 0; i < ni; i++) {
    auto ix = r.u();
    need(ix < nv, "mesh index");
    s.indices.push_back(ix);
  }
  if (s.channels == 4) {
    // N3MM render runs (PQ-265): in order, covering the indices exactly.
    auto runs = r.count(16);
    uint32_t next = 0;
    for (uint32_t i = 0; i < runs; ++i) {
      MaterialRun run;
      run.first = r.u();
      run.count = r.u();
      run.flags = r.u();
      run.alpha_reference = r.f();
      run.source = r.u();
      run.destination = r.u();
      need(run.first == next && run.count > 0 && run.count % 3 == 0 && run.count <= ni - next, "render run range");
      need(run.flags <= 7 && std::isfinite(run.alpha_reference) && run.alpha_reference >= 0 &&
               run.alpha_reference < 1 &&
               ((run.flags & MaterialRun::BLEND) ? run.source <= 9 && run.destination <= 9
                                                 : run.source == 0 && run.destination == 0),
           "render run state");
      next += run.count;
      s.runs.push_back(run);
    }
    need(next == ni, "render runs cover the mesh");
  }
  s.scale = r.floats<3>();
  for (auto v : s.scale)
    need(v > 0, "instance scale");
  s.attachment = r.u();
  need(s.attachment < s.nodes.size(), "attachment");
}
Scene load_scene(const Release &release, const std::string &name) {
  Scene s;
  bool combat_name=false;
  if(release.combat_animation)for(size_t i=0;i<release.combat_animation->clips.size();++i)
    combat_name|=name=="combat-"+std::to_string(i)+".bin";
  if(release.skills)for(const auto&skill:release.skills->entries)combat_name|=name=="player-skill-"+std::to_string(skill.animation)+".bin";
  need(combat_name || name == "scene.bin" || (release.loot_model&&name=="loot-model.bin") ||
           (release.animation && release.animation->size() >= 11 &&
            (name == "npc-idle.bin" || name == "npc-walk.bin" ||
             name == "npc-attack.bin" || name == "npc-death.bin")) ||
           (release.presentation &&
            (name == "player-idle.bin" || name == "player-walk.bin" ||
             name == "player-attack.bin" || name == "player-death.bin")) ||
           (release.locomotion &&
            (name == "player-run.bin" || name == "player-backward.bin")) ||
           (release.ready_pose && name == "player-ready.bin") || (release.rest && (name=="player-sit-down.bin"||name=="player-sit-idle.bin"||name=="player-stand-up.bin")),
       "scene name");
  Reader r(release.root / name);
  r.magic("N3S1");
  read_scene_head(r, s);
  read_scene_tracks(r, s, s.tracks);
  read_scene_tail(r, s);
  r.end();
  if(name=="loot-model.bin"){
    need(s.tracks.empty(),"loot model must be static");
    for(float v:s.scale)need(v<=100,"loot model scale");
    for(const auto&node:s.nodes)for(float v:node.s)need(v<=100,"loot node scale");
    auto mesh=s.skin(s.nodes);
    for(size_t i=0;i<mesh.size();i+=8)for(unsigned k=0;k<3;++k)need(std::isfinite(mesh[i+k])&&std::abs(mesh[i+k])<=100,"loot model bounds");
    return s;
  }
  s.collision = load_collision(release.root / "collision.bin");
  if(release.commerce&&name=="scene.bin")for(const auto &shop:release.commerce->shops)need(std::isfinite(s.ground_height(shop.position[0],shop.position[2])),"shop not on map");
  return s;
}
// A looks model file (N3NM, N3MM, N3NI, N3MI): four scenes sharing one
// skeleton, each clip's duration checked against its table record.
static std::vector<Scene> load_looks_model(const std::filesystem::path &path, bool materials, bool influences,
                                           const std::array<Clip, 4> &records, const char *what) {
  Reader r(path);
  r.magic(influences ? (materials ? "N3MI" : "N3NI") : materials ? "N3MM" : "N3NM");
  std::vector<Scene> clips(4);
  clips[0].channels = materials ? 4 : 3;
  read_scene_head(r, clips[0]);
  for (auto &clip : clips) read_scene_tracks(r, clips[0], clip.tracks);
  read_scene_tail(r, clips[0], influences);
  r.end();
  for (size_t i = 0; i < clips.size(); ++i) {
    auto &clip = clips[i];
    if (i) {
      clip.width = clips[0].width;
      clip.height = clips[0].height;
      clip.channels = clips[0].channels;
      clip.nodes = clips[0].nodes;
      clip.joints = clips[0].joints;
      clip.scale = clips[0].scale;
      clip.attachment = clips[0].attachment;
    }
    float duration = 0;
    for (const auto &track : clip.tracks) duration = std::max(duration, track.keys.back().time);
    need(std::abs(duration - records[i].duration) <= .001f, what);
  }
  return clips;
}
std::vector<Scene> load_npc_looks(const Release &release, size_t index) {
  need(index < release.npc_looks.size(), "npc looks index");
  const auto &looks = release.npc_looks[index];
  return load_looks_model(release.root / ("npc-looks-" + std::to_string(index) + ".bin"), looks.materials,
                          looks.influences, looks.clips, "npc looks clip duration");
}
std::vector<Scene> load_attachment(const Release &release, size_t index) {
  need(release.attachments && index < release.attachments->entries.size(), "attachment index");
  const auto &e = release.attachments->entries[index];
  auto clips = load_looks_model(release.root / ("attachment-" + std::to_string(index) + ".bin"), e.materials,
                                e.influences, e.clips, "attachment clip duration");
  const auto &model = clips[0];
  bool ends = e.lit == 0 || model.runs.empty();
  for (const auto &run : model.runs) ends |= run.first + run.count == e.lit;
  need(e.lit <= model.indices.size() && ends, "attachment lit indices");
  return clips;
}
std::vector<Node> Scene::sample(float time) const {
  need(std::isfinite(time) && time >= 0, "animation time");
  auto animated = nodes;
  for (const auto &t : tracks) {
    float at = std::min(time, t.keys.back().time);
    size_t k = 0;
    while (k + 2 < t.keys.size() && t.keys[k + 1].time < at)
      ++k;
    const auto &a = t.keys[k];
    const auto &b = t.keys[k + 1];
    Q v = interpolate(a.value, b.value, (at - a.time) / (b.time - a.time),
                      t.path == 1);
    if (t.path == 1)
      animated[t.node].q = v;
    else
      for (int i = 0; i < 3; i++)
        (t.path == 0 ? animated[t.node].t : animated[t.node].s)[i] = v[i];
  }
  return animated;
}
std::vector<float> Scene::animate(float time) const {
  auto out = skin(sample(time));
  // The whole surface: a stand-in only drawn when the package has no world.
  const auto collision = this->collision.all();
  out.reserve(out.size() + collision.size() * 8);
  for (size_t i = 0; i < collision.size(); i += 3) {
    V a = collision[i], b = collision[i + 1], c = collision[i + 2];
    V x{b[0] - a[0], b[1] - a[1], b[2] - a[2]},
        y{c[0] - a[0], c[1] - a[1], c[2] - a[2]};
    auto n = norm({x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2],
                   x[0] * y[1] - x[1] * y[0]});
    for (V p : {a, b, c}) {
      out.insert(out.end(), p.begin(), p.end());
      out.insert(out.end(), n.begin(), n.end());
      out.insert(out.end(), {.75f, .25f});
    }
  }
  return out;
}
bool Scene::compatible(const Scene &other) const {
  return nodes == other.nodes && joints == other.joints &&
         vertices == other.vertices && influences == other.influences && indices == other.indices &&
         scale == other.scale && texture == other.texture &&
         width == other.width && height == other.height;
}
std::vector<float> Scene::skin(const std::vector<Node> &animated) const {
  return skin(animated, indices);
}
V Scene::joint_position(const std::vector<Node>&pose,unsigned joint)const{
  need(pose.size()==nodes.size()&&joint<joints.size(),"effect attachment joint");
  unsigned node=joints[joint].node;M m=trs(pose[node]);
  for(int parent=nodes[node].parent;parent!=-1;parent=nodes[parent].parent)m=mul(trs(pose[parent]),m);
  return {m[12]*scale[0],m[13]*scale[1],m[14]*scale[2]};
}
void transform_skinned(std::vector<float> &vertices, const M &m, float scale) {
  need(vertices.size() % 8 == 0 && std::isfinite(scale) && scale > 0, "skinned vertices");
  for (size_t i = 0; i < vertices.size(); i += 8) {
    auto p = point(m, {vertices[i] * scale, vertices[i + 1] * scale, vertices[i + 2] * scale});
    auto n = normal(m, {vertices[i + 3], vertices[i + 4], vertices[i + 5]});
    for (int k = 0; k < 3; ++k) vertices[i + k] = p[k], vertices[i + 3 + k] = n[k];
  }
}
M multiply(const M &a, const M &b) { return mul(a, b); }
M placement_matrix(const std::array<float, 12> &rows) {
  M m = identity();
  for (int r = 0; r < 3; ++r) {
    for (int c = 0; c < 3; ++c) m[c * 4 + r] = rows[r * 4 + c];
    m[12 + r] = rows[r * 4 + 3];
  }
  return m;
}
M Scene::joint_matrix(const std::vector<Node>&pose,unsigned joint)const{
  need(pose.size()==nodes.size()&&joint<joints.size(),"attachment joint");
  unsigned node=joints[joint].node;M m=trs(pose[node]);
  for(int parent=nodes[node].parent;parent!=-1;parent=nodes[parent].parent)m=mul(trs(pose[parent]),m);
  M instance=identity();for(int i=0;i<3;i++)instance[i*5]=scale[i];
  return mul(instance,m);
}
std::vector<float> Scene::skin(const std::vector<Node> &animated, std::span<const uint32_t> active_indices) const {
  need(animated.size() == nodes.size(), "pose size");
  std::vector<M> world(nodes.size());
  for (size_t i = 0; i < nodes.size(); i++) {
    M m = trs(animated[i]);
    for (int p = nodes[i].parent; p != -1; p = nodes[p].parent)
      m = mul(trs(animated[p]), m);
    world[i] = m;
  }
  M instance = identity();
  for (int i = 0; i < 3; i++)
    instance[i * 5] = scale[i];
  std::vector<M> palette;
  for (const auto &j : joints)
    palette.push_back(mul(instance, mul(world[j.node], j.inverse)));
  std::vector<float> out;
  out.reserve((active_indices.size() + 3) * 8);
  auto append = [&](V p, V n, std::array<float, 2> uv) {
    out.insert(out.end(), p.begin(), p.end());
    out.insert(out.end(), n.begin(), n.end());
    out.insert(out.end(), uv.begin(), uv.end());
  };
  // Indexed meshes share each vertex between about three triangles: skin every
  // referenced vertex once and reuse it (identical arithmetic, same output).
  std::vector<std::array<V, 2>> skinned(vertices.size());
  std::vector<uint8_t> done(vertices.size(), 0);
  for (auto ix : active_indices) {
    const auto &v = vertices[ix];
    if (!done[ix]) {
      M m{};
      for (int j = 0; j < 4; j++)
        for (int k = 0; k < 16; k++)
          m[k] += palette[v.joints[j]][k] * v.weights[j];
      // Then each further influence, in order (PQ-283: KO's 00419f00 sums
      // every influence of a vertex).
      for (uint32_t f = v.first_influence; f < v.first_influence + v.influences; ++f)
        for (int k = 0; k < 16; k++)
          m[k] += palette[influences[f].joint][k] * influences[f].weight;
      skinned[ix] = {point(m, v.p), normal(m, v.n)};
      done[ix] = 1;
    }
    append(skinned[ix][0], skinned[ix][1], v.uv);
  }
  auto attach = mul(instance, world[attachment]);
  for (V p : {V{0, 0, 0}, V{.22f, 0, 0}, V{0, .12f, 0}})
    append(point(attach, p), normal(attach, {0, 0, 1}), {0, 0});
  return out;
}
float Scene::ground_height(float x, float z) const { return collision.ground_height(x, z); }
// Spec 11's front end (content/front-end.md): every bound ko_front_end.py
// checks, the required actions per screen, and each embedded model read as
// load_scene reads a package scene, with the front end's 2048 atlas.
FrontEnd load_front_end(const Release &release) {
  need(release.front_end, "front end not in the package");
  Reader r(release.root / "front-end.bin", kFrontEndFile);
  r.magic("N3FE");
  need(r.u() == 4, "front end version");
  FrontEnd fe;
  fe.character_slots = r.count(3);
  fe.canvas_width = r.u();
  fe.canvas_height = r.u();
  need(fe.canvas_width == 1024 && fe.canvas_height == 768, "front end canvas");
  const auto textures = r.count(64);
  for (uint32_t i = 0; i < textures; ++i) {
    HudTexture t;
    t.width = r.count(1024);
    t.height = r.count(1024);
    auto pixels = r.raw(size_t(t.width) * t.height * 4);
    t.pixels.assign(pixels.begin(), pixels.end());
    fe.textures.push_back(std::move(t));
  }
  auto text = [&](size_t limit) { return r.raw(r.count(uint32_t(limit), 0)); };
  auto ascii = [](const std::string &s) {
    for (unsigned char c : s) need(c == '\n' || (c >= 32 && c < 127), "front end text");
    return s;
  };
  const auto fonts = r.count(8, 0);
  for (uint32_t i = 0; i < fonts; ++i) {
    FrontFont font;
    font.texture = r.u();
    font.pixels = r.count(48, 6);
    font.height = r.count(32);
    font.top = r.u();
    font.advances = r.floats<95>();
    need(font.texture < fe.textures.size() && fe.textures[font.texture].width == 512 &&
             fe.textures[font.texture].height == 192 && font.top + font.height <= 32,
         "front end font");
    for (float a : font.advances) need(a > 0 && a <= 28, "front end font advance");
    fe.fonts.push_back(font);
  }
  static const std::array<std::vector<FrontAction>, size_t(FrontScreen::count)> required{{
      {FrontAction::login, FrontAction::exit, FrontAction::login_group, FrontAction::realm_group,
       FrontAction::realm_list, FrontAction::realm_connect},
      {FrontAction::select_prev, FrontAction::select_next, FrontAction::back, FrontAction::exit,
       FrontAction::char_info},
      {FrontAction::create_confirm, FrontAction::back, FrontAction::name_field, FrontAction::char_view},
      {FrontAction::progress},
      {FrontAction::message, FrontAction::ok},
  }};
  for (size_t screen = 0; screen < fe.screens.size(); ++screen) {
    auto &nodes = fe.screens[screen];
    const auto count = r.count(1024);
    std::set<FrontAction> bound;
    for (uint32_t i = 0; i < count; ++i) {
      FrontNode n;
      n.kind = r.u();
      n.parent = r.u();
      need(n.kind <= FrontNode::LIST && (i == 0 ? n.parent == 0xffffffffu : n.parent < i), "front end node");
      n.rect = r.floats<4>();
      need(n.rect[0] <= n.rect[2] && n.rect[1] <= n.rect[3] && std::abs(n.rect[0]) <= 16384 &&
               std::abs(n.rect[1]) <= 16384 && std::abs(n.rect[2]) <= 16384 && std::abs(n.rect[3]) <= 16384,
           "front end rect");
      n.id = text(64);
      const auto action = r.u();
      need(action < uint32_t(FrontAction::count), "front end action");
      n.action = FrontAction(action);
      need(n.action == FrontAction::none || bound.insert(n.action).second, "front end action bound twice");
      n.flags = r.u();
      n.mask = r.u();
      need(n.flags <= 7 && n.mask >= 1 && n.mask <= 15, "front end node state");
      if (n.kind == FrontNode::IMAGE) {
        n.texture = r.u();
        n.uv = r.floats<4>();
        need(n.texture < fe.textures.size(), "front end image texture");
        for (float v : n.uv) need(v >= 0 && v <= 1, "front end image uv");
      } else if (n.kind == FrontNode::TEXT) {
        n.text = ascii(text(1024));
        n.font = r.u();
        n.color = r.u();
        n.style = r.u();
      } else if (n.kind == FrontNode::EDIT) {
        n.font = r.u();
        n.color = r.u();
        n.style = r.u();
      } else if (n.kind == FrontNode::LIST) {
        n.font = r.u();
        n.color = r.u();
      }
      need((n.kind != FrontNode::TEXT && n.kind != FrontNode::EDIT && n.kind != FrontNode::LIST) ||
               n.font < fe.fonts.size(),
           "front end font index");
      nodes.push_back(std::move(n));
    }
    for (auto action : required[screen]) need(bound.contains(action), "front end screen action unbound");
  }
  for (auto &s : fe.strings) s = ascii(text(1024));
  // D3DLIGHT9's range is unclamped (the intro's point lights carry 1e6 and
  // 1e7), so it is read past Reader::f's 1e6 bound.
  auto light = [&] {
    FrontLight l;
    l.kind = r.u();
    need(l.kind >= FrontLight::POINT && l.kind <= FrontLight::DIRECTIONAL, "front end light type");
    l.diffuse = r.floats<3>();
    l.ambient = r.floats<3>();
    l.position = r.floats<3>();
    l.direction = r.floats<3>();
    l.range = std::bit_cast<float>(r.u());
    need(std::isfinite(l.range) && l.range > 0 && l.range <= 1e8f, "front end light range");
    l.falloff = r.f();
    l.attenuation = r.floats<3>();
    l.theta = r.f();
    l.phi = r.f();
    need(l.attenuation[0] >= 0 && l.attenuation[1] >= 0 && l.attenuation[2] >= 0 &&
             l.attenuation[0] + l.attenuation[1] + l.attenuation[2] > 0,
         "front end light attenuation");
    return l;
  };
  auto mesh = [&] {
    FrontMesh m;
    m.texture = r.u();
    m.flags = r.u();
    need(m.texture < fe.textures.size() && m.flags <= 3, "front end mesh");
    m.diffuse = r.floats<3>();
    m.ambient = r.floats<3>();
    const auto vertices = r.count(65536);
    m.vertices.reserve(size_t(vertices) * 8);
    for (uint32_t i = 0; i < vertices * 8; ++i) m.vertices.push_back(r.f());
    const auto indices = r.count(196608, 3);
    need(indices % 3 == 0, "front end mesh triangles");
    for (uint32_t i = 0; i < indices; ++i) {
      m.indices.push_back(r.u());
      need(m.indices.back() < vertices, "front end mesh index");
    }
    return m;
  };
  auto scene = [&](FrontScene &out) {
    out.camera.eye = r.floats<3>();
    out.camera.at = r.floats<3>();
    out.camera.up = r.floats<3>();
    out.camera.fov = r.f();
    out.camera.near_plane = r.f();
    out.camera.far_plane = r.f();
    need(out.camera.fov > 0 && out.camera.fov < 3.14159f && out.camera.near_plane > 0 &&
             out.camera.near_plane < out.camera.far_plane && out.camera.far_plane <= 1000,
         "front end camera");
    const auto lights = r.count(8, 0);
    for (uint32_t i = 0; i < lights; ++i) out.lights.push_back(light());
    out.ambient = r.floats<3>();
  };
  auto model = [&](FrontScene &out) {
    const auto bytes = r.u();
    const auto start = r.p;
    const auto magic = r.raw(4);
    need(magic == "N3S1" || magic == "N3SM", "front end model magic");
    out.model.channels = magic == "N3SM" ? 4 : 3;
    read_scene_head(r, out.model, 2048);
    read_scene_tracks(r, out.model, out.model.tracks);
    read_scene_tail(r, out.model);
    need(r.p - start == bytes, "front end model length");
    out.clips.push_back(out.model.tracks);
    const auto extra = r.count(4, 0);
    for (uint32_t i = 0; i < extra; ++i) {
      const auto length = r.u();
      const auto at = r.p;
      std::vector<Track> tracks;
      read_scene_tracks(r, out.model, tracks);
      need(r.p - at == length, "front end clip length");
      out.clips.push_back(std::move(tracks));
    }
    for (const auto &clip : out.clips) need(!clip.empty(), "front end clip without tracks");
    // Version 4: each clip's blend time (__AnimData::fTimeBlend, seconds).
    for (size_t i = 0; i < out.clips.size(); ++i) {
      const float blend = std::bit_cast<float>(r.u());
      need(std::isfinite(blend) && blend >= 0 && blend <= 10, "front end clip blend");
      out.blends.push_back(blend);
    }
    const auto plugs = r.count(4, 0);
    for (uint32_t i = 0; i < plugs; ++i) {
      FrontPlug plug;
      plug.joint = r.u();
      need(plug.joint < out.model.joints.size(), "front end plug joint");
      plug.mesh = mesh();
      out.plugs.push_back(std::move(plug));
    }
  };
  scene(fe.intro);
  model(fe.intro);
  fe.backdrop = r.u();
  fe.backdrop_rect = r.floats<4>();
  need(fe.backdrop < fe.textures.size() && fe.backdrop_rect[0] < fe.backdrop_rect[2] &&
           fe.backdrop_rect[1] < fe.backdrop_rect[3],
       "front end backdrop");
  scene(fe.select);
  const auto slots = r.count(3);
  need(slots == fe.character_slots, "front end slots");
  for (uint32_t i = 0; i < slots; ++i) {
    FrontSlot slot;
    slot.position = r.floats<3>();
    slot.yaw = r.f();
    slot.eye = r.floats<3>();
    slot.spot = light();
    fe.slots.push_back(slot);
  }
  // Version 4: the spot's growth rate (theta per second).
  fe.spot_rate = std::bit_cast<float>(r.u());
  need(std::isfinite(fe.spot_rate) && fe.spot_rate > 0 && fe.spot_rate <= 100, "front end spot rate");
  const auto parts = r.count(64);
  for (uint32_t i = 0; i < parts; ++i) fe.hall.push_back(mesh());
  model(fe.select);
  // The hover, start and rest clips (pre_select, selected, dummy).
  need(fe.select.clips.size() == 3, "front end select clips");
  model(fe.create);
  // 9. Music (version 3, RQ-018): each track's frames checked whole here, so
  // the stream that decodes them later meets only well-formed frames.
  const auto tracks = r.count(kMusicTracks, 0);
  for (uint32_t i = 0; i < tracks; ++i) {
    auto track = std::make_shared<MusicTrack>();
    track->rate = r.u();
    track->channels = r.u();
    const auto loop = r.u();
    need(loop <= 1, "music loop");
    track->loop = loop == 1;
    track->frames = r.count(uint32_t(kMusicTrackBytes / 24));
    track->data = r.raw(r.count(uint32_t(kMusicTrackBytes)));
    check_music_track(*track);
    fe.music.push_back(std::move(track));
  }
  for (auto &screen : fe.screen_music) {
    screen = r.u();
    need(screen == FrontEnd::kNoMusic || screen < fe.music.size(), "music screen track");
  }
  r.end();
  return fe;
}
} // namespace n3e
