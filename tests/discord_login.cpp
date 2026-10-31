// Spec 02, the client's side without a server: realm.json and session.json, PKCE
// (RFC 7636's own example), the authorize address, the loopback callback's state
// check, the player-facing wording, and the login screen's answers to the server.
#include "network/discord_login.h"
#include <arpa/inet.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <netinet/in.h>
#include <openssl/sha.h>
#include <stdexcept>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
namespace {
using namespace n3e::login;
void check(bool ok, const std::string &what) {
  if (!ok) throw std::runtime_error(what);
}
// One HTTP request to the callback, as a browser sends it; the status line back.
std::string get(const std::string &redirect, const std::string &query, Callback &callback, Callback::Result &result,
                std::string &code) {
  int port = std::stoi(redirect.substr(redirect.rfind(':') + 1));
  int fd = ::socket(AF_INET, SOCK_STREAM, 0);
  sockaddr_in a{};
  a.sin_family = AF_INET;
  a.sin_port = htons(uint16_t(port));
  a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  check(::connect(fd, reinterpret_cast<sockaddr *>(&a), sizeof a) == 0, "connect to the callback");
  std::string request = "GET /callback?" + query + " HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n";
  check(::send(fd, request.data(), request.size(), 0) == ssize_t(request.size()), "send");
  for (int i = 0; i < 100 && (result = callback.poll(code)) == Callback::Result::waiting; ++i) {
    char probe;
    if (::recv(fd, &probe, 1, MSG_PEEK | MSG_DONTWAIT) > 0) break;
    ::usleep(10000);
  }
  char buffer[512] = {};
  ssize_t n = ::recv(fd, buffer, sizeof buffer - 1, 0);
  ::close(fd);
  std::string reply(buffer, n > 0 ? size_t(n) : 0);
  return reply.substr(0, reply.find("\r\n"));
}
} // namespace
int main() {
  try {
    auto dir = std::filesystem::temp_directory_path() / ("n3e-login-check-" + std::to_string(::getpid()));
    std::filesystem::remove_all(dir);
    std::filesystem::create_directories(dir);
    ::setenv("XDG_CONFIG_HOME", dir.c_str(), 1);

    // RFC 7636 appendix B: verifier -> S256 challenge, base64url without padding.
    check(base64url(std::string(32, '\xff')) == "__________________________________________8", "base64url alphabet");
    for (const std::string &raw : std::vector<std::string>{"", "a", "ab", "abc", std::string("\0\x01\xfe", 3)})
      check(unbase64url(base64url(raw)) == raw, "base64url round trip");
    check(unbase64url("a+b").empty() && unbase64url("abcde").empty(), "base64url refuses non-url text");
    unsigned char digest[32];
    std::string verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    SHA256(reinterpret_cast<const unsigned char *>(verifier.data()), verifier.size(), digest);
    check(base64url(std::string(reinterpret_cast<char *>(digest), 32)) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
          "RFC 7636 S256 vector");
    auto p = make_pkce();
    check(p.verifier.size() == 64 && p.challenge.size() == 43 && p.state.size() == 22, "PKCE sizes");
    auto url = authorize_url("123", "http://127.0.0.1:49152/callback", p);
    check(url.starts_with("https://discord.com/oauth2/authorize?client_id=123&response_type=code&scope=identify"
                          "&redirect_uri=http%3A%2F%2F127.0.0.1%3A49152%2Fcallback&state=") &&
              url.ends_with("&code_challenge=" + p.challenge + "&code_challenge_method=S256&prompt=none"),
          "authorize address " + url);
    std::cout << "PASS PKCE: RFC 7636 S256 vector, 64-character verifier, authorize address encoded\n";

    // realm.json (spec 04) and the flat JSON reader.
    auto realm_path = dir / "realm.json";
    std::ofstream(realm_path) << R"({"id": "n3e-realm", "name": "N3E \"Realm\"", "host": "play.example.org",
      "port": 7777, "discord_client_id": "123456789012345678"})";
    auto realm = read_realm(realm_path);
    check(realm.id == "n3e-realm" && realm.name == "N3E \"Realm\"" && realm.endpoint() == "play.example.org:7777" &&
              realm.discord_client_id == "123456789012345678", "realm.json fields");
    for (std::string bad : {R"({"id": "../x", "host": "h", "port": 1, "discord_client_id": "1"})",
                            R"({"id": "x", "host": "h", "port": 70000, "discord_client_id": "1"})",
                            R"({"id": "x", "host": "h", "port": 1, "discord_client_id": "abc"})",
                            R"({"id": "x", "nested": {"a": 1}})", R"({"id": "x")"}) {
      std::ofstream(realm_path) << bad;
      bool refused = false;
      try {
        read_realm(realm_path);
      } catch (const std::exception &) {
        refused = true;
      }
      check(refused, "realm.json accepted: " + bad);
    }
    std::cout << "PASS realm.json: id, host, port and a numeric Discord client id; traversal, bad port, nesting refused\n";

    // session.json: mode 0600, the token as base64url, expiry honoured, junk ignored.
    check(rfc3339(1793405908) == "2026-10-31T00:18:28Z" && parse_rfc3339("2026-10-31T00:18:28Z") == 1793405908,
          "rfc3339");
    auto path = session_path("n3e-realm");
    check(path == dir / "n3e-realm/n3e-realm/session.json", "session path " + path.string());
    std::string token(32, '\0');
    for (int i = 0; i < 32; ++i) token[i] = char(i * 7);
    check(save_session(path, {token, 2000000000, "Nelly \"N\""}), "save");
    struct stat st{};
    ::stat(path.c_str(), &st);
    check((st.st_mode & 0777) == 0600, "session.json mode");
    auto loaded = load_session(path, 1900000000);
    check(loaded && loaded->token == token && loaded->expires_at == 2000000000 && loaded->discord_name == "Nelly \"N\"",
          "session round trip");
    check(!load_session(path, 2000000000), "an expired session is not used");
    std::ofstream(path) << "{\"token\": \"short\", \"expires_at\": \"2040-01-01T00:00:00Z\"}";
    check(!load_session(path, 0), "a malformed token is not used");
    std::ofstream(path) << "not json";
    check(!load_session(path, 0), "an unreadable file is not used");
    forget_session(path);
    check(!std::filesystem::exists(path), "forget");
    std::cout << "PASS session.json: mode 0600, base64url token, expired/malformed/unreadable files ignored\n";

    // Player-facing wording (spec 02, KO's where it exists).
    check(player_text("kicked:afk") == "You were disconnected by an operator: afk.", "kick text");
    check(player_text("banned:perm:cheating") == "Your account is blocked until further notice: cheating.", "perm ban");
    check(player_text("banned:2026-10-31T00:18:28Z:spam: lots") ==
              "Your account is blocked until 2026-10-31 00:18 UTC: spam: lots.", "timed ban");
    check(player_text("discord:unavailable").starts_with("Discord login failed (unavailable)"), "discord text");
    std::cout << "PASS wording: kick, permanent and timed ban, Discord failure\n";

    // The loopback callback: a wrong state is refused and the wait goes on; the right one ends it.
    Callback callback("expected-state");
    check(callback.open(), "a callback port in 49152-49155");
    auto redirect = callback.redirect_uri();
    check(redirect.starts_with("http://127.0.0.1:4915") && redirect.ends_with("/callback"), redirect);
    Callback::Result result{};
    std::string code;
    check(get(redirect, "code=x&state=other", callback, result, code) == "HTTP/1.1 400 Bad Request" &&
              result == Callback::Result::waiting, "a wrong state is refused");
    check(get(redirect, "code=a%2Bb&state=expected-state", callback, result, code) == "HTTP/1.1 200 OK" &&
              result == Callback::Result::code && code == "a+b", "the right state ends the wait");
    Callback denied("s");
    check(denied.open(), "second callback");
    check(get(denied.redirect_uri(), "error=access_denied&state=s", denied, result, code) == "HTTP/1.1 200 OK" &&
              result == Callback::Result::denied, "a denial ends the wait");
    // An answered attempt leaves TIME_WAIT on its port; the next attempt reuses it.
    Callback retry("r");
    check(retry.open() && retry.redirect_uri() == redirect, "a retry binds the first port again: " + retry.redirect_uri());
    std::cout << "PASS callback: wrong state 400 and still waiting, the right state hands over the code, a denial ends it, a retry gets the first port again\n";

    // The login screen: a stored session is sent first; expired falls through to the
    // browser; a ban stops with its reason; a LoginResult with a token is stored.
    n3e::WorldState world;
    world.connected = true;
    Flow flow(realm, false);
    check(!flow.update(world, false, false, 1900000000) && flow.phase() == Flow::Phase::idle, "no session: idle");
    flow.update(world, true, false, 1900000000);
    check(flow.phase() == Flow::Phase::browser, "ENTER opens the browser step");
    check(!flow.update(world, false, true, 1900000000) && flow.phase() == Flow::Phase::idle, "ESC cancels");
    world.login_result.set_token(token);
    world.login_result.set_expires_at_unix(2000000000);
    world.login_result.set_discord_name("Nelly");
    ++world.login_results;
    flow.update(world, false, false, 1900000000);
    check(flow.phase() == Flow::Phase::done && load_session(session_path(realm.id), 1900000000), "token stored");
    Flow again(realm, false);
    auto sent = again.update(world, false, false, 1900000000);
    check(sent && sent->has_session_login() && sent->session_login().token() == token &&
              again.phase() == Flow::Phase::session, "a stored session is sent first");
    world.refusal_detail = "expired";
    ++world.refusals;
    again.update(world, false, false, 1900000000);
    check(again.phase() == Flow::Phase::browser && !std::filesystem::exists(session_path(realm.id)),
          "expired: file dropped, browser step");
    save_session(session_path(realm.id), {token, 2000000000, "Nelly"});
    Flow banned(realm, false);
    banned.update(world, false, false, 1900000000);
    world.refusal_detail = "banned:perm:cheating";
    ++world.refusals;
    banned.update(world, true, false, 1900000000);
    check(banned.phase() == Flow::Phase::stopped && banned.status() == player_text("banned:perm:cheating") &&
              !std::filesystem::exists(session_path(realm.id)), "banned: stopped with the reason");
    std::cout << "PASS login screen: stored session first, ENTER/ESC, token stored, expired -> browser, ban stops\n";
    std::filesystem::remove_all(dir);
    std::cout << "PASS client Discord login checks\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "FAIL " << e.what() << "\n";
    return 1;
  }
}
