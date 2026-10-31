"""Host network record for a failed live run (PQ-456).

A host event (a VPN connect installing ip rules and an nft output chain, a
firewall reload, a route change) fails many live suites at once, and their logs
hold only symptoms: connect timeouts, Redis "no reply within 700 ms", EOF. This
module lets tests/live.py and tests/live_ko.py tell such an event from a
regression. It is diagnosis only: nothing here retries, skips or passes a suite.

Watch samples the host's network state from the start of a run to its end, every
SAMPLE_S seconds, as three sources: `ip rule` (IPv4 and IPv6), `ip route show
table all` (IPv4 and IPv6) and `nft -s list ruleset`. Each source is reduced to
its host-level lines and digested (SHA-256). The run's own Docker activity is
not host-level and is removed before the digest:

- routes on a Docker interface (docker0, br-<12 hex> bridges, which the PQ-457
  pool networks n3e-test-net-N and every other Docker network get, and veth*):
  a container start or stop adds and removes these, and a bridge's `linkdown`
  flips with its first and last container (PQ-458, D-230);
- route lifetimes (`expires 1795sec`), which count down on their own;
- nft tables named after Docker, chains named DOCKER*, and rules naming
  DOCKER, docker or a Docker interface (the published-port DNAT and masquerade
  rules Docker adds per container); counters are not listed (`-s`).

Docker never adds ip rules, so `ip rule` is kept whole. A source that cannot be
read (nft needs CAP_NET_ADMIN, so without root it is reported "not readable")
is named in the record and left out of the comparison, never an error.

The host network changed when any readable source's digest differs from its
digest at the start: at a sample during the run (a VPN that connects and
disconnects again within the run, as on 2026-10-28) or at the end. Then the
runner adds `host-network-changed` to its LIVE_FAIL (LIVE_KO_FAIL) line.

When a run has a failed suite or prepare step, write_record() writes
<kept run>/host.txt: the run's start and end, its first and last failure
times, each source's digests at the start and the end, every change seen with
its time, the lines each changed state added or removed against the start
state, and the system journal of the network services (NetworkManager,
systemd-networkd and -resolved, dockerd, firewalld, nftables, iptables, ufw,
wpa_supplicant, iwd, and any VPN unit: *vpn*, wg-quick@*, openvpn*, mullvad*,
tailscaled) in a window from WINDOW_BEFORE seconds before each failure to
WINDOW_AFTER seconds after it, overlapping windows merged.

Bounds. At most MAX_WINDOWS windows (the first and last ones), MAX_WINDOW_LINES
kept journal lines in each (its first and last ones), MAX_DIFF_LINES changed
lines a state, MAX_STATES states a source and MAX_RECORD bytes in all.

Privacy: the journal is an allowlist. A journal entry is printed only when its
message matches one of the TEMPLATES below, and then not as logged: the record
prints the template's own fixed text, filled only with a short word of the
pattern's characters, which the logging program fills from its own state
names (a NetworkManager state or reason code, a device type, an ip rule
priority, a connection state such as CONNECTED), and with an interface name only if it has a generic shape (eth0,
wlan0, tun0, wg0, nordlynx; any other name prints as <dev>). A server, host
name, address, key, fingerprint, SSID, connection name, user or path in the
message is therefore never printed, whatever its form. Every other entry is
withheld and counted per unit; entries that name a Docker interface (the run's
own containers) are counted apart. A unit prints by its family name (an
instance after "@" is dropped; a VPN unit outside the known names prints as
"vpn unit"). The state diffs print route, rule and nft lines with mask():
public IP addresses, URLs, host names, MAC addresses, long hex or base64 tokens
(keys, fingerprints) and non-generic interface names and quoted strings are
replaced. Kept as they are: private, loopback, link-local and CGNAT addresses
(the LAN, bridge and tunnel subnets a diagnosis needs), numbers such as table
ids, rule priorities and marks, the failed suites' names, and every other word
of a state line, such as nft table, chain and set names, named routing tables,
short hex or digit-free base64, single-label names, and quoted strings or
interface names of generic shape.
"""
import difflib
import hashlib
import ipaddress
import json
import re
import subprocess
import threading
import time

