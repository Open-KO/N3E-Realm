"""Checks for tests/host_network.py, the host network record of a failed live run
(PQ-456), without touching the host's network: the changed path is driven by a
stub reader and synthetic `ip` and `nft` output, the journal by stub entries.
The real host is only read (ip rule, ip route), never changed. make live shows
the real path (a full run with no host change reports no flag)."""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import host_network as hn  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + str(detail)[-1500:]}")
    if not ok:
        FAILS.append(name)


ROUTES = """default via 192.168.1.1 dev enp3s0 proto dhcp src 192.168.1.21 metric 100
172.17.0.0/16 dev docker0 proto kernel scope link src 172.17.0.1
172.20.0.0/16 dev br-0a1b2c3d4e5f proto kernel scope link src 172.20.0.1 linkdown
192.168.1.0/24 dev enp3s0 proto kernel scope link src 192.168.1.21 metric 100
2001:db8::/64 dev enp3s0 proto ra metric 100 expires 1795sec pref medium
fe80::/64 dev enp3s0 proto kernel metric 1024 pref medium
"""
# The run's own Docker activity: a pool network's bridge comes up (linkdown
# gone), a new bridge and veths appear, the RA route's lifetime counts down.
ROUTES_DOCKER = """default via 192.168.1.1 dev enp3s0 proto dhcp src 192.168.1.21 metric 100
172.17.0.0/16 dev docker0 proto kernel scope link src 172.17.0.1
172.20.0.0/16 dev br-0a1b2c3d4e5f proto kernel scope link src 172.20.0.1
172.21.0.0/16 dev br-5f4e3d2c1b0a proto kernel scope link src 172.21.0.1
192.168.1.0/24 dev enp3s0 proto kernel scope link src 192.168.1.21 metric 100
2001:db8::/64 dev enp3s0 proto ra metric 100 expires 1201sec pref medium
fe80::/64 dev enp3s0 proto kernel metric 1024 pref medium
fe80::/64 dev veth3cba2b2 proto kernel metric 256 pref medium
fe80::/64 dev vethd010a0a proto kernel metric 256 pref medium
"""
ROUTES_VPN = ROUTES + "default dev nordlynx table 205 scope link\n185.1.2.3 via 192.168.1.1 dev enp3s0\n"

NFT = """table ip filter {
	chain DOCKER {
		ip daddr 172.17.0.2 iifname != "docker0" oifname "docker0" tcp dport 5432 counter packets 4 bytes 240 accept
	}
	chain DOCKER-USER {
	}
	chain FORWARD {
		type filter hook forward priority filter; policy drop;
		counter packets 11245 bytes 2717847 jump DOCKER-USER
		iifname "br-0a1b2c3d4e5f" oifname != "br-0a1b2c3d4e5f" counter packets 0 bytes 0 accept
	}
	chain INPUT {
		type filter hook input priority filter; policy accept;
		tcp dport 22 accept
	}
}
table ip docker-bridges {
	chain forward {
		iifname "br-5f4e3d2c1b0a" accept
	}
}
"""
NFT_DOCKER = NFT.replace(
    'tcp dport 5432 counter packets 4 bytes 240 accept\n',
    'tcp dport 5432 counter packets 4 bytes 240 accept\n'
    '\t\tip daddr 172.17.0.3 iifname != "docker0" oifname "docker0" tcp dport 6379 accept\n').replace(
    "counter packets 11245 bytes 2717847", "counter packets 99999 bytes 123456789")
NFT_VPN = NFT + """table inet nordvpn {
	chain output {
		type route hook output priority mangle; policy drop;
		meta mark 0xe1f1 accept
	}
}
"""


