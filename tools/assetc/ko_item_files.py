"""The file KO draws on a character for an item (RQ-159, content/character-create.md).

KO names an item's artwork from its Item_Org row and, for a hand plug, its
Item_Ext row; this module reads those two tables (KO `.tbl`, decrypted with
ko_tbl) and names the file as the client does. Read statically in 1298's
KnightOnLine.exe (`006157b0`, sha256 828ab0db...43a5e5) and in the 1264
client (`005d2a80`, sha256 61e9a086...136471), which do the same; binary,
specs/KO-FINDINGS.md section 10.3:

- The row's attach byte (+0x42, column 13) makes the item a hand plug (0-4:
  the right hand for 0, 1 and 3, the left for 2 and 4; ".n3cplug",
  `006d8e70`) or a body part (5-9: upper 0, lower 1, helmet 5, gauntlets 3,
  boots 4; ".n3cpart", `006d8e64`); any other attach is an icon (".dxt").
- A row whose resource (+0x30, column 7) is 0 names no file.
- A plug is named from its Item_Ext row's resource (+0x2c, column 6) when that
  is not 0, else the Item_Org row's; without an Item_Ext row it names none.
  The name is "Item\\%.1d_%.4d_%.2d_%.1d%s" (`006d8e28`) of value / 10^7,
  value / 1000 % 10000, value / 10 % 100 and value % 10.
- A part is named from the Item_Org row's own number (+0x00) / 10, not its
  resource: with the wearer's class above 11 and its race not 0, 20 or 100,
  a race and class the switch at `00615be4` accepts (CLASSES) give
  number / 100000 x 100000 + number % 1000 + race x 1000. Any other race or
  class with those bounds names the file from a stack address (the default
  case loads the out string's pointer, `00615e2a`), which this module refuses;
  a class of 11 or less, or race 0, 20 or 100, names none. A row whose number
  / 10000 % 100 is not 0 takes "Item\\%.2d_..." (`006d8e44`) with that number
  first, unless its +0x54 (column 22) is 2.

The robe test the create's part set applies (1298 `00462bd0`, 1264
`00463350`) is the row's +0x41 (column 12), except where the package's table
names the client's exemption (`robe_exempt`). No package's ids are here; the
races and classes below are the clients' own switch.
"""
import ko_tbl

# Item_Org columns (0-based): number, extension table, resource, kind
# (byClass, +0x40), robe (+0x41), attach (+0x42), +0x54; and their KO types
# (ko_tbl: 2 Byte, 5 Int32, 6 UInt32). Item_Ext: number and resource.
ORG = dict(number=0, extension=1, resource=6, kind=10, robe=11, attach=12, sale=21)
ORG_TYPES = {0: 6, 1: 2, 6: 6, 10: 2, 11: 2, 12: 2, 21: 5}
EXT = dict(number=0, resource=5)
EXT_TYPES = {0: 6, 5: 6}
PLUG_SLOT = {0: 0, 1: 0, 3: 0, 2: 1, 4: 1}
PART_SLOT = {5: 0, 6: 1, 7: 5, 8: 3, 9: 4}
# The client's Item_Ext tables (0..23). The name function indexes the table
# array with the row's extension unbounded for every item it names, part or
# plug (1298 006157b0, 1264 005d2a80); only the build's own lookup of a part's
# extension stops below it (005fd120, 00439970: `< 0x18`).
EXTENSIONS = 24
# The part slots a robe joins: an upper that is a robe leaves the lower bare.
UPPER, LOWER = 0, 1
# 006157b0 / 005d2a80: the classes each race's switch case accepts.
CLASSES = {
    1: {101, 105, 106},
    2: {102, 104, 107, 108, 111, 112},
    3: {103, 109, 110},
    4: {104, 111, 112},
    11: {201, 205, 206},
    12: set(range(201, 213)),
    13: set(range(201, 213)),
}
UNNAMED_RACES = {0, 20, 100}


def table(data, types, what):
    """{number: row} of a KO item table, refusing another layout or a number twice."""
    header, rows = ko_tbl.parse(ko_tbl.decrypt(data))
    for column, kind in types.items():
        if len(header) <= column or header[column] != kind:
            raise ValueError("%s: column %d is not KO's item table layout" % (what, column + 1))
    out = {}
    for row in rows:
        if row[0] in out:
            raise ValueError("%s: row %d twice" % (what, row[0]))
        out[row[0]] = row
    return out


def stem(value):
    return "%d_%04d_%02d_%d" % (value // 10000000, value // 1000 % 10000, value // 10 % 100, value % 10)


def form(org):
    """("plug", hand slot) or ("part", part slot) of an Item_Org row, or None for
    an icon-only item."""
    attach = org[ORG["attach"]]
    if attach in PLUG_SLOT:
        return "plug", PLUG_SLOT[attach]
    if attach in PART_SLOT:
        return "part", PART_SLOT[attach]
    return None


def name(org, ext, race, specialty):
    """The file KO names for the item (`Item/...`, the tree's own case left to
    the reader), or "" when it names none. Refuses an icon-only item and a
    part whose race and class name a file from a stack address."""
    kind = form(org)
    if kind is None:
        raise ValueError("Item_Org %d: attach %d is neither a hand plug nor a body part"
                         % (org[ORG["number"]], org[ORG["attach"]]))
    resource = org[ORG["resource"]]
    if resource == 0:
        return ""
    if kind[0] == "plug":
        if ext is None:
            return ""
        return "Item/%s.n3cplug" % stem(ext[EXT["resource"]] or resource)
    if specialty <= 11 or race in UNNAMED_RACES:
        return ""
    if specialty not in CLASSES.get(race, ()):
        raise ValueError("Item_Org %d: race %d and class %d name its part from a stack address (006157b0 00615e2a)"
                         % (org[ORG["number"]], race, specialty))
    number = org[ORG["number"]]
    value = number // 10
    value = value // 100000 * 100000 + value % 1000 + race * 1000
    first = 0 if org[ORG["sale"]] == 2 else number // 10000 % 100
    return "Item/%s%s.n3cpart" % ("%02d_" % first if first else "", stem(value))


def robe(org, nation, exempt):
    """Whether the create's part set takes the row as a robe: its robe byte,
    unless (nation, number / 10^6) is one of the table's `exempt` pairs."""
    if not org[ORG["robe"]]:
        return False
    return [nation, org[ORG["number"]] // 1000000] not in exempt