SAMPLE_S = 2.0
WINDOW_BEFORE, WINDOW_AFTER = 180, 15
MAX_WINDOWS = 6
MAX_WINDOW_LINES = 150
MAX_LINE = 300
MAX_DIFF_LINES = 60
MAX_STATES = 8
MAX_RECORD = 256 << 10
COMMAND_TIMEOUT = 10
JOURNAL_TIMEOUT = 30
JOURNAL_MAX_BYTES = 64 << 20

SOURCES = {
    "ip rule": [["ip", "-4", "rule"], ["ip", "-6", "rule"]],
    "ip route": [["ip", "-4", "route", "show", "table", "all"], ["ip", "-6", "route", "show", "table", "all"]],
    "nft ruleset": [["nft", "-s", "list", "ruleset"]],
}
# Matched against each entry's _SYSTEMD_UNIT here, not passed as journalctl -u
# globs: journalctl resolves a glob against every unit name the journal holds,
# which took 65 s on the reference machine (an unfiltered window: 0.1 s).
JOURNAL_UNITS = re.compile(r"(NetworkManager|systemd-networkd|systemd-resolved|docker|firewalld|nftables"
                           r"|iptables|ip6tables|ufw|wpa_supplicant|iwd|tailscaled|.*vpn.*|wg-quick@.*|openvpn.*"
                           r"|mullvad.*)\.service", re.I)

DOCKER_DEV = re.compile(r"(?<![\w-])(docker0|br-[0-9a-f]{12}|veth[0-9a-z]+)(?![\w-])")
EXPIRES = re.compile(r"\s+expires\s+-?\d+sec")
NFT_COUNTER = re.compile(r"\s*counter packets \d+ bytes \d+")

# An interface name printed as it is; any other prints as <dev>.
GENERIC_DEV = re.compile(r"lo|e[nt][a-z0-9]{1,12}|wl[a-z0-9]{1,12}|ww[a-z0-9]{1,12}|(?:tun|tap|wg|ppp)\d{1,4}"
                         r"|nordlynx|nordtun|tailscale\d{0,3}|docker0|br-[0-9a-f]{12}|veth[0-9a-z]{1,12}"
                         r"|p2p-dev-wl[a-z0-9]{1,12}")
URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)
MAC = re.compile(r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b", re.I)
# A dotted quad; a trailing full stop (end of a sentence) is not part of it.
IPV4 = re.compile(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?!\w|\.\d)")
IPV6 = re.compile(r"(?<![\w:])[0-9a-f]{0,4}(?::[0-9a-f]{0,4}){2,7}(?![\w:])", re.I)
HOST = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}\b", re.I)
# Keys and fingerprints: 16+ hex digits, or 20+ base64 characters with a digit.
TOKEN = re.compile(r"(?<![\w+/])(?:[0-9a-f]{16,}|[A-Za-z0-9+/]{20,}={0,2})(?![\w+/=])", re.I)
QUOTED = re.compile(r"\"([^\"]*)\"|'([^']*)'")
DEV_AFTER = re.compile(r"\b(dev|iif|oif|iifname|oifname)\s+(?![\"'])([\w.@-]+)")


def _public(text):
    address = text.split("/")[0].split("%")[0]
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


def dev(name):
    return name if GENERIC_DEV.fullmatch(name) else "<dev>"


