#!/usr/bin/env python3
"""Persistent, isolated local Moradon feature demo; imported assets remain local.

--layout chooses the Moradon map (PQ-223, D-171): xmas, the default, is the map
the pinned Zones.tbl names for key 210 (Moradon_xmas); classic is the same
install's own Zones/moradon.* that the table does not name; 1097 is the 2003
Moradon of the player's own KnightOnline_1097.exe (PQ-224, D-172: that install's
Zones.tbl key 21, its headerless Zones/moradon.* and the GTT files, meshes and
textures they name, with the 2004 client's player, HUD and feature data). Each
layout has its own package, Compose project, server image tag, port, realm and
state, so choosing one never touches another's stack:
  xmas     build/packages/moradon          n3e-moradon          7780
  classic  build/packages/moradon-classic  n3e-moradon-classic  7799
  1097     build/packages/moradon-1097     n3e-moradon-1097     7801
When the 1097 install is not unpacked yet, ref/ko-bin/installer/KnightOnline_1097.exe
is unpacked first by the pinned tools/ko-reference/unpack_installer.py (nothing
in it is run).

--glow-2233 (PQ-315, D-184) adds the 2233 client's equipment glow, a 2233/2145
addition the 1298 client does not have, cooked from the player's own 2145
install (build/ko-reference/installer-2145, unpacked first from
ref/ko-bin/installer/KnightOnlineSetup_v2145.exe by tools/ko-reference/unpack_inno.py
when missing). It is a package, project, image tag, port and realm of its own
beside the layout's (suffix -glow2233; ports 7803, 7805 and 7807 for xmas,
classic and 1097), so the plain stacks are never touched. In that package the
two-hand blade is drawn as Durandal, which glows (PQ-320), and named and shown
as Durandal in the inventory's equipment and bag slots and their tooltips (PQ-321).
It also carries the rogue Krowaz Assassin armour (PQ-319, D-190), drawn with
its 2145 artwork and glowing, in four equipment slots that package adds; each
new character gets the five parts in its bag.
The same package carries the zone's 2233 HDR bloom and tone map from the 2145
Zones/hdr.n3pp (PQ-316, D-185), which the client draws only with Option.ini
[Addition2233] HDR=1.
"""
import argparse,json,os,pathlib,re,secrets,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)
# layout -> (ko_bake.py arguments before --features, name suffix, default port);
# the first argument is the Zones.tbl key the state records (21 is the 1097 table's).
LAYOUTS={'xmas':(['210'],'',7780),'classic':(['210','--layout=classic'],'-classic',7799),
         '1097':(['21','--client=1097'],'-1097',7801)}
INSTALLER_1097=ROOT/'ref/ko-bin/installer/KnightOnline_1097.exe'
INSTALLER_2145=ROOT/'ref/ko-bin/installer/KnightOnlineSetup_v2145.exe'
GLOW_PORTS={'xmas':7803,'classic':7805,'1097':7807}
p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('zone',nargs='?',default='210',help='Zones.tbl zone key (210 is Moradon)')
p.add_argument('--companion',action='store_true',help='join the running demo as Companion, without restarting it')
p.add_argument('--tools',action='store_true',help='use the tools client; server permissions remain character-authorized')
p.add_argument('--reuse',action='store_true',help='join the running demo without rebuilding or restarting it')
p.add_argument('--no-build',action='store_true',help='use the already built client/server and cooked feature package')
p.add_argument('--provision-only',action='store_true',help='prepare the local demo and credentials without opening a client')
p.add_argument('--des',action='store_true',help="exploration: Demon's Souls characters from the user's own dump, in a separate package and realm")
p.add_argument('--glow-2233',action='store_true',help="the 2233 client's equipment glow from your own 2145 install (a 2233/2145 addition), in a package and realm of its own")
p.add_argument('--layout',choices=sorted(LAYOUTS),default='xmas',help='the Moradon map: xmas (the default, Zones.tbl key 210), classic (the install\'s own unnamed Zones/moradon.*) or 1097 (the 2003 Moradon of your KnightOnline_1097.exe)')
raw=sys.argv[1:];separator=raw.index('--') if '--' in raw else len(raw)
args=p.parse_args(raw[:separator]);client_args=raw[separator+1:]
if not re.fullmatch('[0-9]{1,9}',args.zone):p.error('the zone is a Zones.tbl key such as 210 (Moradon)')
bake,layout_suffix,layout_port=LAYOUTS[args.layout]
if args.layout!='xmas' and (args.des or args.zone!='210'):p.error('--layout %s is Moradon (zone 210) without --des'%args.layout)
if args.glow_2233 and args.des:p.error('--glow-2233 does not combine with --des')
if args.glow_2233:layout_suffix,layout_port=layout_suffix+'-glow2233',GLOW_PORTS[args.layout]
suffix='-des' if args.des else layout_suffix
work=ROOT/('build/moradon-demo'+suffix if not layout_suffix else 'build/moradon'+suffix+'-demo');work.mkdir(parents=True,exist_ok=True)
package=ROOT/('build/packages/moradon'+suffix)
project='n3e-moradon'+suffix;env=os.environ.copy()
# The default and --des stacks keep their image tag; another layout builds its own.
env.update(N3E_UID=str(os.getuid()),N3E_GID=str(os.getgid()),N3E_IMAGE='n3e-moradon%s:local'%layout_suffix,N3E_PACKAGE_PATH=str(package))
compose=['docker','compose','-p',project]
def run(*cmd,input=None,capture=False):
    return subprocess.run(cmd,env=env,input=input,text=True,check=True,capture_output=capture)
