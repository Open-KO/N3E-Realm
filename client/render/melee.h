#pragma once
#include "assets/assets.h"
#include <algorithm>
#include <cmath>
namespace n3e {
// One client-owned intent, one outstanding request; damage is exclusively
// server-owned.
inline void face_target(V actor, V victim, float &heading) {
  float x = victim[0] - actor[0], z = victim[2] - actor[2];
  if (std::isfinite(x) && std::isfinite(z) && std::hypot(x, z) > .0001f)
    heading = std::atan2(-x, -z);
}
// PQ-421 (D-218): whether the bag carries a ranged shot's ammunition: the
// first slot holding `item` (in slot order; equipment never counts) holds at
// least `count`, as 1298's client counts it (004a29e0, the first of the 28
// inventory slots holding the item, in 0057f7f0) and Ebenezer removes it
// (004b0792). An empty `item` needs none.
template <class Bag> bool ammo_carried(const Bag &bag, const std::string &item, uint32_t count) {
  if (item.empty())
    return true;
  for (const auto &slot : bag.slots())
    if (slot.instance() && slot.item() == item)
      return slot.quantity() >= count;
  return false;
}
struct ManualAttackInput {
  unsigned previous=0;
  bool cancel(bool layered,bool forward,bool backward,bool turning){
    unsigned held=unsigned(forward)|(unsigned(backward)<<1);
    bool pressed=(held&~previous)!=0;previous=held;
    return layered?pressed:(held!=0||turning);
  }
};
struct MeleeIntent {
  uint64_t target = 0, pending = 0;
  double next = 0, deadline = 0, sent_at = 0;
  const char *state = "Stopped";
  // false: walk to the target and stop on arrival, never attack (PQ-011: a
  // Ctrl+click or double click on an actor the attack predicate refuses).
  bool attack = true;
  // true: KO's chase (00465950, tick 0046b0d0) is walking to the target; it
  // arrives only strictly inside the reach measured in 3-D, and no swing is
  // sent before (PQ-011).
  bool chase = false;
  // true: auto-attack is on (KO player +0xae5), so a swing may be sent, also
  // during a chase the attack tick itself started (PQ-145). A Ctrl+click or
  // double-click chase is not armed until it arrives (0046b0d0 calls
  // 005d6850(1) only then).
  bool armed = false;
  // PQ-416 (D-216): above 0, the selected profile is a ranged basic attack and
  // this is its strike limit (both radii summed plus the profile's range,
  // 3-D, 1298 `00583780`); the caller sets it each frame. The attack tick then
  // never chases (004659b0 casts instead of walking), and a target beyond it
  // is refused once an interval (too_far). A Ctrl or double click still
  // walks, to the cfg's range, whose reach the caller takes from the profile
  // (00468620 adds the bow's range).
  float ranged = 0;
  // PQ-421 (D-218): false while the selected ranged profile's ammunition is
  // not carried (ammo_carried); the caller sets it each frame. The shot is
  // then not sent, and no_ammo posts the package's notice once an interval,
  // before the range test, as 1298's 005819e0 runs the usable check 0057f7f0
  // (text 0xfa7) before its range check 00583780.
  bool ammo = true;
  void stop() {
    target = pending = 0;
    attack = true;
    chase = false;
    armed = false;
    state = "Stopped";
  }
  void toggle(uint64_t id) {
    if (target)
      stop();
    else
      start(id);
  }
  // Start attacking; unlike toggle, an attack already running on this target
  // continues (005d6850(1) returns when auto-attack is already on). Without
  // `walk` auto-attack is on at once and an out-of-reach target is chased by
  // the attack tick (004659b0, PQ-145, in update). With `walk`, walk as KO's
  // chase does first: 0046b0d0 starts the attack (005d6850(1)) once the 3-D
  // distance is below the reach.
  void start(uint64_t id, bool walk = false) {
    if (id && target == id && attack) {
      chase = chase && walk;
      armed = armed || !walk;
      return;
    }
    stop();
    target = id;
    chase = id && walk;
    armed = id && !walk;
    state = id ? "Approaching" : "Stopped";
  }
  // Walk to the actor without attacking (the 00465950 chase toward an actor
  // the predicate refuses): it stops strictly inside the reach in 3-D
  // (0046b0d0), and n3e then starts no swing.
  void approach(uint64_t id) {
    stop();
    target = id;
    attack = false;
    chase = id != 0;
    state = id ? "Approaching" : "Stopped";
  }
  void select(uint64_t id) {
    if (target && target != id)
      stop();
  }
  void result(uint64_t seq, const std::string &status) {
    if (!pending || pending != seq)
      return;
    pending = 0;
    // PQ-420 (D-217): a held shot a walk cancelled (`interrupted`) leaves the
    // attack on; 1298's cancel (00585830, phase 4) does not touch auto-attack.
    if (status != "hit" && status != "miss" && status != "cooldown" && status != "out_of_range" &&
        status != "combat_pending" && status != "target_pending" && status != "combat_capacity" &&
        status != "interrupted" && status != "no_ammo")
      stop();
    // PQ-439 (D-223): a ranged shot sent while the previous arrow's arrival
    // writes (combat_pending, target_pending) is tried again at once, not an
    // interval later; the server refused it without spending the interval.
    if (ranged > 0 && (status == "combat_pending" || status == "target_pending"))
      next = std::min(next, sent_at);
  }
  // PQ-439 (D-223): the server has released the pending ranged shot (the
  // archer's strike fields show it `released`): its arrow flies and its
  // result comes when it arrives, so the next shot may go out once the
  // interval has run, as 1298's bow tick (004659b0) casts once an interval
  // with an arrow still in flight: neither it nor 005819e0 tests the flight
  // (binary, by absence; the PQ-439 evidence lists what they test). A later
  // result for it is ignored.
  void released(uint64_t seq) {
    if (pending && pending == seq)
      pending = 0;
  }
  // Returns direction toward the target. Caller applies normal
  // prediction/input.
  V update(double now, V actor, V victim, float &heading,
           const MeleeConfig &cfg, float step = .225f, bool manual = false) {
    if (!target)
      return {};
    if (pending && now >= deadline) {
      stop();
      return {};
    }
    float x = victim[0] - actor[0], z = victim[2] - actor[2];
    float d = std::hypot(x, z);
    if (!std::isfinite(d)) {
      stop();
      return {};
    }
    if(manual&&attack&&!chase){state="Moving attack";return {};}
    face_target(actor, victim, heading);
    // 004659b0 (camera mode 3): when the attack predicate refuses a swing and
    // the target is beyond the reach, the attack tick walks and sets the chase
    // target (00465950's fields +0xb18/+0xb1c); the chase below then arrives.
    // A planar distance beyond the reach is also one in 3-D.
    if (armed && !chase && d > cfg.range() && ranged <= 0)
      chase = true;
    if (chase) {
      // 0046b0d0: keep walking while reach <= the 3-D distance; strictly
      // inside it the walk stops and the attack starts (a walk-only approach
      // just stops). With a height difference beyond the reach it never
      // arrives, as in KO.
      float y = victim[1] - actor[1], r = cfg.range();
      if (std::sqrt(d * d + y * y) < r) {
        if (!attack) {
          stop();
          return {};
        }
        chase = false;
        armed = true;
      } else {
        state = "Approaching";
        float stop_at = std::sqrt(std::max(0.f, r * r - y * y)) * .95f;
        if (d < .0001f) return {};
        float scale = std::min(1.f, std::max(0.f, d - stop_at) / step);
        return {x / d * scale, 0, z / d * scale};
      }
    }
    state = ranged > 0 && attack && !within(actor, victim) ? "Out of range" : "Attacking";
    return {};
  }
  // A ranged strike's 3-D limit (inclusive, as the server's).
  bool within(V actor, V victim) const {
    float x = victim[0] - actor[0], y = victim[1] - actor[1], z = victim[2] - actor[2];
    float d = std::sqrt(x * x + y * y + z * z);
    return std::isfinite(d) && d <= ranged;
  }
  // KO's bow tick tries once an interval and records the time even when the
  // range check refuses the shot (004659b0: 00466102, 00466111): true at most
  // once an interval while an armed ranged attack's target, as predicted, is
  // beyond the limit; the caller posts the package's notice. A target the
  // prediction reaches but the server's position does not yet is left to the
  // next frame, without a notice.
  // True at most once an interval while an armed ranged attack has no
  // ammunition; the bow tick records the try either way (004659b0), so the
  // notice repeats once an interval. Checked before too_far.
  bool no_ammo(double now, const MeleeConfig &cfg, uint32_t interval_ms = 0) {
    if (!target || !attack || !armed || pending || ranged <= 0 || ammo || now < next)
      return false;
    next = now + (interval_ms ? ((interval_ms + 49) / 50) * .05 : cfg.cooldown_ticks * .05);
    return true;
  }
  bool too_far(double now, V actor, V victim, const MeleeConfig &cfg, uint32_t interval_ms = 0) {
    if (!target || !attack || !armed || pending || ranged <= 0 || now < next || within(actor, victim))
      return false;
    next = now + (interval_ms ? ((interval_ms + 49) / 50) * .05 : cfg.cooldown_ticks * .05);
    return true;
  }
  bool ready(double now, V actor, V victim, float heading,
             const MeleeConfig &cfg, V authoritative) const {
    float x = victim[0] - actor[0], z = victim[2] - actor[2],
          d = std::hypot(x, z);
    // Prediction can reach the stop point before the server processes movement.
    // Do not spend an attack interval on a request its current position rejects.
    if (ranged > 0)
      // KO's archery tick checks neither the melee predicate nor the facing
      // (004659b0 calls 005819e0 directly); the cast turns the caster
      // (00585830 -> 004579d0). Both positions must reach the target.
      return target && attack && armed && !pending && now >= next && ammo &&
             within(actor, victim) && within(authoritative, victim);
    float confirmed = std::hypot(victim[0] - authoritative[0],
                                 victim[2] - authoritative[2]);
    // While armed, the attack tick swings whenever the planar predicate holds,
    // even during its own chase (004659b0 runs 00468750 before the walk).
    return target && attack && armed && !pending && now >= next && d <= cfg.range() &&
           std::isfinite(confirmed) && confirmed <= cfg.range() &&
           (d < .0001f || (-std::sin(heading) * x - std::cos(heading) * z) / d >
                              cfg.facing_dot);
  }
  // `cast_ms` (PQ-420, D-217): a held shot's result comes when it lands, so
  // the wait for it is the cast time longer.
  void sent(uint64_t seq, double now, const MeleeConfig &cfg, uint32_t interval_ms=0, uint32_t cast_ms=0) {
    pending = seq;
    sent_at = now;
    deadline = now + 2 + cast_ms / 1000.;
    next = now + (interval_ms ? ((interval_ms+49)/50)*.05 : cfg.cooldown_ticks * .05);
  }
};
} // namespace n3e
