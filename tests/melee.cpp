#include "render/melee.h"
#include <iostream>
#include <stdexcept>
using namespace n3e;
void check(bool ok) {
  if (!ok)
    throw std::runtime_error("melee assertion");
}
int main(int argc, char **argv) {
  auto r = load_release(argv[1]);
  check(r.melee.has_value());
  auto cfg = *r.melee;
  check(cfg.range() == 1 && cfg.cooldown_ticks == 20);
  float facing = 0;
  face_target({}, {1, 20, 0}, facing);
  check(std::abs(facing + 1.5707963f) < .00001f);
  face_target({}, {}, facing);
  check(std::abs(facing + 1.5707963f) < .00001f);
  MeleeIntent m;
  float heading = 0;
  V actor{0, 0, 0}, target{0, 100, -1};
  m.toggle(10);
  check(m.ready(0, actor, target, heading,
                cfg,actor)); // horizontal, inclusive boundary
  target[2] = -1.0001f;
  check(!m.ready(0, actor, target, heading, cfg,actor));
  {  // out of reach: the attack tick starts the chase (PQ-145, 004659b0)
    MeleeIntent far;far.toggle(10);
    check(far.update(0, actor, V{0, 0, -1.0001f}, heading, cfg)[2] < 0 && far.chase && far.armed);
  }
  target[2] = -.9f;
  check(!m.ready(0, actor, target, 3.14159265f, cfg,actor));
  check(!m.ready(0, actor, target, std::acos(cfg.facing_dot) + .0001f, cfg,actor));
  check(m.ready(0, actor, target, std::acos(cfg.facing_dot) - .0001f, cfg,actor));
  check(m.update(0, actor, target, heading, cfg) == V{});
  auto larger = cfg;
  larger.target_radius = 2;
  check(m.ready(0, actor, V{0, 50, -1.5f}, 0, larger,actor));
  check(!m.ready(0, actor, V{0, 50, -1.5001f}, 0, larger,actor));
  larger.reach = .5f;
  check(m.ready(0, actor, V{0, 50, -2}, 0, larger,actor));
  auto strict = cfg;
  strict.facing_dot = 0;
  check(!m.ready(0, actor, V{.9f, 0, 0}, 0, strict,actor)); // exact dot equality
  m.sent(1, 0, cfg);
  check(!m.ready(.5, actor, target, heading, cfg,actor));
  m.result(999, "actor_dead");
  check(m.target == 10);
  m.result(1, "hit");
  check(!m.ready(.999, actor, target, heading, cfg,actor));
  check(m.ready(1, actor, target, heading, cfg,actor));
  m.sent(2, 1, cfg);
  m.update(3, actor, target, heading, cfg);
  check(!m.target);
  m.toggle(10);
  m.select(11);
  check(!m.target);
  m.toggle(11);
  m.toggle(11);
  check(!m.target);
  m.toggle(11);
  m.sent(3, 4, cfg);
  m.result(3, "target_dead");
  check(!m.target);
  // Failed attempts retain pacing; large frame gaps never catch up with a
  // burst.
  m.toggle(11);
  m.sent(4, 5, cfg);
  m.result(4, "out_of_range");
  check(!m.ready(5.9, actor, target, heading, cfg,actor));
  check(m.ready(100, actor, target, heading, cfg,actor));
  m.sent(5, 100, cfg);
  check(!m.ready(100, actor, target, heading, cfg,actor));
  m.result(5, "miss");
  check(m.target == 11 && !m.ready(100.9, actor, target, heading, cfg,actor));
  check(m.ready(101, actor, target, heading, cfg,actor));
  for(const char *status:{"combat_pending","target_pending","combat_capacity"}) {
    m.sent(6,110,cfg);m.result(6,status);
    check(m.target==11&&!m.pending&&!m.ready(110.9,actor,target,heading,cfg,actor));
    check(m.ready(111,actor,target,heading,cfg,actor));
  }
  m.sent(7,120,cfg,1140);m.result(7,"hit");m.stop();m.toggle(11);
  check(!m.ready(121.149,actor,target,heading,cfg,actor)&&m.ready(121.15,actor,target,heading,cfg,actor));
  m.sent(8,122,cfg,1390);m.result(8,"miss");check(!m.ready(123.399,actor,target,heading,cfg,actor)&&m.ready(123.4,actor,target,heading,cfg,actor));
  // Regression: predicted arrival must not send while the latest server
  // position is still outside melee range. A new snapshot admits immediately,
  // without reserving a full interval for an out-of-range attempt.
  MeleeIntent arriving;arriving.toggle(99);
  V predicted{0,0,-.05f}, victim{0,0,-1.f}, behind{0,0,.275f};
  check(!arriving.ready(200,predicted,victim,0,cfg,behind));
  check(!arriving.pending && arriving.next==0);
  check(arriving.ready(200.1,predicted,victim,0,cfg,predicted));
  arriving.sent(1,200.1,cfg,1140);arriving.result(1,"hit");
  check(!arriving.ready(201.249,predicted,victim,0,cfg,predicted));
  check(arriving.ready(201.251,predicted,victim,0,cfg,predicted));
  check(!arriving.ready(202,predicted,victim,0,cfg,{NAN,0,0}));
  check(!arriving.ready(202,{0,0,.1f},victim,0,cfg,predicted));
  ManualAttackInput input;
  check(input.cancel(true,true,false,false));check(!input.cancel(true,true,false,false));
  check(!input.cancel(true,true,false,true));check(input.cancel(true,true,true,false));
  check(!input.cancel(true,false,false,false));check(input.cancel(true,false,true,false));
  check(input.cancel(false,false,true,false));
  m.result(8,"hit");m.target=11;float manual_heading=1.2f;
  check(m.update(125,actor,target,manual_heading,cfg,.225f,true)==V{});
  check(manual_heading==1.2f&&m.target==11&&!m.ready(125,actor,target,manual_heading,cfg,actor));
  // PQ-011: start() never toggles a running attack off (005d6850(1) returns
  // when auto-attack is on); approach() walks to an actor the attack predicate
  // refuses and stops inside the reach without attacking (0046b0d0).
  MeleeIntent s;s.start(20);check(s.target==20&&s.attack);
  s.pending=5;s.start(20);check(s.target==20&&s.pending==5);
  s.start(21);check(s.target==21&&!s.pending&&s.attack);
  MeleeIntent walk;walk.approach(30);check(walk.target==30&&!walk.attack);
  float walk_heading=0;V far{0,0,-3},near{0,0,-.9f};
  check(walk.update(0,actor,far,walk_heading,cfg)[2]<0&&walk.target==30);
  check(!walk.ready(0,actor,far,walk_heading,cfg,actor)&&!walk.ready(0,actor,near,walk_heading,cfg,actor));
  check(walk.update(0,actor,near,walk_heading,cfg)==V{}&&!walk.target&&walk.attack);
  walk.approach(31);check(walk.update(0,actor,far,walk_heading,cfg,.225f,true)[2]<0);  // a walk is never a moving attack
  walk.start(31);check(walk.attack&&walk.target==31);  // an attack replaces the walk
  // The chase arrives only strictly inside the reach measured in 3-D
  // (0046b0d0: reach <= distance keeps walking). Height matters: planar 0.9
  // with 0.8 up is 1.2 away; exactly the reach (1.0) still walks.
  V above{0,.8f,-.9f},edge{0,0,-1},inside{0,.5f,-.5f};
  MeleeIntent up;up.approach(40);
  check(up.update(0,actor,above,walk_heading,cfg)[2]<0&&up.target==40);
  check(up.update(0,actor,edge,walk_heading,cfg)[2]<0&&up.target==40);
  check(up.update(0,actor,inside,walk_heading,cfg)==V{}&&!up.target);
  MeleeIntent chase;chase.start(41,true);check(chase.chase&&chase.attack);
  check(chase.update(0,actor,above,walk_heading,cfg)[2]<0&&!chase.ready(0,actor,above,walk_heading,cfg,actor));
  check(!chase.ready(0,actor,inside,walk_heading,cfg,actor));  // no swing before the arrival
  check(chase.update(0,actor,inside,walk_heading,cfg)==V{}&&!chase.chase&&chase.target==41&&chase.ready(0,actor,inside,walk_heading,cfg,actor));
  MeleeIntent tall;tall.start(42,true);  // a height beyond the reach never arrives
  check(tall.update(0,actor,{0,2,-.5f},walk_heading,cfg)[2]<0&&tall.chase&&tall.update(0,actor,{0,2,0},walk_heading,cfg)==V{}&&tall.chase);
  MeleeIntent near_start;near_start.start(43,false);check(!near_start.chase);  // in reach: attack at once
  near_start.start(43,true);check(!near_start.chase);  // a running attack is not turned into a walk
  // PQ-145: KO's auto-attack (R, 005d6850) never walks itself, but its attack
  // tick (004659b0, camera mode 3) walks and sets the chase target when the
  // predicate refuses a swing and the target is beyond the reach in 3-D; the
  // chase (0046b0d0) arrives strictly inside the reach. Auto-attack stays on
  // meanwhile, so a swing goes out whenever the planar predicate holds.
  MeleeIntent rt;rt.toggle(50);
  check(rt.target==50&&rt.armed&&!rt.chase&&rt.state==std::string("Approaching"));
  check(!rt.ready(0,actor,far,walk_heading,cfg,actor));        // 3 away: no swing
  check(rt.update(0,actor,far,walk_heading,cfg)[2]<0&&rt.chase);  // walk (chase)
  check(rt.ready(0,actor,above,walk_heading,cfg,actor));        // planar 0.9: the tick swings
  check(rt.update(0,actor,above,walk_heading,cfg)[2]<0&&rt.chase);  // 1.2 in 3-D: still walking
  check(rt.update(0,actor,edge,walk_heading,cfg)[2]<0&&rt.chase);   // exactly the reach walks
  check(rt.update(0,actor,inside,walk_heading,cfg)==V{}&&!rt.chase&&rt.armed&&rt.target==50);
  check(rt.state==std::string("Attacking")&&rt.ready(0,actor,inside,walk_heading,cfg,actor));
  check(rt.update(0,actor,near,walk_heading,cfg)==V{}&&!rt.chase);  // in reach: stand
  check(rt.update(0,actor,V{0,0,-1.5f},walk_heading,cfg)[2]<0&&rt.chase);  // it steps away: chase again
  MeleeIntent in_reach;in_reach.toggle(51);
  check(in_reach.update(0,actor,near,walk_heading,cfg)==V{}&&!in_reach.chase&&in_reach.ready(0,actor,near,walk_heading,cfg,actor));
  check(in_reach.update(0,actor,above,walk_heading,cfg)==V{}&&!in_reach.chase);  // planar reach: no walk
  MeleeIntent click;click.start(52,true);  // the click chase is not armed until it arrives
  check(!click.armed&&!click.ready(0,actor,above,walk_heading,cfg,actor));
  check(click.update(0,actor,inside,walk_heading,cfg)==V{}&&click.armed&&!click.chase);
  MeleeIntent rclick;rclick.toggle(53);rclick.start(53,true);  // Ctrl+click on a running auto-attack
  check(rclick.armed&&!rclick.chase&&rclick.update(0,actor,far,walk_heading,cfg)[2]<0&&rclick.chase);
  MeleeIntent off;off.toggle(54);off.toggle(54);check(!off.target&&!off.armed);  // R again: off
  MeleeIntent manual_r;manual_r.toggle(55);float manual_h=.5f;  // a layered moving attack never walks
  check(manual_r.update(0,actor,far,manual_h,cfg,.225f,true)==V{}&&!manual_r.chase&&manual_h==.5f);
  // PQ-416 (D-216): a ranged basic attack (strike limit 10 = radii 1 + 1 +
  // range 8, 3-D). KO's bow tick (004659b0) never walks: an armed attack on a
  // target beyond the limit stands, is refused once an interval (too_far,
  // the tick records the time at 00466111) and shoots when the target comes
  // in; no facing or melee predicate; both positions must reach. A Ctrl or
  // double click walks to the cfg's range (00468620 with the bow's reach).
  {
    auto bow = cfg; bow.reach = 6;  // the click walk arrives inside (1 + 1) / 2 + 6 = 7
    MeleeIntent b; b.ranged = 10; b.toggle(60); float h = 0;
    V far10{0, 0, -10.001f}, at10{0, 6, -8}, aside{9.9f, 0, 0}, above10{0, 6.01f, -8};
    check(b.update(0, actor, far10, h, bow) == V{} && !b.chase && b.armed && b.state == std::string("Out of range"));
    check(!b.ready(0, actor, far10, h, bow, actor));
    check(b.too_far(0, actor, far10, bow, 1450) && b.next > 1.449 && b.next < 1.451);
    check(!b.too_far(1, actor, far10, bow, 1450) && !b.ready(1, actor, at10, h, bow, actor));  // one try per interval
    check(b.too_far(1.46, actor, far10, bow, 1450));
    check(!b.ready(2.92, actor, above10, h, bow, actor) && b.too_far(2.92, actor, above10, bow, 1450));  // 3-D: 10.008
    check(b.ready(4.38, actor, at10, h, bow, actor) && !b.too_far(4.38, actor, at10, bow, 1450));     // exactly 10
    check(b.update(4.38, actor, at10, h, bow) == V{} && b.state == std::string("Attacking"));
    check(b.ready(4.38, actor, aside, 3.14159265f, bow, actor));   // no facing requirement
    check(!b.ready(4.38, actor, at10, h, bow, V{0, 0, 1}));         // the server's position must reach too
    check(!b.too_far(4.38, actor, at10, bow, 1450));                  // ... without a notice
    b.sent(9, 4.38, bow, 1450);
    check(!b.ready(5, actor, at10, h, bow, actor) && !b.too_far(5, actor, far10, bow, 1450));  // pending
    b.result(9, "out_of_range"); check(b.target == 60);  // the server's refusal keeps the attack on
    check(!b.ready(5.82, actor, at10, h, bow, actor) && b.ready(5.84, actor, at10, h, bow, actor));
    MeleeIntent nan; nan.ranged = 10; nan.toggle(61);
    check(!nan.ready(0, actor, V{NAN, 0, 0}, h, bow, actor) && nan.too_far(0, actor, V{NAN, 0, 0}, bow, 1450));
    MeleeIntent melee_tick; melee_tick.toggle(62);  // the same target under melee: the tick chases
    check(melee_tick.update(0, actor, far10, h, bow)[2] < 0 && melee_tick.chase && !melee_tick.too_far(0, actor, far10, bow));
    MeleeIntent click; click.ranged = 10; click.start(63, true);  // Ctrl/double click: walk to 7 (3-D), then armed
    check(click.update(0, actor, V{0, 0, -7}, h, bow)[2] < 0 && click.chase && !click.ready(0, actor, V{0, 0, -7}, h, bow, actor));
    check(click.update(0, actor, V{0, 0, -6.9f}, h, bow) == V{} && click.armed && !click.chase);
    check(click.ready(0, actor, V{0, 0, -6.9f}, h, bow, actor));
    MeleeIntent walk_only; walk_only.ranged = 10; walk_only.approach(64);  // walk-only: never a shot or notice
    check(walk_only.update(0, actor, far10, h, bow)[2] < 0 && !walk_only.too_far(0, actor, far10, bow) &&
          !walk_only.ready(0, actor, V{0, 0, -5}, h, bow, actor));
    // PQ-420 (D-217): a held shot's result comes when it lands, so its wait is
    // the cast time longer (2 s + 1.3 s), and a walk's cancel (`interrupted`)
    // keeps the attack on (1298's 00585830 cancel leaves auto-attack alone);
    // the server refusing the target still stops it.
    MeleeIntent cast; cast.ranged = 10; cast.toggle(65);
    cast.sent(11, 0, bow, 1450, 1300);
    check(cast.update(3.29, actor, at10, h, bow) == V{} && cast.target == 65 && cast.pending == 11);  // still waiting
    check(cast.update(3.31, actor, at10, h, bow) == V{} && cast.target == 0);                         // timed out
    MeleeIntent plain; plain.ranged = 10; plain.toggle(66); plain.sent(12, 0, bow, 1450);
    check(plain.update(2.01, actor, at10, h, bow) == V{} && plain.target == 0);  // without a cast time: 2 s
    cast.toggle(65); cast.sent(13, 0, bow, 1450, 1300);
    cast.result(13, "interrupted"); check(cast.target == 65 && !cast.pending && cast.armed);
    check(!cast.ready(1.44, actor, at10, h, bow, actor) && cast.ready(1.46, actor, at10, h, bow, actor));  // next interval
    cast.sent(14, 1.46, bow, 1450, 1300); cast.result(14, "target_dead"); check(cast.target == 0);
    // PQ-421 (D-218): without its ammunition the bow neither shoots nor walks;
    // the package's notice comes once an interval and before the range test
    // (1298's 005819e0 runs 0057f7f0, text 0xfa7, before 00583780); the
    // count is the first bag slot holding the item, as 004a29e0's; a
    // `no_ammo` result keeps the attack on.
    struct Slot { uint64_t id; std::string name; uint32_t count;
      uint64_t instance() const { return id; } const std::string &item() const { return name; } uint32_t quantity() const { return count; } };
    struct Bag { std::vector<Slot> list; const std::vector<Slot> &slots() const { return list; } };
    Bag bag{{{0, "", 0}, {7, "g:arrow", 2}, {8, "g:arrow", 50}}};
    check(ammo_carried(bag, "g:arrow", 2) && !ammo_carried(bag, "g:arrow", 3));  // the first stack only
    check(!ammo_carried(Bag{}, "g:arrow", 1) && ammo_carried(Bag{}, "", 1) && !ammo_carried(bag, "g:bolt", 1));
    MeleeIntent dry; dry.ranged = 10; dry.ammo = false; dry.toggle(67);
    check(dry.update(0, actor, at10, h, bow) == V{} && !dry.chase && !dry.ready(0, actor, at10, h, bow, actor));
    check(dry.no_ammo(0, bow, 1450) && !dry.too_far(0, actor, far10, bow, 1450));  // the ammo notice first
    check(!dry.no_ammo(1, bow, 1450) && dry.no_ammo(1.46, bow, 1450));           // once an interval
    dry.ammo = true;
    check(!dry.no_ammo(2.92, bow, 1450) && dry.ready(2.92, actor, at10, h, bow, actor));
    dry.sent(15, 2.92, bow, 1450); dry.result(15, "no_ammo"); check(dry.target == 67 && dry.armed);
    MeleeIntent swing; swing.toggle(68); swing.ammo = false;  // melee never needs it
    check(!swing.no_ammo(0, bow, 1450));
    // PQ-439 (D-223): the server's release of the pending shot ends the wait
    // (its result comes when the arrow arrives), so the next shot goes out
    // once the interval has run, not after the flight; that late result is
    // ignored. A shot refused while the arrow's arrival writes is retried at
    // once, not an interval later; a melee attack keeps its interval.
    MeleeIntent bowman; bowman.ranged = 10; bowman.toggle(69);
    bowman.sent(16, 0, bow, 1450, 1300);
    bowman.released(15); check(bowman.pending == 16);                     // another shot's release
    bowman.released(16); check(!bowman.pending && bowman.target == 69);
    check(!bowman.ready(1.44, actor, at10, h, bow, actor) && bowman.ready(1.46, actor, at10, h, bow, actor));
    bowman.sent(17, 1.46, bow, 1450, 1300);
    bowman.result(16, "target_dead"); check(bowman.target == 69 && bowman.pending == 17);  // the old arrow's result
    bowman.result(17, "combat_pending"); check(!bowman.pending && bowman.ready(1.5, actor, at10, h, bow, actor));
    bowman.sent(18, 1.5, bow, 1450, 1300); bowman.result(18, "target_pending");
    check(bowman.ready(1.55, actor, at10, h, bow, actor));
    bowman.sent(19, 1.55, bow, 1450, 1300); bowman.result(19, "cooldown");  // a refused interval is not retried at once
    check(!bowman.ready(2.9, actor, at10, h, bow, actor) && bowman.ready(3.01, actor, at10, h, bow, actor));
    MeleeIntent blade; blade.toggle(70);
    blade.sent(20, 0, bow, 1450); blade.result(20, "combat_pending");
    check(blade.next > 1.44 && !blade.pending);
  }
  std::cout << "PASS melee range/facing, approach, target/cancel, response "
               "fencing, pacing/timeout, start without toggle, approach-only walk, 3-D chase arrival, "
               "attack-tick chase, ranged attack without a chase, a held shot's wait and walk cancel, "
               "ranged ammunition (the first stack, the notice once an interval before the range test), "
               "a released shot's end of the wait and the retry of a shot refused by the arrival's write\n";
}