def sql(query):
    return run(*compose,'exec','-T','postgres','psql','-U','n3e','-d','n3e','-At','-v','ON_ERROR_STOP=1',input=query,capture=True).stdout.strip()
def quote(value):return "'"+value.replace("'","''")+"'"
state_path=work/'session.json'
if args.reuse or args.companion:
    start='tools/play-moradon'+('' if args.layout=='xmas' else ' --layout '+args.layout)+(' --glow-2233' if args.glow_2233 else '')
    if not state_path.exists():raise SystemExit('Start %s once before joining the companion.'%start)
    state=json.loads(state_path.read_text());env.update(N3E_PORT=str(state['port']),N3E_REALM=state['realm'])
    if state['release']!=(package/'release.sha256').read_text().strip():raise SystemExit('Cooked package changed; run %s to start its matching realm.'%start)
else:
    if not args.no_build:
        run('make',*(['TOOLS=1'] if args.tools else []),'client','server')
        if args.layout=='1097' and not (ROOT/'build/ko-reference/installer-1097/manifest.json').is_file():
            if not INSTALLER_1097.is_file():raise SystemExit('The 1097 Moradon needs your own KnightOnline_1097.exe at %s.'%INSTALLER_1097)
            run(sys.executable,'-I','tools/ko-reference/unpack_installer.py',str(INSTALLER_1097))
        if args.glow_2233 and not (ROOT/'build/ko-reference/installer-2145/manifest.json').is_file():
            if not INSTALLER_2145.is_file():raise SystemExit('The 2233 equipment glow needs your own KnightOnlineSetup_v2145.exe at %s.'%INSTALLER_2145)
            run(sys.executable,'-I','tools/ko-reference/unpack_inno.py',str(INSTALLER_2145))
        run(sys.executable,'tools/assetc/ko_bake.py',*(bake if args.layout!='xmas' else [args.zone]),'--features',*(['--des'] if args.des else []),*(['--glow-2233'] if args.glow_2233 else []))
    recipe=json.loads((package/'recipe.json').read_text())['manifest']
    if recipe['engine_version']<33 or 'storage_auth' not in recipe:raise SystemExit('Cook the Moradon feature package before using --no-build.')
    if layout_suffix:
        # The package must be this layout's feature cook (its provenance names the layout).
        cooked=json.loads((ROOT/('build/ko-moradon'+suffix)/'provenance.json').read_text())
        if cooked.get('features',{}).get('layout')!=(None if args.layout=='xmas' else args.layout) or ('glow_2233' in cooked)!=args.glow_2233 or ('hdr_2233' in cooked)!=args.glow_2233:
            raise SystemExit('build/packages/moradon%s is not the %s feature cook; run without --no-build.'%(suffix,args.layout+(' --glow-2233' if args.glow_2233 else '')))
    run('bash','deploy/local-ca.sh')
    release=(package/'release.sha256').read_text().strip()
    state={'port':int(env.get('N3E_PORT','7782' if args.des else str(layout_port))),'realm':'test-moradon'+suffix+'-'+release[:12],'release':release,'zone':args.zone if args.layout=='xmas' else bake[0]}
    if layout_suffix:state.update(layout=args.layout,project=project,package='moradon'+suffix)
    if args.glow_2233:state.update(glow_2233=True)
    env.update(N3E_PORT=str(state['port']),N3E_REALM=state['realm'])
    run(*compose,'build','server')
    run(*compose,'up','-d','--wait','postgres','redis')
    run(*compose,'run','--rm','--no-deps','migrate')
    # Stop only this demo's server, allowing its lease to drain before conversion.
    run(*compose,'stop','server')
    if not sql('SELECT 1 FROM realm_reward_policy WHERE realm='+quote(state['realm'])+';'):
        run(*compose,'run','--rm','--no-deps','-e','N3E_TEST_PROGRESSION=disposable','server','convert-progression')
    run(*compose,'up','-d','--wait','--force-recreate','server')
    state_path.write_text(json.dumps(state,indent=2)+'\n')
