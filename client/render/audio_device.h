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
  void open(){
    if(!SDL_InitSubSystem(SDL_INIT_AUDIO)){std::cerr<<"Audio unavailable: "<<SDL_GetError()<<'\n';return;}
    SDL_AudioSpec spec{SDL_AUDIO_F32,2,48000};
    stream=SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK,&spec,nullptr,nullptr);
    if(!stream||!SDL_ResumeAudioStreamDevice(stream)){std::cerr<<"Audio unavailable: "<<SDL_GetError()<<'\n';if(stream)SDL_DestroyAudioStream(stream);stream=nullptr;return;}
    enabled=true;
  }
  void clear(){mixer.voices.clear();if(stream)SDL_ClearAudioStream(stream);next=0;}
  void tick(double now,const n3e::AudioListener&listener){
    if(!stream){mixer.retire(now);return;}
    int queued=SDL_GetAudioStreamQueued(stream);
    if(queued<0){close();return;}
    constexpr unsigned frames=1024;
    if(queued>int(frames*2*sizeof(float)))return;
    if(next<now-.1||next>now+.2)next=now;
    auto samples=mixer.mix(next,frames,listener);next+=frames/48000.;
    for(float sample:samples)peak=std::max(peak,std::abs(sample));
    if(!SDL_PutAudioStreamData(stream,samples.data(),int(samples.size()*sizeof(float))))close();
    else if(std::any_of(samples.begin(),samples.end(),[](float sample){return std::abs(sample)>.0001f;}))audible_frames+=frames;
  }
  void close(){if(stream)SDL_DestroyAudioStream(stream);stream=nullptr;enabled=false;mixer.voices.clear();}
  ~AudioDevice(){close();}
};
