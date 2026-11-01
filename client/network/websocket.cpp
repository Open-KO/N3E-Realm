#include "websocket.h"
#include "platform/tls.h"
#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstring>
#include <memory>
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <openssl/sha.h>
#include <stdexcept>
namespace n3e::ws {
namespace {
void check(bool b, const char *m) {
  if (!b)
    throw std::runtime_error(m);
}
// Spec 12: the subprotocol, and the largest frame either side accepts.
constexpr const char *PROTOCOL = "n3e-wire.1";
constexpr size_t MAX_FRAME = 64 * 1024 + 1024;
constexpr size_t MAX_HEAD = 8 * 1024;

std::string base64(const unsigned char *p, size_t n) {
  std::string out(4 * ((n + 2) / 3) + 1, '\0');
  out.resize(EVP_EncodeBlock(reinterpret_cast<unsigned char *>(out.data()), p, int(n)));
  return out;
}
std::string lower(std::string s) {
  std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return char(std::tolower(c)); });
  return s;
}
// The value of header `name` in an HTTP response head; "" when absent.
std::string header(const std::string &head, const std::string &name) {
  auto h = lower(head), key = "\r\n" + name + ":";
  auto at = h.find(key);
  if (at == std::string::npos)
    return "";
  at += key.size();
  auto end = head.find("\r\n", at);
  auto v = head.substr(at, end - at);
  v.erase(0, v.find_first_not_of(" \t"));
  v.erase(v.find_last_not_of(" \t") + 1);
  return v;
}

BIO_METHOD *method() {
  static BIO_METHOD *m = [] {
    auto *m = BIO_meth_new(BIO_get_new_index() | BIO_TYPE_SOURCE_SINK, "n3e websocket");
    BIO_meth_set_write(m, [](BIO *b, const char *p, int n) {
      return static_cast<Edge *>(BIO_get_data(b))->write(p, n);
    });
    BIO_meth_set_read(m, [](BIO *b, char *p, int n) {
      return static_cast<Edge *>(BIO_get_data(b))->read(p, n);
    });
    BIO_meth_set_ctrl(m, [](BIO *, int cmd, long, void *) -> long { return cmd == BIO_CTRL_FLUSH; });
    BIO_meth_set_create(m, [](BIO *b) {
      BIO_set_init(b, 1);
      return 1;
    });
    return m;
  }();
  return m;
}
} // namespace

