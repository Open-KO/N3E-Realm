#pragma once
// The few socket calls the client makes, on POSIX sockets and on Winsock. A socket
// is a `Socket`; `BAD_SOCKET` marks none. Winsock starts on first use.
#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <cerrno>
#include <csignal>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
#endif
#include <stdexcept>
namespace n3e::net {
#ifdef _WIN32
using Socket = SOCKET;
constexpr Socket BAD_SOCKET = INVALID_SOCKET;
constexpr int NO_SIGNAL = 0;
#else
using Socket = int;
constexpr Socket BAD_SOCKET = -1;
constexpr int NO_SIGNAL = MSG_NOSIGNAL;
#endif

// Once per process, before any other call here.
inline void start() {
#ifdef _WIN32
  static const bool started = [] {
    WSADATA data;
    return WSAStartup(MAKEWORD(2, 2), &data) == 0;
  }();
  if (!started)
    throw std::runtime_error("Winsock did not start");
#else
  // A peer that closes mid-write is an error return, not a signal.
  static const bool ignored = [] { return std::signal(SIGPIPE, SIG_IGN) != SIG_ERR; }();
  (void)ignored;
#endif
}

inline void close(Socket s) {
#ifdef _WIN32
  ::closesocket(s);
#else
  ::close(s);
#endif
}

inline bool nonblocking(Socket s) {
#ifdef _WIN32
  u_long on = 1;
  return ::ioctlsocket(s, FIONBIO, &on) == 0;
#else
  int flags = ::fcntl(s, F_GETFL, 0);
  return flags >= 0 && ::fcntl(s, F_SETFL, flags | O_NONBLOCK) == 0;
#endif
}

// The last call failed only because it would have blocked (or a connect is under way).
inline bool would_block() {
#ifdef _WIN32
  int e = WSAGetLastError();
  return e == WSAEWOULDBLOCK || e == WSAEINPROGRESS || e == WSAEINTR;
#else
  return errno == EAGAIN || errno == EWOULDBLOCK || errno == EINPROGRESS || errno == EINTR;
#endif
}

// Waits up to `ms` for `events` (POLLIN, POLLOUT) on one socket; > 0 when ready.
inline int wait(Socket s, short events, int ms) {
  pollfd p{};
  p.fd = s;
  p.events = events;
#ifdef _WIN32
  return ::WSAPoll(&p, 1, ms);
#else
  return ::poll(&p, 1, ms);
#endif
}

// A listening socket's port is ours alone: Windows' SO_REUSEADDR would let another
// process bind it too, so there it is SO_EXCLUSIVEADDRUSE. On Linux SO_REUSEADDR
// only binds past an earlier TIME_WAIT and still fails if something listens.
inline void exclusive_port(Socket s) {
  int on = 1;
#ifdef _WIN32
  ::setsockopt(s, SOL_SOCKET, SO_EXCLUSIVEADDRUSE, reinterpret_cast<const char *>(&on), sizeof on);
#else
  ::setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &on, sizeof on);
#endif
}

inline bool no_delay(Socket s) {
  int on = 1;
  return ::setsockopt(s, IPPROTO_TCP, TCP_NODELAY, reinterpret_cast<const char *>(&on), sizeof on) == 0;
}

// The pending error of a non-blocking connect; 0 once connected.
inline int pending_error(Socket s) {
  int err = 0;
  socklen_t n = sizeof err;
  if (::getsockopt(s, SOL_SOCKET, SO_ERROR, reinterpret_cast<char *>(&err), &n) != 0)
    return -1;
  return err;
}
} // namespace n3e::net
