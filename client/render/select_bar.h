#pragma once
// RQ-109 (N3FE version 13): what 1298's select bar's buttons do
// (co_CharacterSelect_us.uif; content/front-end.md, "Actions";
// specs/KO-FINDINGS.md §9.6). Its ReceiveMessage (00607160) sends btn_create to
// 005ff920, which takes the slot in focus when it is empty, else the first
// empty slot (the camera flown to it), else posts row 7675, "Cannot create
// additional characters."; and btn_delete to row 1501's box, "Character
// deletion has been disabled currently", for a character in focus at rest
// (state 5). btn_start (005ff870) is the centre click's own start, which
// render/front_end.h's primary() already is. The realm fills its slots in
// order, so the first empty slot is the count of characters shown.
// No GL; render/front_end.h acts by it and tests/front_end.cpp checks it.

namespace n3e::front {

// The slot btn_create makes a character in, or -1 when every slot holds one:
// `focus` the slot in focus, `shown` the characters in slots 0..shown-1,
// `slots` the package's slot count.
inline int select_create_slot(int focus, int shown, int slots) {
  if (focus >= shown) return focus;
  return shown < slots ? shown : -1;
}

// Whether btn_delete posts KO's "deletion disabled" box: a character in
// focus, the hall at rest (no turn, no start under way).
inline bool select_delete_posts(int focus, int shown, bool at_rest) { return at_rest && focus < shown; }

// RQ-113 (N3FE version 18, specs/KO-FINDINGS.md §9.6, §9.13): whether the
// select's prev (`next` false) or next arrow draws with `focus` in focus, the
// row running from slot `first` to slot `last` (left to right). The realm's
// rule (`hide_at_end`) hides the arrow with no neighbour to turn to; KO's
// draws both, since no code in 1298, 1264 or 1097 hides one, and a click at
// the end of the row does nothing (DoJobLeft, DojobRight).
inline bool select_arrow_shows(bool hide_at_end, bool next, int focus, int first, int last) {
  return !hide_at_end || focus != (next ? last : first);
}

}  // namespace n3e::front