def mask(line):
    """A route, rule or nft line with the replacements the module docstring lists."""
    line = URL.sub("<url>", line)
    line = MAC.sub("<mac>", line)
    line = TOKEN.sub(lambda m: m.group(0) if not re.search(r"\d", m.group(0)) else "<token>", line)
    line = IPV4.sub(lambda m: "<public-ip>" if _public(m.group(0)) else m.group(0), line)
    line = IPV6.sub(lambda m: "<public-ip>" if _public(m.group(0)) else m.group(0), line)
    line = QUOTED.sub(lambda m: '"' + dev(m.group(1) if m.group(1) is not None else m.group(2)) + '"', line)
    line = DEV_AFTER.sub(lambda m: f"{m.group(1)} {dev(m.group(2))}", line)
    line = HOST.sub("<host>", line)
    return line if len(line) <= MAX_LINE else line[: MAX_LINE - 1] + "…"


# The journal allowlist: (unit family, pattern, fixed text). A pattern's named
# groups match only a short word of the pattern's characters (which the logging
# program fills from its own state names), except `dev`, which prints through dev().
# The message is matched after its logger prefix (NetworkManager's "<info>
# [time]", a Go logger's date, file and level, logfmt's time=) is removed.
_DEV = r"(?P<dev>[\w.@-]{1,32})"
_NM_PHASE = r"[a-z][a-z-]{0,23}"
TEMPLATES = [
    ("NetworkManager", rf"^device \({_DEV}\): state change: (?P<a>{_NM_PHASE}) -> (?P<b>{_NM_PHASE}) "
                       rf"\(reason '(?P<r>{_NM_PHASE})'", "device ({dev}): state change: {a} -> {b} (reason '{r}')"),
    ("NetworkManager", rf"^device \({_DEV}\): Activation: (?P<a>successful|failed)", "device ({dev}): activation {a}"),
    ("NetworkManager", rf"^device \({_DEV}\): carrier: link (?P<a>connected|disconnected)",
     "device ({dev}): carrier: link {a}"),
    ("NetworkManager", rf"^manager: \({_DEV}\): new (?P<a>[A-Za-z]{{1,20}}) device", "manager: ({dev}): new {a} device"),
    ("NetworkManager", r"^manager: NetworkManager state is now (?P<a>[A-Z_]{1,24})$", "manager: state is now {a}"),
    ("NetworkManager", rf"^policy: set '.*' \({_DEV}\) as default for (?P<a>IPv4|IPv6)",
     "policy: ({dev}) is the default for {a}"),
    ("NetworkManager", rf"^dhcp(?P<v>[46]) \({_DEV}\): state changed (?P<a>{_NM_PHASE})",
     "dhcp{v} ({dev}): state changed {a}"),
    ("systemd-networkd", rf"^{_DEV}: (?P<a>Link UP|Link DOWN|Gained carrier|Lost carrier|Gained IPv6LL|Configured"
                         r"|DHCPv4 address|DHCP lease lost)", "({dev}): {a}"),
    ("systemd-resolved", rf"^{_DEV}: Bus client set (?P<a>DNS server list|search domain list|default route setting"
                         r"|DNSSEC setting|DNSOverTLS setting|LLMNR setting|MulticastDNS setting)",
     "({dev}): bus client set {a}"),
    ("systemd-resolved", r"^(?P<a>Flushed all caches|Switching to (?:fallback )?DNS server|Using degraded feature set"
                         r"|Grace period over|Clock change detected)", "{a}"),
    ("nordvpnd", r"(?P<a>\[FW\] configuring firewall|\[FW\] flush firewall rules|Setting the routing rules up"
                 r"|starting vpn|stopping vpn|starting network configuration|stopping network configuration"
                 r"|removing route to tunnel|removing route to the vpn server|unset allow list"
                 r"|resolver set VPN connected to (?:true|false)|\[DNS\] setting DNS using systemd-resolved"
                 r"|\[DNS\] (?:Set|Unset) on interface|reconnecting|disconnecting)(?![\w-])", "{a}"),
    ("nordvpnd", r"Selected candidate for new rule priority:\s+(?P<a>\d{1,5})$", "new ip rule priority {a}"),
    ("nordvpnd", r"^connected to \S+$", "connected to <server>"),
    ("nordvpnd", r"notifying about data connect change event: \{Status:\{State:(?P<a>[A-Z_]{1,24}) ",
     "connection state {a}"),
    ("vpn unit", r"(?P<a>Initialization Sequence Completed|SIGTERM|SIGHUP|SIGUSR1|Restart pause|Connection reset"
                 r"|Inactivity timeout|TLS Error)(?![\w-])", "{a}"),
    ("wg-quick@", r"^\[#\] (?P<a>ip link (?:add|delete)|ip -[46] (?:rule|route) (?:add|delete)|nft -f|resolvconf)\b",
     "[#] {a} ..."),
    ("docker", r'^level=(?P<l>info|warning|error|fatal) msg="(?P<a>Processing signal \'[A-Za-z]{1,12}\'|Daemon has completed '
               r'initialization|Loading containers: (?:start|done)\.|Starting up|Daemon shutdown complete)"', "{a} ({l})"),
    ("docker", r'^level=(?P<l>info|warning|error|fatal) msg="[^"]*(?P<a>[Ff]irewalld|iptables|nftables)[^"]*[Rr]eload',
     "{a} reload ({l})"),
    ("firewall", r".", "activity (message withheld)"),
    ("wpa_supplicant", r"(?P<a>CTRL-EVENT-(?:CONNECTED|DISCONNECTED|SCAN-FAILED|TERMINATING|REGDOM-CHANGE))(?![\w-])",
     "{a}"),
    ("systemd", r"^(?P<a>Starting|Started|Stopping|Stopped|Reloading|Reloaded|Deactivated successfully"
                r"|Failed with result)\b", "{a} {unit}"),
]
TEMPLATES = [(family, re.compile(pattern), text) for family, pattern, text in TEMPLATES]
PREFIX = re.compile(r"^(?:<\w+>\s+\[[\d.]+\]\s+|(?:\d{4}/\d\d/\d\d \d\d:\d\d:\d\d(?:\.\d+)? )?[\w.-]+\.go:\d+: \[\w+\] "
                    r"|time=\"[^\"]*\"\s+)")
