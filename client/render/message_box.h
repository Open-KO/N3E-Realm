#pragma once
// RQ-111 (N3FE version 14): KO's message box styles (content/front-end.md,
// "Actions"; specs/KO-FINDINGS.md §9.7). 1298's CUIMessageBox::SetBoxStyle
// (00527a40) hides its four buttons and shows Btn_Yes and Btn_No for MB_YESNO
// (4), Btn_Cancel for MB_CANCEL (6) and Btn_OK otherwise; its OnKeyPress
// (00527c60, vtable 006a6710 slot 24) presses No for ESC and Yes for ENTER or
// the keypad's ENTER in a yes/no box, and OK for any of the three in an OK box;
// its ReceiveMessage (00526d00) quits for Yes or OK on BEHAVIOR_EXIT and hides
// the box for No or Cancel. The realm raises one question, exit_confirm (1298's
// btn_exit: row 1502, MB_YESNO, BEHAVIOR_EXIT); every other message is an OK
// box. No GL; render/front_end.h acts by it and tests/front_end.cpp checks it.
#include "assets/assets.h"

namespace n3e::front {

enum class BoxStyle { ok, yes_no };
enum class BoxKey { none, enter, escape };

// A message's box: the engine's one question asks yes or no.
inline BoxStyle box_style(FrontMessage kind) {
  return kind == FrontMessage::exit_confirm ? BoxStyle::yes_no : BoxStyle::ok;
}

// Whether a message box node bound to `action` draws in a box of `style`
// (SetBoxStyle): OK in an OK box only, Yes and No in a yes/no box only.
inline bool box_shows(FrontAction action, BoxStyle style) {
  switch (action) {
  case FrontAction::ok: return style == BoxStyle::ok;
  case FrontAction::yes:
  case FrontAction::no: return style == BoxStyle::yes_no;
  default: return true;
  }
}

// The button a key presses (OnKeyPress): none for other keys.
inline FrontAction box_key(BoxStyle style, BoxKey key) {
  if (key == BoxKey::none) return FrontAction::none;
  if (style == BoxStyle::yes_no) return key == BoxKey::enter ? FrontAction::yes : FrontAction::no;
  return FrontAction::ok;
}

// What pressing `button` in a box of message `kind` does: whether it closes
// the box, and whether it leaves the game (Yes on exit_confirm: 1298's
// BEHAVIOR_EXIT, PostQuitMessage). A button the box does not show does
// nothing, as does any other action.
struct BoxAnswer {
  bool closes = false, exits = false;
};
inline BoxAnswer box_press(FrontMessage kind, FrontAction button) {
  const bool a_button = button == FrontAction::ok || button == FrontAction::yes || button == FrontAction::no;
  if (!a_button || !box_shows(button, box_style(kind))) return {};
  return {true, kind == FrontMessage::exit_confirm && button == FrontAction::yes};
}

}  // namespace n3e::front
