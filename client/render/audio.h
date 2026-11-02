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
  // RQ-105 (Q75 (a), maintainer 2026-11-02): every stream of a new track
  // starts at its first sample, and a restart period counts from that start,
  // so a return to the login plays its track at once.
  // carry_music_clock (off by default; RQ-103's realm-owner option, which
  // sets it before the first play_music): RQ-096's process clock instead. A
  // restarting track keeps its clock for the process; the clock runs only
  // while the track is the screen's (it counts the frames mixed for it); a
  // stream that leaves keeps its phase, and the next stream of that track
  // starts at it, silent until the period, as KO 1097's and 1264's login Init
  // creates the login track again but only the login tick's own timer
  // (006e0344, 007ac9d0) plays it. At most kMusicTracks phases are kept,
  // those of tracks no longer loaded dropped first.
  bool carry_music_clock=false;
  std::unique_ptr<MusicStream> music;
  // RQ-101: the music's gain under the voices' (1, or a fade-out the screen
  // sets each frame: 1264's logo fades its track, 004371a0).
  float music_gain=1;
  struct MusicPhase {std::weak_ptr<const MusicTrack> track;uint64_t frames=0;};
  std::vector<MusicPhase> music_phases;
  uint64_t music_phase(const std::shared_ptr<const MusicTrack>&track)const{
    for(const auto&p:music_phases)if(p.track.lock()==track)return p.frames;
    return 0;
  }
  void keep_music_phase(){
    if(!music||!music->restarting())return;
    std::erase_if(music_phases,[](const auto&p){return p.track.expired();});
    for(auto&p:music_phases)if(p.track.lock()==music->track()){p.frames=music->period_phase();return;}
    if(music_phases.size()>=kMusicTracks)music_phases.erase(music_phases.begin());
    music_phases.push_back({music->track(),music->period_phase()});
  }
  void play_music(const std::shared_ptr<const MusicTrack>&track){
    if(music&&music->track()==track)return;
    if(carry_music_clock)keep_music_phase();
    if(!track){music.reset();return;}
    music=std::make_unique<MusicStream>(track,carry_music_clock?music_phase(track):0);
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
    if(music)music->mix(out.data(),frames,.6f*std::clamp(music_gain,0.f,1.f));
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
