"""Local KO icon artwork mapped to package item IDs; no gameplay data import."""
import hashlib
import re
from common import count, f, string, u


def path(base, extension=0):
    # Binary 006157b0: nonzero extension icon overrides basic-row icon.
    for value in (base, extension):
        if type(value) is not int or not 0 <= value <= 0xffffffff:
            raise ValueError('item icon ID')
    value = extension or base
    return f'UI/ItemIcon_{value//10000000:01}_{value//1000%10000:04}_{value//10%100:02}_{value%10:01}.dxt'


def path_2233(number, base, extension=0):
    """The 2233 client's icon path for item `number` (CGameBase::
    MakeResrcFileNameForUPC 009b3fc0, 009b4bc1-009b4ce1; PQ-338): no icon for
    number / 10^9 of 4 or more; the extension row's icon (+0x48) when non-zero,
    else the Item_Org row's (+0x4c); its first field printed with "%.2d"
    (00b9aa14) for number / 10^9 of 1 to 3, else "%.1d" (00b9a9f0), as 1298's
    006157b0 prints every icon."""
    if type(number) is not int or not 0 < number <= 0xffffffff or number // 10**9 >= 4:
        raise ValueError('2233 item icon number')
    first = path(base, extension)
    if number // 10**9 == 0:
        return first
    value = extension or base
    return f'UI/ItemIcon_{value//10000000:02}_{value//1000%10000:04}_{value//10%100:02}_{value%10:01}.dxt'


def cook(assets, tex, mappings):
    """`mappings`: {item: {base, extension}} (the 1298 rule, the file from the
    client's `assets`), or, only from the --glow-2233 cook, {item: {base,
    extension, item_2233, assets}} (the 2233 rule for 2145 item `item_2233`,
    the file from that entry's own `assets`, PQ-338)."""
    count(len(mappings), 256, 0)
    icons = []
    sources = []
    for item, mapping in sorted(mappings.items()):
        if not re.fullmatch(r'[a-z][a-z0-9_-]*:[a-z][a-z0-9_/-]{0,95}', item) or len(item)>200:
            raise ValueError('item icon namespace')
        if set(mapping) == {'base', 'extension'}:
            filename = path(mapping['base'], mapping['extension'])
            data = assets.get(filename)
            texture = tex(filename)
            source = dict(**mapping)
        elif set(mapping) == {'base', 'extension', 'item_2233', 'assets'} and hasattr(mapping['assets'], 'namespace'):
            filename = path_2233(mapping['item_2233'], mapping['base'], mapping['extension'])
            data = mapping['assets'].get(filename)
            texture = tex(filename, mapping['assets'])
            source = dict(base=mapping['base'], extension=mapping['extension'], item_2233=mapping['item_2233'],
                          rule='009b3fc0', assets=mapping['assets'].namespace)
        else:
            raise ValueError('item icon vocabulary')
        # Binary 004c1430 uses UV (0,0,45/64,45/64) in the UIF slot rectangle.
        icons.append((item, texture, (0, 0, 45/64, 45/64)))
        sources.append(dict(item=item, path=filename, **source,
                            sha256=hashlib.sha256(data).hexdigest()))
    return icons, sources


def encode(icons):
    data = u(count(len(icons), 256, 0))
    for item, texture, uv in icons:
        data += string(item)+u(texture)+f(uv)
    return data
