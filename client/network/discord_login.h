#pragma once
// Discord login on the client (specs/02-auth-sessions.md): the realm config the
// Launcher writes, the stored session token, PKCE and the loopback redirect, and the
// login screen's state machine. The Discord client id comes from realm.json, never
// from the build, so a fork logs in with its own Discord application.
#include "network/world.h"
#include "platform/net.h"
#include <chrono>
#include <filesystem>
#include <map>
#include <memory>
#include <optional>
#include <string>
namespace n3e::login {
// realms/<id>/realm.json (spec 04): {id, name, host, port, discord_client_id}.
struct RealmConfig {
  std::string id, name, host, discord_client_id;
  int port = 0;
  std::string endpoint() const { return host + ":" + std::to_string(port); }
};
RealmConfig read_realm(const std::filesystem::path &);
// A flat JSON object of strings, numbers, booleans and nulls (realm.json, session.json).
std::map<std::string, std::string> flat_json(const std::string &);

struct Session {
  std::string token; // the 32 raw bytes
  int64_t expires_at = 0;
  std::string discord_name;
};
// <config>/n3e-realm/<realm id>/session.json (platform/dirs.h: XDG config; %APPDATA%).
std::filesystem::path session_path(const std::string &realm_id);
// The stored session if it is readable, well formed and not yet expired.
std::optional<Session> load_session(const std::filesystem::path &, int64_t now);
// Written through a temporary file, mode 0600 on Linux (Windows: the per-user
// %APPDATA%); false when it could not be.
bool save_session(const std::filesystem::path &, const Session &);
void forget_session(const std::filesystem::path &);

std::string base64url(const std::string &);
std::string unbase64url(const std::string &);
std::string rfc3339(int64_t unix_seconds);
std::optional<int64_t> parse_rfc3339(const std::string &);
// The host name, control characters stripped, at most 64 bytes.
std::string client_label();

struct Pkce {
  std::string verifier, challenge, state;
};
Pkce make_pkce();
std::string authorize_url(const std::string &client_id, const std::string &redirect, const Pkce &);
// What a refusal's detail means for the player (spec 02 wording), or "" for none.
std::string player_text(const std::string &detail);

// The loopback redirect target: the first free port of 49152-49155, polled once a
// frame without blocking. One request carrying the expected state ends it.
class Callback {
  net::Socket listener = net::BAD_SOCKET;
  int port_ = 0;
  std::string state;

public:
  enum class Result { waiting, code, denied, failed };
  explicit Callback(std::string expected_state) : state(std::move(expected_state)) {}
  ~Callback();
  Callback(const Callback &) = delete;
  Callback &operator=(const Callback &) = delete;
  bool open();
  std::string redirect_uri() const;
  Result poll(std::string &code);
};

// Starts the system browser at `url`; false if it could not be started.
bool open_browser(const std::string &url);

// The login screen with a realm config: a stored session first, else "Log in with
// Discord" (ENTER), the browser, the code. `update` returns a message to send.
class Flow {
public:
  enum class Phase { start, idle, session, browser, code, done, stopped };
  Flow(RealmConfig realm, bool launch_browser) : realm(std::move(realm)), launch(launch_browser) {}
  std::optional<Envelope> update(const WorldState &, bool start, bool cancel, int64_t now);
  const std::string &status() const { return text; }
  // Counts the texts the player must read (failures, the address to open);
  // the KO screens show each in their message box.
  uint64_t alerts() const { return alerts_; }
  Phase phase() const { return phase_; }
  void reset();

private:
  RealmConfig realm;
  bool launch;
  Phase phase_ = Phase::start;
  std::string text = "Connecting";
  uint64_t refusals = 0, results = 0, alerts_ = 0;
  Pkce pkce;
  std::unique_ptr<Callback> callback;
  std::chrono::steady_clock::time_point browser_until{};
  std::optional<Envelope> begin_browser();
};
} // namespace n3e::login
