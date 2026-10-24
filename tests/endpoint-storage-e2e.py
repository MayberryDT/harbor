#!/usr/bin/env python3
"""Native endpoint promotion under partial write, crash and fsync failures.
Failures: partial final anchor bricks the peer; readable but uncommitted anchor
promotes a pin; restart loses the probe debt; hidden partial staging becomes
an authority. Restoring storage must recover actual encrypted message delivery.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
spec=importlib.util.spec_from_file_location('peers',Path(__file__).with_name('group-admin-e2e.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
spec=importlib.util.spec_from_file_location('consent',Path(__file__).with_name('device-consent-fixture.py'))
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
binary=Path(sys.argv[1]).resolve();shim=Path(sys.argv[2]).resolve();receipt=Path(sys.argv[3]).resolve()
expected=hashlib.sha256(binary.read_bytes()).hexdigest();shim_sha=hashlib.sha256(shim.read_bytes()).hexdigest();checks=[]
for mode,variable in (('partial-write','HARBOR_E2E_FAIL_ANCHOR_WRITE'),('file-fsync','HARBOR_E2E_FAIL_ANCHOR_FILE_FSYNC'),
                       ('directory-fsync','HARBOR_E2E_FAIL_ANCHOR_DIR_FSYNC'),('partial-write-crash','HARBOR_E2E_CRASH_ANCHOR_WRITE')):
    if len(sys.argv)>4 and mode not in sys.argv[4].split(','):continue
    print('endpoint storage: '+mode,flush=True)
    with tempfile.TemporaryDirectory(prefix='harbor-anchor-storage-') as temporary:
        root=Path(temporary);failure=root/'failure';seen=root/'seen';people_failure=root/'people-failure';devices_failure=root/'devices-failure';failure.touch()
        a=p.Peer(binary,root,'alice');b=p.Peer(binary,root,'bob');running=[a,b]
        def start_target():
            os.environ.update(LD_PRELOAD=str(shim),HARBOR_E2E_ANCHOR_FAULT_SEEN=str(seen),HARBOR_E2E_FAIL_CONTACT_FSYNC=str(people_failure),HARBOR_E2E_FAIL_DEVICES_FSYNC=str(devices_failure))
            os.environ[variable]=str(failure)
            try:target=p.Peer(binary,root,'laptop');running.append(target);return target
            finally:
                for name in ('LD_PRELOAD','HARBOR_E2E_ANCHOR_FAULT_SEEN','HARBOR_E2E_FAIL_CONTACT_FSYNC','HARBOR_E2E_FAIL_DEVICES_FSYNC',variable):os.environ.pop(name,None)
        target=start_target()
        def device(peer,op,**fields):
            request='storage-'+str(peer.mark());peer.send({'op':op,'request':request,**fields})
            result=peer.wait(lambda e:e.get('request')==request and e.get('event') in ('devices','devices.error'),15)
            assert result['event']=='devices',result
            return result
        try:
            ak=p.start_identity(a);bk=p.start_identity(b);tk=p.start_identity(target)
            alice=device(a,'device.initialize',nickname='Alice');bob=device(b,'device.initialize',nickname='Bob')
            proposal=device(target,'device.propose')
            roster=device(a,'device.authorize',payload=proposal['proposal'],text=c.consent(target,alice['person']),nickname='Laptop',accept=True)
            device(target,'device.adopt',key=alice['person'],text=roster['roster'],accept=True)
            p.pair(a,b,bk,'anchor-storage')
            deadline=time.monotonic()+180
            while not seen.exists() and time.monotonic()<deadline:time.sleep(.2)
            assert seen.exists(), (mode,'storage fault never exercised')
            anchor=target.home/'endpoint-anchors'/bk;pin=target.home/'ratchet/rk'/('d:'+bk)
            assert not pin.exists(), (mode,'pin promoted before durability succeeded')
            assert any(path.read_bytes()[64:96]==bytes.fromhex(bk) for path in (target.home/'endpoint-probes').iterdir() if not path.name.startswith('.'))
            if mode=='directory-fsync':assert anchor.exists() and len(anchor.read_bytes())==128
            else:assert not anchor.exists(), (mode,'partial anchor published at final name')
            if mode=='partial-write-crash':
                deadline=time.monotonic()+15
                while target.process.poll() is None and time.monotonic()<deadline:time.sleep(.1)
                assert target.process.poll()==78
                assert any(path.stat().st_size<128 for path in (target.home/'endpoint-anchors').glob('.anchor.*'))
                failure.unlink();target.stop();target=start_target();p.start_identity(target)
            elif mode in ('file-fsync','directory-fsync'):
                target.process.kill();target.process.wait(timeout=5);target.stop();target=start_target();p.start_identity(target)
                time.sleep(3)
                assert not pin.exists(),(mode,'restart trusted a failed durability step')
                if mode=='directory-fsync':
                    people_failure.touch();time.sleep(3)
                    proposals=[path for path in (target.home/'endpoint-probes').iterdir()
                               if not path.name.startswith('.') and path.read_bytes()[64:96]==bytes.fromhex(bk)]
                    assert proposals and all(not (path.read_bytes()[136]&2) for path in proposals),'temporary roster read closed the valid probe'
                    people_failure.unlink();checks.append('temporary-roster-read-retains-probe')
                failure.unlink()
            else:
                # Exercise cleanup, then explicitly redeem while reservation
                # reads are unavailable. Ownership must survive the read error.
                devices_failure.touch()
                proposals=[path for path in (target.home/'endpoint-probes').iterdir()
                           if not path.name.startswith('.') and path.read_bytes()[64:96]==bytes.fromhex(bk)]
                assert proposals
                for path in proposals:
                    data=bytearray(path.read_bytes());data[128:136]=(int(time.time())-1).to_bytes(8,'big');data[136]=3;path.write_bytes(data)
                time.sleep(3)
                assert all(path.read_bytes()[136]&1 for path in proposals),'failed own-device read discarded cleanup debt'
                invitation_marker=b.mark();b.send({'op':'invite.create','kind':'direct','ttlSec':300,'request':'cleanup-invite'})
                invitation=b.wait(lambda e:e.get('event')=='invite' and e.get('request')=='cleanup-invite' and isinstance(e.get('url'),str) and 'k=direct' in e['url'],15,invitation_marker)
                marker=target.mark();target.send({'op':'invite.redeem','id':'cleanup-recovery','payload':invitation['url']})
                target.wait(p.event_is('invite.redeemed',kind='direct'),30,marker)
                assert pin.exists(),'explicit invite lost ownership of the provisional friendship'
                devices_failure.unlink();failure.unlink();checks.append('failed-own-device-read-retains-cleanup-ownership')
            deadline=time.monotonic()+180
            while (not anchor.exists() or not pin.exists()) and time.monotonic()<deadline:time.sleep(.2)
            assert anchor.exists() and pin.exists(),(mode,'promotion did not recover')
            assert anchor.read_bytes()==bytes.fromhex(bob['person']+bob['proposal'])
            assert anchor.stat().st_nlink==1
            target.send({'op':'msg.send','conversation':'p:'+bob['person'],'key':bob['person'],'id':'storage-recovered','text':'anchor '+mode+' recovered'})
            b.wait(p.event_is('message',text='anchor '+mode+' recovered',dir='in'),180)
            checks.append(mode)
        finally:
            for peer in running:peer.stop()
assert hashlib.sha256(binary.read_bytes()).hexdigest()==expected and hashlib.sha256(shim.read_bytes()).hexdigest()==shim_sha
receipt.write_text(json.dumps({'runner_path':str(Path(__file__).resolve()),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runner_manifest':str(Path(__file__).resolve().parent.parent/'manifest.json'),'suite':'native-endpoint-storage-recovery','helper_sha256':expected,'shim_sha256':shim_sha,'passed':checks,
    'scope':'actual write/fsync failures and process crash; not power-loss simulation'},indent=2)+'\n')
print('endpoint-storage-e2e: pass',flush=True)
