#include "network/discord_login.h"
#include "platform/dirs.h"
#include <cstring>
#include <ctime>
#include <fstream>
#include <iostream>
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <openssl/sha.h>
#include <sstream>
#include <stdexcept>
#include <thread>
#ifdef _WIN32
#include <windows.h>
#include <shellapi.h>
#else
#include <fcntl.h>
#include <spawn.h>
#include <sys/stat.h>
#include <sys/wait.h>
extern char **environ;
#endif
namespace n3e::login {
namespace {
constexpr int FIRST_PORT = 49152, LAST_PORT = 49155;
constexpr auto BROWSER_WAIT = std::chrono::minutes(5);
const std::string AUTHORIZE = "https://discord.com/oauth2/authorize";

std::string url_encode(const std::string &v) {
  static const char *hex = "0123456789ABCDEF";
  std::string out;
  for (unsigned char c : v) {
    if (std::isalnum(c) || c == '-' || c == '.' || c == '_' || c == '~')
      out += char(c);
    else {
      out += '%';
      out += hex[c >> 4];
      out += hex[c & 15];
    }
  }
  return out;
}
std::string url_decode(const std::string &v) {
  std::string out;
  for (size_t i = 0; i < v.size(); ++i) {
    if (v[i] == '+')
      out += ' ';
    else if (v[i] == '%' && i + 2 < v.size() && std::isxdigit((unsigned char)v[i + 1]) &&
             std::isxdigit((unsigned char)v[i + 2])) {
      out += char(std::stoi(v.substr(i + 1, 2), nullptr, 16));
      i += 2;
    } else
      out += v[i];
  }
  return out;
}
std::map<std::string, std::string> query(const std::string &q) {
  std::map<std::string, std::string> out;
  std::stringstream in(q);
  std::string pair;
  while (std::getline(in, pair, '&')) {
    auto eq = pair.find('=');
    if (eq != std::string::npos)
      out[url_decode(pair.substr(0, eq))] = url_decode(pair.substr(eq + 1));
  }
  return out;
}
std::string random_bytes(size_t n) {
  std::string b(n, '\0');
  if (RAND_bytes(reinterpret_cast<unsigned char *>(b.data()), int(n)) != 1)
    throw std::runtime_error("no random bytes");
  return b;
}
std::string json_string(const std::string &v) {
  std::string out = "\"";
  for (unsigned char c : v) {
    if (c == '"' || c == '\\') {
      out += '\\';
      out += char(c);
    } else if (c < 0x20) {
      char e[8];
      std::snprintf(e, sizeof e, "\\u%04x", c);
      out += e;
    } else
      out += char(c);
  }
  return out + "\"";
}
} // namespace

std::map<std::string, std::string> flat_json(const std::string &text) {
  std::map<std::string, std::string> out;
  size_t i = 0;
  auto space = [&] {
    while (i < text.size() && std::isspace((unsigned char)text[i]))
      ++i;
  };
  auto expect = [&](char c) {
    space();
    if (i >= text.size() || text[i] != c)
      throw std::runtime_error(std::string("JSON: expected ") + c);
    ++i;
  };
  auto string = [&] {
    expect('"');
    std::string s;
    while (true) {
      if (i >= text.size())
        throw std::runtime_error("JSON: unterminated string");
      char c = text[i++];
      if (c == '"')
        return s;
      if (c != '\\') {
        s += c;
        continue;
      }
      if (i >= text.size())
        throw std::runtime_error("JSON: escape");
      char e = text[i++];
      switch (e) {
      case 'n': s += '\n'; break;
      case 't': s += '\t'; break;
      case 'r': s += '\r'; break;
      case 'b': s += '\b'; break;
      case 'f': s += '\f'; break;
      case 'u': {
        if (i + 4 > text.size())
          throw std::runtime_error("JSON: escape");
        unsigned code = std::stoul(text.substr(i, 4), nullptr, 16);
        i += 4;
        // Basic Multilingual Plane only; the files this reads are ASCII.
        if (code < 0x80)
          s += char(code);
        else if (code < 0x800) {
          s += char(0xc0 | code >> 6);
          s += char(0x80 | (code & 0x3f));
        } else {
          s += char(0xe0 | code >> 12);
          s += char(0x80 | (code >> 6 & 0x3f));
          s += char(0x80 | (code & 0x3f));
        }
        break;
      }
      default: s += e;
      }
    }
  };
  expect('{');
  space();
  if (i < text.size() && text[i] == '}')
    return out;
  while (true) {
    auto key = string();
    expect(':');
    space();
    if (i < text.size() && text[i] == '"')
      out[key] = string();
    else {
      size_t start = i;
      while (i < text.size() && (std::isalnum((unsigned char)text[i]) || text[i] == '-' || text[i] == '.' || text[i] == '+'))
        ++i;
      if (start == i)
        throw std::runtime_error("JSON: only a flat object of scalars is read (" + key + ")");
      out[key] = text.substr(start, i - start);
    }
    space();
    if (i < text.size() && text[i] == ',') {
      ++i;
      continue;
    }
    expect('}');
    return out;
  }
}

RealmConfig read_realm(const std::filesystem::path &path) {
  std::ifstream in(path);
  if (!in)
    throw std::runtime_error("realm config unreadable: " + path.string());
  std::stringstream text;
  text << in.rdbuf();
  auto v = flat_json(text.str());
  RealmConfig r;
  r.id = v["id"];
  r.name = v["name"];
  r.host = v["host"];
  r.discord_client_id = v["discord_client_id"];
  r.edge = v["edge"];
  if (!r.edge.empty() && r.edge.compare(0, 6, "wss://") != 0)
    throw std::runtime_error("realm config's edge must be a wss:// URL: " + path.string());
  try {
    r.port = std::stoi(v["port"]);
  } catch (...) {
    r.port = 0;
  }
  bool id_ok = !r.id.empty() && r.id.size() <= 64 &&
               r.id.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789-_.") == std::string::npos && r.id[0] != '.';
  if (!id_ok || r.host.empty() || r.port < 1 || r.port > 65535 ||
      r.discord_client_id.find_first_not_of("0123456789") != std::string::npos || r.discord_client_id.size() > 20)
    throw std::runtime_error("realm config needs id, host, port and a numeric discord_client_id: " + path.string());
  return r;
}

std::filesystem::path session_path(const std::string &realm_id) {
  auto base = dirs::config();
  if (base.empty())
#ifdef _WIN32
    throw std::runtime_error("no APPDATA for session.json");
#else
    throw std::runtime_error("no XDG_CONFIG_HOME or HOME for session.json");
#endif
  return base / "n3e-realm" / realm_id / "session.json";
}

std::string base64url(const std::string &raw) {
  std::string out(4 * ((raw.size() + 2) / 3) + 1, '\0');
  int n = EVP_EncodeBlock(reinterpret_cast<unsigned char *>(out.data()),
                          reinterpret_cast<const unsigned char *>(raw.data()), int(raw.size()));
  out.resize(n);
  while (!out.empty() && out.back() == '=')
    out.pop_back();
  for (auto &c : out)
    c = c == '+' ? '-' : c == '/' ? '_' : c;
  return out;
}
std::string unbase64url(const std::string &text) {
  if (text.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_") != std::string::npos ||
      text.size() % 4 == 1)
    return {};
  std::string s = text;
  for (auto &c : s)
    c = c == '-' ? '+' : c == '_' ? '/' : c;
  size_t pad = (4 - s.size() % 4) % 4;
  s.append(pad, '=');
  std::string out(s.size() / 4 * 3, '\0');
  int n = EVP_DecodeBlock(reinterpret_cast<unsigned char *>(out.data()),
                          reinterpret_cast<const unsigned char *>(s.data()), int(s.size()));
  if (n < 0)
    return {};
  out.resize(size_t(n) - pad);
  return out;
}

std::string rfc3339(int64_t t) {
  std::time_t v = std::time_t(t);
  std::tm tm{};
#ifdef _WIN32
  gmtime_s(&tm, &v);
#else
  gmtime_r(&v, &tm);
#endif
  char b[32];
  std::strftime(b, sizeof b, "%Y-%m-%dT%H:%M:%SZ", &tm);
  return b;
}
std::optional<int64_t> parse_rfc3339(const std::string &text) {
  std::tm tm{};
  char z = 0;
  if (text.size() != 20 || std::sscanf(text.c_str(), "%4d-%2d-%2dT%2d:%2d:%2d%c", &tm.tm_year, &tm.tm_mon, &tm.tm_mday,
                                       &tm.tm_hour, &tm.tm_min, &tm.tm_sec, &z) != 7 || z != 'Z')
    return std::nullopt;
  tm.tm_year -= 1900;
  tm.tm_mon -= 1;
#ifdef _WIN32
  return int64_t(_mkgmtime(&tm));
#else
  return int64_t(timegm(&tm));
#endif
}

std::optional<Session> load_session(const std::filesystem::path &path, int64_t now) {
  try {
    std::ifstream in(path);
    if (!in)
      return std::nullopt;
    std::stringstream text;
    text << in.rdbuf();
    auto v = flat_json(text.str());
    Session s;
    s.token = unbase64url(v["token"]);
    auto expires = parse_rfc3339(v["expires_at"]);
    if (s.token.size() != 32 || !expires || *expires <= now)
      return std::nullopt;
    s.expires_at = *expires;
    s.discord_name = v["discord_name"];
    return s;
  } catch (const std::exception &) {
    return std::nullopt; // unreadable: the Discord flow runs instead (spec 02)
  }
}

bool save_session(const std::filesystem::path &path, const Session &s) {
  std::error_code e;
  std::filesystem::create_directories(path.parent_path(), e);
  auto temporary = path;
  temporary += ".tmp";
  std::string text = "{\"token\": " + json_string(base64url(s.token)) + ", \"expires_at\": " +
                     json_string(rfc3339(s.expires_at)) + ", \"discord_name\": " + json_string(s.discord_name) + "}\n";
#ifdef _WIN32
  // %APPDATA% is the user's own; the file replaces the old one in one move.
  HANDLE f = ::CreateFileW(temporary.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (f == INVALID_HANDLE_VALUE)
    return false;
  DWORD written = 0;
  bool ok = ::WriteFile(f, text.data(), DWORD(text.size()), &written, nullptr) && written == text.size() &&
            ::FlushFileBuffers(f);
  ok = ::CloseHandle(f) && ok;
  if (!ok || !::MoveFileExW(temporary.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
    ::DeleteFileW(temporary.c_str());
    return false;
  }
#else
  ::chmod(path.parent_path().c_str(), 0700);
  int fd = ::open(temporary.c_str(), O_CREAT | O_WRONLY | O_TRUNC | O_CLOEXEC, 0600);
  if (fd < 0)
    return false;
  ::fchmod(fd, 0600);
  bool ok = ::write(fd, text.data(), text.size()) == ssize_t(text.size()) && ::fsync(fd) == 0;
  ok = ::close(fd) == 0 && ok;
  if (!ok || ::rename(temporary.c_str(), path.c_str()) != 0) {
    ::unlink(temporary.c_str());
    return false;
  }
#endif
  return true;
}
void forget_session(const std::filesystem::path &path) {
  std::error_code e;
  std::filesystem::remove(path, e);
}

std::string client_label() {
  char host[256] = {};
  try {
    net::start();
  } catch (const std::exception &) {
    return "client";
  }
  if (::gethostname(host, int(sizeof host - 1)) != 0)
    return "client";
  std::string out;
  for (unsigned char c : std::string(host))
    if (c >= 0x20 && c != 0x7f && out.size() < 64)
      out += char(c);
  return out.empty() ? "client" : out;
}

Pkce make_pkce() {
  Pkce p;
  p.verifier = base64url(random_bytes(48)); // 64 characters (43..128)
  unsigned char digest[SHA256_DIGEST_LENGTH];
  SHA256(reinterpret_cast<const unsigned char *>(p.verifier.data()), p.verifier.size(), digest);
  p.challenge = base64url(std::string(reinterpret_cast<char *>(digest), sizeof digest));
  p.state = base64url(random_bytes(16));
  return p;
}
std::string authorize_url(const std::string &client_id, const std::string &redirect, const Pkce &p) {
  return AUTHORIZE + "?client_id=" + url_encode(client_id) + "&response_type=code&scope=identify&redirect_uri=" +
         url_encode(redirect) + "&state=" + url_encode(p.state) + "&code_challenge=" + url_encode(p.challenge) +
         "&code_challenge_method=S256&prompt=none";
}

std::string player_text(const std::string &detail) {
  if (detail.starts_with("kicked:"))
    return "You were disconnected by an operator: " + detail.substr(7) + ".";
  if (detail.starts_with("banned:")) {
    auto rest = detail.substr(7);
    std::string when = "further notice", reason;
    if (rest.starts_with("perm:"))
      reason = rest.substr(5);
    else if (rest.size() >= 21 && rest[20] == ':') {
      when = rest.substr(0, 10) + " " + rest.substr(11, 5) + " UTC";
      reason = rest.substr(21);
    } else
      reason = rest;
    return "Your account is blocked until " + when + ": " + reason + ".";
  }
  if (detail.starts_with("discord:"))
    return "Discord login failed (" + detail.substr(8) + "). ENTER to try again.";
  if (detail == "dependency")
    return "The realm cannot log you in right now. ENTER to try again.";
  return {};
}

Callback::~Callback() {
  if (listener != net::BAD_SOCKET)
    net::close(listener);
}
bool Callback::open() {
  try {
    net::start();
  } catch (const std::exception &) {
    return false;
  }
  for (int port = FIRST_PORT; port <= LAST_PORT; ++port) {
#ifdef _WIN32
    // Not inherited by the browser ShellExecute starts.
    auto fd = ::WSASocketW(AF_INET, SOCK_STREAM, IPPROTO_TCP, nullptr, 0, WSA_FLAG_OVERLAPPED | WSA_FLAG_NO_HANDLE_INHERIT);
#else
    auto fd = ::socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
#endif
    if (fd == net::BAD_SOCKET)
      return false;
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_port = htons(uint16_t(port));
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    // A previous attempt's answered request leaves TIME_WAIT on its port; the
    // port must still be ours alone (platform/net.h).
    net::exclusive_port(fd);
    if (::bind(fd, reinterpret_cast<sockaddr *>(&a), sizeof a) == 0 && ::listen(fd, 4) == 0 &&
        net::nonblocking(fd)) {
      listener = fd;
      port_ = port;
      return true;
    }
    net::close(fd);
  }
  return false;
}
std::string Callback::redirect_uri() const { return "http://127.0.0.1:" + std::to_string(port_) + "/callback"; }
Callback::Result Callback::poll(std::string &code) {
  if (listener == net::BAD_SOCKET)
    return Result::failed;
#ifdef _WIN32
  auto c = ::accept(listener, nullptr, nullptr);
#else
  auto c = ::accept4(listener, nullptr, nullptr, SOCK_CLOEXEC);
#endif
  if (c == net::BAD_SOCKET)
    return net::would_block() ? Result::waiting : Result::failed;
  // A browser sends its request at once; a client that does not is dropped.
  std::string request;
  char buffer[2048];
  auto until = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (request.find("\r\n\r\n") == std::string::npos && request.size() < 8192 &&
         std::chrono::steady_clock::now() < until) {
    if (net::wait(c, POLLIN, 100) <= 0)
      continue;
    auto n = ::recv(c, buffer, int(sizeof buffer), 0);
    if (n <= 0)
      break;
    request.append(buffer, size_t(n));
  }
  auto respond = [&](const char *status, const std::string &body) {
    std::string r = std::string("HTTP/1.1 ") + status +
                    "\r\nContent-Type: text/html; charset=utf-8\r\nCache-Control: no-store\r\nConnection: close\r\n"
                    "Content-Length: " + std::to_string(body.size()) + "\r\n\r\n" + body;
    (void)!::send(c, r.data(), int(r.size()), net::NO_SIGNAL);
    net::close(c);
  };
  auto line = request.substr(0, request.find("\r\n"));
  if (!line.starts_with("GET /callback?")) {
    respond("404 Not Found", "Not found.");
    return Result::waiting;
  }
  auto target = line.substr(4, line.rfind(' ') - 4);
  auto v = query(target.substr(target.find('?') + 1));
  if (v["state"] != state) {
    respond("400 Bad Request", "This login link is stale. Return to the game and try again.");
    return Result::waiting;
  }
  net::close(listener);
  listener = net::BAD_SOCKET;
  if (!v["error"].empty() || v["code"].empty()) {
    respond("200 OK", "<!doctype html><title>N3E Realm</title><p>Discord login was cancelled. You can close this tab.");
    return Result::denied;
  }
  code = v["code"];
  respond("200 OK", "<!doctype html><title>N3E Realm</title><p>You are logged in. You can close this tab and "
                    "return to the game.");
  return Result::code;
}

bool open_browser(const std::string &url) {
#ifdef _WIN32
  // The default browser; the URL is ASCII (authorize_url encodes everything else).
  const std::wstring wide(url.begin(), url.end());
  return reinterpret_cast<INT_PTR>(::ShellExecuteW(nullptr, L"open", wide.c_str(), nullptr, nullptr, SW_SHOWNORMAL)) > 32;
#else
  pid_t pid;
  const char *args[] = {"xdg-open", url.c_str(), nullptr};
  if (posix_spawnp(&pid, "xdg-open", nullptr, nullptr, const_cast<char **>(args), environ) != 0)
    return false;
  // xdg-open hands the URL to the browser and exits; it is reaped off the frame.
  std::thread([pid] { int status; ::waitpid(pid, &status, 0); }).detach();
  return true;
#endif
}

void Flow::reset() {
  phase_ = Phase::start;
  text = "Connecting";
  refusals = results = 0;
  callback.reset();
}

std::optional<Envelope> Flow::begin_browser() {
  pkce = make_pkce();
  callback = std::make_unique<Callback>(pkce.state);
  if (!callback->open()) {
    callback.reset();
    phase_ = Phase::idle;
    text = "Ports 49152-49155 are all in use. ENTER to try again.";
    ++alerts_;
    return std::nullopt;
  }
  auto url = authorize_url(realm.discord_client_id, callback->redirect_uri(), pkce);
  // Always printed, so a player whose browser did not open can copy it (spec 02).
  std::cout << "Open this address to log in with Discord: " << url << std::endl;
  bool opened = launch && open_browser(url);
  phase_ = Phase::browser;
  browser_until = std::chrono::steady_clock::now() + BROWSER_WAIT;
  text = opened || !launch ? "Waiting for Discord... ESC cancels" : "Open the address printed in the console. ESC cancels";
  if (launch && !opened) ++alerts_;
  return std::nullopt;
}

std::optional<Envelope> Flow::update(const WorldState &world, bool start, bool cancel, int64_t now) {
  if (!world.connected) {
    if (phase_ != Phase::stopped)
      text = world.status;
    return std::nullopt;
  }
  const auto path = session_path(realm.id);
  if (phase_ == Phase::start) {
    refusals = world.refusals;
    results = world.login_results;
    if (auto s = load_session(path, now)) {
      Envelope e;
      e.mutable_session_login()->set_token(s->token);
      e.mutable_session_login()->set_client_label(client_label());
      phase_ = Phase::session;
      text = "Logging in" + (s->discord_name.empty() ? std::string() : " as " + s->discord_name);
      return e;
    }
    phase_ = Phase::idle;
    text = "ENTER - Log in with Discord";
  }
  if (world.login_results != results) {
    results = world.login_results;
    const auto &r = world.login_result;
    if (!r.token().empty() && !save_session(path, {r.token(), int64_t(r.expires_at_unix()), r.discord_name()}))
      std::cerr << "client: could not save " << path << "; the next start asks Discord again" << std::endl;
    phase_ = Phase::done;
    text = "Logged in as " + r.discord_name();
    return std::nullopt;
  }
  if (world.refusals != refusals) {
    refusals = world.refusals;
    if (phase_ == Phase::session || phase_ == Phase::code) {
      const auto &detail = world.refusal_detail;
      if (detail == "expired" || detail == "revoked") {
        forget_session(path);
        return begin_browser();
      }
      if (detail.starts_with("banned:")) {
        forget_session(path);
        phase_ = Phase::stopped;
        text = player_text(detail);
        ++alerts_;
        return std::nullopt;
      }
      phase_ = Phase::idle;
      text = player_text(detail);
      if (text.empty())
        text = detail + ". ENTER to try again.";
      ++alerts_;
    }
  }
  if (phase_ == Phase::idle && start)
    return begin_browser();
  if (phase_ == Phase::browser) {
    if (cancel) {
      callback.reset();
      phase_ = Phase::idle;
      text = "Cancelled. ENTER - Log in with Discord";
      return std::nullopt;
    }
    if (std::chrono::steady_clock::now() > browser_until) {
      callback.reset();
      phase_ = Phase::idle;
      text = "Discord did not answer in 5 minutes. ENTER to try again.";
      ++alerts_;
      return std::nullopt;
    }
    std::string code;
    switch (callback->poll(code)) {
    case Callback::Result::waiting:
      return std::nullopt;
    case Callback::Result::code: {
      Envelope e;
      auto *l = e.mutable_discord_login();
      l->set_code(code);
      l->set_code_verifier(pkce.verifier);
      l->set_redirect_uri(callback->redirect_uri());
      l->set_client_label(client_label());
      callback.reset();
      phase_ = Phase::code;
      text = "Logging in with Discord";
      return e;
    }
    case Callback::Result::denied:
      callback.reset();
      phase_ = Phase::idle;
      text = "Discord login was cancelled. ENTER to try again.";
      ++alerts_;
      return std::nullopt;
    case Callback::Result::failed:
      callback.reset();
      phase_ = Phase::idle;
      text = "The login callback failed. ENTER to try again.";
      ++alerts_;
      return std::nullopt;
    }
  }
  return std::nullopt;
}
} // namespace n3e::login
