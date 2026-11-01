"""The realm loop's queue (docs/loop/README.md): one JSON object per line in
docs/loop/queue.jsonl, worked top to bottom.

  python3 tools/loop/queue.py check              the file is well formed
  python3 tools/loop/queue.py next [--json]      the first ready item whose deps are done
  python3 tools/loop/queue.py show RQ-NNN
  python3 tools/loop/queue.py set RQ-NNN key=value ...   (a JSON value, else a string; key= removes)
  python3 tools/loop/queue.py add --top|--after RQ-NNN '<item JSON>'   (id assigned when absent)
  python3 tools/loop/queue.py stats | questions | testme
"""
import json
from pathlib import Path
import re
import sys

QUEUE = Path(__file__).resolve().parents[2] / "docs/loop/queue.jsonl"
LANES = {"review", "character", "front-end", "engine", "roadmap", "flake"}
KINDS = {"research", "verify", "fix", "feature", "review"}
STATUSES = {"ready", "blocked", "done", "deviation", "split"}
REQUIRED = ("id", "slug", "lane", "kind", "status", "title", "refs", "deps")
OPTIONAL = {"attempts": int, "note": str, "blocked_on": str, "question": str, "testme": str,
            "accepted": bool, "stash": str}


def load():
    return [json.loads(line) for line in QUEUE.read_text().splitlines() if line.strip()]


def save(items):
    QUEUE.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items))


def problems(items):
    out, ids = [], [i.get("id") for i in items]
    for n, i in enumerate(items, 1):
        where = f"line {n} ({i.get('id')})"
        for k in REQUIRED:
            if k not in i:
                out.append(f"{where}: no {k}")
        for k, v in i.items():
            if k not in REQUIRED and k not in OPTIONAL:
                out.append(f"{where}: unknown field {k}")
            elif k in OPTIONAL and not isinstance(v, OPTIONAL[k]):
                out.append(f"{where}: {k} is not {OPTIONAL[k].__name__}")
        if not re.fullmatch(r"RQ-\d{3}", str(i.get("id"))):
            out.append(f"{where}: id is not RQ-nnn")
        if ids.count(i.get("id")) > 1:
            out.append(f"{where}: duplicate id")
        if not re.fullmatch(r"[a-z0-9-]{1,48}", str(i.get("slug"))):
            out.append(f"{where}: slug is not [a-z0-9-]")
        for k, allowed in (("lane", LANES), ("kind", KINDS), ("status", STATUSES)):
            if i.get(k) not in allowed:
                out.append(f"{where}: {k} {i.get(k)!r} not in {sorted(allowed)}")
        if i.get("status") == "blocked" and not i.get("blocked_on"):
            out.append(f"{where}: blocked without blocked_on")
        for d in i.get("deps", []):
            if d not in ids:
                out.append(f"{where}: dep {d} does not exist")
        if not isinstance(i.get("refs"), list) or not isinstance(i.get("deps"), list):
            out.append(f"{where}: refs and deps are lists")
    return out


def eligible(items):
    done = {i["id"] for i in items if i["status"] in ("done", "deviation", "split")}
    return [i for i in items if i["status"] == "ready" and all(d in done for d in i["deps"])]


def find(items, id_):
    for n, i in enumerate(items):
        if i["id"] == id_:
            return n
    raise SystemExit(f"queue: no item {id_}")


def value(text):
    try:
        return json.loads(text)
    except ValueError:
        return text


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    items, verb = load(), argv[0]
    if verb == "check":
        bad = problems(items)
        print("\n".join(bad) if bad else f"QUEUE_OK {len(items)} items")
        return 1 if bad else 0
    if verb == "next":
        ready = eligible(items)
        if not ready:
            print("LOOP_QUEUE_EMPTY")
            return 0
        print(json.dumps(ready[0]) if "--json" in argv else f"{ready[0]['id']} {ready[0]['title']}")
        return 0
    if verb == "show":
        print(json.dumps(items[find(items, argv[1])], indent=1))
        return 0
    if verb == "set":
        n = find(items, argv[1])
        for pair in argv[2:]:
            key, _, raw = pair.partition("=")
            if raw == "":
                items[n].pop(key, None)
            else:
                items[n][key] = value(raw)
    elif verb == "add":
        item = json.loads(argv[-1])
        if "id" not in item:
            item["id"] = "RQ-%03d" % (1 + max(int(i["id"][3:]) for i in items))
        item.setdefault("refs", [])
        item.setdefault("deps", [])
        item.setdefault("status", "ready")
        if "--top" in argv:
            at = next((n for n, i in enumerate(items) if i["status"] == "ready"), len(items))
        elif "--after" in argv:
            at = find(items, argv[argv.index("--after") + 1]) + 1
        else:
            at = len(items)
        items.insert(at, item)
        print(item["id"])
    elif verb == "stats":
        for s in sorted(STATUSES):
            print(f"{s:10} {sum(i['status'] == s for i in items)}")
        print(f"{'eligible':10} {len(eligible(items))}")
        return 0
    elif verb == "questions":
        for i in items:
            if i["status"] == "blocked":
                print(f"{i['id']} ({i['blocked_on']}): {i.get('question') or i['title']}")
        return 0
    elif verb == "testme":
        for i in items:
            if i.get("testme") and i["status"] in ("done", "deviation") and not i.get("accepted"):
                print(f"{i['id']} {i['slug']}: {i['testme']}")
        return 0
    else:
        raise SystemExit(__doc__)
    bad = problems(items)
    if bad:
        raise SystemExit("queue: refusing to write:\n" + "\n".join(bad))
    save(items)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
