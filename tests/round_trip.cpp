// RQ-136 (specs/12-edge.md, "The client's round trip"): the client's round-trip
// figures and connect line (client/network/round_trip.h), without a socket.
#include "network/round_trip.h"
#include <iostream>
#include <stdexcept>
namespace {
void check(bool ok, const std::string &what) {
  if (!ok) throw std::runtime_error(what);
}
} // namespace
int main() {
  using namespace n3e;
  {
    // Nearest rank, as tools/edge_rtt.py's percentile().
    std::vector<double> v{1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
    check(nearest_rank(v, 50) == 5 && nearest_rank(v, 95) == 10 && nearest_rank({7}, 95) == 7, "nearest rank");
  }
  {
    // An older server answers no ping: the pings are lost and no line is written.
    RoundTrip r(0);
    for (int i = 0; i < 120; ++i) check(r.ping(i) == uint64_t(i + 1), "nonces count from 1");
    check(r.minute(59.9).empty(), "a line before the minute");
    check(r.minute(60).empty() && r.end(120).empty(), "no echo, no figure");
  }
  {
    // A minute of echoes, 10.4 ms to 68.4 ms: one lost by being overtaken, one by age.
    RoundTrip r(0);
    for (int i = 0; i < 60; ++i) {
      double sent = i;
      auto nonce = r.ping(sent);
      if (i == 30) continue; // dropped by the server: overtaken by the next echo
      if (i == 59) continue; // never answered
      r.echo(nonce, sent + (10.4 + i) / 1000.);
    }
    r.echo(999, 59.5); // an echo of no outstanding ping is ignored
    auto line = r.minute(60);
    check(line == "client rtt span=minute secs=60 n=58 median_ms=38.4 p95_ms=66.4 worst_ms=68.4 lost=1", line);
    check(r.minute(61).empty(), "the next window starts afresh");
    r.ping(71); // the ping at 59 is now older than LOST_AFTER
    auto end = r.end(75);
    check(end == "client rtt span=session secs=75 n=58 median_ms=38.5 p95_ms=66.5 worst_ms=68.4 lost=2", end);
  }
  {
    // The session's line at the end follows the open window's.
    RoundTrip r(0);
    r.echo(r.ping(1), 1.0351);
    auto end = r.end(5);
    check(end == "client rtt span=minute secs=5 n=1 median_ms=35.1 p95_ms=35.1 worst_ms=35.1 lost=0\n"
                 "client rtt span=session secs=5 n=1 median_ms=35.1 p95_ms=35.1 worst_ms=35.1 lost=0",
          end);
  }
  {
    // Outstanding pings are bounded; the oldest is dropped as lost.
    RoundTrip r(0);
    for (size_t i = 0; i < RoundTrip::OUTSTANDING + 5; ++i) r.ping(i * .01);
    r.echo(RoundTrip::OUTSTANDING + 5, 1);
    // 5 dropped past the bound, the 31 still outstanding before the echoed one overtaken.
    auto end = r.end(2);
    check(end.rfind("client rtt span=minute secs=2 n=1 ", 0) == 0 && end.find(" lost=36\n") != std::string::npos, end);
  }
  {
    ConnectTimes t;
    t.edge = true;
    t.tcp = 14.5, t.edge_tls = 31.8, t.upgrade = 97.1, t.tls = 81.3, t.handshake = 35.7, t.snapshot = 271;
    check(t.line() == "client connect path=edge tcp_ms=14.5 edge_tls_ms=31.8 upgrade_ms=97.1 tls_ms=81.3 "
                      "handshake_ms=35.7 snapshot_ms=271.0 login=none",
          t.line());
    ConnectTimes d;
    d.tcp = 1, d.tls = 2, d.handshake = 3, d.snapshot = 6, d.login_kind = "session", d.login = 40.25;
    check(d.line() == "client connect path=tcp tcp_ms=1.0 tls_ms=2.0 handshake_ms=3.0 snapshot_ms=6.0 "
                      "login=session login_ms=40.2",
          d.line());
  }
  std::cout << "PASS client round trip: nonces, nearest-rank minute and session figures, lost pings, "
               "bounds, connect line\n";
}
