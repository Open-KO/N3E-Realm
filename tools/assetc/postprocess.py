"""Package screen post-process: bloom and tone map (PQ-316, D-185). Original n3e code.

Source form (package manifest key ``postprocess``)::

    {"threshold": 0.367, "bloom": 0.7, "exposure": 0.1, "saturation": 1.0,
     "lift": 0.65, "adapt_rate": 0.3, "blur_variance": 1.0}

The client renders the world scene into its own target and, when the player
turns the post-process on, runs a fixed chain over it before the HUD
(client/render/postprocess.h): a bright pass that keeps the 2x2-average colour
whose luminance is at least ``threshold``; a luminance reduction (log average,
maximum, minimum) read back to the CPU and adapted toward the measured values
by at most ``adapt_rate`` per second; a 4x4 downscale of the bright pass; a
separable 9-tap Gaussian blur of variance ``blur_variance`` (in downscaled
texels) whose normalised weights are multiplied by ``bloom`` in each pass; and
a composite of scene plus bloom through an extended Reinhard tone map,
``k = Lm (1 + Lm / W^2) / (1 + Lm) + lift`` with ``Lm = L / average x
exposure`` and the white point ``W = maximum x (1 + bloom)``, then a
saturation of ``saturation`` around the result's luminance.

The chain is the 2233 client's (CN3PostProcess, a 2233/2145 addition; 1298 has
none), described with its addresses in
docs/implementation/evidence/pq-316-hdr-bloom-post-process-2233.md. Which
values a zone uses is package data; the KO cook fills them from the player's
own 2145 ``Zones/hdr.n3pp`` (tools/assetc/ko_hdr_2233.py).

Cooked as ``postprocess.bin``: ``N3PF`` then seven f32 in the order of
``FIELDS``. It needs the presentation assets and engine 33, as ``effects.bin``.
"""
import math
import struct

MAGIC = b"N3PF"
# name: (lowest, highest, lowest excluded)
BOUNDS = {
    "threshold": (0.0, 1.0, False),
    "bloom": (0.0, 4.0, False),
    "exposure": (0.0, 16.0, False),
    "saturation": (0.0, 4.0, False),
    "lift": (0.0, 4.0, False),
    "adapt_rate": (0.0, 100.0, False),
    "blur_variance": (0.0, 16.0, True),
}
FIELDS = tuple(BOUNDS)
SIZE = 4 + 4 * len(FIELDS)


def check(name, value):
    """The value as the readers see it, rounded to f32, within its bounds
    (a variance above 0 that rounds to 0 in f32 is refused here, as the
    readers refuse it)."""
    low, high, open_low = BOUNDS[name]
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("postprocess %s is not a finite number" % name)
    try:
        value = struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError:
        raise ValueError("postprocess %s bounds" % name)
    if value > high or value < low or (open_low and value == low):
        raise ValueError("postprocess %s bounds" % name)
    return value


def cook(c):
    if not isinstance(c, dict) or set(c) != set(FIELDS):
        raise ValueError("postprocess fields")
    values = [check(name, c[name]) for name in FIELDS]
    return MAGIC + struct.pack("<%df" % len(values), *values)


def parse(data):
    """The fields of a cooked postprocess.bin, refused as the readers refuse it."""
    if len(data) != SIZE or data[:4] != MAGIC:
        raise ValueError("postprocess format")
    values = struct.unpack("<%df" % len(FIELDS), data[4:])
    return {name: check(name, v) for name, v in zip(FIELDS, values)}
