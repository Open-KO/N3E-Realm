#pragma once
// RQ-108 (N3FE version 12): which of the login screen's state-bound nodes draw
// (content/front-end.md, "Actions"). KO's login (1264's CUILogIn,
// specs/KO-FINDINGS.md §9.4) hides its copyright line at Load (005c1411) and
// shows it only through SetVisibleLogInUIs (005c2820): a login press hides the
// login group and shows the line until the login's answer; a failure shows the
// group again and hides the line, a success leaves both and opens the server
// list. The realm's login is the Discord flow, so "a login waits" is the
// viewer's: from the press (held through the connection) or a stored
// session's login, through the browser step and the code, to the answer.
// No GL; render/front_end.h draws by it and tests/front_end.cpp checks it.
#include "assets/assets.h"

namespace n3e::front {

// Whether a node bound to `action` draws on the login screen in this state:
// `login` the login state (the bar), `realms` the realm list, `waiting` a
// login under way, `closes` whether the layout has a node bound to
// login_closed. Only such a layout (the package's choice of 1264's behaviour)
// hides its login group while a login is under way; one without keeps the bar
// up, as before version 12. Actions this rule does not name always draw.
inline bool login_state_shows(FrontAction action, bool login, bool realms, bool waiting, bool closes) {
  switch (action) {
  case FrontAction::login_group: return login && !(waiting && closes);
  case FrontAction::realm_group: return realms;
  case FrontAction::login_closed: return realms || (login && waiting);
  default: return true;
  }
}

}  // namespace n3e::front