KNOWN_UNITS = {"NetworkManager", "systemd-networkd", "systemd-resolved", "docker", "firewalld", "nftables",
               "iptables", "ip6tables", "ufw", "wpa_supplicant", "iwd", "tailscaled", "nordvpnd",
               "nordvpnd-killswitch", "openvpn", "openvpn@", "openvpn-client@", "openvpn-server@", "wg-quick@",
               "mullvad-daemon", "mullvad-early-boot-blocking"}
FAMILY = {"nordvpnd-killswitch": "nordvpnd", "firewalld": "firewall", "nftables": "firewall",
          "iptables": "firewall", "ip6tables": "firewall", "ufw": "firewall"}


def unit_name(unit):
    """A unit as the record prints it: no instance, no unknown name."""
    name = unit.removesuffix(".service")
    if "@" in name:
        name = name.split("@")[0] + "@"
    return name if name in KNOWN_UNITS else "vpn unit"


def family(name):
    if name in FAMILY:
        return FAMILY[name]
    if name in ("tailscaled", "openvpn", "openvpn@", "openvpn-client@", "openvpn-server@") or name.startswith("mullvad"):
        return "vpn unit"
    return name


def template(name, message, **extra):
    """The fixed text the allowlist prints for `message` from unit `name`, or None.
    `extra` fills fields the record supplies itself (systemd's unit name)."""
    fam = family(name)
    body = PREFIX.sub("", message.strip(), count=1)
    for owner, pattern, text in TEMPLATES:
        if owner == fam or (owner == "vpn unit" and fam in ("nordvpnd", "wg-quick@")):
            m = pattern.search(body)
            if m:
                groups = {k: v for k, v in m.groupdict().items() if v is not None}
                if "dev" in groups:
                    groups["dev"] = dev(groups["dev"])
                return text.format(**groups, **extra)
    return None


