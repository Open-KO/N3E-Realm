#pragma once
// PQ-407 (D-210): the HUD message line's log. 1298's message output window
// appends each message with its own colour (0052acd0), ignores an empty one,
// wraps it at '\n' and where the next character would pass the text area
// (0052af90, every wrapped line keeping the message's colour) and fills its rows
// from the top with consecutive wrapped lines (0052aa10, 0052b4c0).
//
// PQ-408 (D-211): with the package's scroll block the log keeps a history behind
// a scroll bar, as 1298's window does. 0052acd0 keeps at most `records` messages
// and drops wrapped lines past `lines`, oldest first, only while the track bar's
// position is above 0 and at most that many; the view follows the bottom when
// the position was at the maximum, else keeps its first line. The track bar
// (constructor 00410120) holds a range [0, max] and a position, set through
// 00410660 / 004106b0, which clamp; 00410700 places the thumb; 004107f0 drags
// it; 004103f0 pages; the scroll bar 0040d090 steps by its line size on a button
// click or repeat (00403c80: on release after a press, and on every pass once
// held for the repeat delay). Correction (D-211): a message dropped past the
// record limit takes its remaining wrapped lines with it.
//
// Without the scroll block the log keeps D-210's behaviour: the newest `rows`
// messages, of which the last `rows` wrapped lines are drawn. No GL here, so the
// unit check can drive it.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace n3e {
// A server refusal (D-209) or one of the client's own notices; the package
// gives each kind its colour. A post may carry its own colour instead, as
// 1298's callers pass one per message (PQ-469, D-235: a server-refused
// skill's line in the skill policy's colour).
enum class MessageKind : uint8_t { refusal, notice };

struct MessageLine {
  std::string text;
  uint32_t color = 0;
  bool operator==(const MessageLine &) const = default;
};

// The package's scroll-back (N3HS): the message records and wrapped lines kept,
// the scroll bar's line and page steps and the button's hold delay in seconds.
struct MessageHistory {
  uint32_t records = 1, lines = 1, line_step = 1, page_step = 1;
  float repeat = 0.5f;
};

// What the pointer is over or holds: the scroll bar's buttons or its track.
enum class MessagePart : uint8_t { none, up, down, track };

struct MessageLog {
  struct Post {
    std::string text;
    MessageKind kind;
    uint64_t serial;
    std::optional<uint32_t> color;  // the post's own colour, over its kind's
  };
  struct Wrapped {
    std::string text;
    MessageKind kind;
    uint64_t serial;  // the post it came from
    std::optional<uint32_t> color;
  };
  std::deque<Post> posts;      // newest last
  std::deque<Wrapped> wrapped;  // every kept post's lines, oldest first
  size_t rows = 1, columns = 0;
  uint64_t count = 0;  // messages accepted, so the same text again counts
  std::optional<MessageHistory> history;
  // The track bar: range [0, max] (min is always 0 here), position, and the
  // thumb's offset from the track's top, in HUD units. `ranged` is false until
  // the first range is set: 1298's track bar starts at 0 of 0-10, so its first
  // message does not follow the bottom.
  int max = 0, pos = 0;
  bool ranged = false;
  float track = 0, thumb_size = 0, thumb = 0;
  // The pointer: the button held since its press (and whether it is in its
  // down state, which a release turns into a step), the time it has been held,
  // and a thumb drag with the pointer's last offset in the track.
  MessagePart held = MessagePart::none;
  bool held_down = false, dragging = false, pressed_now = false;
  float hold = 0, last_y = 0;

