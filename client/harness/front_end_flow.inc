// Test-only fragment (PQ-006): included into viewer() by the test client
// (n3e-test-client, N3E_HARNESS=1) only; see client/harness/harness.h.
// Spec 11 acceptance 7: N3E_TEST_FRONT_FLOW=NAME,NAME... plays the KO screens
// with the events a player sends (ENTER, text input, backspace): Discord login,
// the realm, create with each name in turn until one is accepted, start, the
// world. A message box is printed and dismissed; one that comes after the
// world (a kick) ends the run. Login is one ENTER at the first frame, which
// may come before the connection is up, and once more after a message box on
// the login screen (a failed Discord login). It prints, for
// tests/front_end_flow_live.py:
//   FRONT_FLOW screen=login|realms|select|create|loading|world characters=N
//   FRONT_FLOW enter connected=0|1
//   FRONT_FLOW message='...'
//   FRONT_FLOW music=none|streamK (RQ-018: K counts the streams started; a
//   line each time the mixer's stream changes, a frame after the screen)
//   FRONT_FLOW hover phase=P clip=C t=T end=E blend=B theta=H spot=0|1 info=0|1
//   (RQ-066, RQ-075: on select, before start, the character in front as
//   View::front_pose reports it: its clip, the clip's time and length, the
//   blend into it, the spot's theta and light, the info text. Phases: `out`,
//   the pointer off the centre rect at rest; `in`, the first frame after it
//   comes on; `play`, a second later; `hold`, after the clip's end;
//   `back`, the first frame after it leaves; `rest`, a second and a half
//   later. RQ-076, after ENTER: `start`, the first frame on the start clip;
//   `blend`, 0.3 s later, still blending; `started`, a second after `start`,
//   the clip playing)
{
  static const char *flow_names = std::getenv("N3E_TEST_FRONT_FLOW");
  static std::vector<std::string> names;
  static size_t next_name = 0;
  static int last_screen = -1;
  static uint64_t last_push = 0;
  static bool was_in_world = false, entered = false, retry = false;
  static std::string typed;
  if (flow_names && front && network) {
    if (names.empty())
      for (std::string_view rest = flow_names; !rest.empty();) {
        const auto comma = rest.find(',');
        names.emplace_back(rest.substr(0, comma));
        rest = comma == std::string_view::npos ? std::string_view{} : rest.substr(comma + 1);
      }
    auto key = [&](SDL_Keycode k) {
      SDL_Event ev{};
      ev.type = SDL_EVENT_KEY_DOWN;
      ev.key.key = k;
      ev.key.scancode = SDL_GetScancodeFromKey(k, nullptr);
      ev.key.down = true;
      SDL_PushEvent(&ev);
      ev.type = SDL_EVENT_KEY_UP;
      ev.key.down = false;
      SDL_PushEvent(&ev);
    };
    const int screen = !front_active() ? 5 : int(front->screen());
    static const char *labels[] = {"login", "realms", "select", "create", "loading", "world"};
    if (screen != last_screen) {
      std::cout << "FRONT_FLOW screen=" << labels[screen] << " characters=" << world.characters.characters_size()
                << std::endl;
      last_screen = screen;
    }
    static const void *last_stream = nullptr;
    static int streams = 0;
    if (audio.mixer.music.get() != last_stream) {
      last_stream = audio.mixer.music.get();
      if (last_stream) ++streams;
      std::cout << "FRONT_FLOW music=" << (last_stream ? "stream" + std::to_string(streams) : std::string("none"))
                << std::endl;
    }
    was_in_world = was_in_world || screen == 5;
    const uint64_t now_ms = SDL_GetTicks();
    if (front->showing_message() && front_active() && now_ms - last_push > 500) {
      std::cout << "FRONT_FLOW message='" << front->message_text() << "'" << std::endl;
      last_push = now_ms;
      retry = screen == 0;
      if (was_in_world) {
        SDL_Event quit{};
        quit.type = SDL_EVENT_QUIT;
        SDL_PushEvent(&quit);
      } else
        key(SDLK_RETURN);
    } else if (screen == 2 && next_name > 0 && world.characters.characters_size() && !front->showing_message()) {
      // RQ-066, RQ-075: the pointer off the character in front, then on it
      // (its clip blends in, plays once and holds the last frame, the spot
      // widens, the info text shows), then off again (the rest clip blends
      // back, the spot narrows to off, the text hides); then ENTER: the new
      // character, in focus, starts: its start clip blends in over 0.6 s on
      // its first frame, then plays (RQ-076). Run every frame: the blends last
      // 0.3 and 0.6 s.
      static int phase = 0;
      static uint64_t phase_at = 0;
      const auto pose = front->front_pose();
      auto pointer = [&](float y) {
        int lw = 0, lh = 0;
        SDL_GetWindowSize(w, &lw, &lh);
        SDL_Event ev{};
        ev.type = SDL_EVENT_MOUSE_MOTION;
        ev.motion.x = lw * .5f;
        ev.motion.y = lh * y;
        SDL_PushEvent(&ev);
      };
      auto report = [&](const char *name) {
        std::cout << "FRONT_FLOW hover phase=" << name << " clip=" << pose.clip << " t=" << pose.time
                  << " end=" << pose.length << " blend=" << pose.blend << " theta=" << pose.theta
                  << " spot=" << pose.spot << " info=" << pose.info << std::endl;
      };
      auto next = [&] { ++phase, phase_at = now_ms; };
      if (phase == 0) {
        pointer(.2f);
        next();
      } else if (phase == 1 && now_ms - phase_at > 1500) {
        report("out");
        pointer(.65f);
        next();
      } else if (phase == 2 && pose.clip == 0) {
        report("in");
        next();
      } else if (phase == 3 && now_ms - phase_at > 1000) {
        report("play");
        next();
      } else if (phase == 4 && now_ms - phase_at > uint64_t(pose.length * 1000) + 500) {
        report("hold");
        pointer(.2f);
        next();
      } else if (phase == 5 && pose.clip == 2) {
        report("back");
        next();
      } else if (phase == 6 && now_ms - phase_at > 1500) {
        report("rest");
        next();
        last_push = now_ms;
        key(SDLK_RETURN);
      } else if (phase == 7 && pose.clip == 1) {
        report("start");
        next();
      } else if (phase == 8 && now_ms - phase_at > 300) {
        report("blend");
        next();
      } else if (phase == 9 && now_ms - phase_at > 700) {
        report("started");
        next();
      }
    } else if (screen < 5 && !front->showing_message() && now_ms - last_push > 700) {
      last_push = now_ms;
      if (screen == 0 && !entered) {
        std::cout << "FRONT_FLOW enter connected=" << world.connected << std::endl;
        entered = true;
        key(SDLK_RETURN);
      } else if (screen == 0 && retry && !was_in_world &&
                 discord_flow->phase() == n3e::login::Flow::Phase::idle) {
        retry = false;
        key(SDLK_RETURN);
      } else if (screen == 1 ||
          (screen == 2 && !world.characters.characters_size()))
        key(SDLK_RETURN);
      else if (screen == 3 && !front->creating() && next_name < names.size()) {
        for (size_t i = 0; i < typed.size(); ++i) key(SDLK_BACKSPACE);
        typed = names[next_name++];
        SDL_Event ev{};
        ev.type = SDL_EVENT_TEXT_INPUT;
        ev.text.text = typed.c_str();
        SDL_PushEvent(&ev);
        key(SDLK_RETURN);
      }
    }
  }
}
