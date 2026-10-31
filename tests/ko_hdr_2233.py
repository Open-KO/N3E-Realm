"""PQ-316: the 2233 client's per-zone HDR settings cooked into postprocess, on original synthetic bytes.

Checks CN3PostProcess::Load's reading of hdr.n3pp (00477860: version 1, a
count, rows of kind 1 reading key, r2, r3, r4, r6 and kind 2 reading key, r2,
r3, r4, r6, r5; a later row replaces a key, 00477760), the zone apply
(00476f50: r2 threshold, r3 bloom scale, r4 exposure, r6 saturation, r5 lift;
with no row 0, 1.5, 1.2, 1.2, 0), the constants added from 2233 (adaptation
0.3 per second, 00476690; blur variance 1.0, 00477bd0), and n3e's own guards
(version, kinds, size, bounds, the pinned install with each file as its
manifest lists it, the zone key a row of the 2145 Zones.tbl). The cooked
values go through tools/assetc/postprocess.py and the client reader
(build/client/n3e-postprocess-check). No KO data is read; with --local Moradon's
row (key 210) is cooked from the player's own 2145 install (SKIP without it).
"""
import hashlib
import json
import pathlib
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/assetc'))
import ko_glow_2233  # noqa: E402
import ko_hdr_2233 as h  # noqa: E402
import postprocess  # noqa: E402

CHECK = ROOT / 'build/client/n3e-postprocess-check'


def refused(call, text):
    try:
        call()
    except ValueError as error:
        assert text in str(error), (text, str(error))
        return
    raise AssertionError('accepted: ' + text)


def n3pp(rows, version=1, count=None):
    """An hdr.n3pp: (kind, key, floats in file order) rows."""
    out = struct.pack('<II', version, len(rows) if count is None else count)
    for kind, key, values in rows:
        out += struct.pack('<Ii%df' % len(values), kind, key, *values)
    return out


class Reader:
    @staticmethod
    def load(path):
        data = json.loads(pathlib.Path(path).read_text())
        return 'block', b'', data['types'], data['rows']