  void set_rows(size_t n) {
    rows = n ? n : 1;
    if (!history)
      while (posts.size() > rows) drop_oldest();
    rewrap();
  }
  // The characters a row holds, as the drawing branch measures them. A new
  // count wraps the kept messages again and returns the view to the bottom.
  void set_columns(size_t n) {
    if (!n) n = 1;
    if (n == columns) return;
    columns = n;
    rewrap();
  }
  void scroll(MessageHistory h, float track_height, float thumb_height, float thumb_offset) {
    history = h;
    track = track_height;
    thumb_size = thumb_height;
    thumb = thumb_offset;
    rewrap();
  }
  void post(std::string text, MessageKind kind, std::optional<uint32_t> color = {}) {
    if (text.empty()) return;  // 0052acd0 returns for an empty text
    // 0052acd0 reads the track bar after its record drop, which leaves it alone.
    const bool follow = ranged && max == pos;
    int at = pos;
    posts.push_back({std::move(text), kind, ++count, color});
    const size_t limit = history ? history->records : rows;
    while (posts.size() > limit) at = std::max(0, at - int(drop_oldest()));
    if (columns) wrap(posts.back());
    if (!history) return;
    // 0052ae7f-0052af17: lines past the limit go only while the position read
    // before the message is above 0, one per line dropped.
    for (; wrapped.size() > history->lines && at > 0; --at) wrapped.pop_front();
    const int end = std::max(0, int(wrapped.size()) - int(rows));
    set_range(end);
    if (follow) at = end;
    set_pos(std::max(0, at));
  }
  // Scroll bar (0040d090): the up button steps back, the down button forward.
  void step(int lines) {
    if (history) set_pos(pos + lines);
  }
  // Track bar press outside the thumb (004103f0): a page back when at or above
  // the thumb's top, else a page forward.
  void page(bool forward) {
    if (history) set_pos(pos + (forward ? 1 : -1) * int(history->page_step));
  }
  // Thumb drag (004107f0): the thumb moves by the pointer's motion and the
  // position follows its fraction of the free track, truncated; past either end
  // the position is that end and the thumb stays where it was.
  void drag(float dy) {
    if (!history || track <= 0 || thumb_size <= 0 || track <= thumb_size) return;
    const float fraction = (thumb + dy) / (track - thumb_size);
    if (fraction > 1) pos = max;
    else if (fraction < 0) pos = 0;
    else {
      thumb += dy;
      pos = int(float(max) * fraction);
    }
  }
  // Pointer input. `y` is the pointer's offset from the track's top, in HUD
  // units. A press on a button holds it; on the track it starts a thumb drag
  // when inside the thumb, else pages.
  void press(MessagePart part, float y) {
    cancel();
    if (!history) return;
    if (part == MessagePart::up || part == MessagePart::down) {
      held = part;
      held_down = true;  // 00403c80: the down state on a press, hold time reset
      pressed_now = true;
    } else if (part == MessagePart::track) {
      if (y >= thumb && y < thumb + thumb_size) {
        dragging = true;
        last_y = y;
      } else
        page(y > thumb);
    }
  }
  void motion(MessagePart over, float y) {
    if (dragging) {
      // 004103f0: the drag ends once the pointer leaves the track.
      if (over != MessagePart::track) dragging = false;
      else {
        drag(y - last_y);
        last_y = y;
      }
    }
    if (held != MessagePart::none && over != held) held_down = false;
  }
  void release(MessagePart over) {
    if (held != MessagePart::none && over == held && held_down) step(direction());
    cancel();
  }
  // Every client frame: a held button over which the pointer stays repeats its
  // step on every frame once held for the delay (00403c80). The frame of the
  // press adds no time: 00403c80 handles the press instead of the hold there.
  void frame(MessagePart over, float dt) {
    if (std::exchange(pressed_now, false)) return;
    if (!history || held == MessagePart::none || over != held) return;
    hold += dt;
    if (hold >= history->repeat) {
      held_down = true;
      step(direction());
    }
  }
  void cancel() {
    held = MessagePart::none;
    held_down = dragging = pressed_now = false;
    hold = 0;
  }
  const std::string &newest() const {
    static const std::string none;
    return posts.empty() ? none : posts.back().text;
  }
  // The first line drawn: the position with a scroll bar (0052b4c0 clamps it
  // to the line count), else the last `rows` lines.
  size_t first() const {
    if (history) return std::min(size_t(std::max(0, pos)), wrapped.size());
    return wrapped.size() > rows ? wrapped.size() - rows : 0;
  }
  // The rows drawn, from the top: consecutive lines from first(), then empty
  // rows (0052b4c0 empties the rest).
  std::vector<MessageLine> lines(uint32_t refusal, uint32_t notice) const {
    std::vector<MessageLine> out;
    for (size_t i = first(); i < wrapped.size() && out.size() < rows; ++i)
      out.push_back({wrapped[i].text, wrapped[i].color.value_or(wrapped[i].kind == MessageKind::refusal ? refusal : notice)});
    while (out.size() < rows) out.push_back({{}, 0});
    return out;
  }

 private:
  int direction() const {
    return (held == MessagePart::up ? -1 : 1) * int(history ? history->line_step : 1);
  }
  // Drops the oldest message and the lines it wrapped to that are still kept
  // (the oldest lines); returns how many lines went.
  size_t drop_oldest() {
    const uint64_t serial = posts.front().serial;
    posts.pop_front();
    size_t dropped = 0;
    while (!wrapped.empty() && wrapped.front().serial == serial) {
      wrapped.pop_front();
      ++dropped;
    }
    return dropped;
  }
  void wrap(const Post &p) {
    std::string line;
    auto emit = [&] {
      wrapped.push_back({line, p.kind, p.serial, p.color});
      line.clear();
    };
    for (char c : p.text) {
      if (c == '\n') {
        emit();
        continue;
      }
      if (line.size() == columns) emit();
      line += c;
    }
    // 0052af90 ends with the rest of the text, if any: a closing '\n' adds no
    // empty line, while a leading or doubled one does.
    if (!line.empty()) emit();
  }
  void rewrap() {
    wrapped.clear();
    if (!columns) return;
    for (const auto &p : posts) wrap(p);
    if (!history || posts.empty()) return;
    while (wrapped.size() > history->lines) wrapped.pop_front();
    const int end = std::max(0, int(wrapped.size()) - int(rows));
    set_range(end);
    set_pos(end);
  }
  // 00410660: a new range clamps the position and places the thumb.
  void set_range(int end) {
    if (ranged && end == max) return;
    ranged = true;
    max = end;
    pos = std::clamp(pos, 0, max);
    place_thumb();
  }
  // 004106b0: a new position, clamped to the range, places the thumb.
  void set_pos(int at) {
    if (at == pos) return;
    pos = std::clamp(at, 0, max);
    place_thumb();
  }
  // 00410700: the thumb at position / range of the free track, truncated; an
  // empty range leaves it where it is.
  void place_thumb() {
    if (max == 0) return;
    thumb = std::trunc(float(pos) / float(max) * (track - thumb_size));
  }
};
}  // namespace n3e