role='companion' if args.companion else 'explorer'
credentials=work/(role+'.json')
if credentials.exists():account=json.loads(credentials.read_text())
else:
    account={'account':'moradon'+role+secrets.token_hex(4),'password':secrets.token_urlsafe(24)}
    run(*compose,'exec','-T','server','n3e-server','account-create',account['account'],input=account['password']+'\n',capture=True)
    with os.fdopen(os.open(credentials,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w')as f:json.dump(account,f)
# Existing credential changes survive repeat launches; provisioning is insert-only.
if not sql('SELECT 1 FROM storage_credentials s JOIN accounts a ON a.id=s.account_id WHERE a.name='+quote(account['account'])+' AND s.realm='+quote(state['realm'])+';'):
    run(*compose,'exec','-T','server','n3e-server','storage-password-init',account['account'],input='Moradon1\n',capture=True)
sys.path.insert(0,str(ROOT/'tests'))
from world_peer import Peer
recipe=json.loads((package/'recipe.json').read_text())['manifest']
peer=Peer(state['port'],account['account'],account['password'],content=state['release'],game=recipe['game_id'],protocol=recipe['protocol_version'])
if not peer.characters:peer.create('Companion' if args.companion else 'Explorer')
character=peer.characters[0][0];peer.s.close()
if role=='explorer':run(*compose,'exec','-T','server','n3e-server','role','grant',account['account'],str(character),state['realm'],'movement.turbo',capture=True)
print('Moradon feature demo%s%s: '%('' if args.layout=='xmas' else ' ('+args.layout+' layout)',' with the 2233 equipment glow' if args.glow_2233 else '')+role.title()+' on localhost:'+str(state['port']),flush=True)
if args.glow_2233:print('Equipment glow: a 2233/2145 addition (KO 1298 has none). The Round Shield (2145 item 170251015) and, in this package, '
                       'the two-hander, named, shown and drawn as Durandal (2145 item 126311011), glow, each a pulse at 2x; '
                       'Option.ini [Addition2233] EquipmentGlow=0 turns it off.',flush=True)
if args.glow_2233:print('Upgrade paths (2145 data, 2233 glow): a normal upgrade, +10 included, does not glow; a reverse '
                       'upgrade glows by grade (+1-4 pulse 1x, +5-10 steady 1x, +11-20 pulse 2x, +21-30 steady 2x). '
                       'Each new character\'s bag (two pages) holds both paths; their tooltips name each in its '
                       'kind\'s colour (<selfname> is your character\'s name) with the kind line under it.',flush=True)
if args.glow_2233:print('Krowaz Assassin armour, five rogue parts per grade (head, upper, lower, hands, feet): '
                       'normal +10 (items 248001020-248005020, no glow), reverse +1 (258001001-258005001, pulse 1x) '
                       'and reverse +30 (258001030-258005030, steady 2x).',flush=True)
if args.glow_2233:print('<selfname>\'s Azagai bow (left hand): plain (1110532000), normal +10 (1110432510, no glow), '
                       'reverse +1 (1110532501, pulse 1x), +10 (1110532510, steady 1x) and +30 (1110532600, steady 2x); '
                       'every upgrade draws its poison weapon effect.',flush=True)
if args.glow_2233:print('HDR bloom: a 2233/2145 addition (KO 1298 has none), with this zone\'s 2145 hdr.n3pp settings; '
                       'off unless Option.ini [Addition2233] HDR=1 (in $XDG_CONFIG_HOME/n3e or ~/.config/n3e).',flush=True)
print('Inventory / Character / Invite and the top-center UIF buttons open features.',flush=True)
print('KO keys: T walk/run, E auto-run, Z/X/B target, R attack, F1-F8 and PgUp/PgDn hotbar pages, U character, F10 help; click a chest to loot; F12 reconnects.',flush=True)
print('Warehouse initial password: Moradon1 (your changes persist). Help lists commands.',flush=True)
again='tools/play-moradon'+('' if args.layout=='xmas' else ' --layout '+args.layout)+(' --glow-2233' if args.glow_2233 else '')
print('Second player: %s --companion. Rejoin: %s --reuse.'%(again,again),flush=True)
if layout_suffix:print('Stop: docker compose -p %s stop (down -v also removes its characters).'%project,flush=True)
if args.provision_only:sys.exit(0)
size=env.get('N3E_WINDOW_SIZE','1280x1024')
if size not in ('1024x768','1280x1024','1600x1200'):raise SystemExit('N3E_WINDOW_SIZE must be 1024x768,1280x1024 or1600x1200')
env.update(N3E_TEST_ACCOUNT=account['account'],N3E_TEST_PASSWORD=account['password'])
cmd=[str(ROOT/('build/client-tools/n3e-test-client' if args.tools else 'build/client/n3e-test-client')),str(package),'--connect','localhost:'+str(state['port']),'--ca','deploy/local/ca.pem','--auto-login','--fixed-window',size,*(['--fullscreen'] if env.get('N3E_FULLSCREEN')=='1' else []),*client_args]
os.execve(cmd[0],cmd,env)
