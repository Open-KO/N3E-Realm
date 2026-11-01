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
//   FRONT_FLOW hover t=T end=E (RQ-066: on select, before start, the front
//   character's clip time T and clip length E with the pointer on it; three
//   lines, the first while it plays, two after its end)
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
      else if (screen == 2 && next_name > 0 && world.characters.characters_size()) {
        // RQ-066: the pointer on the character in front (the centre rect);
        // its clip plays once and holds the last frame. One sample while it
        // plays, two after its end, then ENTER: the new character, in focus,
        // starts.
        static uint64_t hover_at = 0;
        static int samples = 0;
        const auto [t, length] = front->front_pose();
        if (!hover_at) {
          int lw = 0, lh = 0;
          SDL_GetWindowSize(w, &lw, &lh);
          SDL_Event ev{};
          ev.type = SDL_EVENT_MOUSE_MOTION;
          ev.motion.x = lw * .5f;
          ev.motion.y = lh * .65f;
          SDL_PushEvent(&ev);
          hover_at = now_ms;
        } else if (samples < 3 && (samples == 0 || now_ms - hover_at > uint64_t(length * 1000) + 500)) {
          std::cout << "FRONT_FLOW hover t=" << t << " end=" << length << std::endl;
          ++samples;
        } else if (samples == 3)
          key(SDLK_RETURN);
      }
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