double now() {
  return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

net::Socket connect_tcp(const std::string &host, const std::string &port) {
  addrinfo hints{}, *raw = nullptr;
  hints.ai_socktype = SOCK_STREAM;
  check(getaddrinfo(host.c_str(), port.c_str(), &hints, &raw) == 0, "DNS failed");
  std::unique_ptr<addrinfo, decltype(&freeaddrinfo)> addresses(raw, freeaddrinfo);
  for (auto *a = raw; a; a = a->ai_next) {
    auto fd = ::socket(a->ai_family, a->ai_socktype, a->ai_protocol);
    if (fd == net::BAD_SOCKET)
      continue;
    if (net::nonblocking(fd)) {
      int r = ::connect(fd, a->ai_addr, int(a->ai_addrlen));
      if ((r == 0 || net::would_block()) && net::wait(fd, POLLOUT, 2000) > 0 && net::pending_error(fd) == 0) {
        check(net::no_delay(fd), "TCP_NODELAY failed");
        return fd;
      }
    }
    net::close(fd);
  }
  throw std::runtime_error("connect failed");
}

Url parse(const std::string &url) {
  const std::string scheme = "wss://";
  check(url.compare(0, scheme.size(), scheme) == 0, "the edge must be a wss:// URL");
  auto rest = url.substr(scheme.size());
  auto slash = rest.find('/');
  Url u;
  u.path = slash == std::string::npos ? "/" : rest.substr(slash);
  auto authority = rest.substr(0, slash);
  auto colon = authority.rfind(':');
  u.host = colon == std::string::npos ? authority : authority.substr(0, colon);
  u.port = colon == std::string::npos ? "443" : authority.substr(colon + 1);
  check(!u.host.empty() && u.host.find_first_of("@[] ") == std::string::npos &&
            !u.port.empty() && u.port.find_first_not_of("0123456789") == std::string::npos &&
            u.path.find_first_of(" \r\n") == std::string::npos,
        "the edge must be wss://HOST[:PORT]/PATH");
  return u;
}

Edge::~Edge() {
  if (ssl)
    SSL_free(ssl);
  if (ctx)
    SSL_CTX_free(ctx);
  if (fd != net::BAD_SOCKET)
    net::close(fd);
}

bool Edge::wait(int error, double end) {
  int ms = int((end - now()) * 1000);
  return ms > 0 && net::wait(fd, short(error == SSL_ERROR_WANT_WRITE ? POLLOUT : POLLIN), ms) > 0;
}

void Edge::open(const std::string &url, const std::string &ca, double end) {
  auto u = parse(url);
  fd = connect_tcp(u.host, u.port);
  ctx = SSL_CTX_new(TLS_client_method());
  check(ctx, "TLS context");
  SSL_CTX_set_min_proto_version(ctx, TLS1_2_VERSION);
  SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, nullptr);
  check(tls::trust(ctx, ca), ca.empty() ? "no system CA certificates" : "CA failed");
  ssl = SSL_new(ctx);
  check(ssl, "TLS allocation");
  SSL_set_fd(ssl, int(fd));
  SSL_set_tlsext_host_name(ssl, u.host.c_str());
  check(SSL_set1_host(ssl, u.host.c_str()) == 1, "hostname policy");
  for (;;) {
    int r = SSL_connect(ssl);
    if (r == 1)
      break;
    int e = SSL_get_error(ssl, r);
    check((e == SSL_ERROR_WANT_READ || e == SSL_ERROR_WANT_WRITE) && wait(e, end), "edge TLS failed");
  }
  check(SSL_get_verify_result(ssl) == X509_V_OK, "edge TLS verification failed");

  unsigned char nonce[16];
  check(RAND_bytes(nonce, sizeof nonce) == 1, "random");
  auto key = base64(nonce, sizeof nonce);
  auto host = u.port == "443" ? u.host : u.host + ":" + u.port;
  auto request = "GET " + u.path + " HTTP/1.1\r\nHost: " + host +
                 "\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: " + key +
                 "\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: " + PROTOCOL +
                 "\r\nUser-Agent: n3e-client\r\n\r\n";
  check(write_all(request.data(), request.size(), end), "edge upgrade failed");
  size_t head_end;
  while ((head_end = rx.find("\r\n\r\n")) == std::string::npos) {
    check(rx.size() < MAX_HEAD, "edge upgrade failed");
    char b[1024];
    int r = SSL_read(ssl, b, sizeof b);
    if (r > 0) {
      rx.append(b, size_t(r));
      continue;
    }
    int e = SSL_get_error(ssl, r);
    check((e == SSL_ERROR_WANT_READ || e == SSL_ERROR_WANT_WRITE) && wait(e, end), "edge upgrade failed");
  }
  auto head = rx.substr(0, head_end + 2);
  rx.erase(0, head_end + 4);
  if (head.compare(0, 13, "HTTP/1.1 101 ") != 0)
    throw std::runtime_error("edge refused (" + head.substr(0, head.find("\r\n")) + ")");
  unsigned char digest[SHA_DIGEST_LENGTH];
  auto accept = key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
  SHA1(reinterpret_cast<const unsigned char *>(accept.data()), accept.size(), digest);
  check(header(head, "sec-websocket-accept") == base64(digest, sizeof digest) &&
            header(head, "sec-websocket-protocol") == PROTOCOL,
        "edge upgrade failed");
}

BIO *Edge::bio() {
  BIO *b = BIO_new(method());
  check(b, "BIO allocation");
  BIO_set_data(b, this);
  return b;
}

bool Edge::write_all(const char *p, size_t n, double end) {
  while (n) {
    int r = SSL_write(ssl, p, int(n));
    if (r > 0) {
      p += r;
      n -= size_t(r);
      continue;
    }
    int e = SSL_get_error(ssl, r);
    if (!(e == SSL_ERROR_WANT_READ || e == SSL_ERROR_WANT_WRITE) || !wait(e, end))
      return false;
  }
  return true;
}

