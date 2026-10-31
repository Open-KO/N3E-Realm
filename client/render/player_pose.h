#pragma once
#include "assets/assets.h"
#include "wire.pb.h"
#include <cmath>
struct StrikePresentation { uint64_t key; double start; bool cancelled; };
struct PlayerPose {
  n3e::V previous{};
  float heading = 0;
  int state = 0, base_state = 0;
  double base_since = 0;
  double since = 0, moving_until = 0, attack_until = 0;
  uint64_t strike = 0, identity = 0, attack_key = 0;
  bool initialized = false, predicted = false;
  void update(n3e::V position, const n3e::Entity &e, double now,
              float attack_duration, uint64_t tick,
              const n3e::V *intent = nullptr, uint32_t mode = 0,
              bool locomotion_clips = false, bool ready = false,
              float sit_duration=0,float stand_duration=0,
              const StrikePresentation *local = nullptr) {
    if (initialized && identity != e.id())
      *this = PlayerPose{};
    identity = e.id();
    bool restart = false;
    double attack_start = now;
    if (!intent)
      mode = e.movement_mode();
    if (initialized) {
      float dx = position[0] - previous[0], dz = position[2] - previous[2];
      if (!intent && dx * dx + dz * dz > .000001f) {
        heading = mode == 2 ? std::atan2(dx, dz) : std::atan2(-dx, -dz);
        moving_until = now + .12;
      }
    } else {
      initialized = true;
      // PQ-400: the layered base clip's clock starts at first sight too; left
      // at 0 it ran from the steady clock's epoch, so an idle actor's base
      // phase was the host's uptime modulo the clip (different in every client).
      since = base_since = now;
    }
    // Local corrections must not reverse facing or restart locomotion at rest.
    if (intent) {
      bool moving =
          (*intent)[0] * (*intent)[0] + (*intent)[2] * (*intent)[2] > .000001f;
      if (moving)
        heading = mode == 2 ? std::atan2((*intent)[0], (*intent)[2])
                            : std::atan2(-(*intent)[0], -(*intent)[2]);
      moving_until = moving ? now + .12 : now;
    }
    if (!local && predicted) attack_until = 0;
    predicted = local != nullptr;
    if (local) {
      attack_start = local->start;
      restart = attack_key != local->key;
      attack_key = local->key;
      attack_until = local->cancelled ? 0 : attack_start + attack_duration;
      strike = e.strike_tick();
    } else if (e.strike_tick() != strike) {
      // PQ-420 (D-217): the server clears a held ranged shot it cancelled;
      // the cast's clip stops with it.
      if (!e.strike_tick()) attack_until = 0;
      attack_key = e.strike_sequence() ? e.strike_sequence() : e.strike_tick();
      if (e.health() && e.strike_tick() && tick >= e.strike_tick() &&
          tick - e.strike_tick() <= uint64_t(attack_duration * 20)) {
        attack_start = now - double(tick - e.strike_tick()) / 20;
        attack_until = attack_start + attack_duration;
        restart = true;
      }
      strike = e.strike_tick();
    }
    int locomotion = locomotion_clips && mode == 1   ? 4
                     : locomotion_clips && mode == 2 ? 5
                                                     : 1;
    int base = now < moving_until ? locomotion : ready ? 6 : 0;
    if(base!=base_state){base_state=base;base_since=now;}
    int desired = !e.health()          ? 3
                  : now < attack_until ? 2
                  : now < moving_until ? locomotion
                  : ready              ? 6
                                       : 0;
    if(e.health()&&sit_duration>0){
      if(e.sitting())desired=(state==8||(state==7&&now-since>=sit_duration))?8:7;
      else if((state==7||state==8)&&desired!=1&&desired!=4&&desired!=5&&desired!=2)desired=9;
      else if(state==9&&now-since<stand_duration&&(desired==0||desired==6))desired=9;
    }
    if (desired != state || (desired == 2 && restart)) {
      state = desired;
      since = desired == 2 ? attack_start : now;
    }
    if (!e.health())
      attack_until = 0;
    previous = position;
  }
};
