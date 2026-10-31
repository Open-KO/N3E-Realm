#include "render/player_pose.h"
#include "render/combat_pose.h"
#include "render/progress.h"
#include "render/motion.h"
#include "render/remote_motion.h"
#include "render/navigation.h"
#include <source_location>
#include <stdexcept>
void check(bool value,
           std::source_location where = std::source_location::current()) {
  if (!value)
    throw std::runtime_error("player playback assertion at line " +
                             std::to_string(where.line()));
}
#include <iostream>
int main() {
  {
    // PQ-400: two clients that first see the same idle actor at different host
    // clock values play its base (layered) clip from that first sight, so after
    // the same time on screen both are at the same phase; the base clock used to
    // stay 0, the steady clock's epoch, so the phase was the host's uptime.
    n3e::Entity e;e.set_id(21);e.set_health(10);
    PlayerPose one,two;
    for(double at:{0.,.5,10.75}){one.update({1,0,1},e,508794.25+at,1,1);two.update({1,0,1},e,7.5+at,1,1);}
    check(one.state==0&&one.base_state==0&&one.since==508794.25&&one.base_since==508794.25);
    check(two.base_since==7.5&&(508794.25+10.75)-one.base_since==(7.5+10.75)-two.base_since);
    e.set_id(22);one.update({1,0,1},e,508900.,1,1);
    check(one.base_since==508900.&&one.since==508900.);  // a new identity is a new first sight
    std::cout<<"PASS an actor's base clip clock starts when it is first seen (not at the host clock's epoch)\n";
  }
  {
    n3e::CombatAnimation policy;policy.profiles={{0,{1,2}},{3,{4,5}}};
    n3e::Entity e;e.set_id(10);e.set_health(10);e.set_combat_style(2);e.set_strike_style(2);e.set_strike_tick(100);
    CombatPose local,remote;local.update(policy,e);remote.update(policy,e);
    check(local.attack==remote.attack&&(local.attack==14||local.attack==15));
    auto frozen=local.attack;e.set_combat_style(1);local.update(policy,e);
    check(local.attack==frozen&&local.clip(policy,e,6)==10);
    e.set_strike_style(1);e.set_strike_tick(120);local.update(policy,e);
    check(local.attack==11||local.attack==12);
    unsigned seen=0;for(unsigned tick=1;tick<=200;++tick)seen|=1u<<(CombatPose::sample(10,tick)%2);
    check(seen==3);e.set_id(11);e.set_strike_tick(0);local.update(policy,e);check(local.attack==2);
    policy.upper_nodes={1};policy.profiles[0].moving=6;e.set_id(10);e.set_strike_tick(201);e.set_strike_style(1);e.set_strike_moving(true);local.update(policy,e);remote.update(policy,e);
    check(local.layered&&local.attack==16&&remote.attack==16);e.set_strike_moving(false);local.update(policy,e);check(local.layered);
    std::cout<<"PASS weapon style, stable per-strike variants, remote agreement, gear-change freeze and entity reset\n";
  }

  {
    n3e::World before, current;
    before.set_session(1); before.set_tick(10);
    current.set_session(1); current.set_tick(12);
    auto *old = before.add_entities();
    old->set_id(7); old->set_health(100); old->set_life_state(n3e::ALIVE);
    auto *actor = current.add_entities(); *actor = *old; actor->set_x(1);
    check(remote_position(before, current, *actor, .05)[0] == .5f);
    check(remote_position(before, current, *actor, 2)[0] == 1);
    // Stop and restart remain continuous; never extrapolate past the baseline.
    old->set_x(1);
    check(remote_position(before, current, *actor, .05)[0] == 1);
    actor->set_x(2);
    check(remote_position(before, current, *actor, .05)[0] == 1.5f);
    actor->set_health(0); actor->set_life_state(n3e::DEAD_WAITING);
    check(remote_position(before, current, *actor, 0)[0] == 2);
    actor->set_health(100); actor->set_life_state(n3e::ALIVE);
    actor->set_id(8); // respawn uses a fresh runtime identity
    check(remote_position(before, current, *actor, 0)[0] == 2);
    actor->set_id(7); current.set_session(2);
    check(remote_position(before, current, *actor, 0)[0] == 2);
    current.set_session(1); current.set_tick(20);
    check(remote_position(before, current, *actor, 0)[0] == 2);
    current.set_tick(12); before.clear_entities(); // visibility reentry
    check(remote_position(before, current, *actor, 0)[0] == 2);
    std::cout << "PASS remote start/stop, death, respawn, reconnect, stream gap and visibility resets\n";
  }

  {
    PlayerPose p;n3e::Entity e;e.set_id(1);e.set_health(10);
    auto update=[&](double now){p.update({},e,now,.8,200,nullptr,0,true,false,1.,.5);};
    update(1);e.set_sitting(true);update(2);check(p.state==7);
    update(2.9);check(p.state==7&&p.since==2);update(3.01);check(p.state==8);
    update(9);check(p.state==8);e.set_sitting(false);update(10);check(p.state==9);
    update(10.4);check(p.state==9);update(10.6);check(p.state==0);
    e.set_sitting(true);update(11);e.set_health(0);update(11.1);check(p.state==3);
    std::cout<<"PASS sit-down, seated loop, stand-up, interruption and death playback\n";
  }
  {
    // PQ-420 (D-217): an observer starts a held shot's clip at its cast start
    // and stops it when the server clears the cancelled cast (strike_tick 0).
    PlayerPose p;n3e::Entity e;e.set_id(3);e.set_health(10);
    auto update=[&](double now,uint64_t tick){p.update({},e,now,1.1,tick,nullptr,0,true,false);};
    update(1,100);check(p.state==0);
    e.set_strike_tick(100);e.set_strike_sequence(9);update(1.05,101);check(p.state==2);
    update(1.5,110);check(p.state==2);
    e.set_strike_tick(0);e.set_strike_sequence(0);update(1.55,111);check(p.state==0);
    e.set_strike_tick(140);update(3,141);check(p.state==2);update(4.2,165);check(p.state==0);  // a landed one plays out
    std::cout<<"PASS a held shot's clip plays from its cast start and stops when the server clears it\n";
  }
  const std::array<uint64_t, 10> curve{0,20,50,90,140,200,270,350,440,540};
  check(progress_view(curve, 1, 19).text() == "19/20");
  check(progress_view(curve, 2, 20).fraction() == 0);
  check(progress_view(curve, 2, 35).fraction() == .5f);
  check(progress_view(curve, 3, 60).text() == "10/40");
  check(progress_view(curve, 10, 550).text() == "MAX");
  check(progress_view(curve, 10, 550).fraction() == 1);
  check(progress_view(curve, 2, 0).earned == 0);

  for (int fps : {30, 60, 144}) {
    float heading = 0;
    for (int frame = 0; frame < fps * 3 / 2; ++frame) {
      auto input = facing_input(heading, -1, 0, 1.0 / fps);
      check(input == n3e::V{});
    }
    check(std::abs(heading - 1.5707963f) < .00001f);
    auto forward = facing_input(heading, 0, 1, 1.0 / fps);
    auto backward = facing_input(heading, 0, -1, 1.0 / fps);
    check(forward[0] < -.9999 && std::abs(forward[2]) < .00001);
    check(backward[0] > .9999 && std::abs(backward[2]) < .00001);
    auto before = heading;
    facing_input(heading, 1, 0, 1);
    check(before == heading);
  }
  HeldGround held;
  held.begin(false, 0);
  check(!held.refresh(1, true));
  held.begin(true, 0);
  check(!held.refresh(.05, true) && held.refresh(.11, true));
  check(held.refresh(.3, true));
  check(!held.refresh(.4, false) && !held.refresh(.5, true));
  held.begin(true, 1);
  held.cancel();
  check(!held.refresh(2, true));
  PlayerPose p;
  n3e::Entity e;
  e.set_health(100);
  p.update({0, 0, 0}, e, 10, .8, 200);
  check(p.state == 0 && p.since == 10);
  p.update({1, 0, 0}, e, 10.1, .8, 202);
  check(p.state == 1);
  check(std::abs(p.heading + 1.5707963f) < .001);
  p.update({1, 0, 0}, e, 10.3, .8, 206);
  check(p.state == 0);
  e.set_strike_tick(207);
  p.update({1, 0, 0}, e, 10.35, .8, 207);
  check(p.state == 2);
  e.set_strike_tick(217);
  p.update({1, 0, 0}, e, 10.85, .8, 217);
  check(p.state == 2 && p.since == 10.85);
  p.update({1, 0, 0}, e, 11.7, .8, 234);
  check(p.state == 0);
  e.set_health(0);
  p.update({1, 0, 0}, e, 11.8, .8, 236);
  check(p.state == 3);
  p.update({1, 0, 0}, e, 12, .8, 240);
  check(p.state == 3 && p.since == 11.8);
  PlayerPose late;
  e.set_health(100);
  late.update({0, 0, 0}, e, 30, .8, 600);
  check(late.state == 0);
  n3e::V forward{1, 0, 0}, stopped{};
  PlayerPose local;
  local.update({0, 0, 0}, e, 40, .8, 800, &forward);
  local.update({-.05f, 0, 0}, e, 40.05, .8, 801, &forward);
  check(local.state == 1 && std::abs(local.heading + 1.5707963f) < .001);
  local.update({.05f, 0, 0}, e, 40.1, .8, 802, &stopped);
  check(local.state == 0 && std::abs(local.heading + 1.5707963f) < .001);
  // Backpedal reverses travel without turning the body. Walk/run/backward use
  // distinct looping clips, locally and from server mode plus remote motion.
  n3e::V front{0, 0, -1}, back{0, 0, 1};
  local.update({}, e, 41, .8, 820, &front, 0, true);
  check(local.state == 1 && std::abs(local.heading) < .001);
  local.update({}, e, 41.1, .8, 822, &front, 1, true);
  check(local.state == 4 && local.since == 41.1);
  local.update({}, e, 41.2, .8, 824, &back, 2, true);
  check(local.state == 5 && std::abs(local.heading) < .001);
  local.update({}, e, 41.3, .8, 826, &stopped, 2, true);
  check(local.state == 0 && std::abs(local.heading) < .001);
  e.set_movement_mode(2);
  PlayerPose remote;
  remote.update({}, e, 42, .8, 840, nullptr, 0, true);
  remote.update({0, 0, .1f}, e, 42.1, .8, 842, nullptr, 0, true);
  check(remote.state == 5 && std::abs(remote.heading) < .001);

  // Target ready is cosmetic, lower priority than movement/strike/death.
  PlayerPose ready;
  e.set_strike_tick(0);
  ready.update({}, e, 50, .8, 1000, &stopped, 0, true, true);
  check(ready.state == 6 && ready.attack_until == 0 && ready.strike == 0);
  ready.update({}, e, 50.2, .8, 1004, &front, 1, true, true);
  check(ready.state == 4);
  ready.update({}, e, 50.4, .8, 1008, &stopped, 0, true, true);
  check(ready.state == 6);
  e.set_strike_tick(1009);
  ready.update({}, e, 50.45, .8, 1009, &stopped, 0, true, true);
  check(ready.state == 2);
  ready.update({}, e, 51.4, .8, 1028, &stopped, 0, true, true);
  check(ready.state == 6);
  ready.update({}, e, 51.5, .8, 1030, &stopped, 0, true, false);
  check(ready.state == 0);
  e.set_health(0);
  ready.update({}, e, 51.6, .8, 1032, &stopped, 0, true, true);
  check(ready.state == 3);

  // Replay 3 m/s prediction at 20 Hz, sampled at several render rates. The old
  // renderer alternated zero displacement with full 15 cm jumps.
  for (float speed : {1.5f, 3.f, 4.5f, 6.f})
    for (int fps : {30, 60, 144}) {
      PlayerMotion motion;
      float previous = 0, max_step = 0, raw_previous = 0, raw_max = 0;
      for (int frame = 0; frame <= fps * 2; ++frame) {
        double now = double(frame) / fps;
        float target = std::floor((now + 1e-8) * 20) * (speed * .05f);
        auto position = motion.update({target, 0, 0}, now, 1, 1, true);
        check(position[0] >= previous - 1e-5 && position[0] <= target + 1e-5);
        max_step = std::max(max_step, position[0] - previous);
        raw_max = std::max(raw_max, target - raw_previous);
        previous = position[0];
        raw_previous = target;
        if (now > .5)
          check(target - position[0] < speed * .1f);
      }
      check(max_step < raw_max * .8f);
      // Releasing input settles in one frame, without an idle glide. A final
      // acknowledgement/correction at rest must also leave no velocity tail.
      auto stopped_motion = motion;
      check(stopped_motion.update({speed * 2, 0, 0}, 2.01, 1, 1, true,
                                  false)[0] == speed * 2);
      check(stopped_motion.velocity == n3e::V{});
      // The camera retains its own continuous trajectory when the actor
      // settles.
      auto camera = motion;
      auto camera_before = camera.position;
      auto camera_after = camera.update({speed * 2, 0, 0}, 2.001, 1, 1, true);
      check(camera_after[0] - camera_before[0] < speed * .003f);
      check(camera_after[0] < stopped_motion.position[0]);
      check(stopped_motion.update({speed * 2 + .01f, 0, 0}, 2.02, 1, 1, true,
                                  false)[0] == speed * 2 + .01f);
      check(stopped_motion.velocity == n3e::V{});
      for (int frame = 1; frame <= fps; ++frame)
        motion.update({speed * 2, 0, 0}, 2.0 + double(frame) / fps, 1, 1, true);
      check(std::abs(motion.position[0] - speed * 2) < .00001);
      // Small reconciliation is smoothed, while discontinuities snap.
      check(motion.update({speed * 2 - .1f, 0, 0}, 3.01, 1, 1, true)[0] >
            speed * 2 - .01f);
      check(motion.update({20, 0, 0}, 3.02, 1, 1, true)[0] == 20);
      check(motion.update({20.1f, 0, 0}, 3.03, 1, 1, false)[0] == 20.1f);
      check(motion.update({20.2f, 0, 0}, 3.04, 1, 2, true)[0] == 20.2f);
      check(motion.update({20.3f, 0, 0}, 3.05, 2, 2, true)[0] == 20.3f);
      check(motion.update({20.4f, 0, 0}, 4, 2, 2, true)[0] == 20.4f);
      std::cout << "PASS movement " << speed << " m/s " << fps
                << " fps: largest step " << max_step << " m (raw " << raw_max
                << " m), bounded lag and stop; "
                   "correction/death/respawn/session/stall resets\n";
    }
  // Blended locomotion stops must not consume the full tracking lag in one
  // frame or separate the actor from its continuously smoothed camera.
  for (float speed : {1.5f, 4.5f, -1.5f})
    for (int fps : {30, 60, 144}) {
      float worst_old = 0, worst_new = 0;
      for (double phase : {0., .01, .025, .04}) {
        PlayerMotion actor, camera;
        int stop_frame = fps * 2;
        float target = 0;
        for (int frame = 0; frame <= stop_frame; ++frame) {
          double now = double(frame) / fps;
          target = std::floor((now + phase + 1e-8) * 20) * speed * .05f;
          actor.update({target, 0, 0}, now, 1, 1, true, true, true);
          camera.update({target, 0, 0}, now, 1, 1, true);
        }
        auto before = actor.position;
        auto legacy = actor;
        double step = 1. / fps;
        auto snapped =
            legacy.update({target, 0, 0}, 2 + step, 1, 1, true, false);
        auto settled =
            actor.update({target, 0, 0}, 2 + step, 1, 1, true, false, true);
        auto focus = camera.update({target, 0, 0}, 2 + step, 1, 1, true);
        float old_jump = std::abs(snapped[0] - before[0]);
        float new_step = std::abs(settled[0] - before[0]);
        worst_old = std::max(worst_old, old_jump);
        worst_new = std::max(worst_new, new_step);
        check(new_step < old_jump * .65f);
        check(std::abs(settled[0] - focus[0]) < 1e-6);
        for (int frame = 2; frame <= fps; ++frame) {
          auto previous = actor.position;
          auto position = actor.update({target, 0, 0}, 2 + frame * step, 1, 1,
                                       true, false, true);
          check(std::abs(position[0] - target) <=
                std::abs(previous[0] - target) + 1e-6);
          check(std::abs(position[0] - previous[0]) <=
                std::abs(speed) * step * 1.25);
          if (frame * step >= .3)
            check(std::abs(position[0] - target) < .001f);
        }
        // The stop blend cannot suppress the existing life/identity/stall
        // snaps.
        check(actor.update({target + .1f, 0, 0}, 3.01, 1, 1, false, false,
                           true)[0] == target + .1f);
        check(actor.update({target + .2f, 0, 0}, 3.02, 1, 2, true, false,
                           true)[0] == target + .2f);
        check(actor.update({target + .3f, 0, 0}, 3.03, 2, 2, true, false,
                           true)[0] == target + .3f);
        check(actor.update({target + .4f, 0, 0}, 4, 2, 2, true, false,
                           true)[0] == target + .4f);
      }
      std::cout << "PASS blended stop " << speed << " m/s " << fps
                << " fps: old jump=" << worst_old << " new step=" << worst_new
                << " m\n";
    }
  // Exact spring integration is independent of subdivisions for a fixed target.
  PlayerMotion coarse, fine;
  coarse.update({}, 0, 1, 1, true);
  fine.update({}, 0, 1, 1, true);
  coarse.update({1, 0, 0}, .2, 1, 1, true);
  for (int i = 1; i <= 20; ++i)
    fine.update({1, 0, 0}, i * .01, 1, 1, true);
  check(std::abs(coarse.position[0] - fine.position[0]) < 1e-6);
  std::cout << "PASS idle/run/attack/death playback, facing, repeat strike "
               "restart and stale strike suppression\n";
}
