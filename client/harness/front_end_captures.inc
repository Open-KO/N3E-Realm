// Test-only fragment (PQ-006): included into viewer() by the test client
// (n3e-test-client, N3E_HARNESS=1) only; see client/harness/harness.h.
// Spec 11 acceptance 6: N3E_TEST_FRONT_END=PREFIX draws each KO screen at rest
// in the window (--fixed-window), writes PREFIX.<shot>.ppm and prints, per
// shot, the characters drawn (pixel boxes, y down) and one bound node's rect:
//   FRONT_SHOT name=N size=WxH path=P rect=x0,y0,x1,y1 drawn=intro|hall|create:x0,y0,x1,y1;...
// then the screens' music (FRONT_MUSIC, below), and exits.
// tests/front_end_live.py checks the frames and the music. No server.
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
      const auto &v = d.viewport;
      static const char *kinds[] = {"intro", "hall", "create"};
      std::cout << sep << kinds[d.which] << ":" << int(v[0] + (b[0] + 1) / 2 * v[2]) << ","
                << int(height - v[1] - (b[3] + 1) / 2 * v[3]) << "," << int(v[0] + (b[2] + 1) / 2 * v[2]) << ","
                << int(height - v[1] - (b[1] + 1) / 2 * v[3]);
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
  // RQ-018 (Q57): each screen's track (its index among the tracks the
  // screens name, or none), then the login track streamed past its end:
  //   FRONT_MUSIC login=0 realms=0 select=0 create=0 loading=none
  //   FRONT_MUSIC_STREAM rate=R channels=C frames=F decoded=D peak=P audible=A ended=0|1
  std::vector<const n3e::MusicTrack *> tracks;
  std::cout << "FRONT_MUSIC";
  for (const auto &[label, screen] : {std::pair{"login", Screen::login}, std::pair{"realms", Screen::realms},
                                      std::pair{"select", Screen::select}, std::pair{"create", Screen::create},
                                      std::pair{"loading", Screen::loading}}) {
    front->jump(screen);
    const auto track = front->music();
    auto at = std::find(tracks.begin(), tracks.end(), track.get());
    if (track && at == tracks.end()) at = tracks.insert(tracks.end(), track.get());
    std::cout << " " << label << "=" << (track ? std::to_string(at - tracks.begin()) : std::string("none"));
  }
  std::cout << std::endl;
  front->jump(Screen::login);
  if (const auto track = front->music()) {
    n3e::MusicStream stream(track);
    std::vector<float> chunk(4800 * 2);
    float peak = 0;
    uint64_t audible = 0;
    // One pass is frames x 1152 (MPEG-1) or 576 samples; go one second past it.
    const uint64_t pass = uint64_t(track->frames) * (track->rate >= 32000 ? 1152 : 576) * 48000 / track->rate;
    for (uint64_t written = 0; written < pass + 48000 && !stream.ended();) {
      std::fill(chunk.begin(), chunk.end(), 0.f);
      const auto n = stream.mix(chunk.data(), 4800, 1.f);
      for (unsigned i = 0; i < n * 2; ++i) peak = std::max(peak, std::abs(chunk[i]));
      for (unsigned i = 0; i < n; ++i) audible += std::abs(chunk[i * 2]) > 1e-4f || std::abs(chunk[i * 2 + 1]) > 1e-4f;
      written += n;
    }
    std::cout << "FRONT_MUSIC_STREAM rate=" << track->rate << " channels=" << track->channels
              << " frames=" << track->frames << " decoded=" << stream.decoded_frames() << " peak=" << peak
              << " audible=" << audible << " ended=" << stream.ended() << std::endl;
  }
  if (glGetError() != GL_NO_ERROR) throw std::runtime_error("GL error");
  std::cout << "FRONT_SHOTS done" << std::endl;
  return 0;
}
