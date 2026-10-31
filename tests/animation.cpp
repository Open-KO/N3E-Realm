#include "render/animation.h"
#include "render/player_pose.h"
#include <iostream>
void check(bool ok) {
  if (!ok)
    throw std::runtime_error("animation boundary");
}
float error(const std::vector<n3e::Node> &a, const std::vector<n3e::Node> &b) {
  float e = 0;
  for (size_t i = 0; i < a.size(); ++i) {
    for (int k = 0; k < 3; ++k) {
      e = std::max(e, std::abs(a[i].t[k] - b[i].t[k]));
      e = std::max(e, std::abs(a[i].s[k] - b[i].s[k]));
    }
    for (int k = 0; k < 4; ++k)
      e = std::max(e, std::abs(a[i].q[k] - b[i].q[k]));
  }
  return e;
}
int main(int argc, char **argv) {
  try {
    check(argc == 2);
    auto release = n3e::load_release(argv[1]);
    check(release.animation.has_value());
    for (int role = 0; role < (release.animation->size() == 11 ? 2 : 1); ++role) {
      std::vector<n3e::Scene> scenes;
      for (const char *state : {"idle", "walk", "attack", "death"})
        scenes.push_back(n3e::load_scene(
            release, std::string(role ? "npc-" : "player-") + state + ".bin"));
      auto clips = release.animation->data() + (role ? 7 : 0);
      for (auto &s : scenes)
        check(scenes[0].compatible(s));
      for (int fps : {30, 60, 144}) {
        AnimationPlayer p;
        p.update(scenes, clips, 1, 0, 0, 0);
        auto before = p.evaluate(scenes, clips, .35);
        auto at = p.update(scenes, clips, 0, 0, .35, .35);
        if (clips[0].blend > 0) {
          check(error(before, at) < 1e-6);
          auto halfway =
              p.update(scenes, clips, 0, 0, .35, .35 + clips[0].blend / 2);
          check(error(halfway, blend_pose(before, scenes[0].sample(0), .5)) <
                1e-5);
          // Interrupt a blend from its evaluated pose, without jumping.
          double now = .35 + clips[0].blend / 2;
          check(error(halfway, p.update(scenes, clips, 2, 10, now, now)) <
                1e-6);
        }
        p = {};
        p.update(scenes, clips, 0, 0, 0, 0);
        p.update(scenes, clips, 2, 20, 1, 1);
        unsigned pulses = 0;
        for (int frame = 1;
             frame <= int((clips[2].duration + clips[2].blend + .1) * fps);
             ++frame) {
          double now = 1 + double(frame) / fps;
          p.update(scenes, clips, 2, 20, 1, now);
          pulses += bool(p.markers);
        }
        unsigned expected = 0;
        for (float m : clips[2].markers)
          expected += m >= 0;
        check(pulses == expected); // coincident two markers can share one pulse
        check(error(p.current, scenes[2].sample(clips[2].duration)) < 1e-5);
        auto prior = p.evaluate(scenes, clips, 10);
        check(error(p.update(scenes, clips, 2, 21, 10, 10),
                    clips[2].blend > 0 ? prior : scenes[2].sample(0)) < 1e-5);
        p.update(scenes, clips, 3, 21, 10.1, 10.1);
        p.update(scenes, clips, 3, 22, 10.1, 10000);
        check(error(p.current, scenes[3].sample(clips[3].duration)) < 1e-5 &&
              !p.markers);
        p.update(scenes, clips, 0, 0, 10000, 10000, true);
        check(error(p.current, scenes[0].sample(0)) < 1e-5);
        p.update(scenes, clips, 3, 0, 10001, 10001, true);
        check(error(p.current, scenes[3].sample(clips[3].duration)) < 1e-5);
      }
      // A marker at clip zero waits for entry blending; absent second marker
      // stays quiet.
      n3e::Clip zero[4];
      std::copy(clips, clips + 4, zero);
      zero[2].blend = .2f;
      zero[2].markers = {0, -1};
      AnimationPlayer marker;
      marker.update(scenes, zero, 0, 0, 0, 0);
      marker.update(scenes, zero, 2, 1, .1, .1);
      check(marker.markers == 0);
      marker.update(scenes, zero, 2, 1, .1, .2);
      check(marker.markers == 0);
      marker.update(scenes, zero, 2, 1, .1, .31);
      check(marker.markers == 1);
      marker.update(scenes, zero, 2, 1, .1, .32);
      check(marker.markers == 0);
      // Analytic loop/end boundary, including end-to-start blend flags.
      n3e::Clip local[4];
      std::copy(clips, clips + 4, local);
      local[0].loop_blend = true;
      local[0].blend = .2;
      AnimationPlayer loop;
      loop.update(scenes, local, 0, 0, 0, 0);
      check(error(loop.evaluate(scenes, local, local[0].duration + .1),
                  blend_pose(scenes[0].sample(local[0].duration),
                             scenes[0].sample(0), .5)) < 1e-5);
      check(error(loop.evaluate(scenes, local, local[0].duration + .2),
                  scenes[0].sample(0)) < 1e-5);
      for (auto &scene : scenes) {
        auto vertices = scene.skin(scene.sample(.3));
        for (float v : vertices)
          check(std::isfinite(v));
      }
    }
    // The actual seven-clip player set must preserve the outgoing pose at
    // stop, regardless of stride phase or forward/run/backward selection.
    std::vector<n3e::Scene> player;
    for (const char *name : {"idle", "walk", "attack", "death", "run", "backward", "ready"})
      player.push_back(n3e::load_scene(release, std::string("player-") + name + ".bin"));
    {
      auto source=n3e::load_scene(release,"player-attack.bin");
      std::vector<n3e::Scene> scenes(12,source);std::vector<n3e::Clip> clips(12,(*release.animation)[2]);
      AnimationPlayer p;p.update(scenes,clips.data(),10,1,0,0,false,2);
      p.update(scenes,clips.data(),10,1,0,100,false,2);
      check(error(p.current,source.sample(clips[10].duration))<1e-5);
      p.update(scenes,clips.data(),11,1,100,100,false,6);
      auto before=p.evaluate(scenes,clips.data(),100.1);
      p.update(scenes,clips.data(),10,1,0,100.1,false,6);
      check(p.start==100.1&&error(before,p.current)<1e-5);
      p.update(scenes,clips.data(),3,1,101,101,false,3);p.update(scenes,clips.data(),3,2,101,1000,false,3);
      check(!p.markers);
      std::cout<<"PASS dynamic combat clip one-shot, ready-switch blend and death interruption\n";
    }
    auto clips = release.animation->data();
    for (int moving : {1, 4, 5}) for (float phase : {.05f, .35f, .75f, .99f}) {
      AnimationPlayer p;
      double stop = clips[moving].duration * phase;
      p.update(player, clips, moving, 0, 0, 0);
      auto outgoing = p.evaluate(player, clips, stop);
      auto at = p.update(player, clips, 0, 0, stop, stop);
      if (clips[0].blend > 0) {
        check(error(outgoing, at) < 1e-6);
        auto half = p.update(player, clips, 0, 0, stop, stop + clips[0].blend / 2);
        check(error(half, blend_pose(outgoing, player[0].sample(0), .5)) < 1e-5);
      }
      auto settled = p.update(player, clips, 0, 0, stop, stop + clips[0].blend);
      check(error(settled, player[0].sample(0)) < 1e-5);
    }
    // Original three-joint fixture: root/lower travel must not inherit the
    // attack's translations, including stop, fade-out and death interruption.
    for(int fps:{30,60,144}){
      std::vector<n3e::Scene> scenes(4);
      n3e::Clip clips[4];
      for(int c=0;c<4;++c){clips[c].duration=1;clips[c].blend=.1;
        for(unsigned n=0;n<3;++n){scenes[c].nodes.push_back({n?0:-1,{0,0,0},{1,1,1},{0,0,0,1}});
          n3e::Track track;track.node=n;track.path=0;track.keys={{0,{float(c*10+n),0,0,0}},{1,{float(c*10+n+1),0,0,0}}};scenes[c].tracks.push_back(track);}}
      AnimationPlayer action;LayeredAnimation layers;
      auto update=[&](double now,bool upper,int role=2){return layers.update(action,scenes,clips,upper?2:role,upper?2:role,10,upper?.2:now,now,1,1,0,{1},upper);};
      update(0,false,1);update(.2,true);
      for(int frame=1;frame<=fps/2;++frame){double now=.2+double(frame)/fps;auto pose=update(now,true);auto base=layers.base.evaluate(scenes,clips,now);check(pose[0]==base[0]&&pose[2]==base[2]);if(now>.31)check(pose[1].t[0]>20);}
      auto before=layers.current;auto ended=update(.71,false,1);check(ended[1]==before[1]);
      auto settled=update(.9,false,1);check(error(settled,layers.base.evaluate(scenes,clips,.9))<1e-5);
      update(1.,true);auto death=update(1.05,false,3);check(!layers.was_upper&&layers.was_full);check(error(death,layers.current)<1e-6);
    }
    std::cout<<"PASS moving upper-body composition preserves root/lower phase, blends out and interrupts for death at 30/60/144 FPS\n";
    // Independent analytic TRS midpoint: 180-degree Z rotation gives 90
    // degrees, translation and nonuniform scale interpolate linearly;
    // quaternion sign flips represent the same rotation and take the shortest
    // arc.
    n3e::Node a{-1, {0, 0, 0}, {1, 1, 1}, {0, 0, 0, 1}},
        b{-1, {2, 4, 6}, {3, 5, 7}, {0, 0, 1, 0}};
    auto half = blend_pose({a}, {b}, .5)[0];
    check(half.t == n3e::V{1, 2, 3} && half.s == n3e::V{2, 3, 4});
    check(std::abs(half.q[2] - std::sqrt(.5f)) < 1e-6 &&
          std::abs(half.q[3] - std::sqrt(.5f)) < 1e-6);
    b.q = {0, 0, 0, -1};
    check(error(blend_pose({a}, {b}, .5),
                {n3e::Node{-1, {1, 2, 3}, {2, 3, 4}, {0, 0, 0, 1}}}) < 1e-6);
    // Same authoritative strike starts at the same tick age locally/remotely.
    PlayerPose local, remote;
    n3e::Entity e;
    e.set_id(10);
    e.set_health(100);
    e.set_strike_tick(100);
    n3e::V stop{};
    local.update({}, e, 10, 1, 104, &stop);
    remote.update({}, e, 10, 1, 104);
    check(local.state == 2 && remote.state == 2 &&
          local.since == remote.since && std::abs(local.since - 9.8) < 1e-6);
    e.set_health(0);
    local.update({}, e, 10.1, 1, 105);
    double death = local.since;
    e.set_strike_tick(105);
    local.update({}, e, 10.2, 1, 106);
    check(local.state == 3 && local.since == death);
    e.set_id(11);
    e.set_health(100);
    e.set_strike_tick(0);
    local.update({}, e, 11, 1, 120);
    check(local.state == 0 && local.attack_until == 0);
    std::cout << "PASS player/NPC numeric blend, interruption, loop/end, "
                 "markers, long gap, tick age, death and identity reset\n";
  } catch (const std::exception &e) {
    std::cerr << e.what() << "\n";
    return 1;
  }
}
