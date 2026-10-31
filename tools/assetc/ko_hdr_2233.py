"""The 2233 client's per-zone HDR settings as a package post-process (PQ-316).

A 2233/2145 addition: the pinned 1298 client has no post-process and stays the
source of truth. This cook runs only on request, inside the
`ko_bake.py ... --features --glow-2233` cook of the 2233/2145 additions
package, and reads the player's own 2145 install, unpacked by
tools/ko-reference/unpack_inno.py; nothing here is a build step. The client
draws it only when the player sets Option.ini [Addition2233] HDR=1.

Evidence: docs/implementation/evidence/pq-316-hdr-bloom-post-process-2233.md.
2233 image (static analysis of the unpacked 2233 client, PQ-314;
binary for that image only, a secondary reference):

- CN3PostProcess::Load (00477860), called by 00477030 for zones\\HDR.n3pp
  (00b91bf8): a u32 version that must be 1 (otherwise nothing is read), a u32
  count, then per row a u32 kind; kind 1 reads key, r2, r3, r4, r6 and kind 2
  reads key, r2, r3, r4, r6, r5 (f32 each). Unread fields keep r2 = 0.5
  (00b8fb94), r3 = r4 = r6 = 1 and r5 = 0. Insert 00477760 replaces a key's
  earlier row.
- On each zone entry (00476f50, from CGameProcIntroChrSelect::InitZone
  004cc820 with the zone row's id) the row of that key sets r2 -> +0x78 the
  bright-pass threshold, r3 -> +0x8c the bloom scale (the blur weights,
  004759f0, and the white point, pp.fx P6), r4 -> +0x84 exposure, r5 -> +0x88
  lift and r6 -> +0x90 saturation. With no row: 0, 1.5 (00b91a54), 1.2
  (00b91a58), 0 and 1.2.
- The adaptation rate is 0.3 per second (00476690, the double at 00b905a8) and
  the blur variance 1.0 (+0x80, set only by the constructor 00477bd0).

So a 2145 kind-2 row is, in file order: threshold, bloom scale, exposure,
saturation, lift. Applying 2233's reading to the 2145 file is an inference:
the 2145 exe is packed and unread.

n3e's guards, not KO behaviour: the install must be the pinned 2145
installer's unpack with `Zones/hdr.n3pp` and `Data/Zones.tbl` matching its
manifest; a version other than 1, a kind other than 1 or 2, a size that does
not match the rows, or a value outside postprocess.py's bounds is refused
(2233 would silently draw with no rows or misread the rest); and the zone's
runtime key must be a row of the 2145 Zones.tbl, whose name and map the
report records beside the cooked zone's.
"""
import hashlib
import pathlib
import struct

import postprocess

HDR = 'Zones/hdr.n3pp'
ZONES = 'Data/Zones.tbl'
MAX_HDR = 64 * 1024
# 00476f50's values with no row for the zone, in postprocess.py's names.
NO_ROW = dict(threshold=0.0, bloom=1.5, exposure=1.2, saturation=1.2, lift=0.0)
# 00477860's record defaults for fields a kind does not read.
RECORD = dict(threshold=0.5, bloom=1.0, exposure=1.0, saturation=1.0, lift=0.0)
# The fields each kind reads, in file order (00477860).
KINDS = {1: ('threshold', 'bloom', 'exposure', 'saturation'),
         2: ('threshold', 'bloom', 'exposure', 'saturation', 'lift')}
ADAPT_RATE = 0.3     # 00476690, 00b905a8
BLUR_VARIANCE = 1.0  # +0x80, 00477bd0


def parse(data):
    """{key: (kind, settings)} of an hdr.n3pp, refused unless well formed."""
    if len(data) < 8:
        raise ValueError('hdr.n3pp: truncated header')
    version, count = struct.unpack_from('<II', data)
    if version != 1:
        raise ValueError('hdr.n3pp: version %d, not 1 (00477860 reads nothing then)' % version)
    rows, at = {}, 8
    for _ in range(count):
        if at + 4 > len(data):
            raise ValueError('hdr.n3pp: truncated at row %d' % len(rows))
        kind, = struct.unpack_from('<I', data, at)
        if kind not in KINDS:
            raise ValueError('hdr.n3pp: row kind %d (00477860 reads kinds 1 and 2)' % kind)
        fields = KINDS[kind]
        if at + 8 + 4 * len(fields) > len(data):
            raise ValueError('hdr.n3pp: truncated at row %d' % len(rows))
        key, = struct.unpack_from('<i', data, at + 4)
        values = struct.unpack_from('<%df' % len(fields), data, at + 8)
        at += 8 + 4 * len(fields)
        settings = dict(RECORD, **dict(zip(fields, values)))
        for name, value in settings.items():
            postprocess.check(name, value)
        rows[key] = (kind, settings)  # 00477760: a later row replaces the key's
    if at != len(data):
        raise ValueError('hdr.n3pp: %d trailing bytes' % (len(data) - at))
    return rows


def checked(install, name, limit):
    """One file of the 2145 unpack, checked against its manifest."""
    path = install.root / 'client' / name
    if not path.is_file():
        raise ValueError('2145 file %s is missing' % path)
    if path.stat().st_size > limit:
        raise ValueError('%s is over the bound' % path)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if install.hashes.get(name.lower()) != digest:
        raise ValueError('%s differs from the 2145 installer\'s (manifest)' % path)
    install.read[name] = digest
    return data


def settings(rows, key):
    """The package post-process for zone `key`: its row, else 00476f50's."""
    kind, values = rows[key] if key in rows else (None, NO_ROW)
    cooked = dict(values, adapt_rate=ADAPT_RATE, blur_variance=BLUR_VARIANCE)
    postprocess.cook(cooked)
    return cooked, kind


def cook(zone_key, install=None):
    """(manifest `postprocess`, report) for the cooked zone's runtime key."""
    if install is None:
        import ko_glow_2233
        install = ko_glow_2233.Install()
    rows = parse(checked(install, HDR, MAX_HDR))
    _, zones = install.table(ZONES)
    if zone_key not in zones:
        raise ValueError('zone %d is not a row of the 2145 %s' % (zone_key, ZONES))
    value, kind = settings(rows, zone_key)
    row = zones[zone_key]
    return value, dict(addition='2233 code (00476b40, 00477860, 00476f50), 2145 data', install=str(install.root),
                       files=dict(sorted((k, v) for k, v in install.read.items() if k in (HDR, ZONES))),
                       zone_key=zone_key, zone_2145=dict(name=row[2], map=row[1]),
                       row='kind %d' % kind if kind else 'none: 00476f50 defaults', rows=len(rows),
                       postprocess=value)
