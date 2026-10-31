"""Native draggable HUD panels against the prepared Moradon stack (D-111).

Drags the chat (with its message-output follower) and the hotkey window with
SDL mouse events, exits normally so the layout is saved client-side, then
starts again and checks the restored layout. Uses a fresh account and a private
XDG_STATE_HOME; no user character or saved layout is touched.
"""
import argparse, json, os, pathlib, re, secrets, subprocess, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from world_peer import Peer
import moradon_stack

p = argparse.ArgumentParser(); p.add_argument('--size', default='1280x1024'); p.add_argument('--fullscreen', action='store_true'); a = p.parse_args()
root = pathlib.Path(__file__).resolve().parents[1]; os.chdir(root)
state = moradon_stack.state()
package = (root / moradon_stack.PACKAGE).resolve(); recipe = json.loads((package / 'recipe.json').read_text())['manifest']
assert state['release'] == (package / 'release.sha256').read_text().strip()
assert (package / 'hud.bin').read_bytes()[:4] in (b'N3HC', b'N3HD')
env = {**os.environ, 'N3E_IMAGE': moradon_stack.IMAGE, 'N3E_PACKAGE_PATH': str(package), 'N3E_PORT': str(state['port']), 'N3E_REALM': state['realm']}
account = 'panel' + secrets.token_hex(6); password = secrets.token_urlsafe(24)
subprocess.run(['docker', 'compose', '-p', moradon_stack.PROJECT, 'exec', '-T', 'server', 'n3e-server', 'account-create', account],
               input=password + '\n', text=True, env=env, capture_output=True, check=True)
peer = Peer(state['port'], account, password, content=state['release'], game=recipe['game_id'], protocol=recipe['protocol_version'])
peer.create('Pnl' + secrets.token_hex(4)); peer.s.close()
w, h = (int(v) for v in a.size.split('x'))
work = root / 'build/ko-completion/panels'; work.mkdir(parents=True, exist_ok=True)


def run(mode, state_home, size=a.size, capture=None):
    cmd = ['build/client/n3e-test-client', str(package), '--connect', 'localhost:' + str(state['port']), '--ca', 'deploy/local/ca.pem',
           '--auto-login', '--fixed-window', size, *(['--fullscreen'] if a.fullscreen else []), '--world-smoke', '90',
           *(['--capture', str(capture)] if capture else [])]
    out = subprocess.run(cmd, env={**env, 'N3E_TEST_ACCOUNT': account, 'N3E_TEST_PASSWORD': password, 'N3E_TEST_PANELS': mode,
                                   'XDG_STATE_HOME': state_home}, text=True, capture_output=True, timeout=150)
    (work / f'{mode}-{size}.log').write_text(out.stdout + out.stderr)
    assert out.returncode == 0, (mode, out.stdout[-1500:], out.stderr[-1500:])
    layouts = {}
    for m in re.finditer(r'PANEL (\S+) chat=(-?\d+),(-?\d+) hotkey=(-?\d+),(-?\d+) follower=(-?\d+),(-?\d+)', out.stdout):
        layouts[m.group(1)] = [int(v) for v in m.groups()[1:]]
    layouts['stdout'] = out.stdout
    return layouts


# XDG_STATE_HOME must be absolute; a relative one falls back to the user's HOME.
with tempfile.TemporaryDirectory(dir=root / 'build') as home:
    first = run('drag', home)
    # 005d23d0 defaults: chat (0, H-198), msgoutput at (chat.right, chat.top), hotkey (0, statebar.bottom).
    assert first['default'] == [0, h - 198, 0, 65, 541, h - 198], first
    print('PASS binary default origins: chat (0,H-198), msgoutput (541,H-198), hotkey (0,65)')
    assert first['chat-moved'][:2] == [200, h - 498] and first['chat-moved'][4:] == [741, h - 498], first
    print('PASS chat handle drag moves chat and message output as one group without a viewport clamp')
    assert first['moved'][2:4] == [0, 185], first
    print('PASS hotkey drag snaps its left edge back to the viewport edge within 10 px')
    files = list(pathlib.Path(home, 'n3e/panels').glob('*.txt'))
    assert len(files) == 1 and files[0].read_text().splitlines()[0] == 'N3P1', files
    saved = files[0].read_text()
    assert f'chat 200 {h - 498}' in saved and 'hotkey 0 185' in saved, saved
    second = run('restore', home)
    assert second['restored'] == first['moved'], (second, first)
    print('PASS normal exit saves chat and hotkey client-side; the next session restores the same layout')
    # Restore clamps into a smaller viewport (00647210) and keeps the follower attached.
    small = run('restore', home, '1024x768')['restored']
    assert small[0] == 200 and 0 <= small[1] <= 768 - 145 and small[4:] == [741, small[1]], small
    print('PASS restore into 1024x768 keeps the saved layout inside the viewport', small)

    # Overview map (Zones column 8): hidden at start, M opens it, the command-bar map
    # button closes it; the green heading arrow is drawn inside the image.
    def ppm(path):
        data = pathlib.Path(path).read_bytes(); parts = data.split(maxsplit=4)
        assert parts[0] == b'P6'; width, height = int(parts[1]), int(parts[2]); return width, height, parts[4]
    shots = work / 'minimap'
    result = run('minimap', home, capture=shots)['stdout']
    states = dict(re.findall(r'MINIMAP (open|closed) open=([01]) rect=(\S+)', result) and
                  [(m[0], (m[1], [int(float(v)) for v in m[2].split(',')])) for m in re.findall(r'MINIMAP (open|closed) open=([01]) rect=(\S+)', result)])
    assert states['open'][0] == '1' and states['closed'][0] == '0', states
    rect = states['open'][1]
    def region(path):
        width, height, pixels = ppm(path); out = []
        for y in range(rect[1], rect[3]):
            row = pixels[(y * width + rect[0]) * 3:(y * width + rect[2]) * 3]
            out.extend(tuple(row[i:i + 3]) for i in range(0, len(row), 3))
        return out
    opened, closed = region(str(shots) + '.open.ppm'), region(str(shots) + '.closed.ppm')
    green = sum(1 for r, g, b in opened if g > 200 and r < 60 and b < 60)
    assert green >= 10 and not any(g > 200 and r < 60 and b < 60 for r, g, b in closed), green
    changed = sum(1 for x, y in zip(opened, closed) if x != y)
    assert changed > len(opened) // 2, (changed, len(opened))
    print('PASS minimap hidden at start, M opens the zone overview with the heading arrow, map button closes it', rect, green)

    # Esc (PQ-010): each press closes the front-most dialog only, the most
    # recently opened first; the minimap (state-bar group) stays.
    result = run('escape', home, capture=work / 'escape')['stdout']
    assert re.findall(r'ESCAPE (\w+)=', result) == ['first', 'second', 'third'], result[-1500:]
    assert 'ESCAPE first=inventory character=open minimap=open' in result, result[-1500:]
    assert 'ESCAPE second=character minimap=open' in result and 'ESCAPE third=none minimap=open' in result, result[-1500:]
    print('PASS Esc closes the front-most window per press (inventory, then character) and keeps the minimap')
