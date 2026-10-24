#!/usr/bin/env python3
"""Disposable hostile signed roster over the actual native encrypted channel.
Failures: an issuer claims another pinned endpoint, installs hidden anchors from
rejected extensions, or changes an unrelated contact's permanent pin/root.
The attacker owns all fixture signing keys but never the victim's private keys.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
spec=importlib.util.spec_from_file_location('peers',Path(__file__).with_name('group-admin-e2e.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
binary=Path(sys.argv[1]).resolve();receipt=Path(sys.argv[2]).resolve();expected=hashlib.sha256(binary.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='harbor-endpoint-boundary-') as temporary:
    root=Path(temporary);a=p.Peer(binary,root,'alice');b=p.Peer(binary,root,'bob');m=p.Peer(binary,root,'mallory');laptop=p.Peer(binary,root,'bob-laptop')
    def ask(peer,op,**fields):
        request='endpoint-'+str(peer.mark());peer.send({'op':op,'request':request,**fields})
        event=peer.wait(lambda e:e.get('request')==request and e.get('event') in ('devices','devices.error'),15)
        assert event['event']=='devices',event
        return event
    fixture=root/'fixture';fixture.mkdir(mode=0o700)
    def sign(seed,message):
        key=fixture/'key.der';key.write_bytes(bytes.fromhex('302e020100300506032b657004220420')+seed)
        path=fixture/'message';path.write_bytes(message)
        return subprocess.run(['openssl','pkeyutl','-sign','-rawin','-inkey',str(key),'-keyform','DER','-in',str(path)],capture_output=True,check=True).stdout
    def public(seed):
        key=fixture/'key.der';key.write_bytes(bytes.fromhex('302e020100300506032b657004220420')+seed)
        return subprocess.run(['openssl','pkey','-in',str(key),'-inform','DER','-pubout','-outform','DER'],capture_output=True,check=True).stdout[-32:]
    try:
        ak=p.start_identity(a);bk=p.start_identity(b);mk=p.start_identity(m);lk=p.start_identity(laptop)
        alice=ask(a,'device.initialize',nickname='Alice');bob=ask(b,'device.initialize',nickname='Bob');bob_proposal=bob['proposal']
        lp=ask(laptop,'device.propose')['proposal']
        consent_spec=importlib.util.spec_from_file_location('consent',Path(__file__).with_name('device-consent-fixture.py'))
        consent=importlib.util.module_from_spec(consent_spec);consent_spec.loader.exec_module(consent)
        authorized=ask(b,'device.authorize',payload=lp,text=consent.consent(laptop,bob['person']),nickname='Laptop',accept=True)
        ask(laptop,'device.adopt',text=authorized['roster'],key=bob['person'],accept=True)
        mallory=ask(m,'device.initialize',nickname='Mallory');person=bytes.fromhex(mallory['person'])
        chain=bytearray.fromhex(mallory['roster']);issuer=(m.home/'devices/key').read_bytes()
        def append_claim(transport,ratchet):
            subject=os.urandom(32);binding=public(subject)+bytes.fromhex(transport+ratchet)
            record=bytearray(346);record[0]=2;record[1]=1;record[2:10]=(len(chain)//346).to_bytes(8,'big')
            record[10:42]=hashlib.sha256(chain[-346:]).digest();record[42:74]=bytes.fromhex(mallory['local']);record[74:170]=binding
            record[170:175]=b'Claim'
            record[218:282]=sign(subject,b'Harbor-device-consent-v2\0'+person+binding)
            record[282:346]=sign(issuer,b'Harbor-device-roster-v2\0'+person+record[:282]);chain.extend(record)
            path=m.home/'devices/roster';path.write_bytes(chain);path.chmod(0o600)
        append_claim(bk,bob_proposal[128:]);append_claim(lk,lp[128:])
        p.pair(a,m,mk,'malicious-roster')
        a.wait(p.event_is('person.info',key=mallory['person']),180)
        deadline=time.monotonic()+45
        def probes_for(key):
            return [path for path in (a.home/'endpoint-probes').glob('*') if not path.name.startswith('.') and path.read_bytes()[64:96]==bytes.fromhex(key)]
        while (not probes_for(bk) or not probes_for(lk)) and time.monotonic()<deadline:time.sleep(.2)
        assert probes_for(bk) and probes_for(lk),'hostile proposals never entered the real probe path'
        assert not (a.home/'ratchet/rk'/('d:'+bk)).exists()
        assert not (a.home/'ratchet/rk'/('d:'+lk)).exists()
        anchor=a.home/'endpoint-anchors'/bk
        assert not anchor.exists(),'foreign roster anchored a separately pinned endpoint'
        # The explicit verified invitation must supersede a hidden provisional
        # friendship. A legitimate simultaneous laptop proposal must also run
        # while the false claim's lease/cooldown still exists.
        if len(sys.argv)>3 and sys.argv[3]=='inviter':
            p.pair(a,b,bk,'explicit-alice-over-probe')
        else:
            p.pair(b,a,ak,'explicit-bob-over-probe')
        original_pin=(a.home/'ratchet/rk'/('d:'+bk)).read_bytes()
        a.wait(p.event_is('person.info',key=bob['person']),180)
        deadline=time.monotonic()+30
        while not anchor.exists() and time.monotonic()<deadline:time.sleep(.2)
        assert anchor.read_bytes()[:32]==bytes.fromhex(bob['person'])
        laptop_anchor=a.home/'endpoint-anchors'/lk
        deadline=time.monotonic()+90
        while not laptop_anchor.exists() and time.monotonic()<deadline:time.sleep(.2)
        assert laptop_anchor.exists(),'false candidate reserved the legitimate laptop discovery slot'
        assert laptop_anchor.read_bytes()[:32]==bytes.fromhex(bob['person'])
        assert (a.home/'ratchet/rk'/('d:'+bk)).read_bytes()==original_pin
        retained=(a.home/'people'/mallory['person']).read_bytes()
        fake=os.urandom(32).hex();append_claim(fake,os.urandom(32).hex());append_claim(ak,os.urandom(32).hex())
        ask(m,'device.status');time.sleep(12)
        assert not (a.home/'endpoint-anchors'/fake).exists()
        assert not any(path.read_bytes()[64:96]==bytes.fromhex(fake) for path in (a.home/'endpoint-probes').iterdir() if not path.name.startswith('.'))
        assert (a.home/'people'/mallory['person']).read_bytes()==retained
        assert anchor.read_bytes()[:32]==bytes.fromhex(bob['person'])
        assert hashlib.sha256(binary.read_bytes()).hexdigest()==expected
        receipt.write_text(json.dumps({'runner_path':str(Path(__file__).resolve()),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runner_manifest':str(Path(__file__).resolve().parent.parent/'manifest.json'),'suite':'native-endpoint-adversarial-boundary','inviter':('alice' if len(sys.argv)>3 else 'bob'),'helper_sha256':expected,
            'passed':['issuer-cannot-anchor-another-endpoint','explicit-invitation-promotes-hidden-probe','competing-legitimate-proposal-is-not-reserved-by-false-claim','legitimate-root-can-bootstrap-after-foreign-claim','existing-signal-pin-preserved','rejected-extension-creates-no-hidden-anchor-or-probe']},indent=2)+'\n')
        print('person-endpoint-boundary-e2e: pass',flush=True)
    finally:
        for peer in (a,b,m,laptop):peer.stop()