def digests():
    route = [hn.digest(hn.host_lines("ip route", t)) for t in (ROUTES, ROUTES_DOCKER, ROUTES_VPN)]
    check("routes: Docker interfaces (docker0, br-*, veth*), linkdown on a bridge and route lifetimes leave the "
          "digest alone", route[0] == route[1], hn.host_lines("ip route", ROUTES_DOCKER))
    check("routes: a VPN table route and a route to the VPN server change the digest", route[0] != route[2])
    nft = [hn.digest(hn.host_lines("nft ruleset", t)) for t in (NFT, NFT_DOCKER, NFT_VPN)]
    lines = hn.host_lines("nft ruleset", NFT)
    check("nft: Docker's chains, tables, per-container rules and counters leave the digest alone",
          nft[0] == nft[1] and not any(re.search(r"docker|DOCKER|br-|counter", l) for l in lines)
          and any("tcp dport 22 accept" in l for l in lines), lines)
    check("nft: a VPN's output chain with policy drop changes the digest", nft[0] != nft[2])


class Stub:
    """A reader that plays back states: one per sample."""

    def __init__(self, states):
        self.states, self.i = states, 0

    def __call__(self, skip=()):
        state = self.states[min(self.i, len(self.states) - 1)]
        self.i += 1
        return {s: v for s, v in state.items() if s not in skip}


def state(route=ROUTES, nft=None):
    return {"ip rule": (["0: from all lookup local"], None), "ip route": (hn.host_lines("ip route", route), None),
            "nft ruleset": (hn.host_lines("nft ruleset", nft), None) if nft else (None, "nft: exit 1: not permitted")}


class Clock:
    def __init__(self):
        self.t = 1793234700.0

    def __call__(self):
        self.t += 2
        return self.t


def watch(states):
    w = hn.Watch(read=Stub(states), every=3600, clock=Clock())
    w.start()
    for _ in states[2:]:
        w._sample()  # the samples the thread would take
    return w.stop()


def watching():
    still = watch([state(), state(ROUTES_DOCKER), state(ROUTES_DOCKER)])
    check("a run whose only change is its own Docker activity is unchanged", not still.changed and not still.changes,
          still.summary())
    check("an unreadable source (nft without root) is named and left out, never an error",
          "nft ruleset" in still.unreadable and still.summary()["sources"]["nft ruleset"]["start"] is None,
          still.summary())
    blip = watch([state(), state(ROUTES_VPN), state(), state()])
    check("a VPN that connects and disconnects within the run is a change, though start and end match",
          blip.changed and len(blip.changes) == 2 and blip.start_state == blip.end_state, blip.summary())
    fw = watch([state(nft=NFT), state(nft=NFT_DOCKER), state(nft=NFT_VPN)])
    check("a firewall change in a readable ruleset is a change", fw.changed and fw.changes[-1][1] == "nft ruleset",
          fw.summary())

    def broken(skip=()):
        raise OSError("no ip")
    w = hn.Watch(read=broken, every=3600).start().stop()
    check("a reader that fails is reported, never a change or an error", not w.changed and w.unreadable, w.unreadable)


FP = "a3f1" * 16  # a 64-hex fingerprint
KEY = "PtEkq9Xb2LmN0vWc7YzR4uHs1JdK8fGa3eQo6iTn5s0s="
# What a record must never print, from the reviewer's adversarial lines (PQ-456
# review round 1) and the real 2026-10-28 journal.
SECRETS = ["9999", "Atlantis", "Exampleton", "zz1234", "zz9999", "nordvpn.com", "bob", "alice", "example",
           "Lab Net", "185.1.2.3", "8.8.8.8", "93, 184", FP, KEY[:12], "test-box", "/etc/", "aa:bb"]


