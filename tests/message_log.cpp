// PQ-407 (D-210): the HUD message line keeps a short log, each line in the colour
// the package gives its kind. Driven with the client's own log
// (client/render/message_log.h) and text layout (client/render/hud_text_layout.h):
// what is kept and dropped, how a message wraps (1298 0052af90: at '\n' and where
// the next character would pass the width, every wrapped line in the message's
// colour), which rows are drawn (0052b4c0: the last wrapped lines from the top,
// the rest empty), and that the drawn rows keep their row and colour in the
// record's layout ahead of the combat status.
#include "render/hud_text_layout.h"
#include "render/message_log.h"
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
namespace {
using namespace n3e;
void check(bool ok, const std::string &what) {
  if (!ok) throw std::runtime_error(what);
}
constexpr uint32_t RED = 0xffff0000, BLUE = 0xff0000ff;
std::vector<MessageLine> rows(std::initializer_list<std::pair<const char *, uint32_t>> want) {
  std::vector<MessageLine> out;
  for (auto [text, color] : want) out.push_back({text, color});
  return out;
}
}  // namespace
int main() {
  {
    // One row (a HUD without a message block, D-209's line): the newest wins
    // and an empty message changes nothing.
    MessageLog log;
    log.set_columns(40);
    check(log.lines(RED, BLUE) == rows({{"", 0}}), "empty log draws one empty row");
    log.post("chat length/rate", MessageKind::refusal);
    log.post("", MessageKind::notice);
    check(log.count == 1 && log.newest() == "chat length/rate", "an empty message is ignored");
    log.post("Select an enemy first", MessageKind::notice);
    check(log.posts.size() == 1 && log.count == 2, "one row keeps one message");
    check(log.lines(RED, BLUE) == rows({{"Select an enemy first", BLUE}}), "the newest notice, in the notice colour");
    log.post("Select an enemy first", MessageKind::notice);
    check(log.count == 3, "the same text again counts as new");
  }
  {
    // Three rows: filled from the top, the rest empty, then the oldest dropped.
    MessageLog log;
    log.set_rows(3);
    log.set_columns(10);
    log.post("one", MessageKind::refusal);
    check(log.lines(RED, BLUE) == rows({{"one", RED}, {"", 0}, {"", 0}}), "rows fill from the top");
    log.post("two", MessageKind::notice);
    log.post("three", MessageKind::refusal);
    log.post("four", MessageKind::notice);
    check(log.posts.size() == 3 && log.posts.front().text == "two", "the oldest message is dropped");
    check(log.lines(RED, BLUE) == rows({{"two", BLUE}, {"three", RED}, {"four", BLUE}}),
          "each row in its own kind's colour");
  }
  {
    // Wrapping: by character at the width, and at '\n'; a closing '\n' adds no
    // row, a leading or doubled one does; only the last wrapped lines show.
    MessageLog log;
    log.set_rows(4);
    log.set_columns(5);
    log.post("abcdefghijkl", MessageKind::refusal);
    check(log.lines(RED, BLUE) == rows({{"abcde", RED}, {"fghij", RED}, {"kl", RED}, {"", 0}}),
          "a long message wraps, every line in its colour");
    log.post("x\n", MessageKind::notice);
    check(log.lines(RED, BLUE) == rows({{"abcde", RED}, {"fghij", RED}, {"kl", RED}, {"x", BLUE}}),
          "a closing newline adds no row");
    log.post("\ny\n\nz", MessageKind::notice);
    check(log.lines(RED, BLUE) == rows({{"", BLUE}, {"y", BLUE}, {"", BLUE}, {"z", BLUE}}),
          "the last four wrapped lines");
    log.set_rows(2);
    check(log.posts.size() == 2 && log.lines(RED, BLUE) == rows({{"", BLUE}, {"z", BLUE}}), "fewer rows drop the oldest");
    log.set_rows(0);
    check(log.rows == 1, "at least one row");
  }
  {
    // PQ-469 (D-235): a post with its own colour (a server-refused skill's
    // line in the skill policy's colour, as 1298's 00586fa0 passes
    // 0xffff3b3b) draws every wrapped line in it, over its kind's, and keeps
    // it through a rewrap; posts without one keep their kind's.
    constexpr uint32_t FAILED = 0xffff3b3b;
    MessageLog log;
    log.set_rows(4);
    log.set_columns(8);
    log.post("Heal is too far", MessageKind::notice);
    log.post("Light Strike failed", MessageKind::refusal, FAILED);
    log.post("chat length/rate", MessageKind::refusal);
    check(log.lines(RED, BLUE) == rows({{"rike fai", FAILED}, {"led", FAILED}, {"chat len", RED}, {"gth/rate", RED}}),
          "the post's own colour on each of its lines");
    log.set_columns(20);
    check(log.lines(RED, BLUE) == rows({{"Heal is too far", BLUE}, {"Light Strike failed", FAILED}, {"chat length/rate", RED}, {"", 0}}),
          "the colour survives a rewrap");
  }
  {
    // The layout: the KO HUD's message area (text_message, 294 x 121) with the
    // substitute font's metrics. The wrapped rows hold no more than the layout
    // wraps by, so the rows keep their index and the status line its row.
    Hud h;
    h.font_advance = 7.203125f;
    h.font_height = 14;
    h.font_top = 5;
    HudRecord q;
    q.kind = 1;
    q.rect = {4, 1, 298, 122};
    q.binding = "combat";
    const size_t columns = hud_text_columns(h, q);
    check(columns == 40, "columns " + std::to_string(columns));
    MessageLog log;
    log.set_rows(5);
    log.set_columns(columns);
    log.post(std::string(columns, 'a') + std::string(columns, 'b') + "c", MessageKind::refusal);
    log.post("Select an enemy first", MessageKind::notice);
    auto drawn = log.lines(RED, BLUE);
    std::string text;
    for (const auto &line : drawn) text += line.text + "\n";
    text += "Idle 0\ntoken 0/20";
    std::vector<size_t> per_row(8);
    for (const auto &g : hud_text_layout(h, q, text)) {
      check(g.row < 8, "glyph row " + std::to_string(g.row));
      ++per_row[g.row];
      if (g.row < 5) check(g.y == 1 + 14 * g.row - 5, "a message row keeps its height");
    }
    check(per_row[0] == columns && per_row[1] == columns && per_row[2] == 1 && per_row[3] == 21 && per_row[4] == 0,
          "message rows as wrapped");
    check(per_row[5] == 6 && per_row[6] == 10, "the combat status and item rows follow the message rows");
    check(drawn[0].color == RED && drawn[2].color == RED && drawn[3].color == BLUE, "row colours");
  }
  // PQ-408 (D-211): the scroll-back. The demo HUD's limits (12 messages, 6
  // lines, steps 1 and 2, 0.5 s) on two rows of 10 characters, with the demo's
  // track (71 units) and thumb (14 units, at the track's top).
  auto scrolled = [] {
    MessageLog log;
    log.set_rows(2);
    log.set_columns(10);
    log.scroll({12, 6, 1, 2, 0.5f}, 71, 14, 0);
    return log;
  };
  auto texts = [](const MessageLog &log) {
    std::vector<std::string> out;
    for (const auto &l : log.lines(RED, BLUE)) out.push_back(l.text);
    return out;
  };
  using S = std::vector<std::string>;
  {
    // The first message is drawn from its first line (1298's track bar starts
    // at 0 of 0-10, so it does not follow); a short first message leaves the
    // view at its maximum, and later messages follow the bottom.
    auto log = scrolled();
    log.post("one", MessageKind::refusal);
    check(log.pos == 0 && log.max == 0 && texts(log) == S{"one", ""}, "first message");
    log.post("two", MessageKind::notice);
    log.post("three", MessageKind::notice);
    check(log.max == 1 && log.pos == 1 && texts(log) == S{"two", "three"}, "the view follows the bottom");
    check(log.thumb == 57, "the thumb at the end of the free track: " + std::to_string(log.thumb));
    auto tall = scrolled();
    tall.post("aaaaaaaaaabbbbbbbbbbcc", MessageKind::refusal);
    tall.post("next", MessageKind::notice);
    check(tall.pos == 0 && tall.max == 2 && texts(tall) == S{"aaaaaaaaaa", "bbbbbbbbbb"},
          "a first message taller than the rows stays at its top, and so does the view after it");
  }
  {
    // Steps, the follow rule, and dropping lines past 6 only above the view.
    auto log = scrolled();
    for (const char *t : {"l1", "l2", "l3", "l4", "l5", "l6"}) log.post(t, MessageKind::notice);
    check(log.wrapped.size() == 6 && log.pos == 4 && log.max == 4, "six lines, following");
    log.post("l7", MessageKind::notice);
    check(log.wrapped.size() == 6 && log.wrapped.front().text == "l2" && log.pos == 4 && texts(log) == S{"l6", "l7"},
          "following, the oldest line past the limit goes");
    log.step(-1);
    check(log.pos == 3 && texts(log) == S{"l5", "l6"} && log.thumb == std::trunc(3.f / 4.f * 57), "a step back");
    log.post("l8", MessageKind::notice);
    check(log.pos == 2 && log.max == 4 && log.wrapped.size() == 6 && texts(log) == S{"l5", "l6"},
          "off the bottom, a new line drops one above the view and the view keeps its lines");
    log.step(-5);
    check(log.pos == 0 && log.thumb == 0, "a step clamps at the first line");
    log.post("l9", MessageKind::notice);
    log.post("l10", MessageKind::notice);
    check(log.pos == 0 && log.wrapped.size() == 8 && log.max == 6 && texts(log) == S{"l3", "l4"},
          "at the first line no line is dropped (0052ae7f)");
    log.step(100);
    check(log.pos == 6 && texts(log) == S{"l9", "l10"} && log.thumb == 57, "a step clamps at the maximum");
    log.post("l11", MessageKind::notice);
    check(log.wrapped.size() == 6 && log.pos == 4 && texts(log) == S{"l10", "l11"},
          "back at the bottom it follows, and the lines past the limit go");
  }
  {
    // The correction: at the first line, messages past the record limit take
    // their lines with them, so the history stays bounded.
    auto log = scrolled();
    log.post("aaaaaaaaaabbbbbbbbbbcc", MessageKind::refusal);  // three lines, at its top
    for (int i = 0; i < 11; ++i) log.post("m" + std::to_string(i), MessageKind::notice);
    check(log.posts.size() == 12 && log.wrapped.size() == 14 && log.pos == 0 && texts(log) == S{"aaaaaaaaaa", "bbbbbbbbbb"},
          "twelve messages, fourteen lines, the view at the top");
    log.post("m11", MessageKind::notice);
    check(log.posts.size() == 12 && log.wrapped.size() == 12 && log.pos == 0 && texts(log) == S{"m0", "m1"},
          "the oldest message leaves with its three lines");
    for (int i = 12; i < 100; ++i) log.post("m" + std::to_string(i), MessageKind::notice);
    check(log.posts.size() == 12 && log.wrapped.size() == 12 && texts(log) == S{"m88", "m89"},
          "the history stays at the record limit");
    // Off the bottom with the view inside the oldest message's lines: the view
    // moves up with them.
    auto mid = scrolled();
    for (int i = 0; i < 3; ++i) mid.post("n" + std::to_string(i), MessageKind::notice);
    mid.step(-1);
    for (int i = 3; i < 12; ++i) mid.post("n" + std::to_string(i), MessageKind::notice);
    mid.step(1);
    check(mid.pos == 1 && mid.wrapped.size() == 12 && texts(mid) == S{"n1", "n2"}, "one line down from the top");
    mid.post("n12", MessageKind::notice);
    check(mid.pos == 0 && texts(mid) == S{"n1", "n2"} && mid.wrapped.size() == 12,
          "the dropped message's line was above the view, which keeps its lines");
    mid.post("n13", MessageKind::notice);
    check(mid.pos == 0 && texts(mid) == S{"n2", "n3"} && mid.wrapped.size() == 12,
          "the view's first line left with its message: the view shows the oldest kept line");
  }
  {
    // The track: a press above or below the thumb pages; in the thumb it drags.
    auto log = scrolled();
    for (int i = 0; i < 6; ++i) log.post("p" + std::to_string(i), MessageKind::notice);
    log.step(-4);
    check(log.pos == 0 && log.thumb == 0, "at the top");
    log.press(MessagePart::track, 60);
    log.release(MessagePart::track);
    check(log.pos == 2 && log.thumb == std::trunc(2.f / 4.f * 57), "a press below the thumb pages forward");
    log.press(MessagePart::track, 1);
    check(log.pos == 0, "a press above the thumb pages back");
    log.press(MessagePart::track, 5);  // inside the thumb (0-14)
    check(log.dragging, "a press in the thumb drags it");
    log.motion(MessagePart::track, 25);  // 20 units down: 20 / 57 of the range
    check(log.thumb == 20 && log.pos == int(4.f * (20.f / 57.f)) && texts(log) == S{"p1", "p2"}, "the drag moves the view");
    log.motion(MessagePart::track, 80);  // past the end: the position is the end, the thumb stays
    check(log.pos == 4 && log.thumb == 20, "past the end the position is the maximum");
    log.motion(MessagePart::none, 30);
    check(!log.dragging, "the drag ends when the pointer leaves the track");
    log.motion(MessagePart::track, 10);
    check(log.pos == 4, "and does not resume");
  }
  {
    // The buttons: a step on release after a press on the button; none when the
    // pointer left it; a hold repeats on every frame after 0.5 s.
    auto log = scrolled();
    for (int i = 0; i < 12; ++i) log.post("b" + std::to_string(i), MessageKind::notice);
    check(log.pos == 4, "six lines kept");
    log.press(MessagePart::up, 0);
    check(log.pos == 4, "a press alone does not step");
    log.release(MessagePart::up);
    check(log.pos == 3, "the release steps back");
    log.press(MessagePart::up, 0);
    log.motion(MessagePart::none, 0);
    log.release(MessagePart::up);
    check(log.pos == 3, "no step once the pointer left the button");
    log.press(MessagePart::down, 0);
    log.frame(MessagePart::down, 1.f);
    check(log.pos == 3, "the press's own frame adds no hold time");
    log.frame(MessagePart::down, 0.3f);
    check(log.pos == 3, "not yet repeating");
    log.frame(MessagePart::down, 0.3f);
    check(log.pos == 4, "repeats once held 0.5 s");
    log.frame(MessagePart::none, 0.3f);
    check(log.pos == 4, "not while the pointer is off the button");
    log.press(MessagePart::up, 0);
    log.frame(MessagePart::up, 0.f);
    log.frame(MessagePart::up, 0.6f);
    log.frame(MessagePart::up, 0.01f);
    log.frame(MessagePart::up, 0.01f);
    check(log.pos == 1, "a step on every frame while held");
    log.release(MessagePart::up);
    check(log.pos == 0 && log.held == MessagePart::none, "and one more on release");
    log.post("b12", MessageKind::notice);
    check(log.pos == 0, "off the bottom the view stays");
    log.set_columns(20);
    check(log.pos == log.max && texts(log).back() == "b12", "a new width wraps again and returns to the bottom");
  }
  std::cout << "PASS client message scroll-back: the first line follows 1298's start, the view follows the bottom only "
               "from the maximum, lines past the limit go only above the view (0052acd0), a message dropped past the "
               "record limit takes its lines (D-211), steps, pages and thumb drags clamp and place the thumb as the "
               "track bar does, and a held button repeats after its delay\n";
  std::cout << "PASS client message line: the log keeps the newest messages up to its rows, ignores an empty one, "
               "wraps at the width and at newlines as 0052af90 does, draws the last wrapped lines from the top in "
               "their kind's colour and keeps the combat status on the row after them\n";
}
