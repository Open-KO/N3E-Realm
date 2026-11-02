#pragma once
#include "audio.h"
#include <SDL3/SDL.h>
#include <iostream>

struct AudioDevice {
  SDL_AudioStream* stream=nullptr;
  n3e::AudioMixer mixer;
  double next=0;
  bool enabled=false;
  uint64_t audible_frames=0;float peak=0;
  uint64_t block=1024;
  void open(){
    if(!SDL_InitSubSystem(SDL_INIT_AUDIO)){std::cerr<<"Audio unavailable: "<<SDL_GetError()<<'\n';return;}
    SDL_AudioSpec spec{SDL_AUDIO_F32,2,48000};
    stream=SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK,&spec,nullptr,nullptr);
    if(!stream||!SDL_ResumeAudioStreamDevice(stream)){std::cerr<<"Audio unavailable: "<<SDL_GetError()<<'\n';if(stream)SDL_DestroyAudioStream(stream);stream=nullptr;return;}
    enabled=true;
    // RQ-104: the block the device takes at once, in the stream's 48 kHz
    // frames (SDL's default 1,024 when it does not say), at most 0.25 s.
    SDL_AudioSpec device{};int frames=0;
    if(SDL_GetAudioDeviceFormat(SDL_GetAudioStreamDevice(stream),&device,&frames)&&frames>0&&device.freq>0)
      block=std::clamp<uint64_t>(uint64_t(frames)*48000/uint64_t(device.freq),1,12000);
  }
  // RQ-104: the music as the listener hears it (AudioMixer::heard): the
  // stream's queued bytes are frames mixed and not yet played. Nothing
  // without a device.
  n3e::HeardMusic heard_music()const{
    if(!stream)return {};
    const int queued=SDL_GetAudioStreamQueued(stream);
    if(queued<0)return {};
    return mixer.heard(uint64_t(queued)/(2*sizeof(float)),block);
  }
  void clear(){mixer.voices.clear();if(stream)SDL_ClearAudioStream(stream);next=0;}
  void tick(double now,const n3e::AudioListener&listener){
    if(!stream){mixer.retire(now);return;}
    int queued=SDL_GetAudioStreamQueued(stream);
    if(queued<0){close();return;}
    constexpr unsigned frames=1024;
    constexpr int chunk=int(frames*2*sizeof(float));
    // Voices keep one chunk (21 ms) of latency. Music (RQ-018) runs up to
    // six chunks ahead, so a slow frame does not gap it; the voices' clock
    // (next) stays within the resync window below.
    const int ahead=mixer.music_playing()?6:1;
    for(int round=0;round<ahead&&queued<=ahead*chunk;++round){
      if(next<now-.1||next>now+.2)next=now;
      auto samples=mixer.mix(next,frames,listener);next+=frames/48000.;
      for(float sample:samples)peak=std::max(peak,std::abs(sample));
      if(!SDL_PutAudioStreamData(stream,samples.data(),int(samples.size()*sizeof(float)))){close();return;}
      if(std::any_of(samples.begin(),samples.end(),[](float sample){return std::abs(sample)>.0001f;}))audible_frames+=frames;
      queued+=chunk;
    }
  }
  void close(){if(stream)SDL_DestroyAudioStream(stream);stream=nullptr;enabled=false;mixer.voices.clear();mixer.music.reset();}
  ~AudioDevice(){close();}
};
