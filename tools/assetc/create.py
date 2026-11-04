"""The package's character-create rules, `create.bin` (N3CC version 1, RQ-002).

The manifest's `create` section (content/character-create.md, "The realm's
create"): the stats a character has, the nation an account has until the realm
keeps one (RQ-006), the races a create may name with each one's nation, face and
hair counts and specialties (each with its bonus points and base stats), the
name rule, the reserved words, the wording of each refusal and the fixed choice
a create without a race takes (Q52). The server checks every create against
them (server/src/create.rs reads the same layout); no game's ids are here.
"""
import re

from common import string, u

MAGIC = b"N3CC"
VERSION = 1
MAX_STATS = 8
MAX_RACES = 32
MAX_SPECIALTIES = 16
MAX_RESERVED = 256
# characters.name holds at most 24 bytes (deploy/002-multiplayer.sql).
MAX_NAME = 24
MAX_TEXT = 200
MAX_WORD = 24
MAX_VALUE = 1000
# Refusals in the wire's CreateCharacter.Result order (KO's 1, 2, 3, 4, 5, 17).
REFUSALS = ("limit", "mismatch", "taken", "failed", "name", "stats")
KEYS = {"stats", "nation", "races", "name", "reserved", "refusals"}
OPTIONAL = {"fixed"}
RACE_KEYS = {"race", "nation", "faces", "hairs", "specialties"}
SPECIALTY_KEYS = {"specialty", "bonus", "base"}
NAME_KEYS = {"min", "max", "punctuation"}
FIXED_KEYS = {"race", "specialty", "face", "hair", "stats"}
WORD = re.compile(r"[!-@\[-~]{1,%d}\Z" % MAX_WORD)  # printable ASCII, no space or upper case


def whole(v, low, high, what):
    if type(v) is not int or not low <= v <= high:
        raise ValueError("create %s: an integer %d..%d" % (what, low, high))
    return v


def text(v, limit, what):
    if type(v) is not str or len(v) > limit or not all(c == "\n" or " " <= c <= "~" for c in v):
        raise ValueError("create %s: printable ASCII of at most %d bytes" % (what, limit))
    return v


def check(value):
    """The section, checked whole; returns the fixed choice's stats or None."""
    if type(value) is not dict or not KEYS <= set(value) <= KEYS | OPTIONAL:
        raise ValueError("create fields: %s" % ", ".join(sorted(KEYS)))
    stats = whole(value["stats"], 1, MAX_STATS, "stats")
    nation = whole(value["nation"], 1, 255, "nation")
    races = value["races"]
    if type(races) is not list or not 1 <= len(races) <= MAX_RACES:
        raise ValueError("create races: 1 to %d" % MAX_RACES)
    seen = set()
    for race in races:
        if type(race) is not dict or set(race) != RACE_KEYS:
            raise ValueError("create race fields: %s" % ", ".join(sorted(RACE_KEYS)))
        rid = whole(race["race"], 1, 65535, "race")
        if rid in seen:
            raise ValueError("create race %d twice" % rid)
        seen.add(rid)
        whole(race["nation"], 1, 255, "race nation")
        whole(race["faces"], 1, 256, "faces")
        whole(race["hairs"], 1, 256, "hairs")
        specialties = race["specialties"]
        if type(specialties) is not list or not 1 <= len(specialties) <= MAX_SPECIALTIES:
            raise ValueError("create race %d specialties: 1 to %d" % (rid, MAX_SPECIALTIES))
        ids = set()
        for s in specialties:
            if type(s) is not dict or set(s) != SPECIALTY_KEYS:
                raise ValueError("create specialty fields: %s" % ", ".join(sorted(SPECIALTY_KEYS)))
            sid = whole(s["specialty"], 1, 65535, "specialty")
            if sid in ids:
                raise ValueError("create race %d specialty %d twice" % (rid, sid))
            ids.add(sid)
            whole(s["bonus"], 0, MAX_VALUE, "bonus")
            if type(s["base"]) is not list or len(s["base"]) != stats:
                raise ValueError("create race %d specialty %d: %d base stats" % (rid, sid, stats))
            for b in s["base"]:
                whole(b, 0, MAX_VALUE, "base stat")
    name = value["name"]
    if type(name) is not dict or set(name) != NAME_KEYS:
        raise ValueError("create name fields: %s" % ", ".join(sorted(NAME_KEYS)))
    whole(name["max"], 1, MAX_NAME, "name max")
    whole(name["min"], 1, name["max"], "name min")
    punctuation = text(name["punctuation"], 32, "name punctuation")
    if any(c.isalnum() or not "!" <= c <= "~" for c in punctuation):
        raise ValueError("create name punctuation: printable ASCII other than letters, digits and space")
    reserved = value["reserved"]
    if type(reserved) is not list or len(reserved) > MAX_RESERVED or \
            not all(type(w) is str and WORD.match(w) for w in reserved):
        raise ValueError("create reserved: up to %d lower-case printable ASCII words of 1 to %d bytes"
                         % (MAX_RESERVED, MAX_WORD))
    refusals = value["refusals"]
    if type(refusals) is not dict or set(refusals) != set(REFUSALS):
        raise ValueError("create refusals: %s" % ", ".join(REFUSALS))
    for kind in REFUSALS:
        text(refusals[kind], MAX_TEXT, "refusal %s" % kind)
    fixed = value.get("fixed")
    if fixed is not None:
        if type(fixed) is not dict or set(fixed) != FIXED_KEYS:
            raise ValueError("create fixed fields: %s" % ", ".join(sorted(FIXED_KEYS)))
        refused = choice(value, fixed)
        if refused:
            raise ValueError("create fixed choice: %s" % refused)
    return value


