#pragma once
// Package input map vocabulary (PQ-009, D-136). SDL-free so the release loader
// can validate a package's table; client/render/input_map.h maps the key names
// to SDL scancodes. tools/assetc/input_map.py keeps the same lists, and
// tests/input_map.py checks that the two agree.
#include <array>
#include <cstdint>
#include <optional>
#include <string_view>
namespace n3e::input {
enum class Action : uint8_t {
  hotbar_use_1, hotbar_use_2, hotbar_use_3, hotbar_use_4,
  hotbar_use_5, hotbar_use_6, hotbar_use_7, hotbar_use_8,
  hotbar_page_1, hotbar_page_2, hotbar_page_3, hotbar_page_4,
  hotbar_page_5, hotbar_page_6, hotbar_page_7, hotbar_page_8,
  hotbar_page_prev, hotbar_page_next,
  move_forward, move_backward, turn_left, turn_right, turbo,
  camera_pitch_up, camera_pitch_down,
  auto_move, run_toggle, attack_toggle,
  target_enemy, target_party, target_npc, target_cycle,
  rest_toggle, inventory, character, skills, minimap, help, chat, respawn,
  loot_nearest, window_page_prev, window_page_next,
  command_list, names_toggle, camera_mode, hide_hud, chat_size, message_size,
  screenshot, cancel, attack_pick, attack_target,
};
inline constexpr std::array<std::string_view, 53> action_names{
  "hotbar_use_1", "hotbar_use_2", "hotbar_use_3", "hotbar_use_4",
  "hotbar_use_5", "hotbar_use_6", "hotbar_use_7", "hotbar_use_8",
  "hotbar_page_1", "hotbar_page_2", "hotbar_page_3", "hotbar_page_4",
  "hotbar_page_5", "hotbar_page_6", "hotbar_page_7", "hotbar_page_8",
  "hotbar_page_prev", "hotbar_page_next",
  "move_forward", "move_backward", "turn_left", "turn_right", "turbo",
  "camera_pitch_up", "camera_pitch_down",
  "auto_move", "run_toggle", "attack_toggle",
  "target_enemy", "target_party", "target_npc", "target_cycle",
  "rest_toggle", "inventory", "character", "skills", "minimap", "help", "chat", "respawn",
  "loot_nearest", "window_page_prev", "window_page_next",
  "command_list", "names_toggle", "camera_mode", "hide_hud", "chat_size", "message_size",
  "screenshot", "cancel", "attack_pick", "attack_target",
};
static_assert(action_names.size() == size_t(Action::attack_target) + 1);
// Held actions are read from the key state every frame; every other action
// fires once per key press. The camera pitch keys (PQ-012) are held too.
constexpr bool held(Action a) { return a >= Action::move_forward && a <= Action::camera_pitch_down; }
// Physical key positions a package may name. F11, F12 and Grave are listed so a
// table that names them gets a precise refusal (reserved, below). The last two
// are mouse gestures (PQ-011): a left press in the world, and a left release
// that completes a double click (mouse_keys below).
inline constexpr std::array<std::string_view, 78> key_names{
  "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
  "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
  "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
  "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
  "Up", "Down", "Left", "Right", "PageUp", "PageDown", "Home", "End", "Insert", "Delete",
  "Return", "KeypadEnter", "KeypadMinus", "KeypadPlus", "Space", "Tab",
  "LeftBracket", "RightBracket", "Minus", "Equals", "Comma", "Period", "Slash",
  "Semicolon", "Apostrophe", "Backslash", "Grave", "Escape",
  "MouseLeft", "MouseLeftDouble",
};
constexpr bool complete(const auto &list) {
  for (auto name : list)
    if (name.empty()) return false;
  return true;
}
static_assert(complete(action_names) && complete(key_names));
// Engine-reserved keys (D-136): reconnect, tools editor, tools terminal. They
// stay outside the KO key range and no package may bind them.
inline constexpr std::array<std::string_view, 3> reserved_keys{"F12", "F11", "Grave"};
// Modifier bits for a binding's required and forbidden sets.
enum : uint32_t { shift = 1, left_shift = 2, ctrl = 4, alt = 8, all_modifiers = 15 };
inline constexpr std::array<std::string_view, 4> modifier_names{"Shift", "LeftShift", "Ctrl", "Alt"};
// Binding flags: typing = also fires while a text field has focus.
enum : uint32_t { typing = 1, all_flags = 1 };
inline constexpr uint32_t max_bindings = 128;
template <size_t N>
constexpr std::optional<size_t> find(const std::array<std::string_view, N> &list, std::string_view name) {
  for (size_t i = 0; i < N; ++i)
    if (list[i] == name) return i;
  return std::nullopt;
}
constexpr bool reserved(std::string_view key) { return find(reserved_keys, key).has_value(); }
// Mouse gestures (PQ-011). They bind press actions only and never take the
// typing flag: they fire from clicks in the world, which need gameplay focus.
inline constexpr std::array<std::string_view, 2> mouse_keys{"MouseLeft", "MouseLeftDouble"};
constexpr bool mouse(std::string_view key) { return find(mouse_keys, key).has_value(); }
} // namespace n3e::input
