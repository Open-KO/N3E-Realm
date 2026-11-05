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
// render/front_end.h View::visible). RQ-145 (version 23, Q93 (b)): a create
// node flagged UNTIL_CLASS draws only while `marked` is clear: a class click
// sets it (1298's 006062d0 hides the clicked class's cream stat labels, so the
// priest's "STR" and "INT" read in their cyan copies), each open clears it
// (the reset 006066b0 by 00605950), and so does a race click that builds the
// character (005fd120 shows all ten labels, then 006062d0 with the class the
// click unset); a click on the race already chosen builds nothing, so it
// leaves the labels as they are. No GL; render/front_end.h acts by it and
// tests/front_end.cpp checks it.

#include "assets/assets.h"
#include <algorithm>
#include <cctype>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace n3e::front {

// RQ-004 (content/character-create.md, "The create screen (RQ-004)"): what
// create sends, KO's create packet's fields (1298 005fffd0: slot, name, race,
// class, face, hair and the five stats; the nation is the account's).
struct CreateRequest {
  uint32_t slot = 0, race = 0, specialty = 0, face = 0, hair = 0;
  std::vector<uint32_t> stats;
};
// The choice create sends with the package's rules (create.bin): its fixed
// choice (Q100) until the screen's buttons choose race, class, face, hair and
// points (RQ-004's later parts), in `slot`; race 0, the name alone, without
// rules or a fixed choice (the server's own path: a package without create
// rules creates by name).
inline CreateRequest create_request(const std::optional<CreateRules> &rules, uint32_t slot) {
  CreateRequest q;
  if (!rules || !rules->fixed) return q;
  const auto &f = *rules->fixed;
  q.slot = slot, q.race = f.race, q.specialty = f.specialty, q.face = f.face, q.hair = f.hair, q.stats = f.stats;
  return q;
}
// The first slot no listed character holds (the list names each one's slot,
// RQ-002), below `slots`; -1 when all are held.
template <class Slots> int create_free_slot(const Slots &held, int slots) {
  for (int s = 0; s < slots; ++s)
    if (std::find(held.begin(), held.end(), uint32_t(s)) == held.end()) return s;
  return -1;
}
// The name entry (Q99). Without create rules the server's own rule: 1..24
// ASCII letters, digits, `_` and `-` (server/src/create.rs LEGACY_NAME).
inline constexpr uint32_t kLegacyNameMax = 24;
inline uint32_t create_name_max(const std::optional<CreateRules> &rules) {
  return rules ? rules->name_max : kLegacyNameMax;
}
// What the edit takes: any printable ASCII (KO's edit_name takes what is
// typed, its create checks the letters, 1298 005fffd0; the realm's fonts draw
// ASCII 32-126), up to the rule's longest name.
inline bool create_name_takes(const std::optional<CreateRules> &rules, const std::string &name, char c) {
  return c >= ' ' && c <= '~' && name.size() < create_name_max(rules);
}
// Whether Create sends the name (1298 005fffd0's last check, code 5): the
// package's rule (create_name_ok), else the server's legacy one.
inline bool create_name_valid(const std::optional<CreateRules> &rules, std::string_view name) {
  if (rules) return create_name_ok(*rules, name);
  if (name.empty() || name.size() > kLegacyNameMax) return false;
  for (unsigned char c : name)
    if (!std::isalnum(c) && c != '_' && c != '-') return false;
  return true;
}
// The client's wording for an empty name, from the rule (a package's
// `messages` may replace it with KO's row, content/front-end.md).
inline std::string create_name_prompt(const std::optional<CreateRules> &rules) {
  const std::string marks = rules ? rules->punctuation : std::string("_-");
  std::string list;
  for (size_t i = 0; i < marks.size(); ++i)
    list += (i == 0 ? "" : i + 1 == marks.size() ? " or " : ", ") + std::string(1, marks[i]);
  return "Enter a name: " + std::to_string(rules ? rules->name_min : 1) + " to " +
         std::to_string(create_name_max(rules)) + " letters, digits" + (list.empty() ? "" : ", " + list) + ".";
}
// The client's wording for a name the rule refuses: the package's text for
// the name refusal (KO's row, cooked from the create table's texts), else the
// engine's, as the server words the same refusal (server/src/create.rs).
inline std::string create_name_refused(const std::optional<CreateRules> &rules) {
  if (rules && !rules->refusals[size_t(CreateRules::Refusal::name)].empty()) return rules->refusals[size_t(CreateRules::Refusal::name)];
  return "character name invalid";
}

struct CreateChoice {
  // The package's create binds a race button (create_race) or a class
  // button (create_class): create waits for that click.
  bool waits_race = false, waits_class = false;
  bool race = true, klass = true;  // chosen
  // A class click's marks show: create's UNTIL_CLASS nodes are hidden.
  bool marked = false;
  // The slot the new character stands at, set by the click that built it;
  // -1: the slot in focus (a create that does not wait for its race).
  int figure = -1;

  // Create opens: nothing chosen that the package waits for.
  void open(bool binds_race, bool binds_class) {
    waits_race = binds_race, waits_class = binds_class;
    race = !waits_race, klass = !waits_class;
    figure = -1;
    marked = false;
  }
  // A click on the race button with the camera at `camera_slot`: the race
  // chosen and the class not; a race that was not chosen builds the
  // character there, which clears a class click's marks.
  void click_race(int camera_slot) {
    if (!waits_race) return;
    const bool changed = !race;
    race = true;
    if (waits_class) klass = false;
    if (changed) figure = camera_slot, marked = false;
  }
  // A click on the class button: the class chosen and its marks shown; a
  // class that was not chosen builds the character again, at the camera's
  // slot, once a race is.
  void click_class(int camera_slot) {
    if (!waits_class) return;
    const bool changed = !klass;
    klass = true;
    marked = true;
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