def choice(value, c):
    """Why the rules refuse a choice ({race, specialty, face, hair, stats}) in
    the default nation, or None: the server's create::Policy::choice."""
    race = next((r for r in value["races"] if r["race"] == c["race"]), None)
    if race is None or race["nation"] != value["nation"]:
        return "race %r is not offered in nation %d" % (c["race"], value["nation"])
    specialty = next((s for s in race["specialties"] if s["specialty"] == c["specialty"]), None)
    if specialty is None:
        return "specialty %r is not one race %d offers" % (c["specialty"], race["race"])
    if type(c["face"]) is not int or not 0 <= c["face"] < race["faces"] or \
            type(c["hair"]) is not int or not 0 <= c["hair"] < race["hairs"]:
        return "face or hair out of range"
    stats = c["stats"]
    if type(stats) is not list or len(stats) != value["stats"] or any(type(v) is not int for v in stats):
        return "%d stats" % value["stats"]
    if any(v < b for v, b in zip(stats, specialty["base"])) or \
            sum(stats) != sum(specialty["base"]) + specialty["bonus"]:
        return "stats %s are not the base %s with the %d points spent" % (stats, specialty["base"], specialty["bonus"])
    return None


def cook(value):
    check(value)
    stats = value["stats"]
    data = MAGIC + u(VERSION) + u(stats) + u(value["nation"]) + u(len(value["races"]))
    for race in value["races"]:
        data += u(race["race"]) + u(race["nation"]) + u(race["faces"]) + u(race["hairs"]) + u(len(race["specialties"]))
        for s in race["specialties"]:
            data += u(s["specialty"]) + u(s["bonus"]) + b"".join(u(b) for b in s["base"])
    name = value["name"]
    data += u(name["min"]) + u(name["max"]) + string(name["punctuation"])
    data += u(len(value["reserved"])) + b"".join(string(w) for w in value["reserved"])
    data += b"".join(string(value["refusals"][kind]) for kind in REFUSALS)
    fixed = value.get("fixed")
    if fixed is None:
        data += u(0)
    else:
        data += u(1) + u(fixed["race"]) + u(fixed["specialty"]) + u(fixed["face"]) + u(fixed["hair"])
        data += b"".join(u(v) for v in fixed["stats"])
    return data
