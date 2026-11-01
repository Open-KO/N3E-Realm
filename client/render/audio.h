#pragma once
#include "assets/assets.h"
#include "assets/music.h"
#include <algorithm>
#include <cmath>
#include <memory>
#include <vector>

namespace n3e {
// No file access, threads or device calls. All positions use displayed world units.
// eye: the camera eye, which the effect start test measures from. position and
// right: the listener that attenuation and panning use (PQ-013).
struct AudioListener {V eye{};V position{};V right{1,0,0};};
inline float audio_distance(V a,V b){float sum=0;for(unsigned k=0;k<3;++k){float d=a[k]-b[k];sum+=d*d;}return std::sqrt(sum);}
// KO 00475d20: an effect sound starts only when the camera eye is strictly
// nearer than the distance; a sound that fails is never started.
inline bool effect_starts(V source,V eye,float distance){return audio_distance(source,eye)<distance;}
struct AudioPlacement {float gain=0,pan=0;};
// Gain (0 is silent) and pan (-1 left, 1 right) of one positional voice. Effects
// that passed the start test have no cut-off; other voices fade to the package
// cut-off. Generic inverse-distance and equal-power curves: the KO provider's
// curves are not in the supplied binaries.
inline AudioPlacement place_sound(const AudioSpatial&s,V source,const AudioListener&l,bool started_effect){
  float distance=audio_distance(source,l.position),dot=0;
  for(unsigned k=0;k<3;++k)dot+=(source[k]-l.position[k])*l.right[k];
  if(!started_effect&&distance>=s.cutoff)return {};
  float gain=std::min(1.f,s.reference/std::max(s.reference,distance));
  if(!started_effect)gain*=std::min(1.f,(s.cutoff-distance)/5);
  return {gain,distance>.001f?std::clamp(dot/distance,-1.f,1.f):0.f};
}
struct AudioMixer {
  // effect: an effect-bundle sound, which takes the start test when the
  // package sets one. checked: that test has run.
  struct Voice {const SoundClip* clip;double start;V position;bool positional;uint64_t request=0;bool effect=false;bool checked=false;};
  std::vector<Voice> voices;
  uint64_t started=0;
  AudioSpatial spatial;
  // RQ-018 (Q57): one music stream, unpositioned, mixed under the voices at
  // their gain. play_music keeps a stream that already plays the track (KO
  // 1298 005f68e0: the login keeps a BGM of the same file, even one that
  // has ended), starts another from its first frame and stops on nullptr
  // (005fea70 releases the BGM).
  std::unique_ptr<MusicStream> music;
  void play_music(const std::shared_ptr<const MusicTrack>&track){
    if(!track){music.reset();return;}
    if(music&&music->track()==track)return;
    music=std::make_unique<MusicStream>(track);
  }
  bool music_playing()const{return music&&!music->ended();}
  bool play(const Audio&data,const std::string&key,double start,V position={},bool positional=false,uint64_t request=0,bool effect=false){
    auto binding=data.bindings.find(key);if(binding==data.bindings.end()||!std::isfinite(start))return false;
    const auto&clip=data.clips[binding->second];
    if(std::count_if(voices.begin(),voices.end(),[&](const auto&v){return v.clip==&clip;})>=clip.maximum)return false;
    if(voices.size()>=64)return false;
    voices.push_back({&clip,start,position,positional,request,effect});++started;return true;
  }
  void cancel(uint64_t request){if(request)std::erase_if(voices,[&](const auto&v){return v.request==request;});}
  void retire(double now){std::erase_if(voices,[&](const auto&v){return now>=v.start+v.clip->samples.size()/48000.;});}
  bool gated(const Voice&v)const{return v.positional&&v.effect&&spatial.effect_distance>0;}
  std::vector<float> mix(double now,unsigned frames,const AudioListener&listener){
    frames=std::min(frames,4800u);std::vector<float> out(frames*2);
    retire(now);
    // The start test runs once, in the chunk where the voice begins.
    double end=now+frames/48000.;
    for(auto&v:voices)if(gated(v)&&!v.checked&&v.start<end){
      v.checked=true;if(!effect_starts(v.position,listener.eye,spatial.start_distance()))v.clip=nullptr;
    }
    std::erase_if(voices,[](const auto&v){return !v.clip;});
    if(music)music->mix(out.data(),frames,.6f);
    for(const auto&v:voices){
      float gain=.6f,pan=0;
      if(v.positional){
        auto placed=place_sound(spatial,v.position,listener,gated(v));
        if(placed.gain<=0)continue;
        gain*=placed.gain;pan=placed.pan;
      }
      float left=gain*std::sqrt((1-pan)*.5f),right_gain=gain*std::sqrt((1+pan)*.5f);
      auto offset=int64_t(std::floor((now-v.start)*48000));
      for(unsigned i=0;i<frames;++i){auto index=offset+i;if(index<0||uint64_t(index)>=v.clip->samples.size())continue;
        out[i*2]+=v.clip->samples[index]*left;out[i*2+1]+=v.clip->samples[index]*right_gain;
      }
    }
    for(auto&sample:out)sample=std::clamp(sample,-1.f,1.f);
    return out;
  }
};
}
