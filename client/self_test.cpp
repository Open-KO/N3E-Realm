// `n3e-client PACKAGE --self-test --realm realm.json` (specs/06-cd.md "smoke"): the
// player build's install check. CI runs it on each platform's release artifacts
// after the Launcher assembled the package; a player can run it to see why the
// game will not start. It loads the package and its scene, reads realm.json,
// builds the Discord authorize address on a loopback callback port, loads the
// system's CA certificates, finds the settings directory, and opens a hidden
// OpenGL 3.3 core window with every function the client loads. Nothing leaves
// this machine. Exit 0 when all of that worked.
#include "assets/assets.h"
#include "network/discord_login.h"
#include "platform/dirs.h"
#include "platform/gl_load.h"
#include "platform/tls.h"
#include <SDL3/SDL.h>
#include <iostream>
#include <memory>
#include <stdexcept>
namespace {
void check(bool ok, const std::string &what) {
  if (!ok)
    throw std::runtime_error("self-test: " + what);
}
} // namespace
int self_test(const n3e::Release &release, int argc, char **argv) {
  std::filesystem::path realm_path;
  for (int i = 3; i < argc; ++i) {
    std::string a = argv[i];
    if (a == "--realm" && i + 1 < argc)
      realm_path = argv[++i];
    else
      throw std::runtime_error("argument " + a);
  }
  check(!realm_path.empty(), "--self-test needs --realm realm.json");

  auto scene = n3e::load_scene(release);
  std::cout << "package " << release.hash.substr(0, 12) << " game=" << release.game
            << " protocol=" << release.protocol << " nodes=" << scene.nodes.size() << "\n";

  auto realm = n3e::login::read_realm(realm_path);
  auto pkce = n3e::login::make_pkce();
  n3e::login::Callback callback(pkce.state);
  check(callback.open(), "no loopback callback port (49152-49155)");
  auto url = n3e::login::authorize_url(realm.discord_client_id, callback.redirect_uri(), pkce);
  std::cout << "realm " << realm.id << " at " << realm.endpoint() << "; login callback "
            << callback.redirect_uri() << "\n";
  check(url.starts_with("https://discord.com/oauth2/authorize?client_id=" + realm.discord_client_id),
        "authorize address");

  std::unique_ptr<SSL_CTX, decltype(&SSL_CTX_free)> ctx(SSL_CTX_new(TLS_client_method()), SSL_CTX_free);
  check(ctx && n3e::tls::trust(ctx.get(), ""), "no system CA certificates");
  check(!n3e::dirs::config().empty(), "no settings directory");
  std::cout << "settings " << n3e::login::session_path(realm.id).parent_path().string() << "\n";

  check(SDL_Init(SDL_INIT_VIDEO), std::string("video: ") + SDL_GetError());
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
  SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
  SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 24);
  auto *window = SDL_CreateWindow("n3e self-test", 64, 64, SDL_WINDOW_OPENGL | SDL_WINDOW_HIDDEN);
  check(window, std::string("window: ") + SDL_GetError());
  auto gl = SDL_GL_CreateContext(window);
  check(gl, std::string("OpenGL 3.3 core: ") + SDL_GetError());
  load_gl();
  const auto text = [](GLenum name) {
    auto *s = reinterpret_cast<const char *>(glGetString(name));
    return std::string(s ? s : "(null)");
  };
  std::cout << "opengl " << text(GL_VERSION) << " renderer=" << text(GL_RENDERER)
            << " video=" << SDL_GetCurrentVideoDriver() << "\n";
  SDL_GL_DestroyContext(gl);
  SDL_DestroyWindow(window);
  SDL_Quit();
  std::cout << "self-test ok\n";
  return 0;
}
