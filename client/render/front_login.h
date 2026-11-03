#pragma once
// RQ-108 (N3FE version 12): which of the login screen's state-bound nodes draw
// (content/front-end.md, "Actions"). KO's login (1264's CUILogIn,
// specs/KO-FINDINGS.md §9.4) hides its copyright line at Load (005c1411) and
// shows it only through SetVisibleLogInUIs (005c2820): a login press hides the
// login group and shows the line until the login's answer; a failure shows the
// group again and hides the line, a success leaves both and opens the server
// list. RQ-110 (§9.5): 1298 hides its login group the same way (005f74c0) and
// has no line, so every layout hides its login group while a login waits; one
// without a login_closed node then shows neither. The realm's login is the
// Discord flow, so "a login waits" is the viewer's: from the press (held
// through the connection) or a stored session's login, through the browser
// step and the code, to the answer. RQ-123 (§9.12): after a select Back that
// lands on the realm list, 1264 shows its line neither while it connects nor
// on its list (BackHold, below).
// No GL; render/front_end.h draws by it, render/viewer.cpp holds a BackHold
// and tests/front_end.cpp checks both.
#include "assets/assets.h"

namespace n3e::front {

// Whether a node bound to `action` draws on the login screen in this state:
// `login` the login state (the bar), `realms` the realm list, `waiting` a
// login under way, `back` a Back's login and the realm list after it
// (BackHold::line_hidden), where 1264 never shows its line. Actions this rule
// does not name always draw.
inline bool login_state_shows(FrontAction action, bool login, bool realms, bool waiting, bool back) {
  switch (action) {
  case FrontAction::login_group: return login && !waiting;
  case FrontAction::realm_group: return realms;
  case FrontAction::login_closed: return !back && (realms || (login && waiting));
  default: return true;
  }
}

// RQ-112, RQ-123 (specs/KO-FINDINGS.md §9.12): the viewer's hold for a select
// Back that lands on the realm list (the package's select.back realms). 1298's
// and 1264's Back close the socket, make the login active and set its flag
// (1298 +0x21, stored at 00607447; 1264 +0x35, stored at 00445145), whose
// Init connects, asks for the server list (0xf5) and hides the login group
// alone (005f68e0; 005bd9b0), never calling 1264's SetVisibleLogInUIs
// (005c2820), so neither the bar nor 1264's copyright line shows from the
// click to the list, nor on it. The realm's Back logs in again with the
// stored session, as at start: the bar is held hidden from the click until the
// new connection's login flow has started (a session's login then keeps it
// hidden to the answer; with none, idle, the bar returns), and the line is
// hidden from the click, through that login, on the realm list, until the
// list is left. A connection that fails while the bar is held ends both (the
// viewer then shows connect_failed), as do a dropped or reset connection
// (reset) and a flow that leaves the session's login for anything but its
// answer (idle without a session or after a refusal, a logout, the browser).
class BackHold {
public:
  // What the viewer sees each frame.
  struct Frame {
    bool connected;  // the connection is up
    bool failed;     // it is down and no longer connecting
    bool started;    // the login flow has left its start (phase start)
    bool session;    // the flow is on the stored session's login or its answer (session, done)
    bool listed;     // the front end is on the login screen or the realm list
  };
  enum class Step { none, failed };
  // The select's Back: held when it lands on the realm list.
  void back(bool realms) { bar = line = realms; }
  // A dropped or reset connection: no Back under way.
  void reset() { bar = line = false; }
  // Each frame; `failed` when the connection failed while the bar was held.
  Step update(const Frame &f) {
    if (bar && f.failed) {
      reset();
      return Step::failed;
    }
    if (bar && f.connected && f.started) bar = false;
    if (line && ((f.started && !f.session) || !f.listed)) line = false;
    return Step::none;
  }
  // The login bar held hidden (the viewer's login_waiting).
  bool bar_hidden() const { return bar; }
  // The login_closed node hidden (FrontEnd::login_line_hidden).
  bool line_hidden() const { return line; }

private:
  bool bar = false, line = false;
};

}  // namespace n3e::front