def masking():
    lines = {
        "185.1.2.3 via 192.168.1.1 dev wg-zz1234 table 205": "<public-ip> via 192.168.1.1 dev <dev> table 205",
        "default dev nordlynx table 205 scope link": "default dev nordlynx table 205 scope link",
        "from all fwmark 0xe1f1 lookup 205": "from all fwmark 0xe1f1 lookup 205",
        "from 10.5.0.2 iif wg-zz1234 lookup main": "from 10.5.0.2 iif <dev> lookup main",
        '\t\toifname "wg-zz1234" ip daddr 185.1.2.3. accept': '\t\toifname "<dev>" ip daddr <public-ip>. accept',
        '\t\toifname "nordlynx" meta mark 0xe1f1 accept comment "office link zz1234"':
            '\t\toifname "nordlynx" meta mark 0xe1f1 accept comment "<dev>"',
        f"\t\tset peers {{ elements = {{ {KEY}, {FP} }} }}": "\t\tset peers { elements = { <token>, <token> } }",
        "2001:4860:4860::8888 via fe80::1 dev enp3s0 proto static": "<public-ip> via fe80::1 dev enp3s0 proto static",
        "10.0.0.0/8 via 192.168.1.1 dev enp3s0 lladdr aa:bb:cc:dd:ee:ff": "10.0.0.0/8 via 192.168.1.1 dev enp3s0 lladdr <mac>",
        "unreachable 8.8.8.8 proto static # zz1234.example.com": "unreachable <public-ip> proto static # <host>",
    }
    for raw, want in lines.items():
        got = hn.mask(raw)
        check(f"mask (state diff lines): {want.strip()}", got == want, got)
    check("mask: a public address ending a sentence is masked", hn.mask("Connected to 185.1.2.3.") ==
          "Connected to <public-ip>.", hn.mask("Connected to 185.1.2.3."))
    check("a long state line is cut", len(hn.mask("x" * 5000)) == hn.MAX_LINE)


