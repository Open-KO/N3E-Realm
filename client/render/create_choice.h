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
// leaves the labels as they are. RQ-172 (version 25): every race and class
// button bound to KO's codes (content/front-end.md item 14): a race button
// chooses its race (its create model drawn, content/character-create.md "The
// realm's races"; with no class the build takes the race's default class for
// its stat row, 1298 005fd120), a class button the specialty of the chosen
// race it stands for; once a race is chosen the class buttons it cannot take
// (create.bin's races) are hidden for their images and its classes' images
// hidden (1298 006060f0, 1264 0043ec90), replacing version 22's static list;
// each class button marks its own labels (1298 006062d0's pairs, 1264
// 0043ee10's), hidden or shown by the package's flag. A race or class button
// fixed on is chosen at each open (the 1097 choice's Tuarek and priest, Q52,
// Q89 (b)), its labels marked. Create sends the chosen race and specialty,
// refused first as the server's Policy::choice would refuse it. No GL;
// render/front_end.h acts by it and tests/front_end.cpp checks it.

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
// The client's wording for a refusal: the package's text for it (KO's row,
// cooked from the create table's texts), else the engine's, as the server
// words the same refusal (server/src/create.rs Refusal::engine_text).
inline std::string create_refused_text(const std::optional<CreateRules> &rules, CreateRules::Refusal refusal) {
  if (rules && !rules->refusals[size_t(refusal)].empty()) return rules->refusals[size_t(refusal)];
  using R = CreateRules::Refusal;
  switch (refusal) {
    case R::limit: return "character limit reached";
    case R::mismatch: return "race, specialty or nation not offered";
    case R::taken: return "character name taken";
    case R::failed: return "character could not be created";
    case R::name: return "character name invalid";
    default: return "character stats, face or hair invalid";
  }
}
inline std::string create_name_refused(const std::optional<CreateRules> &rules) {
  return create_refused_text(rules, CreateRules::Refusal::name);
}

struct CreateChoice {
  // The package's buttons (version 25; FrontEnd::create_race_buttons and
  // create_class_buttons) and the one of each chosen at every open (FIXED_ON;
  // -1 none). A create that binds no race button keeps its race chosen from
  // the open, one that binds no class button its class (the package's fixed
  // choice, Q100).
  std::vector<FrontCreateRace> races;
  std::vector<FrontCreateClass> classes;
  int race_preset = -1, class_preset = -1;
  // The chosen race and class buttons (-1 none), and the class button whose
  // click marks the create's labels (-1 none: every label as at the open).
  int race = -1, klass = -1, marked = -1;
  // The slot the new character stands at, set by the click that built it;
  // -1: the slot in focus (a create chosen from the open).
  int figure = -1;

