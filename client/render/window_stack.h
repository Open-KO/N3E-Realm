#pragma once
// Open order of the client's dialog windows, for the package's cancel action
// (PQ-010). KO client KnightOnLine.exe: the UI manager keeps its windows in a
// z-ordered list and showing a window moves it to the front and focuses it
// (00579260, called from the windows' SetVisible overrides such as 00495ce0).
// The key dispatcher (00648a40) gives a key press to the focused window only;
// HUD windows pass Esc on to the front-most focusable window (005445c0 ->
// 00579240 -> 00579470), and each dialog closes itself on Esc (004a64d0,
// inventory 004a3af0, skill tree 004ec550, character 0056f1b0, help 00554580,
// shop 004c5830, warehouse 004ad870). One press therefore closes one window,
// the most recently shown first. HUD windows (party list, state bar with its
// minimap) and the loot window never close on Esc.
#include <array>
#include <cstdint>
#include <optional>
#include <vector>
namespace n3e::windows {
// The engine's dialog windows that close on cancel.
enum class Window : uint8_t { inventory, character, skills, help, shop, warehouse };
inline constexpr size_t count = 6;
using Open = std::array<bool, count>;
struct Stack {
  std::vector<Window> order;  // back = front-most
  // Brings the stack in line with which windows are open now: closed windows
  // leave, newly opened ones go to the front. Several opened at once (n3e opens
  // the inventory with a shop) enter in enum order, so the later kind ends up
  // in front. KO probably never shows those two together: 00579260 hides
  // windows that share style bit 0x80 (fidelity gap, PQ-142).
  void sync(const Open &open) {
    std::vector<Window> kept;
    for (auto w : order)
      if (open[size_t(w)]) kept.push_back(w);
    order = std::move(kept);
    for (size_t i = 0; i < count; ++i)
      if (open[i] && !contains(Window(i))) order.push_back(Window(i));
  }
  bool contains(Window w) const {
    for (auto o : order)
      if (o == w) return true;
    return false;
  }
  std::optional<Window> top() const {
    if (order.empty()) return std::nullopt;
    return order.back();
  }
};
} // namespace n3e::windows
