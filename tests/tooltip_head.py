"""PQ-354 (D-194): read an item tooltip's head from a test client's output and
check it in the capture.

The test client's item tooltip replay (N3E_TEST_ITEM_TOOLTIP) prints each row
(ITEM_TOOLTIP: its text; ITEM_TOOLTIP_STYLE: its colour and whether it is
centred) and the tooltip as drawn for its capture (ITEM_TOOLTIP_DRAWN: the box,
the HUD scale and font metrics; ITEM_TOOLTIP_LINE: each row's origin and drawn
width). check() asserts the head rows' texts, colours and centring, and that
in the capture each head row's glyph band holds pixels of its colour (scaled
by the glyph's brightness) and none of the tooltip's old yellow (unless the
row is yellow).

The colour match accepts a pixel k x the colour for a brightness k >= 0.5, so
for a neutral colour (white) any light grey of the backdrop under the
translucent KO tooltip would match too. check() therefore takes the replay's
capture of the same view before the hover (`base`, no tooltip) and counts the
same band there as a control: a row must hold `least` matching pixels more
than its control. A white row drawn in a darker neutral (KO's glyph cores are
130-230, so a 0x808080 row stays below k = 0.5) or not drawn fails.
"""
import re
from pathlib import Path

import npc_looks_live

YELLOW = 0xFFFF00


def parse(text, key):
    """(rows: [(text, colour, centred)], drawn: dict(rect, scale, advance,
    height, lines: [(x, y, width)])) for the tooltip of slot `key`."""
    k = re.escape(key)
    rows = re.findall(r"^ITEM_TOOLTIP key=%s row=(\d+) text=(.*)$" % k, text, re.M)
    styles = re.findall(r"^ITEM_TOOLTIP_STYLE key=%s row=(\d+) color=([0-9a-f]{6}) centred=([01])$" % k, text, re.M)
    assert rows and [r for r, _ in rows] == [r for r, _, _ in styles], (rows, styles)
    drawn = re.findall(r"^ITEM_TOOLTIP_DRAWN key=%s rect=([0-9.e+-]+),([0-9.e+-]+),([0-9.e+-]+),([0-9.e+-]+) "
                       r"scale=([0-9.e+-]+) font=([0-9.e+-]+),(\d+)$" % k, text, re.M)
    lines = re.findall(r"^ITEM_TOOLTIP_LINE key=%s row=(\d+) x=([0-9.e+-]+) y=([0-9.e+-]+) width=([0-9.e+-]+)$" % k,
                       text, re.M)
    assert len(drawn) == 1 and lines, (drawn, lines)
    d = [float(v) for v in drawn[0]]
    return ([(t, int(c, 16), s == "1") for (_, t), (_, c, s) in zip(rows, styles)],
            dict(rect=tuple(d[:4]), scale=d[4], advance=d[5], height=d[6],
                 lines=[tuple(float(v) for v in line[1:]) for line in lines]))


def pixels_of(path, box, colour, tolerance=16, least=.5):
    """Pixels of `box` (x0, y0, x1, y1, floats) in the capture drawn in
    `colour` (0xRRGGBB): k x the colour within `tolerance` in every channel,
    for a brightness k of at least `least` (a glyph's texels are white to grey
    and its edges blend with the dark background, so a line's pixels are its
    colour scaled)."""
    width, height, data = npc_looks_live.read_ppm(Path(path))
    want = (colour >> 16 & 255, colour >> 8 & 255, colour & 255)
    count = 0
    for y in range(max(0, int(box[1])), min(height, int(box[3]) + 1)):
        for x in range(max(0, int(box[0])), min(width, int(box[2]) + 1)):
            i = (y * width + x) * 3
            k = max(data[i:i + 3]) / max(want)
            if k >= least and all(abs(data[i + c] - k * want[c]) <= tolerance for c in range(3)):
                count += 1
    return count


def check(text, key, shot, head, least=20, base=None):
    """`head` is the expected head rows [(text, colour)], each drawn centred;
    returns [(row text, colour, pixels of its colour, the control's count)]
    and the drawn tooltip; `base` is the capture of the same view without the
    tooltip (the replay's item-slot capture).
    Each head row must be drawn at its full text width ([font advance] x scale
    per character), centred in the box, with at least `least` pixels of its
    colour in its band and, when it is not yellow, none of the yellow every
    first row was drawn in before the head (D-194)."""
    rows, drawn = parse(text, key)
    assert rows[:len(head)] == [(t, c, True) for t, c in head], (rows, head)
    s, (x0, _, x1, _) = drawn["scale"], drawn["rect"]
    found = []
    for i, (t, c) in enumerate(head):
        x, y, width = drawn["lines"][i]
        assert abs(width - len(t) * drawn["advance"] * s) < .5, (t, width, drawn)
        assert abs(x + width / 2 - (x0 + x1) / 2) <= 1, (t, x, width, drawn["rect"])
        band = (x, y, x + width, y + 20 * s)  # the glyph quads (16 x 20 at scale s)
        n = pixels_of(shot, band, c)
        control = pixels_of(base, band, c) if base else 0
        assert n >= least + control, ("row %d %r has %d pixels of %06x, %d without the tooltip"
                                      % (i, t, n, c, control), band)
        if c != YELLOW:
            assert not pixels_of(shot, band, YELLOW), ("row %d %r has yellow" % (i, t), band)
        found.append((t, "%06x" % c, n, control))
    return found, drawn
