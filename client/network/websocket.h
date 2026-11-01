#pragma once
// The game wire through a WebSocket edge (specs/12-edge.md): an outer TLS connection
// to the edge, RFC 6455 binary frames, and an OpenSSL BIO that the inner (realm) TLS
// session reads and writes through. The inner session is the game wire's own, so the
// edge carries it without reading it.
#include "platform/net.h"
#include <openssl/ssl.h>
#include <string>
namespace n3e::ws {
// A non-blocking TCP connection to HOST:PORT, each address given 2 s; throws.
net::Socket connect_tcp(const std::string &host, const std::string &port);

struct Url {
  std::string host, port, path;
};
// wss://HOST[:PORT]/PATH; throws on anything else.
Url parse(const std::string &);

class Edge {
public:
  Edge() = default;
  Edge(const Edge &) = delete;
  Edge &operator=(const Edge &) = delete;
  ~Edge();
  // Connects to `url`, verifies the edge's certificate for its host with the same
  // trust as the realm's (`ca`, else the system's roots), and upgrades to the
  // n3e-wire.1 subprotocol by `end`; throws on failure.
  void open(const std::string &url, const std::string &ca, double end);
  // A BIO over the frames for the inner TLS session; the SSL it is set on owns it.
  BIO *bio();
  // True when inner bytes are waiting or arrive within `ms`, or the edge failed
  // (so the next read reports it).
  bool readable(int ms);
  // The deadline for the BIO's reads and writes, in now()'s seconds.
  double deadline = 0;

  int read(char *, int);
  int write(const char *, int);

private:
  net::Socket fd = net::BAD_SOCKET;
  SSL_CTX *ctx = nullptr;
  SSL *ssl = nullptr;
  std::string rx;      // outer bytes not yet parsed into frames
  std::string payload; // inner bytes not yet read
  bool failed = false;
  bool pump(bool block);
  bool parse_frames();
  bool frame(unsigned char opcode, const char *, size_t);
  bool write_all(const char *, size_t, double end);
  bool wait(int error, double end);
};

double now();
} // namespace n3e::ws