// One masked frame from the client (RFC 6455 5.3).
bool Edge::frame(unsigned char opcode, const char *p, size_t n) {
  std::string f;
  f.reserve(n + 14);
  f += char(0x80 | opcode);
  if (n < 126)
    f += char(0x80 | n);
  else if (n <= 0xFFFF) {
    f += char(0x80 | 126);
    f += char(n >> 8);
    f += char(n & 0xFF);
  } else {
    f += char(0x80 | 127);
    for (int i = 7; i >= 0; --i)
      f += char((uint64_t(n) >> (8 * i)) & 0xFF);
  }
  unsigned char mask[4];
  if (RAND_bytes(mask, 4) != 1)
    return false;
  f.append(reinterpret_cast<char *>(mask), 4);
  for (size_t i = 0; i < n; ++i)
    f += char(p[i] ^ mask[i % 4]);
  return write_all(f.data(), f.size(), deadline);
}

// Complete frames in `rx`: data into `payload`, pings answered; false on a frame
// the edge must not send (spec 12, "WebSocket") or a close.
bool Edge::parse_frames() {
  for (;;) {
    if (rx.size() < 2)
      return true;
    auto *b = reinterpret_cast<const unsigned char *>(rx.data());
    unsigned opcode = b[0] & 0x0F;
    bool masked = b[1] & 0x80;
    uint64_t n = b[1] & 0x7F;
    size_t at = 2;
    if (n == 126) {
      if (rx.size() < 4)
        return true;
      n = uint64_t(b[2]) << 8 | b[3];
      at = 4;
    } else if (n == 127) {
      if (rx.size() < 10)
        return true;
      n = 0;
      for (int i = 0; i < 8; ++i)
        n = n << 8 | b[2 + i];
      at = 10;
    }
    if (n > MAX_FRAME)
      return false;
    size_t mask_at = at;
    if (masked)
      at += 4;
    if (rx.size() < at + n)
      return true;
    std::string data = rx.substr(at, size_t(n));
    if (masked)
      for (size_t i = 0; i < data.size(); ++i)
        data[i] = char(data[i] ^ rx[mask_at + i % 4]);
    rx.erase(0, at + size_t(n));
    switch (opcode) {
    case 0x0:
    case 0x2:
      payload += data;
      break;
    case 0x9:
      if (data.size() > 125 || !frame(0xA, data.data(), data.size()))
        return false;
      break;
    case 0xA:
      break;
    default: // text, close, reserved
      return false;
    }
  }
}

// Reads what the outer connection has; with `block`, waits until there is inner
// payload or the deadline. False once the edge failed.
bool Edge::pump(bool block) {
  while (!failed) {
    if (!parse_frames()) {
      failed = true;
      break;
    }
    if (!payload.empty())
      return true;
    if (rx.size() > MAX_FRAME + 14) {
      failed = true;
      break;
    }
    char b[16 * 1024];
    int r = SSL_read(ssl, b, sizeof b);
    if (r > 0) {
      rx.append(b, size_t(r));
      continue;
    }
    int e = SSL_get_error(ssl, r);
    if (!(e == SSL_ERROR_WANT_READ || e == SSL_ERROR_WANT_WRITE)) {
      failed = true;
      break;
    }
    if (!block)
      return true;
    if (!wait(e, deadline)) {
      failed = true;
      break;
    }
  }
  return false;
}

int Edge::read(char *p, int n) {
  if (payload.empty() && !pump(true))
    return -1;
  int k = int(std::min(payload.size(), size_t(n)));
  std::memcpy(p, payload.data(), size_t(k));
  payload.erase(0, size_t(k));
  return k;
}

int Edge::write(const char *p, int n) {
  if (failed || n <= 0)
    return failed ? -1 : 0;
  // Inner TLS records are at most 16 KiB plus overhead; one frame each.
  if (!frame(0x2, p, size_t(n))) {
    failed = true;
    return -1;
  }
  return n;
}

bool Edge::readable(int ms) {
  if (!payload.empty() || failed)
    return true;
  deadline = now() + 2; // for a pong written while pumping
  if (!pump(false))
    return true;
  if (!payload.empty())
    return true;
  if (SSL_pending(ssl) == 0 && net::wait(fd, POLLIN, ms) <= 0)
    return false;
  return !pump(false) || !payload.empty();
}
} // namespace n3e::ws