def install(root, hdr, zones, tamper=None):
    """A synthetic unpack with Zones/hdr.n3pp and a Data/Zones.tbl stand-in."""
    files = {h.HDR: hdr, h.ZONES: json.dumps(dict(types=[6, 7, 7], rows=zones)).encode()}
    entries = []
    for name, data in files.items():
        path = root / 'client' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        entries.append(dict(path=name, sha256=hashlib.sha256(data).hexdigest()))
    if tamper:
        (root / 'client' / tamper).write_bytes((root / 'client' / tamper).read_bytes() + b' ')
    (root / 'manifest.json').write_text(json.dumps(dict(sha256=ko_glow_2233.INSTALLER_SHA256, manifest=entries)))
    return ko_glow_2233.Install(root, reader=Reader)


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def main():
    # Kind 2 in file order: threshold, bloom scale, exposure, saturation, lift.
    rows = h.parse(n3pp([(2, 210, [.367, .7, .1, 1.0, .65]), (1, 20, [.4, .6, .2, 1.1]),
                         (2, 30, [.1, .1, .1, .1, .1]), (2, 30, [.3, .8, .05, 1.2, .5])]))
    assert rows[210] == (2, dict(threshold=f32(.367), bloom=f32(.7), exposure=f32(.1), saturation=1.0,
                                 lift=f32(.65))), rows[210]
    # Kind 1 has no lift: 00477860's default r5 = 0 stands.
    assert rows[20] == (1, dict(threshold=f32(.4), bloom=f32(.6), exposure=f32(.2), saturation=f32(1.1), lift=0.0))
    assert rows[30][1]['bloom'] == f32(.8), 'a later row replaces the key (00477760)'
    value, kind = h.settings(rows, 210)
    assert kind == 2 and value == dict(rows[210][1], adapt_rate=.3, blur_variance=1.0)
    value, kind = h.settings(rows, 999)
    assert kind is None and value == dict(threshold=0.0, bloom=1.5, exposure=1.2, saturation=1.2, lift=0.0,
                                          adapt_rate=.3, blur_variance=1.0), '00476f50 with no row'
    good = n3pp([(2, 210, [.367, .7, .1, 1.0, .65])])
    refused(lambda: h.parse(good[:6]), 'truncated header')
    refused(lambda: h.parse(n3pp([(2, 210, [.3] * 5)], version=2)), 'version 2')
    refused(lambda: h.parse(n3pp([(3, 210, [.3] * 5)])), 'row kind 3')
    refused(lambda: h.parse(n3pp([(2, 210, [.3] * 5)], count=2)), 'truncated at row 1')
    refused(lambda: h.parse(good[:-2]), 'truncated at row 0')
    refused(lambda: h.parse(good + b'\0'), '1 trailing bytes')
    refused(lambda: h.parse(n3pp([(2, 210, [1.5, .7, .1, 1.0, .65])])), 'threshold bounds')
    refused(lambda: h.parse(n3pp([(2, 210, [.3, .7, .1, 1.0, float('nan')])])), 'lift is not a finite number')
    print('PASS 00477860 rows (kind 2: threshold, bloom scale, exposure, saturation, lift; kind 1 without the lift; '
          'a later row replaces a key), 00476f50 defaults with no row, the 2233 rate and variance, refusals', flush=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        zones = [[210, 'Zones\\Moradon.gtd', 'Moradon'], [10, 'Zones\\karus2004.gtd', 'karus2004']]
        inst = install(tmp / 'ok', good, zones)
        value, report = h.cook(210, inst)
        assert value['threshold'] == f32(.367) and value['adapt_rate'] == .3
        assert report['row'] == 'kind 2' and report['zone_2145'] == dict(name='Moradon', map='Zones\\Moradon.gtd')
        assert set(report['files']) == {h.HDR, h.ZONES}
        value, report = h.cook(10, install(tmp / 'norow', good, zones))
        assert report['row'] == 'none: 00476f50 defaults' and value['bloom'] == 1.5
        refused(lambda: h.cook(21, install(tmp / 'nozone', good, zones)), 'zone 21 is not a row of the 2145')
        refused(lambda: h.cook(210, install(tmp / 'tampered', good, zones, tamper=h.HDR)), 'differs from the 2145')
        refused(lambda: ko_glow_2233.Install(tmp / 'none'), 'no 2145 install')
        cooked = tmp / 'postprocess.bin'
        cooked.write_bytes(postprocess.cook(h.cook(210, inst)[0]))
        p = subprocess.run([str(CHECK), str(cooked)], capture_output=True, text=True)
        assert p.returncode == 0 and 'threshold=0.367 bloom=0.7 exposure=0.1 saturation=1 lift=0.65 adapt_rate=0.3 ' \
            'blur_variance=1' in p.stdout, (p.stdout, p.stderr)
    print('PASS the cook: the zone key\'s row or 00476f50\'s defaults, the 2145 zone recorded, the install and its '
          'manifest checked, an unknown zone refused; the client reader takes the cooked file', flush=True)

    if '--local' in sys.argv:
        if not (ko_glow_2233.INSTALL / 'manifest.json').is_file():
            print('SKIP --local: no 2145 install at %s' % ko_glow_2233.INSTALL, flush=True)
            return
        value, report = h.cook(210)
        assert report['rows'] == 55 and report['row'] == 'kind 2', report
        assert report['zone_2145'] == dict(name='Moradon', map='Zones\\Moradon.gtd'), report
        expected = dict(threshold=.367, bloom=.7, exposure=.1, saturation=1.0, lift=.65, adapt_rate=.3, blur_variance=1.0)
        assert value.keys() == expected.keys() and all(abs(value[k] - v) < 1e-5 for k, v in expected.items()), value
        assert report['files'][h.HDR] == '11eda3ee0351522e242aee6e45deec9ba41c12463a6a41462dbd98d6c39ec6cf'
        print('PASS --local: 2145 hdr.n3pp (55 rows) row 210 (Moradon): threshold 0.367, bloom scale 0.7, exposure '
              '0.1, saturation 1.0, lift 0.65; rate 0.3 /s, variance 1.0', flush=True)


if __name__ == '__main__':
    main()
