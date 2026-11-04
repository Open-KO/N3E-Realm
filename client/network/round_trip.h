#pragma once
// RQ-136 (specs/12-edge.md, "The client's round trip"): the client times its 1 s Ping
// against the server's echo, and its connect phases up to Characters, and writes them
// to its log (stderr) as key=value lines. Nothing of it is drawn on KO's screens (Q61).
// Header-only so tests/round_trip.cpp checks it without a socket.
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <string>
#include <utility>
#include <vector>
namespace n3e {
// The nearest-rank percentile `p` of sorted, non-empty `v` (as tools/edge_rtt.py).
inline double nearest_rank(const std::vector<double> &v, unsigned p) {
  size_t k = (size_t(p) * v.size() + 99) / 100;
  return v[std::clamp<size_t>(k, 1, v.size()) - 1];
}
inline std::string milliseconds(double ms) {
  char b[32];
  std::snprintf(b, sizeof b, "%.1f", ms);
  return b;
}
// One line on the client's log; a single write, so lines from two threads do not mix.
inline void log_line(const std::string &line) {
  std::fputs((line + "\n").c_str(), stderr);
  std::fflush(stderr);
}

class RoundTrip {
public:
  static constexpr double WINDOW = 60;      // seconds a "minute" line covers
  static constexpr double LOST_AFTER = 10;  // an echo later than this counts lost
  static constexpr size_t OUTSTANDING = 32; // pings awaiting their echo
  static constexpr size_t SAMPLES = 256;    // samples one window keeps
  static constexpr size_t BINS = 10000;     // the session's 1 ms bins; the last holds the rest

  explicit RoundTrip(double t) : window_start(t), session_start(t), bins(BINS) {}

  // The nonce for a Ping sent at `t`; never 0, which asks for no echo.
  uint64_t ping(double t) {
    while (!outstanding.empty() && t - outstanding.front().second > LOST_AFTER) drop();
    if (outstanding.size() >= OUTSTANDING) drop();
    outstanding.emplace_back(++nonce, t);
    return nonce;
  }
  // The echo of `echoed`, received at `t`. The server answers in order, so pings
  // before it were dropped (lost); an echo of no outstanding ping is ignored.
  void echo(uint64_t echoed, double t) {
    if (echoed == 0 || echoed > nonce) return;
    while (!outstanding.empty() && outstanding.front().first < echoed) drop();
    if (outstanding.empty() || outstanding.front().first != echoed) return;
    double ms = (t - outstanding.front().second) * 1000;
    outstanding.pop_front();
    if (window.size() < SAMPLES) window.push_back(ms);
    ++bins[std::min(size_t(std::max(ms, 0.)), BINS - 1)];
    ++session_n;
    session_worst = std::max(session_worst, ms);
  }
  // The window's line once WINDOW has passed since the last one; "" before then,
  // and for a window with no echo (an older server answers none).
  std::string minute(double t) {
    if (t - window_start < WINDOW) return {};
    return close_window(t);
  }
  // At the session's end: the open window's line, then the whole session's, each
  // only with an echo in it; "" for neither.
  std::string end(double t) {
    // Pings still in flight at the end are not counted lost.
    std::string w = close_window(t), s;
    if (session_n) {
      // Each bin is reported at its middle, so the session's figures are to 1 ms.
      auto rank = [&](unsigned p) {
        uint64_t k = std::max<uint64_t>(1, (uint64_t(p) * session_n + 99) / 100), seen = 0;
        for (size_t i = 0; i < BINS; ++i)
          if ((seen += bins[i]) >= k) return std::min(i + .5, session_worst);
        return session_worst;
      };
      s = line("session", t - session_start, session_n, rank(50), rank(95), session_worst, session_lost);
    }
    return w.empty() ? s : s.empty() ? w : w + "\n" + s;
  }

private:
  uint64_t nonce = 0;
  std::deque<std::pair<uint64_t, double>> outstanding; // (nonce, sent at)
  std::vector<double> window;
  double window_start, session_start;
  uint64_t window_lost = 0, session_lost = 0, session_n = 0;
  double session_worst = 0;
  std::vector<uint32_t> bins;

  void drop() {
    outstanding.pop_front();
    ++window_lost;
    ++session_lost;
  }
  std::string close_window(double t) {
    std::string s;
    if (!window.empty()) {
      std::sort(window.begin(), window.end());
      s = line("minute", t - window_start, window.size(), nearest_rank(window, 50), nearest_rank(window, 95),
               window.back(), window_lost);
    }
    window.clear();
    window_lost = 0;
    window_start = t;
    return s;
  }
  static std::string line(const char *span, double secs, uint64_t n, double median, double p95, double worst,
                          uint64_t lost) {
    return std::string("client rtt span=") + span + " secs=" + std::to_string(int64_t(secs + .5)) +
           " n=" + std::to_string(n) + " median_ms=" + milliseconds(median) + " p95_ms=" + milliseconds(p95) +
           " worst_ms=" + milliseconds(worst) + " lost=" + std::to_string(lost);
  }
};

// The connect phases of one connection, in milliseconds (negative: not reached).
struct ConnectTimes {
  bool edge = false;
  double tcp = -1, edge_tls = -1, upgrade = -1, tls = -1, handshake = -1, snapshot = -1, login = -1;
  std::string login_kind = "none";
  std::string line() const {
    std::string s = std::string("client connect path=") + (edge ? "edge" : "tcp");
    auto put = [&](const char *key, double ms) {
      if (ms >= 0) s += std::string(" ") + key + "=" + milliseconds(ms);
    };
    put("tcp_ms", tcp);
    if (edge) {
      put("edge_tls_ms", edge_tls);
      put("upgrade_ms", upgrade);
    }
    put("tls_ms", tls);
    put("handshake_ms", handshake);
    put("snapshot_ms", snapshot);
    s += " login=" + login_kind;
    put("login_ms", login);
    return s;
  }
};
} // namespace n3e
