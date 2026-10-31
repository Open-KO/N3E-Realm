#include "assets/assets.h"
#include "platform/net.h"
#include "platform/tls.h"
#include "wire.pb.h"
#include <iostream>
#include <memory>
#include <openssl/ssl.h>
#include <stdexcept>
namespace {
void check(bool b, const char *m) {
  if (!b)
    throw std::runtime_error(m);
}
} // namespace
void handshake(const n3e::Release &release, const std::string &endpoint,
               const std::string &ca) {
  n3e::net::start();
  auto colon = endpoint.rfind(':');
  check(colon != std::string::npos, "HOST:PORT required");
  auto host = endpoint.substr(0, colon), port = endpoint.substr(colon + 1);
  addrinfo hints{}, *raw = nullptr;
  hints.ai_socktype = SOCK_STREAM;
  check(getaddrinfo(host.c_str(), port.c_str(), &hints, &raw) == 0,
        "DNS failed");
  std::unique_ptr<addrinfo, decltype(&freeaddrinfo)> addresses(raw,
                                                               freeaddrinfo);
  auto fd = n3e::net::BAD_SOCKET;
  for (auto *a = raw; a; a = a->ai_next) {
    fd = ::socket(a->ai_family, a->ai_socktype, a->ai_protocol);
    if (fd == n3e::net::BAD_SOCKET)
      continue;
#ifdef _WIN32
    DWORD tv = 3000;
#else
    timeval tv{3, 0};
#endif
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char *>(&tv), sizeof tv);
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, reinterpret_cast<const char *>(&tv), sizeof tv);
    if (::connect(fd, a->ai_addr, int(a->ai_addrlen)) == 0)
      break;
    n3e::net::close(fd);
    fd = n3e::net::BAD_SOCKET;
  }
  check(fd != n3e::net::BAD_SOCKET, "connect failed");
  struct Socket {
    n3e::net::Socket fd;
    ~Socket() { n3e::net::close(fd); }
  } socket_guard{fd};
  std::unique_ptr<SSL_CTX, decltype(&SSL_CTX_free)> ctx(
      SSL_CTX_new(TLS_client_method()), SSL_CTX_free);
  check(bool(ctx), "TLS context");
  SSL_CTX_set_min_proto_version(ctx.get(), TLS1_2_VERSION);
  SSL_CTX_set_verify(ctx.get(), SSL_VERIFY_PEER, nullptr);
  check(n3e::tls::trust(ctx.get(), ca), "CA failed");
  std::unique_ptr<SSL, decltype(&SSL_free)> ssl(SSL_new(ctx.get()), SSL_free);
  check(bool(ssl), "TLS allocation");
  SSL_set_tlsext_host_name(ssl.get(), host.c_str());
  check(SSL_set1_host(ssl.get(), host.c_str()) == 1, "hostname policy");
  SSL_set_fd(ssl.get(), int(fd));
  check(SSL_connect(ssl.get()) == 1 &&
            SSL_get_verify_result(ssl.get()) == X509_V_OK,
        "TLS verification failed");
  n3e::Envelope e;
  auto *h = e.mutable_handshake();
  h->set_version(release.protocol);
  h->set_game(release.game);
  h->set_content(release.hash);
  auto b = e.SerializeAsString();
  uint32_t n = htonl(b.size());
  std::string wire((char *)&n, 4);
  wire += b;
  for (size_t at = 0; at < wire.size();) {
    int sent = SSL_write(ssl.get(), wire.data() + at, wire.size() - at);
    check(sent > 0, "TLS write");
    at += sent;
  }
  auto read = [&](char *p, size_t size) {
    while (size) {
      int got = SSL_read(ssl.get(), p, size);
      check(got > 0, "TLS read");
      p += got;
      size -= got;
    }
  };
  read((char *)&n, 4);
  n = ntohl(n);
  check(n > 0 && n <= 65536, "frame bound");
  b.resize(n);
  read(b.data(), n);
  check(e.ParseFromString(b), "malformed reply");
  if (e.has_error())
    throw std::runtime_error("server rejected: " + e.error().detail());
  check(e.has_snapshot(), "handshake reply");
  std::cout << "verified TLS handshake accepted; no authenticated character "
               "session yet\n";
}
