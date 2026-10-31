#pragma once
// Package-owned input map (PQ-009, D-136). The engine owns the actions and what
// they do; a package's input.bin (Release::input) owns which physical keys fire
// them. A package with no table gets the pre-PQ-009 layout (legacy()).
#include "assets/assets.h"
#include "assets/input_names.h"
#include <SDL3/SDL_keyboard.h>
#include <SDL3/SDL_keycode.h>
#include <SDL3/SDL_scancode.h>
#include <algorithm>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>
namespace n3e::input {
// Same order as key_names.
inline constexpr std::array<SDL_Scancode, key_names.size()> key_codes{
  SDL_SCANCODE_A, SDL_SCANCODE_B, SDL_SCANCODE_C, SDL_SCANCODE_D, SDL_SCANCODE_E, SDL_SCANCODE_F,
  SDL_SCANCODE_G, SDL_SCANCODE_H, SDL_SCANCODE_I, SDL_SCANCODE_J, SDL_SCANCODE_K, SDL_SCANCODE_L,
  SDL_SCANCODE_M, SDL_SCANCODE_N, SDL_SCANCODE_O, SDL_SCANCODE_P, SDL_SCANCODE_Q, SDL_SCANCODE_R,
  SDL_SCANCODE_S, SDL_SCANCODE_T, SDL_SCANCODE_U, SDL_SCANCODE_V, SDL_SCANCODE_W, SDL_SCANCODE_X,
  SDL_SCANCODE_Y, SDL_SCANCODE_Z,
  SDL_SCANCODE_1, SDL_SCANCODE_2, SDL_SCANCODE_3, SDL_SCANCODE_4, SDL_SCANCODE_5,
  SDL_SCANCODE_6, SDL_SCANCODE_7, SDL_SCANCODE_8, SDL_SCANCODE_9, SDL_SCANCODE_0,
  SDL_SCANCODE_F1, SDL_SCANCODE_F2, SDL_SCANCODE_F3, SDL_SCANCODE_F4, SDL_SCANCODE_F5, SDL_SCANCODE_F6,
  SDL_SCANCODE_F7, SDL_SCANCODE_F8, SDL_SCANCODE_F9, SDL_SCANCODE_F10, SDL_SCANCODE_F11, SDL_SCANCODE_F12,
  SDL_SCANCODE_UP, SDL_SCANCODE_DOWN, SDL_SCANCODE_LEFT, SDL_SCANCODE_RIGHT, SDL_SCANCODE_PAGEUP,
  SDL_SCANCODE_PAGEDOWN, SDL_SCANCODE_HOME, SDL_SCANCODE_END, SDL_SCANCODE_INSERT, SDL_SCANCODE_DELETE,
  SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_ENTER, SDL_SCANCODE_KP_MINUS, SDL_SCANCODE_KP_PLUS,
  SDL_SCANCODE_SPACE, SDL_SCANCODE_TAB,
  SDL_SCANCODE_LEFTBRACKET, SDL_SCANCODE_RIGHTBRACKET, SDL_SCANCODE_MINUS, SDL_SCANCODE_EQUALS,
  SDL_SCANCODE_COMMA, SDL_SCANCODE_PERIOD, SDL_SCANCODE_SLASH, SDL_SCANCODE_SEMICOLON,
  SDL_SCANCODE_APOSTROPHE, SDL_SCANCODE_BACKSLASH, SDL_SCANCODE_GRAVE, SDL_SCANCODE_ESCAPE,
  SDL_SCANCODE_UNKNOWN, SDL_SCANCODE_UNKNOWN,  // mouse gestures: Binding::mouse
};
// Mouse gestures (PQ-011), in mouse_keys order from 1; 0 is a keyboard key.
enum Gesture : uint8_t { keyboard = 0, left_click = 1, left_double = 2 };
// Engine-reserved keys (D-136); no package binding reaches them.
inline constexpr SDL_Scancode reconnect_key = SDL_SCANCODE_F12;
inline constexpr SDL_Scancode editor_key = SDL_SCANCODE_F11;
inline constexpr SDL_Scancode terminal_key = SDL_SCANCODE_GRAVE;

inline uint32_t modifiers(SDL_Keymod m) {
  return (m & SDL_KMOD_SHIFT ? shift : 0u) | (m & SDL_KMOD_LSHIFT ? left_shift : 0u) |
         (m & SDL_KMOD_CTRL ? ctrl : 0u) | (m & SDL_KMOD_ALT ? alt : 0u);
}
struct Binding {
  Action action;
  SDL_Scancode key;
  uint32_t require = 0, forbid = 0;
  bool typing = false;
  uint8_t mouse = keyboard;
  bool accepts(uint32_t mods) const { return (mods & require) == require && !(mods & forbid); }
};
struct Map {
  std::vector<Binding> bindings;
  bool packaged = false;  // false: the legacy layout of a package without a table

