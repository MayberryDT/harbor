#!/usr/bin/env python3
"""Kill the receiving native helper at real durable-decrypt boundaries.
Failures: losing plaintext after Signal state advancement, an interrupted inbox
commit losing recovery authority, duplicate replay, and stalled acknowledgement.
Requires a separately compiled HARBOR_SYNC_FAULTS helper; production has no hook.
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
spec_journal=importlib.util.spec_from_file_location('journal_fixture',Path(__file__).with_name('journal-fixture.py'))
journal=importlib.util.module_from_spec(spec_journal);spec_journal.loader.exec_module(journal)
normal=Path(sys.argv[1]).resolve();fault=Path(sys.argv[2]).resolve();receipt=Path(sys.argv[3]).resolve()
consent_spec=importlib.util.spec_from_file_location('consent_fixture',Path(__file__).with_name('device-consent-fixture.py'))
consent_fixture=importlib.util.module_from_spec(consent_spec);consent_spec.loader.exec_module(consent_fixture)
consent=consent_fixture.consent
expected_candidates = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (normal, fault)}
def candidate_sha(path):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_candidates[path]:
        raise RuntimeError('candidate executable changed during verification')
    return actual

checks=[]
for point in ('after-envelope-commit','after-inbox'):
    with tempfile.TemporaryDirectory(prefix='harbor-sync-crash-') as temporary:
        root=Path(temporary);a=p.Peer(normal,root,'sender')
        os.environ['HARBOR_SYNC_CRASH_AT']=point
        try:b=p.Peer(fault,root,'receiver')
        finally:os.environ.pop('HARBOR_SYNC_CRASH_AT',None)
        running=[a,b]
        try:
            ak=p.start_identity(a);bk=p.start_identity(b)
            a.send({'op':'device.initialize','request':'init','nickname':'Sender'})
            owner=a.wait(p.event_is('devices',request='init'),15)
            b.send({'op':'device.propose','request':'propose'})
            proposal=b.wait(p.event_is('devices',request='propose'),15)
            a.send({'op':'device.authorize','request':'authorize','payload':proposal['proposal'],'text':consent(b,owner['person']),'nickname':'Receiver','accept':True})
            roster=a.wait(p.event_is('devices',request='authorize'),15)
            b.send({'op':'device.adopt','request':'adopt','key':owner['person'],'text':roster['roster'],'accept':True})
            b.wait(p.event_is('devices',request='adopt'),15)
            a.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==bk and e.get('online'),180)
            a.send({'op':'sync.publish','request':'publish','id':'0a'*16,'conversation':'d:'+'cd'*32,'text':'survive receiving crash'})
            a.wait(p.event_is('sync.state',request='publish'),15)
            deadline=time.monotonic()+90
            while b.process.poll() is None and time.monotonic()<deadline:time.sleep(.1)
            assert b.process.poll()==78,(point,b.process.poll())
            inbox=journal.envelopes(b,'inbox')
            assert len(inbox)==1 and next(iter(inbox.values())).startswith(b'HS2|')
            b=p.Peer(normal,root,'receiver');running.append(b);p.start_identity(b)
            b.wait(p.event_is('sync.item',id='0a'*16,text='survive receiving crash'),180)
            deadline=time.monotonic()+60
            while not any(name.startswith(bk+'.') for name in journal.envelopes(a,'ack')):
                assert time.monotonic()<deadline,'durable ACK missing'
                time.sleep(.2)
            assert len(journal.events(b))==1
            checks.append(point)
        finally:
            for peer in running:peer.stop()
receipt.write_text(json.dumps({'runner_path':str(Path(__file__).resolve()),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runner_manifest':str(Path(__file__).resolve().parent.parent/'manifest.json'),'suite':'native-replication-crash-recovery','normal_sha256':candidate_sha(normal),
    'fault_sha256':candidate_sha(fault),'passed':checks,'scope':'process crash; no power-loss simulation'},indent=2)+'\n')
print('device-sync-crash-e2e: pass',flush=True)