  void bind(std::vector<FrontCreateRace> r, std::vector<FrontCreateClass> c, int race_at_open, int class_at_open) {
    races = std::move(r), classes = std::move(c), race_preset = race_at_open, class_preset = class_at_open;
    open();
  }
  // Create opens (1298's Init 005fab40 and Cancel 005ffb90 set race and
  // class to -1; 1264's Init 00439550 too): nothing chosen but the package's
  // choice at the open, its class's labels marked (1264's 0043ee10 for it).
  void open() {
    race = race_preset, klass = class_preset, marked = class_preset;
    figure = -1;
  }
  // Whether create waits for a click before it can be sent (a button with no
  // choice at the open).
  bool waits() const { return (!races.empty() && race_preset < 0) || (!classes.empty() && class_preset < 0); }
  bool race_chosen() const { return races.empty() || race >= 0; }
  bool class_chosen() const { return classes.empty() || klass >= 0; }
  // A click on race button `button` with the camera at `camera_slot`: the
  // race chosen and the class not (00604f90 sets the class to -1 on every race
  // click; 1264's 0043ec90 too); a race that was not chosen builds the
  // character there, which clears a class click's marks (005fd120's 00605950,
  // 1264's SetChr's Reset 0043ea10).
  void click_race(size_t button, int camera_slot) {
    if (button >= races.size()) return;
    const bool changed = race != int(button);
    race = int(button);
    if (!classes.empty()) klass = -1;
    if (changed) figure = camera_slot, marked = -1;
  }
  // A click on class button `button`: the class chosen and its labels marked
  // (006062d0, 0043ee10); a class that was not chosen builds the character
  // again, at the camera's slot, once a race is.
  void click_class(size_t button, int camera_slot) {
    if (button >= classes.size()) return;
    const bool changed = klass != int(button);
    klass = int(button);
    marked = int(button);
    if (changed && race >= 0) figure = camera_slot;
  }
  // Whether the new character stands (a race chosen).
  bool stands() const { return race_chosen(); }
  // Where it stands: the slot its click built it at, or the slot in focus.
  int stands_at(int focus) const { return figure >= 0 ? figure : focus; }
  // The chosen race button's race code, if one is chosen.
  std::optional<uint32_t> race_code() const {
    if (race < 0) return std::nullopt;
    return races[size_t(race)].race;
  }
  // Whether the chosen race can take class button `button`: any of its
  // specialties is one of the race's in the package's rules (create.bin
  // lists the offered races only, so a race it lacks takes none); without
  // rules, every class.
  bool takes(const std::optional<CreateRules> &rules, size_t button) const {
    const auto code = race_code();
    if (!code || !rules) return true;
    const auto *r = create_race(*rules, *code);
    if (!r) return false;
    for (auto s : classes[button].specialties)
      if (create_specialty(*r, s)) return true;
    return false;
  }
  // Whether class button `button` and its image draw: before a race every
  // button over its image (1298's reset 006066b0 by 00605950); once one is
  // chosen the buttons it cannot take are hidden for their images and the
  // images of those it can are hidden (006060f0, 1264's 0043ec90).
  bool class_drawn(const std::optional<CreateRules> &rules, size_t button) const {
    return !race_code() || takes(rules, button);
  }
  bool image_drawn(const std::optional<CreateRules> &rules, size_t button) const {
    return !race_code() || !takes(rules, button);
  }
  // Whether stat label `node` with `flag` (FrontNode::CLASS_HIDES or
  // CLASS_SHOWS) draws: unless, or only while, the marked class names it.
  bool label_drawn(uint32_t node, uint32_t flag) const {
    const bool named = marked >= 0 && std::find(classes[size_t(marked)].labels.begin(),
                                                classes[size_t(marked)].labels.end(), node) !=
                                          classes[size_t(marked)].labels.end();
    return flag == FrontNode::CLASS_SHOWS ? named : !named;
  }
  // The chosen class's specialty for the chosen race (the one of its codes
  // the race has; 0 when the race has none of them, which the server
  // refuses as a mismatch), or none without a chosen class.
  std::optional<uint32_t> specialty(const std::optional<CreateRules> &rules, uint32_t race_code) const {
    if (klass < 0) return std::nullopt;
    const auto &codes = classes[size_t(klass)].specialties;
    if (!rules) return codes.front();
    if (const auto *r = create_race(*rules, race_code))
      for (auto s : codes)
        if (create_specialty(*r, s)) return s;
    return 0u;
  }
  // The specialty whose stat row the screen shows: the chosen class's, or
  // with none the chosen race's default (1298's build 005fd120 with class -1:
  // 1->101, 2->102, ... 13->204, the race button's `base`); none without a race.
  std::optional<uint32_t> row_specialty(const std::optional<CreateRules> &rules) const {
    const auto code = race_code();
    if (!code) return std::nullopt;
    if (const auto s = specialty(rules, *code)) return s;
    return races[size_t(race)].base;
  }
  // Whether race button `button`, or class button `button`, draws as chosen
  // (its down state, 006060f0 and 006062d0 set UI_STATE_BUTTON_DOWN).
  bool race_down(size_t button) const { return race == int(button); }
  bool class_down(size_t button) const { return klass == int(button); }
  // What Create refuses, in 005fffd0's order (the empty name first: the
  // caller's create_name), or nothing.
  std::optional<FrontMessage> refusal() const {
    if (!race_chosen()) return FrontMessage::create_no_race;
    if (!class_chosen()) return FrontMessage::create_no_class;
    return std::nullopt;
  }
};

// The choice create sends with the package's rules (create.bin), in `slot`:
// the chosen race button's race, else the fixed choice's (Q100); the chosen
// class's specialty for it, else (no class button) the race button's
// default or the fixed choice's; the face, hair and points spent of the fixed
// choice until the screen's arrows choose them (RQ-173, RQ-174), the points
// added to the chosen specialty's base (none without a fixed choice, a sum
// the server refuses); race 0, the name alone, without rules or a race (the
// server's own path: a package without create rules creates by name).
inline CreateRequest create_request(const std::optional<CreateRules> &rules, uint32_t slot,
                                    const CreateChoice &choice = {}) {
  CreateRequest q;
  if (!rules) return q;
  const auto *fixed = rules->fixed ? &*rules->fixed : nullptr;
  const auto code = choice.race_code();
  const uint32_t race = code ? *code : fixed && choice.races.empty() ? fixed->race : 0;
  if (!race) return q;
  uint32_t specialty = 0;
  if (const auto s = choice.specialty(rules, race)) specialty = *s;
  else if (choice.classes.empty()) specialty = code ? choice.races[size_t(choice.race)].base : fixed ? fixed->specialty : 0;
  q.slot = slot, q.race = race, q.specialty = specialty;
  if (fixed) q.face = fixed->face, q.hair = fixed->hair;
  const auto *r = create_race(*rules, race);
  const auto *s = r ? create_specialty(*r, specialty) : nullptr;
  const auto *fr = fixed ? create_race(*rules, fixed->race) : nullptr;
  const auto *fs = fr ? create_specialty(*fr, fixed->specialty) : nullptr;
  if (!s) {
    if (fixed) q.stats = fixed->stats;
    return q;
  }
  q.stats = s->base;
  if (fs && fs->base.size() == q.stats.size() && fixed->stats.size() == q.stats.size())
    for (size_t i = 0; i < q.stats.size(); ++i) q.stats[i] += fixed->stats[i] - fs->base[i];
  return q;
}

}  // namespace n3e::front
