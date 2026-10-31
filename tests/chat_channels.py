"""Real TLS three-peer chat privacy, authentication and lifecycle checks."""
import os
import math
import time
from world_peer import blob, first, integer


def audit(connect):
    unselected = connect('companion', select=False)
    unselected.send(31, blob(1, 'Explorer') + blob(2, 'unauthorized'))
    assert first(unselected.until(4)[1], 1) == 5
    unselected.logout()
    a, b, observer = [connect(name) for name in ('explorer', 'companion', 'bystander')]
    peers = [a, b, observer]

    def drain(seconds=.25, allowed=None):
        deadline = time.monotonic() + seconds
        for peer in peers:
            peer.send(14)
        while time.monotonic() < deadline:
            for peer in peers:
                tag, data = peer.receive()
                assert tag != 11 or peer is allowed, ('chat leak', peer.id, data)

    def cooldown():
        drain(1.1)

    def whisper(recipient, text='private'):
        # Unknown/forged sender fields cannot change authenticated identity.
        a.send(31, blob(1, recipient) + blob(2, text) + integer(99, observer.id))

    if os.environ.get('N3E_CHAT_LEGACY'):
        whisper('Companion', 'must never become public')
        assert first(a.until(4)[1], 1) == 5
        drain(.6)
        print('PASS pre-extension server rejects private envelope without broadcasting text', flush=True)
        return

    a.send(11, blob(1, 'local') + integer(2, b.id) + blob(3, 'Impostor') + integer(4, 1))
    for peer in peers:
        chat = peer.until(11)[1]
        assert first(chat, 1) == b'local'
        assert first(chat, 2) == a.id and first(chat, 3) == b'Explorer'
        assert first(chat, 4) == 0
    cooldown()
    whisper('companion', 'secret')
    chat = b.until(11)[1]
    assert first(chat, 1) == b'secret' and first(chat, 2) == a.id
    assert first(chat, 3) == b'Explorer' and first(chat, 4) == 1
    drain()
    a.send(11, blob(1, 'rate bypass'))
    assert first(a.until(4)[1], 1) == 4
    drain()
    print('PASS private chat authenticated names, recipient-only delivery, no sender echo, shared local/private rate limit', flush=True)

    # Traverse out of local interest: private delivery remains name-addressed.
    end = time.monotonic() + 12
    while time.monotonic() < end:
        for peer in peers:
            peer.pump(.01)
        e = b.entities[b.id]
        dx, dz = -first(e, 3), 9 - first(e, 5)
        distance = math.hypot(dx, dz)
        if distance < .25:
            break
        b.move(dx / distance, dz / distance, mode=1)
    else:
        raise AssertionError('travel timeout')
    b.move(0, 0)
    drain()
    assert b.id not in a.entities
    cooldown()
    whisper('Companion', 'distant private')
    assert first(b.until(11)[1], 1) == b'distant private'
    drain()
    print('PASS private chat crosses local interest boundary without bystander disclosure', flush=True)

    for name, text in [('Missing', 'absent'), ('Explorer', 'self'), ('', 'empty recipient'), ('../Companion', 'bad name'), ('Companion', ''), ('Companion', 'x'*257), ('Companion', 'line\nbreak')]:
        cooldown()
        whisper(name, text)
        assert first(a.until(4)[1], 1) == 4, name
        drain()
    old_id = b.id
    b.logout()
    peers.remove(b)
    cooldown()
    whisper('Companion')
    assert first(a.until(4)[1], 1) == 4
    b = connect('companion')
    peers.append(b)
    assert b.id != old_id
    cooldown()
    whisper('Companion', 'fresh session')
    assert first(b.until(11)[1], 1) == b'fresh session'
    drain()
    print('PASS unavailable/self/malformed/bounded recipient errors and reconnect routing to fresh identity', flush=True)
    collision = connect('companion', select=False)
    other_id = collision.create('COMPANION')
    assert collision.select(other_id)[0] == 10
    peers.append(collision)
    cooldown()
    whisper('CoMpAnIoN', 'ambiguous recipient')
    assert first(a.until(4)[1], 1) == 4
    drain()
    cooldown()
    whisper('Companion', 'exact recipient')
    assert first(b.until(11)[1], 1) == b'exact recipient'
    drain()
    print('PASS selection required and case-distinct names cannot redirect ambiguous private messages', flush=True)



if __name__ == '__main__':
    import subprocess
    import sys
    subprocess.run([sys.executable, 'tools/demo_session.py', '--chat-check'], check=True)
