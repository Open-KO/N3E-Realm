#include "render/audio.h"
#include "render/melee_presentation.h"
#include "render/presentation_events.h"
#include "render/local_release.h"
#include "render/scene_clock.h"
#include <deque>
#include <iostream>
#include <stdexcept>
#include <source_location>
void need(bool value,std::source_location where=std::source_location::current()){if(!value)throw std::runtime_error("audio/event check line "+std::to_string(where.line()));}
bool near(float a,float b){return std::abs(a-b)<1e-5f;}
float energy(const std::vector<float>&out){float sum=0;for(float x:out)sum+=std::abs(x);return sum;}
// RQ-018: synthetic MPEG-1 Layer III frames, 32 kbit/s, mono, no CRC (as
// tests/front_end.py's mp3_frame): `rate` is the header's index (1 48 kHz,
// 2 32 kHz). A tone frame's granules each carry one count1 quadruple, so it
// decodes to a quiet low tone; big_values past 288 makes a frame the decoder
// refuses (minimp3's L3_read_side_info).
std::string mp3_frame(bool tone=true,unsigned rate=1,unsigned big_values=0){
  std::vector<int> bits;
  auto put=[&](unsigned v,int n){for(int i=n-1;i>=0;--i)bits.push_back((v>>i)&1);};
  // sync, MPEG-1, Layer III, no CRC, 32 kbit/s, rate, no padding, private, mono, ...
  const std::pair<unsigned,int> header[]={{0x7ff,11},{3,2},{1,2},{1,1},{1,4},{rate,2},{0,1},{0,1},{3,2},{0,2},{0,1},{0,1},{0,2}};
  for(auto[v,n]:header)put(v,n);
  put(0,9);put(0,5);put(0,4);
  for(int g=0;g<2;++g){
    const std::pair<unsigned,int> side[]={{tone?5u:0u,12},{big_values,9},{210,8},{0,4},{0,1},{0,15},{0,4},{0,3},{0,1},{0,1},{1,1}};
    for(auto[v,n]:side)put(v,n);
  }
  for(int g=0;g<2&&tone;++g){put(7,4);put(0,1);}
  const unsigned size=144000*32/(rate==1?48000:32000);
  bits.resize(size*8,0);
  std::string out(size,'\0');
  for(size_t i=0;i<bits.size();++i)if(bits[i])out[i/8]=char(out[i/8]|(0x80>>(i%8)));
  return out;
}
std::shared_ptr<n3e::MusicTrack> music_track(const std::string&frame,unsigned frames,unsigned rate,bool loop){
  auto t=std::make_shared<n3e::MusicTrack>();t->rate=rate;t->channels=1;t->loop=loop;t->frames=frames;
  for(unsigned i=0;i<frames;++i)t->data+=frame;
  return t;
}
bool refused(const n3e::MusicTrack&t){try{n3e::check_music_track(t);}catch(const std::exception&){return true;}return false;}
// Streams up to `limit` 48 kHz frames in chunks; returns {written, peak}.
std::pair<uint64_t,float> drain(n3e::MusicStream&s,uint64_t limit){
  std::vector<float> out(4800*2);uint64_t written=0;float peak=0;
  while(written<limit){std::fill(out.begin(),out.end(),0.f);auto n=s.mix(out.data(),4800,1);
    for(unsigned i=0;i<n*2;++i)peak=std::max(peak,std::abs(out[i]));written+=n;if(n<4800)break;}
  return {written,peak};
}
// RQ-083: a 16-bit PCM track (KO 1097's WAVs) of `frames` sample frames,
// each channel a ramp, and the restart period KO 1097's login tick gives
// sound 35 (005248f5-00524957).
std::shared_ptr<n3e::MusicTrack> pcm_track(unsigned frames,unsigned rate,unsigned channels,bool loop,float restart=0){
  auto t=std::make_shared<n3e::MusicTrack>();t->kind=n3e::MusicTrack::Kind::pcm;t->rate=rate;t->channels=channels;
  t->loop=loop;t->restart=restart;t->frames=frames;
  for(unsigned i=0;i<frames;++i)for(unsigned c=0;c<channels;++c){
    const int16_t v=int16_t(c?-int(i%100)*200:int(i%100)*200);t->data+=char(uint16_t(v)&0xff);t->data+=char(uint16_t(v)>>8);}
  return t;
}
void pcm_checks(const std::shared_ptr<n3e::MusicTrack>&mpeg){
  // Every sample once at 48 kHz, its value as KO's 16-bit sample / 32768,
  // the right channel its own; then the stream ends.
  auto once=pcm_track(4000,48000,2,false);n3e::check_music_track(*once);
  {n3e::MusicStream s(once);std::vector<float> out(5000*2,0.f);need(s.mix(out.data(),5000,1)==4000&&s.ended());
   need(near(out[0],0)&&near(out[2*7],7*200/32768.f)&&near(out[2*7+1],-7*200/32768.f)&&near(out[2*3999],99*200/32768.f));
   need(s.decoded_frames()==4000);}
  // 22,050 Hz stereo (bgm_login.wav's form) resampled: 48000/22050 output
  // frames a sample; looping, it never ends.
  auto low=pcm_track(22050,22050,2,false);n3e::check_music_track(*low);
  {n3e::MusicStream s(low);auto[written,peak]=drain(s,1<<20);need(written>=47998&&written<=48002&&peak>.5f&&s.ended());}
  auto loop=pcm_track(2205,22050,2,true);
  {n3e::MusicStream s(loop);auto[written,peak]=drain(s,5*48000);need(written==5*48000&&!s.ended()&&s.decoded_frames()>=10*2205);}
  // Mono plays the one channel on both sides.
  {n3e::MusicStream s(pcm_track(100,48000,1,false));std::vector<float> out(200*2,0.f);need(s.mix(out.data(),200,1)==100);
   need(near(out[2*9],9*200/32768.f)&&near(out[2*9+1],out[2*9]));}
  // A restart period: a track that does not loop and is shorter than the
  // period plays once, is silent, and starts again at its first sample on
  // the period, ended or not, without ending; one longer than the period is
  // cut there (bgm_login.wav's last 6.6 ms, 21.667 s against 21.66 s).
  {auto t=pcm_track(1000,48000,1,false,0.1f);n3e::check_music_track(*t);n3e::MusicStream s(t);
   std::vector<float> out(9600*2,0.f);need(s.mix(out.data(),9600,1)==9600&&!s.ended()&&s.restarts()==1);
   need(near(out[2*999],99*200/32768.f)&&out[2*1000]==0&&out[2*4799]==0&&near(out[2*4800],0)&&near(out[2*4807],7*200/32768.f));
   need(s.decoded_frames()==2000);}
  {auto t=pcm_track(48000,48000,1,true,0.5f);n3e::MusicStream s(t);auto[written,peak]=drain(s,48000*2);
   need(written==96000&&s.restarts()==3&&s.decoded_frames()<=4*24000+1152&&!s.ended());}
  // An MPEG track restarts the same way, with a fresh decoder.
  {auto t=std::make_shared<n3e::MusicTrack>(*mpeg);t->restart=0.5f;n3e::check_music_track(*t);n3e::MusicStream s(t);
   auto[written,peak]=drain(s,48000*3);need(written==3*48000&&s.restarts()==5&&!s.ended()&&peak>.1f);}
  // The loader's PCM checks.
  auto t=*once;need(!refused(t));
  t=*once;t.frames=3999;need(refused(t));
  t=*once;t.data.pop_back();need(refused(t));
  t=*once;t.rate=7999;need(refused(t));
  t=*once;t.rate=96001;need(refused(t));
  t=*once;t.channels=3;need(refused(t));
  t=*once;t.data.clear();t.frames=0;need(refused(t));
  t=*once;t.restart=0.05f;need(refused(t));
  t=*once;t.restart=3601;need(refused(t));
  t=*once;t.restart=-1;need(refused(t));
  t=*once;t.restart=0.1f;need(!refused(t));
  t=*once;t.kind=n3e::MusicTrack::Kind(2);need(refused(t));
  t=*once;t.kind=n3e::MusicTrack::Kind::mpeg;need(refused(t)); // samples are not frames
  // The mixer keeps a restarting stream across its restarts.
  n3e::AudioMixer m;auto r=pcm_track(1000,48000,1,false,0.1f);m.play_music(r);auto*stream=m.music.get();
  for(int i=0;i<10;++i)m.mix(i*.1,4800,{});need(m.music.get()==stream&&m.music_playing()&&stream->restarts()==9);
  // RQ-105 (Q75 (a), maintainer 2026-11-02), the default: every entry starts
  // a restarting track at its first sample and its period counts from there.
  // The first entry plays at once; a return after another screen's track
  // plays at once too, and restarts a period after that return; nothing is
  // kept for the track.
  {n3e::AudioMixer m;need(!m.carry_music_clock);
   auto login=pcm_track(1000,48000,1,false,0.1f),other=pcm_track(4800,48000,1,true);
   m.play_music(login);auto out=m.mix(0,2400,{});need(m.music->restarts()==0&&near(out[2*7],.6f*7*200/32768.f));
   need(m.music->period_phase()==2400);
   m.play_music(other);for(int i=0;i<3;++i)m.mix(0,4800,{});need(m.music_phases.empty());
   m.play_music(login);need(m.music->period_phase()==0&&m.music_playing());
   out=m.mix(0,4800,{});
   need(near(out[0],0)&&near(out[2*7],.6f*7*200/32768.f)&&near(out[2*999],.6f*99*200/32768.f)&&out[2*1000]==0);
   need(m.music->restarts()==0&&m.music->period_phase()==4800);
   out=m.mix(0,8,{});need(m.music->restarts()==1&&near(out[2*7],.6f*7*200/32768.f));
   // The world (no track) between keeps nothing either.
   m.play_music(nullptr);need(!m.music&&m.music_phases.empty());
   m.play_music(login);out=m.mix(0,8,{});need(m.music->restarts()==0&&near(out[2*7],.6f*7*200/32768.f));}
  // carry_music_clock (RQ-096, RQ-103's option): the restart clock is the
  // track's for the process, as KO 1097's and 1264's login timer (006e0344,
  // 007ac9d0) that no Init resets. The first entry plays at once; the clock
  // stops while another screen's track plays; back on the track's screen,
  // the track is silent until the clock reaches the period, then starts at
  // its first sample.
  {n3e::AudioMixer m;m.carry_music_clock=true;auto login=pcm_track(1000,48000,1,false,0.1f),other=pcm_track(4800,48000,1,true);
   m.play_music(login);auto out=m.mix(0,2400,{});need(m.music->restarts()==0&&near(out[2*7],.6f*7*200/32768.f));
   need(m.music->period_phase()==2400);
   m.play_music(other);for(int i=0;i<3;++i)m.mix(0,4800,{});need(m.music->period_phase()==0&&m.music_phases.size()==1);
   m.play_music(login);need(m.music->period_phase()==2400&&m.music_playing());
   out=m.mix(0,4800,{});
   bool silent=true;for(unsigned i=0;i<2400*2;++i)silent=silent&&out[i]==0;
   need(silent&&near(out[2*2400],0)&&near(out[2*2407],.6f*7*200/32768.f)&&m.music->restarts()==1&&m.music->period_phase()==2400);
   // Leaving at the period's end and the world (no track) keep the phase too.
   m.play_music(nullptr);need(!m.music&&m.music_phases.size()==1&&m.music_phases[0].frames==2400);
   // A track that does not restart keeps no phase and starts at once.
   m.play_music(other);out=m.mix(0,100,{});need(m.music->period_phase()==0&&near(out[2*7],.6f*7*200/32768.f));
   m.play_music(login);m.mix(0,2399,{});need(m.music->restarts()==0);m.mix(0,2,{});need(m.music->restarts()==1);}
  // The phases kept are bounded by the track count; unloaded tracks go first.
  {n3e::AudioMixer m;m.carry_music_clock=true;std::vector<std::shared_ptr<n3e::MusicTrack>> tracks;
   for(unsigned i=0;i<6;++i){tracks.push_back(pcm_track(100,48000,1,false,1));m.play_music(tracks.back());m.mix(0,10,{});}
   m.play_music(nullptr);need(m.music_phases.size()==n3e::kMusicTracks&&m.music_phase(tracks[5])==10&&m.music_phase(tracks[0])==0);
   tracks[3].reset();m.play_music(pcm_track(100,48000,1,false,1));m.mix(0,5,{});m.play_music(nullptr);
   need(m.music_phases.size()==n3e::kMusicTracks&&m.music_phase(tracks[2])==10&&m.music_phase(tracks[4])==10);}
  std::cout<<"PASS music pcm: 16-bit samples once and looping, 22,050 Hz resampling, mono, restart periods from each entry and the optional process clock (Q75), loader checks\n";
}
void music_checks(){
  const auto tone=mp3_frame();need(tone.size()==96);
  auto f=n3e::mpeg_frame(reinterpret_cast<const unsigned char*>(tone.data()),tone.size());
  need(f&&f->bytes==96&&f->rate==48000&&f->channels==1&&f->mpeg1);
  need(!n3e::mpeg_frame(reinterpret_cast<const unsigned char*>(tone.data()),95));
  // A track that does not loop: every sample once (50 x 1152 at 48 kHz),
  // audible, then the stream ends and stays ended.
  auto once=music_track(tone,50,48000,false);n3e::check_music_track(*once);
  {n3e::MusicStream s(once);auto[written,peak]=drain(s,1<<20);need(written==50*1152&&peak>.1f&&s.ended()&&s.decoded_frames()==50);
   std::vector<float> out(200,0.f);need(s.mix(out.data(),100,1)==0&&energy(out)==0);}
  // Looping: three passes and more, never ending.
  auto loop=music_track(tone,50,48000,true);
  {n3e::MusicStream s(loop);auto[written,peak]=drain(s,3*57600+1000);need(written>=3*57600+1000&&!s.ended()&&s.decoded_frames()>150&&peak>.1f);}
  // 32 kHz resampled to 48 kHz: 1.5 output frames a sample.
  auto low=music_track(mp3_frame(true,2),10,32000,false);need(low->data.size()==1440);n3e::check_music_track(*low);
  {n3e::MusicStream s(low);auto[written,peak]=drain(s,1<<20);need(written>=17278&&written<=17282&&peak>0);}
  // Silent frames stream silence; frames the decoder refuses end even a
  // looping stream after one pass instead of spinning.
  {n3e::MusicStream s(music_track(mp3_frame(false),5,48000,true));auto[written,peak]=drain(s,20000);need(written>=20000&&peak==0);}
  {auto bad=music_track(mp3_frame(true,1,300),5,48000,true);n3e::check_music_track(*bad);
   n3e::MusicStream s(bad);need(drain(s,20000).first==0&&s.ended());}
  // The loader's frame checks.
  auto t=*once;t.frames=49;need(refused(t));
  t=*once;t.rate=44100;need(refused(t));
  t=*once;t.channels=2;need(refused(t));
  t=*once;t.data.pop_back();need(refused(t));
  t=*once;t.data[1]=char(0xfd);need(refused(t)); // Layer II
  t=*once;t.data.clear();t.frames=0;need(refused(t));
  t=*once;t.data+=mp3_frame(true,2);t.frames=51;need(refused(t)); // a second rate
  // The mixer: one stream at the voices' gain, kept for the same track (an
  // ended one too), replaced by another, stopped by none.
  n3e::AudioMixer m;need(!m.music_playing());
  m.play_music(loop);need(m.music_playing());auto*stream=m.music.get();
  m.play_music(loop);need(m.music.get()==stream);
  float most=0;for(int i=0;i<30;++i){auto out=m.mix(i*.1,4800,{});for(float x:out)most=std::max(most,std::abs(x));}
  need(most>.06f&&most<=.6f);
  m.play_music(once);need(m.music.get()!=stream&&m.music->track()==once);
  for(int i=0;i<15;++i)m.mix(i*.1,4800,{});need(!m.music_playing()&&m.music);
  auto*ended=m.music.get();m.play_music(once);need(m.music.get()==ended&&!m.music_playing());
  m.play_music(nullptr);need(!m.music&&energy(m.mix(9,4800,{}))==0);
  std::cout<<"PASS music: frame checks, a track once and looping, 32 kHz resampling, undecodable frames end, mixer keeps and replaces streams\n";
  pcm_checks(once);
}
// RQ-104: the front end's tracks play at their own rate, and the login
// scene (client/render/scene_clock.h) keeps the login track's time, on the
// first entry and on each return.
void scene_music_checks(){
  // The rate: bgm_login.wav's form (22,050 Hz stereo 16-bit, 477,749 frames,
  // here without its restart: one pass) plays 477749 x 48000 / 22050 =
  // 1,039,998.6 frames of the mixer's 48 kHz, the source's 21.667 s, every
  // source frame once; output frame 320 m is source frame 147 m. bless.wav's
  // (mono, 305,280 frames) plays 664,555.1, 13.845 s.
  auto play=[](const std::shared_ptr<n3e::MusicTrack>&t,uint64_t probe,float&at){
    n3e::MusicStream s(t);std::vector<float> out(4800*2);uint64_t written=0;
    for(;;){std::fill(out.begin(),out.end(),0.f);auto n=s.mix(out.data(),4800,1);
      if(written<=probe&&probe<written+n)at=out[2*(probe-written)];
      written+=n;if(n<4800)break;}
    need(s.decoded_frames()==t->frames);return written;};
  {auto t=pcm_track(477749,22050,2,false);n3e::check_music_track(*t);float at=-1;
   const auto written=play(t,320ull*3001,at);
   need(std::abs(double(written)-477749.*48000/22050)<1.5&&std::abs(at-47*200/32768.f)<1e-4f);}
  {auto t=pcm_track(305280,22050,1,false);float at=-1;const auto written=play(t,320ull*11,at);
   need(std::abs(double(written)-305280.*48000/22050)<1.5&&std::abs(at-(1617%100)*200/32768.f)<1e-4f);}
  // Its restart period (21.66 s) is 1,039,680 frames: the frame there is the
  // first sample again.
  {auto t=pcm_track(477749,22050,2,false,21.66f);n3e::check_music_track(*t);n3e::MusicStream s(t);
   std::vector<float> out(4800*2);uint64_t written=0;
   while(written<1039680){std::fill(out.begin(),out.end(),0.f);written+=s.mix(out.data(),unsigned(std::min<uint64_t>(4800,1039680-written)),1);}
   need(s.restarts()==0&&s.period_frames()==1039680&&s.mixed_frames()==1039680);
   std::fill(out.begin(),out.end(),0.f);s.mix(out.data(),400,1);
   need(s.restarts()==1&&near(out[0],0)&&std::abs(out[2*320]-47*200/32768.f)<1e-4f);}
  // What the listener hears (AudioMixer::heard): the position in the period,
  // `queued` frames behind those mixed; at the start while the queue still
  // holds an earlier stream's frames; none for a track without a period.
  {n3e::AudioMixer m;auto login=pcm_track(1000,48000,1,false,0.1f),other=pcm_track(4800,48000,1,true);
   need(!m.heard(0).track);
   m.play_music(other);m.mix(0,2400,{});need(!m.heard(0).track);
   m.play_music(login);auto h=m.heard(2400);need(h.track==login.get()&&h.seconds==0);
   m.mix(0,2400,{});h=m.heard(3000);need(h.track==login.get()&&h.seconds==0);
   h=m.heard(1200);need(near(float(h.seconds),1200/48000.f));
   m.mix(0,2500,{});need(m.music->restarts()==1);
   h=m.heard(0);need(near(float(h.seconds),100/48000.f));
   h=m.heard(300);need(near(float(h.seconds),4600/48000.f));}
  // With the carried clock (carry_music_clock), a return is heard at the
  // carried phase.
  {n3e::AudioMixer m;m.carry_music_clock=true;auto login=pcm_track(1000,48000,1,false,0.1f);
   m.play_music(login);m.mix(0,1200,{});m.play_music(nullptr);m.play_music(login);
   auto h=m.heard(0);need(near(float(h.seconds),1200/48000.f));
   m.mix(0,600,{});h=m.heard(0);need(near(float(h.seconds),1800/48000.f));}
  // The scene clock alone: it starts at 0 on the first frame that shows the
  // scene and runs on the frame time; a heard track of the screen's holds it
  // within the block the device plays (from the block's start to its end);
  // another track's does not; when the track is no longer heard it runs on
  // from where it was.
  {n3e::front::SceneClock c;auto login=pcm_track(100,48000,1,false,1),other=pcm_track(100,48000,1,true);
   need(c.tick(false,3,other.get(),{})==0&&c.entries==0);
   need(c.tick(true,12,login.get(),{other.get(),5,10,.02})==0&&c.entries==1);
   need(c.tick(true,12.5,login.get(),{})==.5);
   need(c.tick(true,12.6,login.get(),{login.get(),.25,1,0})==.25);         // held to the heard time
   need(near(float(c.tick(true,12.61,login.get(),{login.get(),.27,1,.02})),.26f)); // runs on inside the block
   need(near(float(c.tick(true,12.65,login.get(),{login.get(),.27,1,.02})),.27f)); // not past its end
   need(near(float(c.tick(true,12.66,login.get(),{login.get(),.5,1,.02})),.48f));  // nor behind its start
   need(near(float(c.tick(true,12.67,login.get(),{login.get(),.01,.6,.02})),.0f)); // the period started again
   need(near(float(c.tick(true,13.67,login.get(),{})),1));                        // the device closed: on from there
   need(c.entries==1);
   need(c.tick(false,41,other.get(),{other.get(),.5})==0);
   need(c.tick(true,90,login.get(),{})==0&&c.entries==2);
   need(c.tick(true,91,nullptr,{login.get(),.5})==1);}
  // The scene against the music a device plays, frame by frame at 60 Hz:
  // the viewer's order (the heard music, then the frame, then the screen's
  // track and AudioDevice::tick's queue of up to seven 1,024-frame chunks),
  // the device taking 1,024-frame blocks at 48 kHz. The logo's track, then
  // the login (the first entry; a 0.6 s stall the device runs dry over; the
  // realm list), select's track, the login again (a return), loading, the
  // world (no front-end frames, no music), the login again, and the device
  // closing. Wherever the login's track is heard the scene is within the
  // block the device plays, so the character's clip (21.667 s, restarting
  // with the period) and the track keep time; until it is heard the scene
  // holds its first frame. In steady frames its steps are the frame's, and
  // none goes back.
  {auto login=pcm_track(477749,22050,2,false,21.66f),logo=pcm_track(30000,22050,1,false),battle=pcm_track(22050,22050,2,true);
   n3e::AudioMixer m;n3e::front::SceneClock c;constexpr uint64_t block=1024;
   struct Segment {const n3e::MusicTrack*track;uint64_t at,frames;};
   std::deque<Segment> queue;uint64_t queued=0,owed=0;double now=5;bool device=true;
   auto next_at=[&]{return m.music&&m.music->restarting()?(m.music->start_phase()+m.music->mixed_frames())%m.music->period_frames():0;};
   uint64_t checked=0,waiting=0,steady=0,uneven=0;double last_t=-1;int settle=0;
   auto take=[&](uint64_t frames){
     while(frames&&!queue.empty()){auto&s=queue.front();const auto n=std::min(frames,s.frames);
       s.frames-=n;s.at+=n;frames-=n;queued-=n;if(!s.frames)queue.pop_front();}};
   auto consume=[&](uint64_t frames){owed+=frames;while(owed>=block){take(block);owed-=block;}};
   auto frame=[&](bool scene,const n3e::MusicTrack*track,bool draw=true){
     if(draw){
       const auto heard=device?m.heard(queued,block):n3e::HeardMusic{};
       const double t=c.tick(scene,now,scene?track:nullptr,heard);
       if(scene){
         // The queue's front is the frame after the block the device plays.
         const n3e::MusicTrack*playing=queue.empty()?(m.music?m.music->track().get():nullptr):queue.front().track;
         const uint64_t at=queue.empty()?next_at():queue.front().at;
         if(device&&playing==track){
           need(std::abs(heard.seconds-double(at%1039680)/48000)<1e-9);
           need(t<=heard.seconds+1e-9&&t>=heard.seconds-block/48000.-1e-9&&t<21.66);++checked;
         }else if(device){need(t==0);++waiting;}
         if(last_t>=0){double step=t-last_t;if(step<-10)step+=1039680/48000.;
           need(step>=-1e-9);
           if(settle>120){++steady;if(std::abs(step-1/60.)>1e-6)++uneven;}}
         last_t=t;++settle;
       }else{last_t=-1;settle=0;}
     }
     std::shared_ptr<const n3e::MusicTrack> want;
     for(const auto&p:{login,logo,battle})if(p.get()==track)want=p;
     m.play_music(want);
     const uint64_t ahead=m.music_playing()?6:1;
     for(uint64_t round=0;round<ahead&&queued<=ahead*1024;++round){
       queue.push_back({m.music?m.music->track().get():nullptr,next_at(),1024});m.mix(0,1024,{});queued+=1024;}
     consume(800);now+=1/60.;};
   auto run=[&](double seconds,bool scene,const n3e::MusicTrack*track,bool draw=true){
     for(int i=0,n=int(std::lround(seconds*60));i<n;++i)frame(scene,track,draw);};
   run(2,false,logo.get());
   run(10,true,login.get());need(c.entries==1&&waiting>0&&waiting<12);
   consume(28800);now+=.6;settle=0;  // the stall: the device plays out its queue
   run(20,true,login.get());run(5,true,login.get());
   run(3,false,battle.get());waiting=0;
   run(25,true,login.get());need(c.entries==2&&waiting>0&&waiting<12);
   run(.5,false,nullptr);run(2,false,nullptr,false);
   run(200,true,login.get());need(c.entries==3&&checked>15000);
   // In steady frames every step is the frame's (the heard position alone
   // moves in 1,024-frame blocks, 21.3 ms, against 16.7 ms frames).
   need(steady>14000&&uneven*100<steady);
   // The device closes: the scene runs on from where it was, by the frame.
   const double before=c.seconds;device=false;frame(true,login.get());need(near(float(c.seconds-before),1/60.f));
   run(1,true,login.get());need(near(float(c.seconds-before),61/60.f)&&c.entries==3);}
  std::cout<<"PASS front-end music rate (22,050 Hz tracks at their source length, the 21.66 s period) and the login scene on the heard music: first entry, a stall, returns, even steps, the device closing\n";
}
// PQ-013: KO effect start test, listener frame, curves and fixed source positions.
void spatial_checks(){
  const n3e::AudioSpatial legacy,ko{1,48,20,48,30,2};
  // Sound.Distance: default 48; a player's integer option clamps to 20..48 (0064b9b0).
  need(ko.start_distance()==48&&ko.start_distance(10)==20&&ko.start_distance(30)==30&&ko.start_distance(100)==48);
  need(legacy.start_distance()==0&&legacy.start_distance(30)==0);
  // Strict "<" against the camera eye (00475d20 FCOMP/TEST AH,1).
  need(n3e::effect_starts({47.99f,0,0},{},48)&&!n3e::effect_starts({48,0,0},{},48)&&!n3e::effect_starts({0,0,60},{},48));
  // Curves: full gain to the reference, inverse distance beyond it; the cut-off
  // fades over its last 5 m only for voices without the start test.
  n3e::AudioListener at{{},{},{1,0,0}};
  need(near(n3e::place_sound(ko,{1,0,0},at,false).gain,1)&&near(n3e::place_sound(ko,{4,0,0},at,false).gain,.5f));
  need(near(n3e::place_sound(ko,{27.5f,0,0},at,false).gain,2/27.5f*.5f)&&n3e::place_sound(ko,{30,0,0},at,false).gain==0);
  need(near(n3e::place_sound(ko,{40,0,0},at,true).gain,2/40.f)&&near(n3e::place_sound(ko,{47.9f,0,0},at,true).gain,2/47.9f));
  need(near(n3e::place_sound(ko,{0,0,5},at,true).pan,0)&&near(n3e::place_sound(ko,{3,0,4},at,true).pan,.6f));
  // The listener frame pans: facing heading 0 hears +x on the right, heading pi on the left.
  auto facing=[](float h){return n3e::AudioListener{{50,9,50},{},{std::cos(h),0,-std::sin(h)}};};
  need(n3e::place_sound(ko,{5,0,0},facing(0),true).pan>.99f&&n3e::place_sound(ko,{5,0,0},facing(3.14159265f),true).pan<-.99f);
  n3e::Audio a;a.clips.push_back({8,std::vector<float>(48000,.5f)});a.bindings["effect:x"]=0;a.bindings["swing:player"]=0;
  n3e::AudioMixer m;m.spatial=ko;
  // Started at 47 m from the eye: audible with no cut-off (the 30 m cut-off would silence it).
  need(m.play(a,"effect:x",1,{47,0,0},true,0,true));need(m.play(a,"swing:player",1,{47,0,0},true));
  auto out=m.mix(1,100,{{},{},{1,0,0}});need(m.voices.size()==2&&energy(out)>0);
  need(near(out[1],.5f*.6f*2/47*std::sqrt(1.f))&&out[0]<1e-6f); // only the effect, fully right
  // At exactly 48 m from the eye it never starts, though the listener stands on it,
  // and it stays silent when the eye comes near later.
  m.voices.clear();need(m.play(a,"effect:x",1,{48,0,0},true,0,true));
  need(energy(m.mix(1,100,{{},{48,0,0},{1,0,0}}))==0&&m.voices.empty());
  need(energy(m.mix(1.01,100,{{48,0,0},{48,0,0},{1,0,0}}))==0);
  // The test runs in the chunk where the voice begins, not when it is queued.
  need(m.play(a,"effect:x",2,{10,0,0},true,0,true));
  m.mix(1,100,{{100,0,0},{},{1,0,0}});need(m.voices.size()==1&&!m.voices[0].checked);
  need(energy(m.mix(2,100,{{},{},{1,0,0}}))>0&&m.voices[0].checked);
  // Once started it keeps playing however far the eye moves (KO halts no 3-D sample on distance).
  need(energy(m.mix(2.1,100,{{500,0,0},{},{1,0,0}}))>0);
  // The source keeps its start position (KO 004501b0 sets it once; 0044fdf0 changes
  // only volume); the moving listener changes the gain chunk by chunk.
  auto near_chunk=m.mix(2.2,100,{{},{8,0,0},{1,0,0}}),far_chunk=m.mix(2.3,100,{{},{-10,0,0},{1,0,0}});
  need(m.voices[0].position==n3e::V{10,0,0}&&energy(near_chunk)>energy(far_chunk)*4);
  // Without N3A2 data an effect takes the 30 m cut-off like any positional voice.
  n3e::AudioMixer old;need(old.play(a,"effect:x",1,{40,0,0},true,0,true));
  need(energy(old.mix(1,100,{{},{},{1,0,0}}))==0&&old.voices.size()==1);
  // Presentation events flag effect-bundle sounds ("effect:" keys) for the start test only.
  n3e::Release r;r.audio=a;r.audio->bindings["blow"]=0;r.effects.emplace();r.effects->bindings.push_back({2,"*",0,0,{"x"}});
  n3e::WorldState w;w.world.set_tick(50);n3e::PresentationEvent e;e.set_kind(2);e.set_tick(50);e.set_npc(true);e.set_hit(true);
  n3e::AudioMixer events;PresentationEvents::audio(events,r,w,e,5);
  need(events.voices.size()==2&&!events.voices[0].effect&&events.voices[1].effect&&events.voices[1].positional);
  std::cout<<"PASS KO effect start test (<48 m from the eye, 20-48 option), listener frame, curves and fixed source positions\n";
}
// PQ-445 (D-226): the archer's own held shot launches its flight at its
// predicted release (the local start plus the stretched clip's blend and
// first marker; 1298's cast tick 00585830 releases at the marker and
// 00584b00 flies the arrow at once, 005855bc -> 00587ac0), pending until the
// server's release event confirms it; the event then launches no second
// flight. A pending flight that arrives holds its hit until the release
// event; a refused shot ends its flight and drops its hit; a hit or miss
// result confirms a flight whose release event was not seen. Nothing here
// changes the snapshot.
void local_release_checks(){
  n3e::Release r;r.combat_animation.emplace();auto&p=*r.combat_animation;
  p.clips.resize(2);for(auto&c:p.clips){c.duration=.9f;c.blend=.2f;c.markers={.72f,-1};c.stretch=.9f;}
  p.profiles={{0,{0}},{0,{1}}};p.profiles[1].moving=1;
  auto&ranged=p.profiles[1].ranged;ranged.cast_ms=900;ranged.flight="arrow";ranged.flight_speed=10;ranged.hit="blow";ranged.release="pull";
  r.effects.emplace();n3e::EffectBatch tri{0,0,5,6,199,{0,0,-1,0,0,1,1,1,1, .1f,0,0,0,0,1,1,1,1, 0,.1f,0,0,0,1,1,1,1}};
  r.effects->clips.emplace("arrow",n3e::EffectClip{false,10,std::vector<std::vector<n3e::EffectBatch>>(100,{tri})});
  r.effects->clips.emplace("blow",n3e::EffectClip{false,10,std::vector<std::vector<n3e::EffectBatch>>(5,{tri})});
  r.audio.emplace();r.audio->clips.push_back({16,std::vector<float>(4800,.5f)});r.audio->bindings["pull"]=0;r.audio->bindings["effect:arrow"]=0;
  need(LocalRelease::flight(r,1)==nullptr&&LocalRelease::flight(r,2)==&ranged&&LocalRelease::flight(r,3)==nullptr);
  need(std::abs(LocalRelease::at(r,2,10)-10.92)<1e-6);
  n3e::WorldState w;w.connected=true;w.world.set_session(1);w.world.set_self(7);w.world.set_tick(100);
  auto*actor=w.world.add_entities();actor->set_id(7);actor->set_health(100);actor->set_combat_style(2);
  const auto before=w.world.SerializeAsString();
  std::map<uint64_t,n3e::V> positions{{7,{0,0,0}},{8,{0,0,-10}}};std::map<std::pair<uint64_t,int>,n3e::V> joints;std::map<uint64_t,float> headings;
  // A box in pick_attack.h's corner order (tests/effects.cpp).
  auto corners=[](n3e::V lo,n3e::V hi){return std::array<n3e::V,8>{{{lo[0],hi[1],lo[2]},{hi[0],hi[1],lo[2]},{hi[0],lo[1],lo[2]},{lo[0],lo[1],lo[2]},
                                                                  {hi[0],hi[1],hi[2]},{lo[0],hi[1],hi[2]},{lo[0],lo[1],hi[2]},{hi[0],lo[1],hi[2]}}};};
  PresentationEvents::Boxes boxes;boxes[8]=corners({-.5f,0,-10.5f},{.5f,2,-9.5f});
  n3e::AudioMixer mixer;MeleePresentation shots;shots.context(7,1,true,false,10,mixer);
  n3e::EffectPlayer fx;LocalRelease local;
  // The archer's cast effect, drawn since the shot's start.
  r.effects->clips.emplace("cast",n3e::EffectClip{false,10,std::vector<std::vector<n3e::EffectBatch>>(30,{tri})});
  need(fx.start(*r.effects,"cast",7,{0,0,0},{},1,10));fx.active.back().tag="ranged:100";
  shots.begin(41,8,2,false,10);
  // Before the marker: nothing; at it: one pending flight from the marker's time.
  need(local.launch(shots,fx,mixer,r,10.9,positions,joints,headings,boxes).empty());
  auto l=local.launch(shots,fx,mixer,r,10.93,positions,joints,headings,boxes);
  need(l.size()==1&&l[0].request==41&&std::abs(l[0].start-10.93)<1e-6&&std::abs(l[0].due-10.92)<1e-6&&std::abs(l[0].predicted-.92)<1e-6); // at the frame that sees it
  need(fx.active.size()==2&&fx.active.back().flight&&fx.active.back().flight->pending&&fx.active.back().flight->request==41);
  need(std::abs(fx.active.back().flight->dir[1]-1/std::sqrt(101.f))<1e-5f&&std::abs(fx.active.back().flight->launch-std::sqrt(101.f))<1e-4f); // toward the box centre (0, 1, -10)
  // The cast effect ends at the release (00584b00 stops the self FX).
  need(l[0].casts.size()==1&&std::abs(fx.active[0].stop-.93f)<1e-5f);
  // The flight and release sounds at the archer, under the launch's own request.
  need(mixer.voices.size()==2&&std::all_of(mixer.voices.begin(),mixer.voices.end(),[](const auto&v){return v.request==LocalRelease::voice(41)&&std::abs(v.start-10.93)<1e-6;}));
  need(local.launch(shots,fx,mixer,r,11,positions,joints,headings,boxes).empty()); // once
  // The release event confirms it: no second flight, its tick on the tag.
  auto c=local.confirm(41,119,fx,r,11.,positions,joints);
  need(c.found&&c.hits.empty()&&std::abs(c.lead-.07)<1e-6&&!fx.active.back().flight->pending&&fx.active.back().tag=="flight:119");
  {auto again=local.confirm(41,119,fx,r,11.,positions,joints);need(again.found&&again.hits.empty());} // a repeat still launches nothing
  // A confirmed flight's hit starts at its arrival (the box's face 9.5 m ahead).
  auto arrived=PresentationEvents::flights(fx,r,11.9,positions,joints,boxes);
  need(arrived.size()==1&&!arrived[0].pending&&fx.active.back().tag=="hit:119");
  // A second shot arrives before its release event: the hit waits for it.
  shots.begin(42,8,2,false,12);positions[8]={0,0,-1.5f};boxes[8]=corners({-.5f,0,-2},{.5f,2,-1});
  need(local.launch(shots,fx,mixer,r,12.93,positions,joints,headings,boxes).size()==1);
  arrived=PresentationEvents::flights(fx,r,13.1,positions,joints,boxes);
  need(arrived.size()==1&&arrived[0].pending&&arrived[0].request==42);
  auto hits=std::count_if(fx.active.begin(),fx.active.end(),[](const auto&i){return i.tag.starts_with("hit:");});
  local.hold(arrived[0]);need(local.held.size()==1);
  need(local.reconcile(shots,fx,mixer,r,13.15,positions,joints).empty()); // still awaited
  c=local.confirm(42,140,fx,r,13.2,positions,joints);
  need(c.found&&c.hits.size()==1&&c.held.size()==1&&std::abs(c.held[0]-(13.2-arrived[0].at))<1e-6&&local.held.empty());
  need(std::count_if(fx.active.begin(),fx.active.end(),[](const auto&i){return i.tag=="hit:140";})==1&&std::abs(fx.active.back().start-13.2)<1e-9);
  need(std::count_if(fx.active.begin(),fx.active.end(),[](const auto&i){return i.tag.starts_with("hit:");})==hits+1);
  // A third shot is refused (no_ammo at its release): its flight ends where
  // it is, its sounds stop, and a late release event finds none to confirm.
  positions[8]={0,0,-10};boxes.erase(8);
  shots.begin(43,8,2,false,14);need(local.launch(shots,fx,mixer,r,14.93,positions,joints,headings,boxes).size()==1);
  auto*third=&fx.active.back();need(third->flight->request==43);
  shots.result(43,"no_ammo",mixer);
  auto x=local.reconcile(shots,fx,mixer,r,15.02,positions,joints);
  need(x.size()==1&&x[0].request==43&&!x[0].held&&std::abs(x[0].age-.09)<1e-6);
  need(!third->flight->pending&&third->flight->hit.empty()&&std::abs(third->stop-.09f)<1e-5f&&std::abs(third->flight->reach-.9f)<1e-4f);
  need(std::none_of(mixer.voices.begin(),mixer.voices.end(),[](const auto&v){return v.request==LocalRelease::voice(43);}));
  need(PresentationEvents::flights(fx,r,20,positions,joints,boxes).empty());   // it never arrives
  need(!local.confirm(43,160,fx,r,15.1,positions,joints).found);
  // A fourth arrives, then is cancelled (the walk, death, a refusal): its held hit is dropped.
  positions[8]={0,0,-1.5f};
  shots.begin(44,8,2,false,16);need(local.launch(shots,fx,mixer,r,16.93,positions,joints,headings,boxes).size()==1);
  arrived=PresentationEvents::flights(fx,r,17.2,positions,joints,boxes);
  need(arrived.size()==1&&arrived[0].pending);local.hold(arrived[0]);
  shots.find(44)->cancelled=true;
  x=local.reconcile(shots,fx,mixer,r,17.3,positions,joints);
  need(x.size()==1&&x[0].request==44&&x[0].held&&local.held.empty());
  // A fifth's release event is never seen, but its result (a hit) is: it flew.
  shots.begin(45,8,2,false,18);need(local.launch(shots,fx,mixer,r,18.93,positions,joints,headings,boxes).size()==1);
  arrived=PresentationEvents::flights(fx,r,19.2,positions,joints,boxes);local.hold(arrived[0]);
  shots.result(45,"hit",mixer);
  hits=std::count_if(fx.active.begin(),fx.active.end(),[](const auto&i){return i.tag.starts_with("hit:");});
  need(local.reconcile(shots,fx,mixer,r,19.3,positions,joints).empty()&&local.held.empty());
  need(std::count_if(fx.active.begin(),fx.active.end(),[](const auto&i){return i.tag.starts_with("hit:");})==hits+1);
  // Its hit result and its release event in one frame: the result confirms
  // it, and the event then finds it confirmed and launches nothing.
  need(local.confirm(45,170,fx,r,19.3,positions,joints).found);
  // So too for a shot still in the air: one flight, one pair of launch sounds.
  positions[8]={0,0,-10};shots.begin(49,8,2,false,19.5);need(local.launch(shots,fx,mixer,r,20.43,positions,joints,headings,boxes).size()==1);
  shots.result(49,"hit",mixer);need(local.reconcile(shots,fx,mixer,r,20.45,positions,joints).empty());
  need(local.confirm(49,180,fx,r,20.45,positions,joints).found);
  need(std::count_if(fx.active.begin(),fx.active.end(),[](const auto&i){return i.flight&&i.flight->request==49;})==1);
  need(std::count_if(mixer.voices.begin(),mixer.voices.end(),[](const auto&v){return v.request==LocalRelease::voice(49);})==2);
  local.reset();need(!local.confirm(49,180,fx,r,20.5,positions,joints).found&&local.held.empty());
  // An undrawn target leaves the shot to its release event; a session change forgets every shot.
  positions.erase(8);shots.begin(46,8,2,false,20.5);
  need(local.launch(shots,fx,mixer,r,21.43,positions,joints,headings,boxes).empty()&&shots.find(46)->released>=0);
  positions[8]={0,0,-10};shots.begin(47,8,2,false,21);need(local.launch(shots,fx,mixer,r,21.93,positions,joints,headings,boxes).size()==1);
  shots.context(7,2,true,false,22,mixer);
  x=local.reconcile(shots,fx,mixer,r,22,positions,joints);need(x.size()==1&&x[0].request==47);
  // A melee profile predicts nothing.
  shots.begin(48,8,1,false,23);need(local.launch(shots,fx,mixer,r,30,positions,joints,headings,boxes).empty());
  need(w.world.SerializeAsString()==before);
  std::cout<<"PASS PQ-445 local release: the archer's own shot flies at its predicted release (start + blend + marker) with its "
             "sounds, ending its cast effect there; the release event confirms it without a second flight; an early arrival "
             "holds its hit until then; a refused, cancelled or forgotten shot ends its flight and drops its hit; a hit result "
             "confirms an unseen release, after which its release event launches nothing; an undrawn target or a melee profile predicts nothing\n";
}
int main(int argc,char**argv){try{
  if(argc==2){auto a=n3e::load_audio(argv[1]);const auto&s=a.spatial;
    std::cout<<"PASS audio clips="<<a.clips.size()<<" bindings="<<a.bindings.size()<<" listener="<<s.listener<<" effect="<<s.effect_distance
             <<" option="<<s.effect_distance_min<<'-'<<s.effect_distance_max<<" cutoff="<<s.cutoff<<" reference="<<s.reference<<'\n';return 0;}
  {
    n3e::Release r;r.combat_animation.emplace();auto&p=*r.combat_animation;
    p.profiles={{0,{1,2}}};p.profiles[0].moving=3;p.upper_nodes={1};p.clips.resize(4);
    for(auto&clip:p.clips){clip.duration=.8;clip.blend=.1;clip.markers={.3,-1};}
    r.audio.emplace();auto&data=*r.audio;data.clips.push_back({16,std::vector<float>(4800,.5f)});
    for(auto key:{"swing:player","blow","struck:npc"})data.bindings[key]=0;
    data.timings[{1,1}]={.15};data.timings[{1,2}]={.15};data.timings[{1,3}]={.15};
    n3e::WorldState w;w.connected=true;w.world.set_session(1);w.world.set_self(7);w.world.set_tick(100);
    auto*actor=w.world.add_entities();actor->set_id(7);actor->set_health(100);actor->set_combat_style(1);
    auto*target=w.world.add_entities();target->set_id(8);target->set_health(100);target->set_npc(true);
    n3e::AudioMixer audio;MeleePresentation local;local.context(7,1,true,false,10,audio);
    const auto before=w.world.SerializeAsString();local.begin(129,8,1,false,10);
    PlayerPose pose;auto update=[&](double now){auto*a=local.current(*actor);auto view=a?a->view():StrikePresentation{};pose.update({},*actor,now,.9,w.world.tick(),nullptr,0,true,true,0,0,a?&view:nullptr);};
    update(10);need(pose.state==2&&pose.since==10&&pose.attack_key==129);
    n3e::PresentationEvent event;event.set_sequence(1);event.set_tick(100);event.set_actor(7);event.set_target(8);event.set_kind(2);event.set_style(1);event.set_request_sequence(129);
    PresentationEvents::audio(audio,r,w,event,10,10,false,129);need(audio.started==1&&std::abs(audio.voices[0].start-10.15)<.00001);
    r.effects.emplace();r.effects->clips.emplace("impact",n3e::EffectClip{false,30,{{},{}}});
    r.effects->bindings.push_back({2,"*",0,0,{"impact"}});n3e::EffectPlayer fx;
    PresentationEvents::effects(fx,r,w,event,10,{}, {},10);need(fx.active.empty());
    need(w.world.SerializeAsString()==before); // no predicted health, result, tick, or rewards
    // Reliable result before snapshot must retain the original start/variant.
    local.result(129,"hit",audio);update(10.1);need(pose.state==2&&pose.since==10);
    actor->set_strike_tick(102);actor->set_strike_sequence(129);actor->set_strike_style(1);w.world.set_tick(102);
    local.reconcile(*actor);update(10.2);need(pose.since==10&&pose.attack_key==129);
    CombatPose remote;remote.update(p,*actor);need(remote.attack==local.clip(p,*local.find(129)));
    event.set_tick(102);event.set_hit(true);
    PresentationEvents::effects(fx,r,w,event,10.2,{}, {},10);need(fx.active.size()==1&&std::abs(fx.active.back().start-10.4)<.0001);
    PresentationEvents::effects(fx,r,w,event,11.5,{}, {},10);need(fx.active.size()==2&&fx.active.back().start==11.5);
    PresentationEvents::audio(audio,r,w,event,10.2,10,true);need(audio.started==3); // impact+struck, no second swing
    need(std::abs(audio.voices.back().start-10.4)<.0001);
    // Late confirmation is visible on receipt, without replaying the swing.
    audio.voices.clear();PresentationEvents::audio(audio,r,w,event,11.5,10,true);need(audio.started==5&&audio.voices.back().start==11.5);
    update(11.5);need(pose.state!=2);
    // New moving request, rejected result, and stale acknowledgement isolation.
    local.begin(130,8,1,true,12);update(12);need(pose.since==12);
    need(local.clip(p,*local.find(130))==13);
    event.set_hit(false);event.set_request_sequence(130);event.set_moving(true);
    PresentationEvents::audio(audio,r,w,event,12,12,false,130);
    local.result(129,"hit",audio);need(!local.find(130)->confirmed);
    local.result(130,"out_of_range",audio);update(12.1);need(pose.state!=2);
    need(std::none_of(audio.voices.begin(),audio.voices.end(),[](const auto&v){return v.request==130;}));
    local.begin(131,8,1,false,13);local.context(7,1,true,false,15.1,audio);need(local.find(131)->cancelled);
    local.begin(132,8,1,false,16);local.context(7,1,true,true,16.1,audio);need(local.find(132)->cancelled);
    local.begin(133,8,1,false,17);local.context(7,1,false,false,17.1,audio);need(local.find(133)->cancelled);
    local.context(9,2,true,false,18,audio);need(local.attempts.empty());
    for(unsigned seq=1;seq<=40;++seq)local.begin(seq,8,1,false,19);need(local.attempts.size()==16);
    local.context(0,2,false,false,20,audio);need(local.attempts.empty());
    actor->set_strike_tick(0);actor->set_strike_sequence(0);actor->set_id(7);pose={};
    local.context(7,3,true,false,21,audio);local.begin(1,8,1,false,21);update(21);need(pose.state==2);
    local.result(1,"cooldown",audio);update(21.1);need(pose.state!=2);
    // Snapshot before ActionResult and duplicate snapshots preserve the start.
    local.begin(2,8,1,false,22);update(22);
    actor->set_strike_tick(120);actor->set_strike_sequence(2);local.reconcile(*actor);update(22.15);need(pose.since==22);
    local.result(2,"miss",audio);update(22.2);need(pose.since==22);
    local.context(0,3,false,false,22.25,audio);update(22.25);need(pose.state!=2);
    audio.voices.clear();event.set_hit(false);event.set_request_sequence(2);
    auto count=audio.started;PresentationEvents::audio(audio,r,w,event,22.2,22,true);need(audio.started==count);
    std::cout<<"PASS predicted swing, immutable authority, accepted identity/variant, no restart/duplicate audio, late impact, rejection/timeout/cast/death/reconnect and bounded history\n";
  }
  n3e::Audio a;a.clips.push_back({2,std::vector<float>(4800,.5f)});a.bindings["tone"]=0;
  n3e::AudioMixer m;need(m.play(a,"tone",1,{3,0,0},true));need(!m.play(a,"absent",1));
  auto before=m.mix(.98,480,{{},{},{1,0,0}});need(std::all_of(before.begin(),before.end(),[](float x){return x==0;}));
  auto right=m.mix(1,100,{{},{},{1,0,0}});need(right[0]==0&&right[1]>0);
  auto left=m.mix(1,100,{{},{},{-1,0,0}});need(left[0]>0&&left[1]==0);
  auto far=m.mix(1,100,{{40,0,0},{40,0,0},{1,0,0}});need(far[0]==0&&far[1]==0);
  need(m.play(a,"tone",1));need(!m.play(a,"tone",1));m.retire(1.2);need(m.voices.empty());
  spatial_checks();
  music_checks();
  scene_music_checks();
  local_release_checks();
  n3e::WorldState w;w.connected=true;w.world.set_self(7);w.world.set_session(1);w.world.set_tick(100);w.world.set_event_cursor(10);
  auto*e=w.world.add_events();e->set_sequence(10);e->set_tick(100);
  PresentationEvents events;need(events.poll(w).empty()); // reconnect baseline
  e->set_sequence(11);w.world.set_event_cursor(11);need(events.poll(w).size()==1);need(events.poll(w).empty());
  e->set_sequence(12);e->set_tick(1);w.world.set_event_cursor(12);need(events.poll(w).empty());
  w.world.set_session(2);e->set_sequence(13);e->set_tick(100);w.world.set_event_cursor(13);need(events.poll(w).empty());
  w.connected=false;events.poll(w);need(events.cursor==0);
  std::cout<<"PASS audio timing, panning, attenuation, retirement/voice bounds and presentation reconnect/dedup\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