  static Binding parse(const InputBinding &b) {
    auto action = find(action_names, b.action);
    auto key = find(key_names, b.key);
    auto gesture = find(mouse_keys, b.key);
    if (!action || !key || reserved(b.key) || (b.require & b.forbid) || ((b.require | b.forbid) & ~all_modifiers) ||
        (gesture && (held(Action(*action)) || (b.flags & typing))))
      throw std::runtime_error("input binding " + b.action + " " + b.key);
    return {Action(*action), key_codes[*key], b.require, b.forbid, (b.flags & typing) != 0,
            uint8_t(gesture ? *gesture + 1 : keyboard)};
  }
  static Map from(const Release &release) {
    if (!release.input) return legacy();
    Map map;
    map.packaged = true;
    for (const auto &b : *release.input) map.bindings.push_back(parse(b));
    return map;
  }
  // The pre-PQ-009 layout, for releases cooked without an input table.
  static Map legacy() {
    Map map;
    auto add = [&](Action a, SDL_Scancode k) { map.bindings.push_back({a, k}); };
    for (int i = 0; i < 8; ++i) add(Action(int(Action::hotbar_use_1) + i), SDL_Scancode(SDL_SCANCODE_1 + i));
    add(Action::move_forward, SDL_SCANCODE_W);
    add(Action::move_backward, SDL_SCANCODE_S);
    add(Action::turn_left, SDL_SCANCODE_A);
    add(Action::turn_right, SDL_SCANCODE_D);
    add(Action::turbo, SDL_SCANCODE_Q);
    add(Action::rest_toggle, SDL_SCANCODE_C);
    add(Action::respawn, SDL_SCANCODE_E);
    add(Action::loot_nearest, SDL_SCANCODE_F);
    add(Action::skills, SDL_SCANCODE_K);
    add(Action::minimap, SDL_SCANCODE_M);
    add(Action::inventory, SDL_SCANCODE_I);
    add(Action::window_page_prev, SDL_SCANCODE_LEFTBRACKET);
    add(Action::window_page_next, SDL_SCANCODE_RIGHTBRACKET);
    add(Action::run_toggle, SDL_SCANCODE_V);
    add(Action::target_cycle, SDL_SCANCODE_TAB);
    add(Action::target_enemy, SDL_SCANCODE_Z);
    add(Action::attack_toggle, SDL_SCANCODE_R);
    add(Action::attack_toggle, SDL_SCANCODE_SPACE);
    add(Action::attack_toggle, SDL_SCANCODE_1);
    add(Action::chat, SDL_SCANCODE_RETURN);
    add(Action::cancel, SDL_SCANCODE_ESCAPE);
    return map;
  }
  // Press actions bound to this key under these modifiers, in table order. The
  // caller runs them until one accepts the press.
  std::vector<Action> pressed(SDL_Scancode key, uint32_t mods, bool text_focus) const {
    std::vector<Action> out;
    for (const auto &b : bindings)
      if (!b.mouse && b.key == key && !held(b.action) && b.accepts(mods) && (!text_focus || b.typing))
        out.push_back(b.action);
    return out;
  }
  // Actions bound to a mouse gesture under these modifiers, in table order.
  std::vector<Action> clicked(Gesture gesture, uint32_t mods) const {
    std::vector<Action> out;
    for (const auto &b : bindings)
      if (b.mouse == gesture && gesture != keyboard && b.accepts(mods)) out.push_back(b.action);
    return out;
  }
  bool down(Action action, const bool *state, uint32_t mods) const {
    for (const auto &b : bindings)
      if (!b.mouse && b.action == action && state[b.key] && b.accepts(mods)) return true;
    return false;
  }
  std::optional<SDL_Scancode> key(Action action) const {
    for (const auto &b : bindings)
      if (!b.mouse && b.action == action) return b.key;
    return std::nullopt;
  }
  static std::string name(SDL_Scancode k) {
    if (k == SDL_SCANCODE_RETURN) return "Enter";
    if (k == SDL_SCANCODE_KP_ENTER) return "Numpad Enter";
    if (k == SDL_SCANCODE_ESCAPE) return "Esc";
    for (size_t i = 0; i < key_codes.size(); ++i)
      if (key_codes[i] == k) return std::string(key_names[i]);
    return "";
  }
  // Player-facing name of the first key bound to an action ("" when unbound).
  std::string label(Action action) const {
    auto k = key(action);
    return k ? name(*k) : "";
  }
  // Player-facing name of a binding: the key, or the gesture with any required
  // modifiers ("Ctrl+Click", "Double-click").
  static std::string name(const Binding &b) {
    if (!b.mouse) return name(b.key);
    std::string prefix;
    for (size_t i = 0; i < modifier_names.size(); ++i)
      if (b.require & (1u << i)) prefix += std::string(i == 1 ? "Left Shift" : modifier_names[i]) + "+";
    return prefix + (b.mouse == left_click ? "Click" : "Double-click");
  }
  // Every key bound to an action, joined with '/' ("R/Space/1").
  std::string labels(Action action) const {
    std::vector<std::string> names;
    for (const auto &b : bindings)
      if (b.action == action && std::find(names.begin(), names.end(), name(b)) == names.end())
        names.push_back(name(b));
    std::string out;
    for (const auto &n : names) out += (out.empty() ? "" : "/") + n;
    return out;
  }
};
} // namespace n3e::input
