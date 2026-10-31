// Test-only fragment (PQ-006): included into viewer() by the test client
// (n3e-test-client, N3E_HARNESS=1) only; see client/harness/harness.h.
// Spec 11 acceptance 6: N3E_TEST_FRONT_END=PREFIX draws each KO screen at rest
// in the window (--fixed-window), writes PREFIX.<shot>.ppm and prints, per
// shot, the characters drawn (pixel boxes, y down) and one bound node's rect:
//   FRONT_SHOT name=N size=WxH path=P rect=x0,y0,x1,y1 drawn=intro|hall:x0,y0,x1,y1;...
// then exits. tests/front_end_live.py checks the frames. No server.
if (const char *prefix = std::getenv("N3E_TEST_FRONT_END")) {
  if (!front) throw std::runtime_error("N3E_TEST_FRONT_END needs front-end.bin and a Discord realm");
  int width, height;
  SDL_GetWindowSizeInPixels(w, &width, &height);
  n3e::Characters list;
  using Screen = n3e::front::Screen;
  auto shot = [&](const std::string &name, Screen screen, int characters, const std::string &realm, float progress,
                  n3e::FrontAction bound, const std::string &message) {
    SDL_PumpEvents();
    list.Clear();
    for (int i = 0; i < characters; ++i) {
      auto *c = list.add_characters();
      c->set_id(i + 1);
      c->set_name("Shot" + std::to_string(i + 1));
      c->set_level(10 * (i + 1));
    }
    front->jump(screen);
    if (!message.empty()) front->show_message(message);
    const n3e::front::Context context{realm, "ENTER - Log in with Discord", release.version, &list, progress};
    front->draw(width, height, 1.0, context);
    front->draw(width, height, 1.0, context);
    const std::string path = std::string(prefix) + "." + name + ".ppm";
    capture(path, width, height);
    std::cout << "FRONT_SHOT name=" << name << " size=" << width << "x" << height << " path=" << path << " rect=";
    if (auto r = front->action_rect(bound, width, height))
      std::cout << int((*r)[0]) << "," << int((*r)[1]) << "," << int((*r)[2]) << "," << int((*r)[3]);
    std::cout << " drawn=";
    const char *sep = "";
    for (const auto &d : front->drawn()) {
      const auto &b = d.box;
      std::cout << sep << (d.intro ? "intro" : "hall") << ":" << int((b[0] + 1) / 2 * width) << ","
                << int((1 - b[3]) / 2 * height) << "," << int((b[2] + 1) / 2 * width) << ","
                << int((1 - b[1]) / 2 * height);
      sep = ";";
    }
    std::cout << std::endl;
    SDL_GL_SwapWindow(w);
  };
  using A = n3e::FrontAction;
  shot("login", Screen::login, 0, "Local Realm", 0, A::login, "");
  shot("realms", Screen::realms, 0, "Local Realm", 0, A::realm_list, "");
  shot("realms-unnamed", Screen::realms, 0, "", 0, A::realm_list, "");
  for (int n = 1; n <= 3; ++n) shot("select-" + std::to_string(n), Screen::select, n, "Local Realm", 0, A::char_info, "");
  shot("create", Screen::create, 0, "Local Realm", 0, A::name_field, "");
  shot("loading-start", Screen::loading, 1, "Local Realm", 2 / 3.f, A::progress, "");
  shot("loading-world", Screen::loading, 1, "Local Realm", 1, A::progress, "");
  shot("message", Screen::login, 0, "Local Realm", 0, A::message, "Disconnected from server");
  if (glGetError() != GL_NO_ERROR) throw std::runtime_error("GL error");
  std::cout << "FRONT_SHOTS done" << std::endl;
  return 0;
}
