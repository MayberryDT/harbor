#!/usr/bin/env python3
"""Real-session orphan recovery with old durable ciphertext and process crashes.
Fail before implementation integration: commit a fresh Signal session but retain
old envelopes, crash during invalidation, lose logical event IDs, or strand ACKs.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
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
for point in ('after-session','during-rekey'):
    with tempfile.TemporaryDirectory(prefix='harbor-rekey-') as temporary:
        root=Path(temporary);a=p.Peer(normal,root,'sender');b=p.Peer(normal,root,'receiver');running=[a,b];paused=False
        try:
            ak=p.start_identity(a);bk=p.start_identity(b)
            a.send({'op':'device.initialize','request':'init','nickname':'Sender'})
            owner=a.wait(p.event_is('devices',request='init'),15)
            b.send({'op':'device.propose','request':'proposal'})
            proposal=b.wait(p.event_is('devices',request='proposal'),15)
            a.send({'op':'device.authorize','request':'authorize','payload':proposal['proposal'],'text':consent(b,owner['person']),'nickname':'Receiver','accept':True})
            roster=a.wait(p.event_is('devices',request='authorize'),15)
            b.send({'op':'device.adopt','request':'adopt','key':owner['person'],'text':roster['roster'],'accept':True})
            b.wait(p.event_is('devices',request='adopt'),15)
            a.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==bk and e.get('online'),180)
            a.send({'op':'sync.publish','request':'warmup','id':'ee'*16,'conversation':'d:'+'cd'*32,'text':'establish session'})
            b.wait(p.event_is('sync.item',id='ee'*16),90)
            deadline=time.monotonic()+60
            while bk+'.'+'ee'*16 not in journal.envelopes(a,'ack'):
                assert time.monotonic()<deadline;time.sleep(.2)
            # Keep the transport connected but prevent ACKs while the actual
            # encrypted outbox is created. Offline targets are not encrypted
            # speculatively by the current delivery queue.
            b.process.send_signal(signal.SIGSTOP);paused=True
            for index in range(3):
                tag=f'{index+1:032x}'
                a.send({'op':'sync.publish','request':'pending-'+str(index),'id':tag,'conversation':'d:'+'cd'*32,'text':'pending '+str(index)})
                a.wait(p.event_is('sync.state',request='pending-'+str(index)),15)
            deadline=time.monotonic()+30
            while len([name for name in journal.envelopes(a,'outbox') if name.startswith(bk+'.')])<3:
                assert time.monotonic()<deadline;time.sleep(.2)
            a.stop()
            b.process.send_signal(signal.SIGTERM);b.process.send_signal(signal.SIGCONT)
            paused=False;b.process.wait(timeout=15)
            shutil.rmtree(b.home/'ratchet/sess')
            os.environ['HARBOR_SYNC_CRASH_AT']=point
            try:a=p.Peer(fault,root,'sender')
            finally:os.environ.pop('HARBOR_SYNC_CRASH_AT',None)
            running.append(a);p.start_identity(a)
            b=p.Peer(normal,root,'receiver');running.append(b);p.start_identity(b)
            deadline=time.monotonic()+180
            while a.process.poll() is None and time.monotonic()<deadline:time.sleep(.2)
            assert a.process.poll()==78,(point,a.process.poll())
            assert bk in journal.envelopes(a,'rekey'),'recovery intent must survive the crash'
            a=p.Peer(normal,root,'sender');running.append(a);p.start_identity(a)
            for index in range(3):b.wait(p.event_is('sync.item',id=f'{index+1:032x}',text='pending '+str(index)),180)
            deadline=time.monotonic()+60
            while len([name for name in journal.envelopes(a,'ack') if name.startswith(bk+'.')])<4:
                assert time.monotonic()<deadline,'recovered events not acknowledged';time.sleep(.2)
            assert bk not in journal.envelopes(a,'rekey')
            assert len(journal.events(b))==4
            checks.append(point)
            print('rekey crash recovered: '+point,flush=True)
        finally:
            if paused and b.process.poll() is None:b.process.send_signal(signal.SIGCONT)
            for peer in running:peer.stop()
receipt.write_text(json.dumps({'runner_path':str(Path(__file__).resolve()),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runner_manifest':str(Path(__file__).resolve().parent.parent/'manifest.json'),'suite':'native-session-replacement-crash-recovery',
    'normal_sha256':candidate_sha(normal),'fault_sha256':candidate_sha(fault),
    'passed':checks,'scope':'native real relay/process crash; no power-loss simulation'},indent=2)+'\n')
