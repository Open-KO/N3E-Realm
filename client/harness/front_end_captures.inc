// Test-only fragment (PQ-006): included into viewer() by the test client
// (n3e-test-client, N3E_HARNESS=1) only; see client/harness/harness.h.
// Spec 11 acceptance 6: N3E_TEST_FRONT_END=PREFIX draws each KO screen at rest
// in the window (--fixed-window), writes PREFIX.<shot>.ppm and prints, per
// shot, the characters drawn (pixel boxes, y down), one bound node's rect and
// (RQ-106) where the canvas's (0, 0) is as the screen's root carries it, and
// the scale (1: KO's placement on the window's own pixels):
//   FRONT_SHOT name=N size=WxH path=P rect=x0,y0,x1,y1 drawn=intro|hall|create:x0,y0,x1,y1;... origin=X,Y,S
// then the select's buttons where the select placed them (RQ-106):
//   FRONT_PLACED select_prev=x0,y0,x1,y1 select_next=... back=... exit=...
// then (RQ-113) whether prev and next draw at rest with the row's left end in
// focus and with its right end (the package's select.arrows), each 0 or 1:
//   FRONT_ARROWS left=P,N right=P,N
// then (RQ-109), for a select that binds 1298's bar (front-end-1298.json), its
// other buttons and its info texts where the select placed them, and a select
// of no character (the shot select-0, its info texts empty):
//   FRONT_SELECT_BAR select_start=x0,y0,x1,y1 select_create=... select_delete=...
//     char_name=... char_level=... char_class=...
// then (RQ-108) whether the login layout's login group, realm group and
// login_closed node draw at rest, with a login under way and on the realm
// list, each 0 or 1, and (RQ-123) the same with a login under way and on the
// realm list after a Back that lands there (the line hidden, BackHold):
//   FRONT_LOGIN idle=G,R,C waiting=G,R,C realms=G,R,C back=G,R,C back_realms=G,R,C
// (the shot login-waiting is the login with a login under way, rect= the
// login_closed node's).
// then (RQ-111) the select's exit: whether a click on it asks (a package that
// names exit_confirm: 1298's yes/no box) or leaves at once, and, when it asks,
// which of the box's OK, Yes and No draw in that box and in an OK box, and what
// each answer does (closed or open, and the command: none or exit): ESC,
// ENTER, the keypad's ENTER, a click on No, on Yes and on the hidden OK:
//   FRONT_EXIT asks=0 command=exit
//   FRONT_EXIT asks=1 shown=O,Y,N plain=O,Y,N esc=closed:none enter=closed:exit
//     keypad=... no=... yes=... ok=open:none
// and (RQ-116) what ESC on the select at rest does, appended to that line:
// select_esc=asks|back|exit|none
// and (RQ-121) whether ENTER on one character starts it, and what ESC and a
// click on Exit do while its start clip plays:
// started=0|1 start_esc=asks|back|exit|none start_exit=asks|back|exit|none
// and (RQ-112) what a click on Back at rest does and where the package says
// it lands: back=asks|back|exit|none:login|realms
// (the shot message-exit is the select with that box, rect= Yes's);
// then (RQ-114), for a select that binds btn_create, a click on it from an
// occupied slot (the block's own comment below):
//   FRONT_CREATE click=select path=P frames=F ui=0 slot=1 focus=2 arrived=create draws=N back=select slot=2
//   FRONT_CREATE click=create back=select slot=S
// (the second without a fly), or (RQ-125) for a create over the hall:
//   FRONT_CREATE click=create path=P frames=F slot=1 focus=2 new=0 arrived=2 draws=N new=1 back=select slot=2
//     cancel=select slot=2 ui=1
// (on one line);
// then the screens' music (FRONT_MUSIC, below), and exits. RQ-101: the logo
// screen's shots are logo-<group> at a time in each group's hold and
// logo-fade half way into the first group's fade-in, with rect= the logo
// layout's canvas (its pixel rect) and drawn= empty; then
//   FRONT_LOGO groups=G length=L skip=0|1 cursor=0|1 alpha=A0,A1,... before=logo|login end=logo|login
// (L the screen's seconds; A the alpha of each shot in order; before the
// screen on a frame 0.1 s before its end, end the screen after a frame that
// runs it 0.1 s past it).
// tests/front_end_live.py checks the frames and the music. No server.
if (const char *prefix = std::getenv("N3E_TEST_FRONT_END")) {
  if (!front) throw std::runtime_error("N3E_TEST_FRONT_END needs front-end.bin and a Discord realm");
  int width, height;
  SDL_GetWindowSizeInPixels(w, &width, &height);
  n3e::Characters list;
  using Screen = n3e::front::Screen;
  auto shot = [&](const std::string &name, Screen screen, int characters, const std::string &realm, float progress,
                  n3e::FrontAction bound, const std::string &message, double logo = -1,
                  n3e::FrontMessage kind = n3e::FrontMessage::disconnected, bool waiting = false) {
    SDL_PumpEvents();
    list.Clear();
    for (int i = 0; i < characters; ++i) {
      auto *c = list.add_characters();
      c->set_id(i + 1);
      c->set_name("Shot" + std::to_string(i + 1));
      c->set_level(10 * (i + 1));
    }
    front->jump(screen);
    front->login_waiting(waiting);
    if (logo >= 0) front->logo_at(logo);
    if (!message.empty()) front->show_message(kind, message);
    const n3e::front::Context context{realm, "ENTER - Log in with Discord", release.version, &list, progress};
    front->draw(width, height, 1.0, context);
    front->draw(width, height, 1.0, context);
    const std::string path = std::string(prefix) + "." + name + ".ppm";
    capture(path, width, height);
    std::cout << "FRONT_SHOT name=" << name << " size=" << width << "x" << height << " path=" << path << " rect=";
    const auto origin = front->layout_origin(width, height);
    if (logo >= 0) {
      const float s = origin[2];
      std::cout << int(origin[0]) << "," << int(origin[1]) << "," << int(origin[0] + 1024 * s) << ","
                << int(origin[1] + 768 * s);
    } else if (auto r = front->action_rect(bound, width, height))
      std::cout << int((*r)[0]) << "," << int((*r)[1]) << "," << int((*r)[2]) << "," << int((*r)[3]);
    std::cout << " drawn=";
    const char *sep = "";
    for (const auto &d : front->drawn()) {
      const auto &b = d.box;
      const auto &v = d.viewport;
      static const char *kinds[] = {"intro", "hall", "create"};
      std::cout << sep << kinds[d.which] << ":" << int(v[0] + (b[0] + 1) / 2 * v[2]) << ","
                << int(height - v[1] - (b[3] + 1) / 2 * v[3]) << "," << int(v[0] + (b[2] + 1) / 2 * v[2]) << ","
                << int(height - v[1] - (b[1] + 1) / 2 * v[3]);
      sep = ";";
    }
    std::cout << " origin=" << origin[0] << "," << origin[1] << "," << origin[2] << std::endl;
    SDL_GL_SwapWindow(w);
  };
  using A = n3e::FrontAction;
  shot("login", Screen::login, 0, "Local Realm", 0, A::login, "");
  // RQ-108: a login under way: KO's copyright line instead of the login bar.
  shot("login-waiting", Screen::login, 0, "Local Realm", 0, A::login_closed, "", -1,
       n3e::FrontMessage::disconnected, true);
  shot("realms", Screen::realms, 0, "Local Realm", 0, A::realm_list, "");
  shot("realms-unnamed", Screen::realms, 0, "", 0, A::realm_list, "");
  for (int n = 1; n <= 3; ++n) shot("select-" + std::to_string(n), Screen::select, n, "Local Realm", 0, A::char_info, "");
  front->jump(Screen::select);
  std::cout << "FRONT_PLACED";
  for (const auto &[label, action] : {std::pair{"select_prev", A::select_prev}, std::pair{"select_next", A::select_next},
                                      std::pair{"back", A::back}, std::pair{"exit", A::exit}}) {
    const auto r = front->action_rect(action, width, height);
    std::cout << " " << label << "=";
    if (r) std::cout << int((*r)[0]) << "," << int((*r)[1]) << "," << int((*r)[2]) << "," << int((*r)[3]);
  }
  std::cout << std::endl;
  // RQ-113 (KO-FINDINGS 9.6, 9.13): whether prev and next draw with the
  // left end of the row in focus and with the right end, each 0 or 1.
  std::cout << "FRONT_ARROWS";
  for (const auto &[label, at] : {std::pair{"left", 0}, std::pair{"right", 2}}) {
    front->select_at(at);
    std::cout << " " << label << "=" << front->action_shown(A::select_prev) << ","
              << front->action_shown(A::select_next);
  }
  std::cout << std::endl;
  front->jump(Screen::select);
  if (front->action_rect(A::char_name, width, height)) {
    std::cout << "FRONT_SELECT_BAR";
    for (const auto &[label, action] :
         {std::pair{"select_start", A::select_start}, std::pair{"select_create", A::select_create},
          std::pair{"select_delete", A::select_delete}, std::pair{"char_name", A::char_name},
          std::pair{"char_level", A::char_level}, std::pair{"char_class", A::char_class}}) {
      const auto r = front->action_rect(action, width, height);
      std::cout << " " << label << "=";
      if (r) std::cout << int((*r)[0]) << "," << int((*r)[1]) << "," << int((*r)[2]) << "," << int((*r)[3]);
    }
    std::cout << std::endl;
    shot("select-0", Screen::select, 0, "Local Realm", 0, A::char_name, "");
  }
  std::cout << "FRONT_LOGIN";
  for (const auto &[label, screen, waiting, back] :
       {std::tuple{"idle", Screen::login, false, false}, std::tuple{"waiting", Screen::login, true, false},
        std::tuple{"realms", Screen::realms, false, false}, std::tuple{"back", Screen::login, true, true},
        std::tuple{"back_realms", Screen::realms, true, true}}) {
    front->jump(screen);
    front->login_waiting(waiting);
    front->login_line_hidden(back);
    std::cout << " " << label << "=" << front->action_shown(A::login_group) << ","
              << front->action_shown(A::realm_group) << "," << front->action_shown(A::login_closed);
  }
  std::cout << std::endl;
  shot("create", Screen::create, 0, "Local Realm", 0, A::name_field, "");
  shot("loading-start", Screen::loading, 1, "Local Realm", 2 / 3.f, A::progress, "");
  shot("loading-world", Screen::loading, 1, "Local Realm", 1, A::progress, "");
  shot("message", Screen::login, 0, "Local Realm", 0, A::message, "Disconnected from server");
  // RQ-102 (Q81): the same text as a refused create, which the package titles;
  // the rect is the title's.
  shot("message-titled", Screen::login, 0, "Local Realm", 0, A::title, "Disconnected from server", -1,
       n3e::FrontMessage::create_refused);
  {
    // RQ-111 (KO-FINDINGS 9.7): the select's exit, clicked and answered as a
    // player does, through the screens' own input.
    auto click = [&](n3e::FrontAction action) {
      n3e::front::Output out;
      const auto r = front->action_rect(action, width, height);
      if (!r) return out;
      const float x = ((*r)[0] + (*r)[2]) / 2, y = ((*r)[1] + (*r)[3]) / 2;
      SDL_Event e{};
      e.type = SDL_EVENT_MOUSE_MOTION;
      front->event(e, x, y, width, height);
      e = {};
      e.type = SDL_EVENT_MOUSE_BUTTON_DOWN;
      e.button.button = SDL_BUTTON_LEFT;
      e.button.clicks = 1;
      front->event(e, x, y, width, height);
      e.type = SDL_EVENT_MOUSE_BUTTON_UP;
      return front->event(e, x, y, width, height);
    };
    auto key = [&](SDL_Keycode k) {
      SDL_Event e{};
      e.type = SDL_EVENT_KEY_DOWN;
      e.key.key = k;
      return front->event(e, 0, 0, width, height);
    };
    auto asks = [&] {
      front->jump(Screen::select);
      const auto out = click(A::exit);
      return std::pair{front->message_kind() == n3e::FrontMessage::exit_confirm, out};
    };
    auto shown = [&] {
      return std::to_string(front->action_shown(A::ok)) + "," + std::to_string(front->action_shown(A::yes)) + "," +
             std::to_string(front->action_shown(A::no));
    };
    const auto [asked, first] = asks();
    std::cout << "FRONT_EXIT asks=" << asked;
    if (!asked) std::cout << " command=" << (first.command == n3e::front::Command::exit ? "exit" : "none");
    else {
      std::cout << " shown=" << shown();
      front->jump(Screen::select);
      front->show_message(n3e::FrontMessage::disconnected, "Disconnected from server");
      std::cout << " plain=" << shown();
      auto answer = [&](const char *label, auto press) {
        asks();
        const auto out = press();
        std::cout << " " << label << "=" << (front->showing_message() ? "open" : "closed") << ":"
                  << (out.command == n3e::front::Command::exit ? "exit" : out.command == n3e::front::Command::none
                                                                             ? "none"
                                                                             : "other");
      };
      answer("esc", [&] { return key(SDLK_ESCAPE); });
      answer("enter", [&] { return key(SDLK_RETURN); });
      answer("keypad", [&] { return key(SDLK_KP_ENTER); });
      answer("no", [&] { return click(A::no); });
      answer("yes", [&] { return click(A::yes); });
      answer("ok", [&] { return click(A::ok); });
    }
    // RQ-116: ESC on the select at rest: asks (the exit question, 1264's
    // OnKeyPress 004454e0 pressing bt_exit), back, exit or none.
    auto did = [&](const n3e::front::Output &out) {
      return front->message_kind() == n3e::FrontMessage::exit_confirm ? "asks"
             : out.command == n3e::front::Command::back               ? "back"
             : out.command == n3e::front::Command::exit               ? "exit"
                                                                      : "none";
    };
    front->jump(Screen::select);
    std::cout << " select_esc=" << did(key(SDLK_ESCAPE));
    // RQ-121 (KO-FINDINGS 9.10): with one character, ENTER starts it
    // (started=1: the select request), then ESC and a click on Exit while its
    // start clip plays: none, as 1264's and 1097's select take no input then.
    list.Clear();
    list.add_characters()->set_id(1);
    front->jump(Screen::select);
    const bool started = key(SDLK_RETURN).command == n3e::front::Command::select;
    std::cout << " started=" << started << " start_esc=" << did(key(SDLK_ESCAPE));
    std::cout << " start_exit=" << did(click(A::exit));
    list.Clear();
    front->jump(Screen::select);
    // RQ-112 (KO-FINDINGS 9.12): a click on Back at rest, and where the
    // package says it lands: login, or realms (1298's and 1264's, through a login held
    // with the bar hidden from the click).
    std::cout << " back=" << did(click(A::back)) << ":"
              << (front->back_lands() == n3e::FrontSelectBack::realms ? "realms" : "login");
    front->jump(Screen::select);
    std::cout << std::endl;
    // RQ-114 (KO-FINDINGS 9.6): for a select that binds btn_create, a click on
    // it with slots 0 and 1 taken and slot 1, the row's left end, in focus;
    // the screen right after; in the path mode, after a frame, the path
    // playing (its index in the package), its last frame, whether the select
    // UI shows and the slot the camera is at and the one in focus; then
    // ENTER and ESC, and frames 0.25 s apart until the screen is no longer
    // the select (at most 60): the screen and how many frames that took
    // since the click; then ESC on create and a frame: the camera's slot.
    if (front->action_rect(A::select_create, width, height)) {
      list.Clear();
      for (int i = 0; i < 2; ++i) list.add_characters()->set_id(i + 1);
      const n3e::front::Context flight{"Local Realm", "", release.version, &list, 0};
      double t = 100;
      front->select_at(0);
      front->draw(width, height, t, flight);
      click(A::select_create);
      const auto shown_screen = [&] {
        return front->screen() == Screen::create ? "create" : front->screen() == Screen::select ? "select" : "other";
      };
      std::cout << "FRONT_CREATE click=" << shown_screen();
      // RQ-125 (version 19): over the hall create opens with the click and
      // the camera flies behind it: after a frame the path and its last frame,
      // the slot the camera is at and the one in focus, and whether the new
      // character stands in the hall (new=0 while the camera flies); then
      // frames 0.25 s apart until the camera is on the slot (at most 60): the
      // slot, how many frames that took since the click, and new=1 there.
      const auto stands = [&] {
        for (const auto &d : front->drawn())
          if (d.which == 2) return 1;
        return 0;
      };
      const bool over_hall = front->screen() == Screen::create && front->create_over_hall();
      bool flew = false;
      if (over_hall) {
        front->draw(width, height, t += .25, flight);
        const auto turn = front->front_turn();
        std::cout << " path=" << turn.path << " frames=" << turn.frames << " slot=" << turn.slot
                  << " focus=" << turn.focus << " new=" << stands();
        flew = turn.slot != turn.focus;
        int frames = 1;
        while (front->front_turn().slot != front->front_turn().focus && frames < 60)
          front->draw(width, height, t += .25, flight), ++frames;
        if (flew) std::cout << " arrived=" << front->front_turn().slot << " draws=" << frames << " new=" << stands();
      }
      if (front->screen() == Screen::select) {
        front->draw(width, height, t += .25, flight);
        const auto turn = front->front_turn();
        std::cout << " path=" << turn.path << " frames=" << turn.frames << " ui=" << turn.ui << " slot=" << turn.slot
                  << " focus=" << turn.focus;
        key(SDLK_RETURN);
        key(SDLK_ESCAPE);
        int frames = 1;
        while (front->screen() == Screen::select && frames < 60) front->draw(width, height, t += .25, flight), ++frames;
        std::cout << " arrived=" << shown_screen() << " draws=" << frames;
      }
      if (front->screen() == Screen::create) {
        key(SDLK_ESCAPE);
        front->draw(width, height, t += .25, flight);
        std::cout << " back=" << shown_screen() << " slot=" << front->front_turn().slot;
      }
      // RQ-125: over the hall, ESC one frame into the flight: the select at
      // rest on the slot the camera flew to, its UI shown (1298's Cancel,
      // 005ffb90, sets state 5 and shows the bar at once).
      if (flew) {
        front->select_at(0);
        front->draw(width, height, t += .25, flight);
        click(A::select_create);
        front->draw(width, height, t += .25, flight);
        key(SDLK_ESCAPE);
        front->draw(width, height, t += .25, flight);
        std::cout << " cancel=" << shown_screen() << " slot=" << front->front_turn().slot
                  << " ui=" << front->front_turn().ui;
      }
      std::cout << std::endl;
      list.Clear();
      front->jump(Screen::select);
    }
    if (asked)
      shot("message-exit", Screen::select, 1, "Local Realm", 0, A::yes, "Exit the game?", -1,
           n3e::FrontMessage::exit_confirm);
  }
  if (const auto &logo = front->logo()) {
    // RQ-101: each group in its hold, and the first half way into its fade-in.
    std::string alphas;
    auto logo_shot = [&](const std::string &name, double t) {
      shot(name, Screen::logo, 0, "Local Realm", 0, A::none, "", t);
      alphas += (alphas.empty() ? "" : ",") + std::to_string(front->logo_shown().alpha);
    };
    for (size_t g = 0; g < logo->groups.size(); ++g)
      logo_shot("logo-" + std::to_string(g),
                n3e::front::logo_group_start(*logo, g) + logo->groups[g].fade_in + logo->groups[g].hold / 2);
    logo_shot("logo-fade", logo->groups[0].fade_in / 2);
    const double length = n3e::front::logo_length(*logo);
    front->logo_at(length - .1);
    const n3e::front::Context context{"Local Realm", "", release.version, &list, 0};
    front->draw(width, height, 1.0, context);
    const bool before = front->screen() == Screen::logo;
    front->draw(width, height, 1.2, context);
    std::cout << "FRONT_LOGO groups=" << logo->groups.size() << " length=" << length
              << " skip=" << bool(logo->flags & n3e::FrontLogo::SKIP_KEY)
              << " cursor=" << bool(logo->flags & n3e::FrontLogo::HIDE_CURSOR) << " alpha=" << alphas
              << " before=" << (before ? "logo" : "login")
              << " end=" << (front->screen() == Screen::login ? "login" : "logo") << std::endl;
  }
  // RQ-018 (Q57): each screen's track (its index among the tracks the
  // screens name, or none), then each of those tracks streamed one second
  // past its end (RQ-083: a PCM track's pass is its sample frames; a track
  // with a restart period restarts on it):
  //   FRONT_MUSIC login=0 realms=0 select=1 create=1 loading=none
  //   FRONT_MUSIC_STREAM track=K kind=mpeg|pcm rate=R channels=C frames=F loop=0|1 restart=S
  //     decoded=D restarts=N peak=P audible=A ended=0|1
  std::vector<std::shared_ptr<const n3e::MusicTrack>> tracks;
  std::cout << "FRONT_MUSIC";
  for (const auto &[label, screen] : {std::pair{"login", Screen::login}, std::pair{"realms", Screen::realms},
                                      std::pair{"select", Screen::select}, std::pair{"create", Screen::create},
                                      std::pair{"loading", Screen::loading}}) {
    front->jump(screen);
    const auto track = front->music();
    auto at = std::find(tracks.begin(), tracks.end(), track);
    if (track && at == tracks.end()) at = tracks.insert(tracks.end(), track);
    std::cout << " " << label << "=" << (track ? std::to_string(at - tracks.begin()) : std::string("none"));
  }
  // RQ-101: the logo screen's track once its delay has run, with its delay
  // and the group its fade-out starts with:
  //   FRONT_MUSIC ... logo=K|none delay=D fade_group=G|none fade=F
  if (const auto &logo = front->logo()) {
    front->logo_at(logo->music_delay);
    const auto track = front->music();
    auto at = std::find(tracks.begin(), tracks.end(), track);
    if (track && at == tracks.end()) at = tracks.insert(tracks.end(), track);
    std::cout << " logo=" << (track ? std::to_string(at - tracks.begin()) : std::string("none"))
              << " delay=" << logo->music_delay << " fade_group="
              << (logo->fade_group == n3e::FrontLogo::kNone ? std::string("none") : std::to_string(logo->fade_group))
              << " fade=" << logo->fade;
  }
  std::cout << std::endl;
  front->jump(Screen::login);
  for (size_t k = 0; k < tracks.size(); ++k) {
    const auto &track = tracks[k];
    const bool pcm = track->kind == n3e::MusicTrack::Kind::pcm;
    n3e::MusicStream stream(track);
    std::vector<float> chunk(4800 * 2);
    float peak = 0;
    uint64_t audible = 0;
    // One pass is frames x 1152 (MPEG-1) or 576 samples, or (PCM) the
    // sample frames; go one second past it.
    const uint64_t samples = uint64_t(track->frames) * (pcm ? 1 : track->rate >= 32000 ? 1152 : 576);
    const uint64_t pass = samples * 48000 / track->rate;
    for (uint64_t written = 0; written < pass + 48000 && !stream.ended();) {
      std::fill(chunk.begin(), chunk.end(), 0.f);
      const auto n = stream.mix(chunk.data(), 4800, 1.f);
      for (unsigned i = 0; i < n * 2; ++i) peak = std::max(peak, std::abs(chunk[i]));
      for (unsigned i = 0; i < n; ++i) audible += std::abs(chunk[i * 2]) > 1e-4f || std::abs(chunk[i * 2 + 1]) > 1e-4f;
      written += n;
    }
    std::cout << "FRONT_MUSIC_STREAM track=" << k << " kind=" << (pcm ? "pcm" : "mpeg") << " rate=" << track->rate
              << " channels=" << track->channels << " frames=" << track->frames << " loop=" << track->loop
              << " restart=" << track->restart << " decoded=" << stream.decoded_frames()
              << " restarts=" << stream.restarts() << " peak=" << peak << " audible=" << audible
              << " ended=" << stream.ended() << std::endl;
  }
  if (glGetError() != GL_NO_ERROR) throw std::runtime_error("GL error");
  std::cout << "FRONT_SHOTS done" << std::endl;
  return 0;
}
