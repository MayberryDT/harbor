#!/usr/bin/env python3
"""Two people/two native devices each, one existing verified contact invitation.
Failures: treating devices as separate people, root/key substitution, copying
private transport/session state, missing contacts on a linked device, and a
roster fork silently changing trust, and a crash after durable endpoint
endorsement but before Signal pin promotion. This run verifies discovery only.
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
binary=Path(sys.argv[1]).resolve();receipt=Path(sys.argv[2]).resolve()
consent_spec=importlib.util.spec_from_file_location('consent_fixture',Path(__file__).with_name('device-consent-fixture.py'))
consent_fixture=importlib.util.module_from_spec(consent_spec);consent_spec.loader.exec_module(consent_fixture)
consent=consent_fixture.consent
expected_candidate_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
def candidate_sha():
    actual = hashlib.sha256(binary.read_bytes()).hexdigest()
    if actual != expected_candidate_sha:
        raise RuntimeError('candidate executable changed during verification')
    return actual

with tempfile.TemporaryDirectory(prefix='harbor-people-') as temporary:
    root=Path(temporary);devices=[]
    fault=Path(sys.argv[3]).resolve() if len(sys.argv)>3 else None
    fault_sha=hashlib.sha256(fault.read_bytes()).hexdigest() if fault else None
    for index,name in enumerate(('alice-desktop','alice-laptop','bob-desktop','bob-laptop')):
        if fault and index==3:os.environ['HARBOR_SYNC_CRASH_AT']='after-endorsement'
        try:devices.append(p.Peer(fault if fault and index==3 else binary,root,name))
        finally:os.environ.pop('HARBOR_SYNC_CRASH_AT',None)
    try:
        keys=[p.start_identity(peer) for peer in devices]
        roots=[]
        for index in (0,2):
            owner,new=devices[index:index+2]
            owner.send({'op':'device.initialize','request':'initialize','nickname':owner.name})
            identity=owner.wait(p.event_is('devices',request='initialize'),15);roots.append(identity['person'])
            new.send({'op':'device.propose','request':'propose'})
            proposal=new.wait(p.event_is('devices',request='propose'),15)
            owner.send({'op':'device.authorize','request':'authorize','payload':proposal['proposal'],'text':consent(new,identity['person']),'nickname':new.name,'accept':True})
            roster=owner.wait(p.event_is('devices',request='authorize'),15)
            new.send({'op':'device.adopt','request':'adopt','key':identity['person'],'text':roster['roster'],'accept':True})
            new.wait(p.event_is('devices',request='adopt'),15)
        # Recover both old non-hidden and current hidden interrupted staging.
        stale=devices[3].home/'endpoint-probes';stale.mkdir(mode=0o700,exist_ok=True)
        for name in ('roster.'+'ab'*16,'.roster.'+'cd'*16):
            path=stale/name;path.write_bytes(b'interrupted');path.chmod(0o600)
        print('pairing one device of each person',flush=True)
        p.pair(devices[0],devices[2],keys[2],'alice-bob')
        if fault:
            deadline=time.monotonic()+180
            while devices[3].process.poll() is None and time.monotonic()<deadline:time.sleep(.2)
            assert devices[3].process.poll()==78, 'endpoint promotion fault did not fire'
            anchors=list((devices[3].home/'endpoint-anchors').iterdir())
            assert anchors and any(not (devices[3].home/'ratchet/rk'/('d:'+anchor.name)).exists() for anchor in anchors)
            assert list((devices[3].home/'endpoint-probes').iterdir()), 'promotion intent was lost'
            devices[3].stop()
            devices[3]=p.Peer(binary,root,'bob-laptop');p.start_identity(devices[3])

        for index,peer in enumerate(devices):
            other=roots[1 if index<2 else 0]
            card=peer.wait(p.event_is('person.info',id='p:'+other,key=other),180)
            assert card['devices']==2,card
            peer.send({'op':'person.list','request':'people-check'})
            peer.wait(p.event_is('person.list.end',request='people-check'),15)
        # Person cards may appear before all endpoint challenges complete.
        # Every foreign destination must have its own exact durable endorsement.
        for index,peer in enumerate(devices):
            for other_index in ((2,3) if index<2 else (0,1)):
                anchor=peer.home/'endpoint-anchors'/keys[other_index]
                deadline=time.monotonic()+180
                pin=peer.home/'ratchet/rk'/('d:'+keys[other_index])
                while (not anchor.exists() or not pin.exists()) and time.monotonic()<deadline:time.sleep(.2)
                assert anchor.exists() and pin.exists(), (peer.name,devices[other_index].name,'missing endpoint endorsement/promotion')
                binding=anchor.read_bytes()
                assert len(binding)==128 and binding[:32]==bytes.fromhex(roots[1 if index<2 else 0])
                assert binding[64:96]==bytes.fromhex(keys[other_index])
                assert (peer.home/'ratchet/rk'/('d:'+keys[other_index])).exists()
        assert not any(path.name.startswith(('roster.','.roster.')) for path in (devices[3].home/'endpoint-probes').iterdir())
        if fault:assert hashlib.sha256(fault.read_bytes()).hexdigest()==fault_sha
        receipt.write_text(json.dumps({'runner_path':str(Path(__file__).resolve()),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runner_manifest':str(Path(__file__).resolve().parent.parent/'manifest.json'),'suite':'native-person-discovery','helper_sha256':candidate_sha(),'promotion_fault_sha256':fault_sha,
            'passed':['two-independent-devices-per-person','one-contact-invitation','authenticated-person-key-bindings',
                      'contacts-synchronized-to-linked-devices','each-foreign-endpoint-independently-endorsed-before-pin'],
            'scope':'person discovery; messages/groups/UI verified separately'},indent=2)+'\n')
        print('person-discovery-e2e: pass',flush=True)
    finally:
        for peer in devices:peer.stop()