def host_lines(source, text):
    """The host-level lines of `source`'s output: the run's own Docker activity
    and self-changing fields removed (see the module docstring)."""
    lines = []
    if source == "nft ruleset":
        blocks = []  # the open table, chain, set ... headers around the line
        for line in text.splitlines():
            s = line.strip()
            docker = any("docker" in b.lower() for b in blocks) or "docker" in s.lower() or DOCKER_DEV.search(s)
            if s.endswith("{"):
                blocks.append(s)
            elif s == "}" and blocks:
                blocks.pop()
            if s and not docker:
                lines.append(NFT_COUNTER.sub("", line.rstrip()))
        return lines
    for line in text.splitlines():
        if not line.strip() or DOCKER_DEV.search(line):
            continue
        lines.append(" ".join(EXPIRES.sub("", line).split()))
    return lines


def _command(argv, timeout=COMMAND_TIMEOUT):
    """(stdout, None) or (None, why it could not be read)."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=timeout)
    except FileNotFoundError:
        return None, f"{argv[0]} not installed"
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"{' '.join(argv)}: {error!r}"
    if p.returncode:
        why = (p.stderr.strip().splitlines() or [f"exit {p.returncode}"])[-1]
        return None, f"{' '.join(argv)}: exit {p.returncode}: {why[:200]}"
    return p.stdout, None


def read_host(skip=()):
    """{source: (host-level lines, None) or (None, why not readable)}; sources in
    `skip` (not readable at the start: nft without root) are not read again."""
    state = {}
    for source, commands in SOURCES.items():
        if source in skip:
            continue
        lines, error = [], None
        for argv in commands:
            out, error = _command(argv)
            if error:
                break
            lines += host_lines(source, out)
        state[source] = (None, error) if error else (lines, None)
    return state


def digest(lines):
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]


class Watch:
    """The host network from start() to stop(). `read` (default read_host) is
    injectable so a check can drive the changed path without touching the host."""

    def __init__(self, read=read_host, every=SAMPLE_S, clock=time.time):
        self.read, self.every, self.clock = read, every, clock
        self.start_state, self.end_state, self.unreadable = {}, {}, {}
        self.changes, self.states, self.samples = [], {}, 0
        self.started = self.ended = None
        self._last, self._stop, self._thread, self._lock = {}, threading.Event(), None, threading.Lock()

    def _sample(self):
        try:
            state = self.read(skip=tuple(self.unreadable))
        except Exception as error:  # a broken reader is reported, never a run failure
            state = {s: (None, f"reader error: {error!r}") for s in SOURCES if s not in self.unreadable}
        now = self.clock()
        with self._lock:
            self.samples += 1
            for source, (lines, error) in state.items():
                if error:
                    if source not in self._last:
                        self.unreadable[source] = error
                    continue
                d = digest(lines)
                known = self.states.setdefault(source, {})
                if d not in known and len(known) < MAX_STATES:
                    known[d] = lines
                if source in self._last and self._last[source] != d:
                    self.changes.append((now, source, self._last[source], d))
                self._last[source] = d
            return {s: self._last[s] for s in self._last}

    def start(self):
        self.started = self.clock()
        self.start_state = self._sample()
        self._thread = threading.Thread(target=self._loop, name="host-network-watch", daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        while not self._stop.wait(self.every):
            self._sample()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=COMMAND_TIMEOUT * 3 + self.every)
        self.end_state = self._sample()
        self.ended = self.clock()
        return self

    @property
    def changed(self):
        with self._lock:
            return bool(self.changes) or any(self.end_state.get(s) != d for s, d in self.start_state.items())

    def summary(self):
        """For summary.json: digests only, no lines."""
        return {"changed": self.changed, "samples": self.samples, "changes": len(self.changes),
                "sources": {s: {"start": self.start_state.get(s), "end": self.end_state.get(s),
                                "unreadable": self.unreadable.get(s)}
                            for s in SOURCES}}


def _utc(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t % 1 * 1000):03d}Z"


def windows(failures, started=None):
    """Merged [from, to] journal windows around each failure time, with their
    failures; only the first and last MAX_WINDOWS // 2 when there are more."""
    merged = []
    for name, at in sorted(failures, key=lambda f: f[1]):
        lo, hi = at - WINDOW_BEFORE, at + WINDOW_AFTER
        if started is not None:
            lo = max(lo, started - 30)
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
            merged[-1][2].append(name)
        else:
            merged.append([lo, hi, [name]])
    dropped = 0
    if len(merged) > MAX_WINDOWS:
        dropped = len(merged) - MAX_WINDOWS
        merged = merged[: MAX_WINDOWS // 2] + merged[-(MAX_WINDOWS - MAX_WINDOWS // 2):]
    return merged, dropped


def journal(lo, hi, run=subprocess.run):
    """(entries [(time, unit, message first line)], None) of the network
    services from `lo` to `hi` (and systemd's lines about them, as unit
    "systemd:<unit>"), or ([], why not readable)."""
    argv = ["journalctl", "--no-pager", "-q", "-o", "json", "--output-fields=MESSAGE,_SYSTEMD_UNIT,UNIT,__REALTIME_TIMESTAMP",
            "--since", f"@{int(lo)}", "--until", f"@{int(hi) + 1}"]
    try:
        p = run(argv, capture_output=True, timeout=JOURNAL_TIMEOUT)
    except FileNotFoundError:
        return [], "journalctl not installed"
    except (OSError, subprocess.SubprocessError) as error:
        return [], f"journalctl: {error!r}"
    err = p.stderr.decode(errors="replace") if isinstance(p.stderr, bytes) else (p.stderr or "")
    if p.returncode:
        return [], f"journalctl exit {p.returncode}: {(err.strip().splitlines() or [''])[-1][:200]}"
    out = p.stdout[:JOURNAL_MAX_BYTES]
    out = out.decode(errors="replace") if isinstance(out, bytes) else out
    entries = []
    for raw in out.splitlines():
        try:
            entry = json.loads(raw)
            message = entry.get("MESSAGE")
            if isinstance(message, list):  # journald's form for non-UTF-8 bytes
                message = bytes(message).decode(errors="replace")
            at = int(entry["__REALTIME_TIMESTAMP"]) / 1e6
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(message, str):
            continue
        unit = entry.get("_SYSTEMD_UNIT") or ""
        if JOURNAL_UNITS.fullmatch(unit):
            entries.append((at, unit, message.split("\n")[0]))
        elif unit == "init.scope" and JOURNAL_UNITS.fullmatch(entry.get("UNIT") or ""):
            # systemd's own lines about a network unit: started, stopped, reloaded.
            entries.append((at, "systemd:" + entry["UNIT"], message.split("\n")[0]))
    note = None
    if "insufficient permissions" in err or "not seeing messages from other users and the system" in err:
        note = "the system journal is not readable by this user (only its own journal was read)"
    return entries, note


def journal_lines(entries):
    """The printed lines of `entries` (the allowlist, module docstring) and the
    counts of what was not printed: Docker interface lines, and per unit the
    entries no template matched."""
    kept, docker, withheld = [], 0, {}
    for at, unit, message in entries:
        if unit.startswith("systemd:"):
            name, text = "systemd", template("systemd", message, unit=unit_name(unit[len("systemd:"):]))
        else:
            name = unit_name(unit)
            text = None if DOCKER_DEV.search(message) else template(name, message)
            if text is None and DOCKER_DEV.search(message):
                docker += 1
                continue
        if text is None:
            withheld[name] = withheld.get(name, 0) + 1
        else:
            kept.append(f"{_utc(at)} {name}: {text}")
    if len(kept) > MAX_WINDOW_LINES:
        half = MAX_WINDOW_LINES // 2
        kept = kept[:half] + [f"... {len(kept) - 2 * half} lines left out here ..."] + kept[-half:]
    return kept, {"docker": docker, "withheld": dict(sorted(withheld.items()))}


def state_diff(source, watch):
    """Lines each later state of `source` added or removed against its start state."""
    start = watch.start_state.get(source)
    states = watch.states.get(source, {})
    out = []
    for d, lines in states.items():
        if d == start or start not in states:
            continue
        diff = [l for l in difflib.unified_diff(states[start], lines, lineterm="", n=0)
                if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        out.append(f"  state {d} against the start ({len(diff)} lines):")
        out += [f"    {mask(l)}" for l in diff[:MAX_DIFF_LINES]]
        if len(diff) > MAX_DIFF_LINES:
            out.append(f"    ... {len(diff) - MAX_DIFF_LINES} more")
    return out


def write_record(path, watch, failures, read_journal=None):
    """Write the host record (module docstring) to `path`. `failures` is
    [(name, end time)]. Returns whether the host network changed; never raises
    for an unreadable source or journal (they are named in the record)."""
    read_journal = read_journal or journal
    changed = watch.changed
    times = sorted(at for _, at in failures)
    out = ["# Host network record (tests/host_network.py, PQ-456). Diagnosis only: nothing here",
           "# retried, skipped or passed a suite. Times are UTC.",
           f"run:             {_utc(watch.started)} .. {_utc(watch.ended)}",
           f"failures:        {len(failures)}; first {_utc(times[0]) if times else '-'}, "
           f"last {_utc(times[-1]) if times else '-'}",
           *(f"  {_utc(at)} {name}" for name, at in sorted(failures, key=lambda f: f[1])),
           f"host network:    {'CHANGED during the run' if changed else 'unchanged'} "
           f"({watch.samples} samples every {watch.every:g} s; Docker interfaces, Docker's nft chains and "
           f"route lifetimes left out)",
           "sources (digest at start -> end):"]
    for source in SOURCES:
        if source in watch.unreadable:
            out.append(f"  {source:12} not readable: {watch.unreadable[source]}")
        else:
            out.append(f"  {source:12} {watch.start_state.get(source)} -> {watch.end_state.get(source)}")
    if watch.changes:
        out.append("changes seen:")
        out += [f"  {_utc(at)} {source}: {a} -> {b}" for at, source, a, b in watch.changes[:50]]
        if len(watch.changes) > 50:
            out.append(f"  ... {len(watch.changes) - 50} more")
        for source in SOURCES:
            diff = state_diff(source, watch)
            if diff:
                out.append(f"{source} changes (masked):")
                out += diff
    spans, dropped = windows(failures, watch.started)
    out.append(f"journal of the network services, {WINDOW_BEFORE} s before to {WINDOW_AFTER} s after each failure"
               f" ({len(spans)} windows{f', {dropped} middle windows left out' if dropped else ''}; "
               f"units {JOURNAL_UNITS.pattern}):")
    for lo, hi, names in spans:
        out.append(f"window {_utc(lo)} .. {_utc(hi)} (failures: {', '.join(names)})")
        try:
            entries, note = read_journal(lo, hi)
        except Exception as error:  # reported, never a run failure
            entries, note = [], f"journal error: {error!r}"
        if note:
            out.append(f"  journal: {note}")
        lines, omitted = journal_lines(entries)
        out += [f"  {l}" for l in lines]
        held = ", ".join(f"{name} {n}" for name, n in omitted["withheld"].items()) or "none"
        out.append(f"  ({len(entries)} entries, {len(lines)} printed; {omitted['docker']} naming a Docker "
                   f"interface left out; withheld (no allowlisted template): {held})")
    text = "\n".join(out) + "\n"
    if len(text.encode()) > MAX_RECORD:
        text = text.encode()[: MAX_RECORD - 100].decode(errors="ignore") + f"\n[record cut at {MAX_RECORD} bytes]\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return changed
