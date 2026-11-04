#pragma once
// RQ-130 (N3FE version 21): create's race and class, chosen by a click when
// the package's create layout binds them (content/front-end.md, "Actions";
// specs/KO-FINDINGS.md §9.15, the maintainer's choice of Q87 option (b)).
// 1298's in-select create starts with no race and no class each time it opens
// (Init 005fab40 and Cancel 005ffb90 set the player's race +0x48c and class
// +0x494 to -1; a create the server accepts runs Cancel, 005ff6b0). Its
// ReceiveMessage (00604f90) sets the race on a race button's click and the
// class back to -1 on every such click, and the class on a class button's;
// each click that changes its value builds the new character (005fd120),
// which with no race builds nothing (no UPC_DefaultLooks row) and otherwise
// stands at the camera's slot (+0x38c) as it is at that click: one clicked
// while the camera flies stands at the slot the flight left. A chosen button
// is in UI_STATE_BUTTON_DOWN (006060f0, 006062d0), which draws its down image
// whatever the pointer does (CN3UIButton's check style). Its Create (005fffd0)
// refuses an empty name, then no race, then no class (codes 6, 7 and 9).
// A create that binds neither keeps race and class chosen from the open, the
// new character at the slot in focus (Q52; the 1097 choice). The server
// still makes the character it makes: the choice gates the client's Create,
// it sends nothing. RQ-133 (version 22): a create node flagged UNTIL_RACE
// draws only while `race` is not chosen (1298's race click, 006060f0, hides
// the class buttons the race cannot take and the images of those it can;
// render/front_end.h View::visible). No GL; render/front_end.h acts by it and
// tests/front_end.cpp checks it.

#include "assets/assets.h"
#include <optional>

namespace n3e::front {

struct CreateChoice {
  // The package's create binds a race button (create_race) or a class
  // button (create_class): create waits for that click.
  bool waits_race = false, waits_class = false;
  bool race = true, klass = true;  // chosen
  // The slot the new character stands at, set by the click that built it;
  // -1: the slot in focus (a create that does not wait for its race).
  int figure = -1;

  // Create opens: nothing chosen that the package waits for.
  void open(bool binds_race, bool binds_class) {
    waits_race = binds_race, waits_class = binds_class;
    race = !waits_race, klass = !waits_class;
    figure = -1;
  }
  // A click on the race button with the camera at `camera_slot`: the race
  // chosen and the class not; a race that was not chosen builds the
  // character there.
  void click_race(int camera_slot) {
    if (!waits_race) return;
    const bool changed = !race;
    race = true;
    if (waits_class) klass = false;
    if (changed) figure = camera_slot;
  }
  // A click on the class button: the class chosen; a class that was not
  // chosen builds the character again, at the camera's slot, once a race is.
  void click_class(int camera_slot) {
    if (!waits_class) return;
    const bool changed = !klass;
    klass = true;
    if (changed && race && waits_race) figure = camera_slot;
  }
  // Whether the new character stands (a race chosen).
  bool stands() const { return race; }
  // Where it stands: the slot its click built it at, or the slot in focus.
  int stands_at(int focus) const { return figure >= 0 ? figure : focus; }
  // Whether the button bound to `action` draws as chosen (its down state).
  bool down(FrontAction action) const {
    return (action == FrontAction::create_race && waits_race && race) ||
           (action == FrontAction::create_class && waits_class && klass);
  }
  // What Create refuses, in 005fffd0's order (the empty name first: the
  // caller's create_name), or nothing.
  std::optional<FrontMessage> refusal() const {
    if (!race) return FrontMessage::create_no_race;
    if (!klass) return FrontMessage::create_no_class;
    return std::nullopt;
  }
};

}  // namespace n3e::front
