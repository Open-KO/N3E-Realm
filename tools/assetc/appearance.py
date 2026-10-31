"""Public cosmetic keys, separate from private equipment instances."""
from common import u, string


def cook(rows, equipment):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 128:
        raise ValueError('appearance count')
    items = {i['id']: i for i in equipment['items']}
    out = b'N3V1' + u(len(rows))
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'item', 'slot'}:
            raise ValueError('appearance vocabulary')
        item, slot = row['item'], row['slot']
        if item not in items or type(slot) is not int or slot not in items[item]['slots'] or (item, slot) in seen:
            raise ValueError('appearance equipment mapping')
        seen.add((item, slot))
        out += string(item) + u(slot)
    return out