def journal():
    t = 1793234776.0
    go = "2026/10/28 20:46:16.851 {}.go:48: [Info] "
    printed = [  # (unit, message, the exact text the record prints)
        ("nordvpnd.service", go.format("firewall") + "[FW] configuring firewall", "[FW] configuring firewall"),
        ("nordvpnd.service", go.format("logger") + "Setting the routing rules up", "Setting the routing rules up"),
        ("nordvpnd.service", go.format("iprule") + "Selected candidate for new rule priority:  32765",
         "new ip rule priority 32765"),
        ("nordvpnd.service", go.format("logger") + "connected to zz9999.nordvpn.com", "connected to <server>"),
        ("nordvpnd.service", go.format("state") + "notifying about data connect change event: {Status:{State:CONNECTED "
         "VPNProtocol:VPN_PROTOCOL_NORDLYNX IP:185.1.2.3 Name:Atlantis #9999 Hostname:zz9999.nordvpn.com Country:Atlantis "
         "City: Exampleton}", "connection state CONNECTED"),
        ("nordvpnd.service", go.format("logger") + "stopping vpn to zz1234", "stopping vpn"),
        ("NetworkManager.service", "<info>  [1.2] device (enp3s0): state change: activated -> deactivating "
         "(reason 'connection-removed', managed-type: 'full')",
         "device (enp3s0): state change: activated -> deactivating (reason 'connection-removed')"),
        ("NetworkManager.service", "<info>  [1.2] device (zz1234-wg): state change: config -> ip-config (reason 'none')",
         "device (<dev>): state change: config -> ip-config (reason 'none')"),
        ("NetworkManager.service", "<info>  [1.2] policy: set 'Lab Net' (wlan0) as default for IPv4 routing and DNS",
         "policy: (wlan0) is the default for IPv4"),
        ("NetworkManager.service", "<info>  [1.2] manager: (nordlynx): new WireGuard device (/org/freedesktop/x/1)",
         "manager: (nordlynx): new WireGuard device"),
        ("systemd-resolved.service", "nordlynx: Bus client set DNS server list to: 9.9.9.9, 8.8.8.8",
         "(nordlynx): bus client set DNS server list"),
        ("systemd-resolved.service", "Switching to DNS server 8.8.8.8 for interface enp3s0.", "Switching to DNS server"),
        ("docker.service", 'time="x" level=info msg="Processing signal \'terminated\'"',
         "Processing signal 'terminated' (info)"),
        ("docker.service", 'time="x" level=warning msg="Firewalld: reloaded, re-creating rules for zz1234"',
         "Firewalld reload (warning)"),
        ("wpa_supplicant.service", "wlan0: CTRL-EVENT-CONNECTED - Connection to aa:bb:cc:dd:ee:ff completed "
         "[id=0 id_str=] SSID=\"Lab Net\"", "CTRL-EVENT-CONNECTED"),
        ("firewalld.service", "ERROR: COMMAND_FAILED: '/usr/bin/nft' zz1234", "activity (message withheld)"),
        ("openvpn-client@zz1234.service", "Initialization Sequence Completed with 185.1.2.3",
         "Initialization Sequence Completed"),
        ("systemd:nordvpnd.service", "Stopping NordVPN Daemon for bob...", "Stopping nordvpnd"),
        ("systemd:wg-quick@zz1234.service", "Started WireGuard via wg-quick(8) for zz1234.", "Started wg-quick@"),
    ]
    withheld = [  # (unit, message): the reviewer's adversarial lines and the real dumps
        ("nordvpnd.service", go.format("libtelio") + f"Remote gRPC server (IpAddress(V4(Ipv4Addr([93, 184, 215, 14])))) "
         f"sha256 fingerprint: {FP}"),
        ("systemd-resolved.service", "Connected to 185.1.2.3."),
        ("nordvpnd.service", go.format("rpc") + "connecting to server zz1234"),
        ("nordvpnd.service", go.format("rpc") + "server_tag=zz1234"),
        ("nordvpnd.service", go.format("rpc") + f"pubkey={KEY}"),
        ("nordvpnd.service", go.format("rpc") + f"WireGuard public key {KEY}"),
        ("NetworkManager.service", "<info>  [1.2] hostname: hostname changed from arch to test-box"),
        ("NetworkManager.service", "<info>  [1.2] dhcp4 (enp3s0): option host_name => 'test-box'"),
        ("NetworkManager.service", "<info>  [1.2] user bob logged in as alice@example.com"),
        ("nordvpnd.service", go.format("logger") + "connected to zz9999.nordvpn.com via 185.1.2.3"),
        ("nordvpnd.service", "Request: HTTP/1.1 GET https://api.nordvpn.com/v1/servers?token=abc"),
        ("nordvpnd.service", "200 - map[Set-Cookie:[session=secret]]"),
        ("nordvpnd.service", "\t\tmeta l4proto ipv6-icmp accept"),
        ("nordvpnd.service", "System Info:Linux test-box 7.2.8 x86_64 GNU/Linux"),
        ("myvpn-zz1234.service", "tunnel up to zz1234 at 185.1.2.3"),
        ("iwd.service", "Connected to Lab Net (aa:bb:cc:dd:ee:ff)"),
        ("systemd:nordvpnd.service", "nordvpnd.service: Consumed 3s CPU time for bob."),
    ]
    docker = [
        ("NetworkManager.service", "<info>  [1.0] manager: (vethddac5de): new Veth device"),
        ("docker.service", 'time="x" level=info msg="sbJoin" ep=n3e-p2-redis-1 net=n3e-test-net-0 nid=442f2f2d10d2 '
         'eid=fe9749 br-0a1b2c3d4e5f'),
    ]
    entries = [(t + i, u, m) for i, (u, m, _) in enumerate(printed)] + [(t, u, m) for u, m in withheld + docker]
    kept, omitted = hn.journal_lines(entries)
    want = [w for _, _, w in printed]
    got = [k.split(": ", 1)[1] for k in kept]
    check("journal: an allowlisted line prints its template's fixed text, nothing of the message",
          got == want, "\n".join(f"{g!r} != {w!r}" for g, w in zip(got, want) if g != w) or (got, want))
    units = [k.split(" ", 1)[1].split(": ", 1)[0] for k in kept]
    check("journal: units print by family; an instance or an unknown VPN unit name never prints",
          units[-3:] == ["openvpn-client@", "systemd", "systemd"] and "openvpn-client@zz1234" not in "\n".join(kept)
          and omitted["withheld"].get("vpn unit") == 1, (units, omitted))
    text = "\n".join(kept) + json.dumps(omitted)
    check("journal: the adversarial lines are withheld and counted; Docker interface lines counted apart",
          sum(omitted["withheld"].values()) == len(withheld) and omitted["docker"] == len(docker), omitted)
    leaks = [s for s in SECRETS if s in text]
    check("journal: no server, host, address, key, fingerprint, SSID, user or email reaches the record", not leaks, leaks)
    many, _ = hn.journal_lines([(t + i, "nordvpnd.service", go.format("logger") + "starting vpn") for i in range(1000)])
    check("journal: a window keeps its first and last lines only", len(many) == hn.MAX_WINDOW_LINES + 1
          and many[0].startswith(hn._utc(t)) and many[-1].startswith(hn._utc(t + 999))
          and "left out here" in many[hn.MAX_WINDOW_LINES // 2], many[:3])

    class Done:
        returncode, stdout, stderr = 0, b"", b""
    seen = []

    def fake_run(argv, **kw):
        seen.append(argv)
        d = Done()
        d.stdout = (json.dumps({"MESSAGE": "logger.go:35: [Info] stopping vpn", "_SYSTEMD_UNIT": "nordvpnd.service",
                                "__REALTIME_TIMESTAMP": "1793234839000000"}) + "\n"
                    + json.dumps({"MESSAGE": "Stopped NordVPN Daemon.", "_SYSTEMD_UNIT": "init.scope",
                                  "UNIT": "nordvpnd.service", "__REALTIME_TIMESTAMP": "1793234839000000"}) + "\n"
                    + json.dumps({"MESSAGE": "Started Session 4.", "_SYSTEMD_UNIT": "init.scope",
                                  "UNIT": "session-4.scope", "__REALTIME_TIMESTAMP": "1793234839000000"}) + "\n"
                    + json.dumps({"MESSAGE": [104, 105], "_SYSTEMD_UNIT": "NetworkManager.service",
                                           "__REALTIME_TIMESTAMP": "1793234839000000"}) + "\n"
                    + json.dumps({"MESSAGE": "user unit", "_SYSTEMD_UNIT": "user@1000.service",
                                  "__REALTIME_TIMESTAMP": "1793234839000000"}) + "\nnot json\n").encode()
        d.stderr = b"Hint: You are currently not seeing messages from other users and the system.\n"
        return d
    got, note = hn.journal(10, 20, run=fake_run)
    check("journal: network units' entries and systemd's about them parsed (byte-array messages too), others dropped, "
          "the window passed, "
          "a partial journal named",
          [(u, m) for _, u, m in got] == [("nordvpnd.service", "logger.go:35: [Info] stopping vpn"),
                                          ("systemd:nordvpnd.service", "Stopped NordVPN Daemon."),
                                          ("NetworkManager.service", "hi")] and "@10" in seen[0]
          and "@21" in seen[0] and "-u" not in seen[0] and note and "not readable" in note, (got, note, seen))

    def missing(argv, **kw):
        raise FileNotFoundError(argv[0])
    check("journal: no journalctl is reported, not raised", hn.journal(1, 2, run=missing) == ([], "journalctl not installed"))
    spans, dropped = hn.windows([("a", t), ("b", t + 30), ("c", t + 1000)] + [(f"x{i}", t + 2000 * (i + 1)) for i in range(8)])
    check("windows: overlapping failures share one window; more than MAX_WINDOWS keeps the first and last",
          spans[0][2] == ["a", "b"] and len(spans) == hn.MAX_WINDOWS and dropped == 10 - hn.MAX_WINDOWS
          and spans[-1][2] == ["x7"], spans)


def records():
    import live
    scratch = ROOT / "build/host-network-check"
    shutil.rmtree(scratch, ignore_errors=True)
    try:
        blip = watch([state(), state(ROUTES_VPN), state(), state()])
        t = blip.started
        failures = [("party_live", t + 3), ("stats_live", t + 4)]
        calls = []

        def journal_stub(lo, hi):
            calls.append((lo, hi))
            return [(t + 1, "nordvpnd.service", "logger.go:90: [Info] connected to zz9999.nordvpn.com")], None
        path = scratch / "run-1/host.txt"
        changed = hn.write_record(path, blip, failures, read_journal=journal_stub)
        text = path.read_text()
        check("record: failure times, digests, the change with its lines, journal window, no public address or server "
              "host name",
              changed and "first " + hn._utc(t + 3) in text and "last " + hn._utc(t + 4) in text
              and "CHANGED during the run" in text and "+default dev nordlynx table 205 scope link" in text
              and "+<public-ip> via 192.168.1.1 dev enp3s0" in text and "nordvpnd: connected to <server>" in text
              and "not readable: nft" in text and len(calls) == 1 and "185.1.2.3" not in text
              and "nordvpn.com" not in text, text)

        def raising(lo, hi):
            raise RuntimeError("journal gone")
        still = watch([state(), state(ROUTES_DOCKER)])
        changed = hn.write_record(scratch / "run-2/host.txt", still, failures, read_journal=raising)
        text = (scratch / "run-2/host.txt").read_text()
        check("record: unchanged host and a failing journal are written as such", not changed and "unchanged" in text
              and "journal error" in text, text)
        huge = [(f"s{i}", t + 1000 * i) for i in range(hn.MAX_WINDOWS)]
        hn.write_record(scratch / "run-3/host.txt", blip, huge, read_journal=lambda lo, hi: (
            [(lo + i, "nordvpnd.service", "x.go:1: [Info] [FW] configuring firewall") for i in range(2000)], None))
        check("record: bounded", (scratch / "run-3/host.txt").stat().st_size <= hn.MAX_RECORD)

        # The runner's hook: a record and the LIVE_FAIL flag only on failure and change.
        results = [{"name": "party_live", "exit": 1, "ended": t + 3}, {"name": "life_live", "exit": 0, "ended": t + 5}]
        saved = hn.journal
        hn.journal = journal_stub
        try:
            host, flag = live.host_record(watch([state(), state(ROUTES_VPN)]), results, scratch / "run-4")
            ok_host, ok_flag = live.host_record(watch([state(), state(ROUTES_DOCKER)]),
                                                [{"name": "life_live", "exit": 0}], scratch / "run-5")
            same_host, same_flag = live.host_record(watch([state(), state(ROUTES_DOCKER)]), results, scratch / "run-6")
        finally:
            hn.journal = saved
        check("runner: a failed run with a host change writes host.txt and flags the LIVE_FAIL line",
              host["record"] == "build/host-network-check/run-4/host.txt" and host["changed"]
              and flag == "; host-network-changed (see build/host-network-check/run-4/host.txt)"
              and (scratch / "run-4/host.txt").is_file(), (host, flag))
        check("runner: a passing run writes no record; a failed run with no host change has a record and no flag",
              ok_host["record"] is None and not (scratch / "run-5").exists() and ok_flag == ""
              and same_host["record"] and not same_host["changed"] and same_flag == "", (ok_host, same_host))
        check("runner: summary.json gets digests, never state lines",
              set(host) == {"changed", "samples", "changes", "sources", "record"}
              and "nordlynx" not in json.dumps(host), host)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def real_host():
    w = hn.Watch(every=0.2).start()
    w.stop()
    readable = [s for s in ("ip rule", "ip route") if s not in w.unreadable]
    check("the real host is read (ip rule, ip route) without root; nft is read or named not readable",
          readable == ["ip rule", "ip route"] and all(w.start_state.get(s) for s in readable)
          and ("nft ruleset" in w.unreadable or w.start_state.get("nft ruleset")), w.summary())


if __name__ == "__main__":
    digests()
    watching()
    masking()
    journal()
    records()
    real_host()
    print(f"HOST_NETWORK_{'FAIL' if FAILS else 'OK'} {len(FAILS)} failed")
    sys.exit(1 if FAILS else 0)
