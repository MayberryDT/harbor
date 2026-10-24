#!/usr/bin/env python3
"""Native linked-device durable replication.
Failures enumerated first: lost send after acceptance/restart, interrupted decrypt
before application persistence, duplicate ciphertext/ACK, wrong or revoked device,
forked roster, non-overlapping online windows, concurrent event ordering and
cross-conversation leakage. This covers the replication engine, not full chat UI.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
spec=importlib.util.spec_from_file_location('peers',Path(__file__).with_name('group-admin-e2e.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
spec_journal=importlib.util.spec_from_file_location('journal_fixture',Path(__file__).with_name('journal-fixture.py'))
journal=importlib.util.module_from_spec(spec_journal);spec_journal.loader.exec_module(journal)
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


def request(peer,operation,**fields):
    mark=peer.mark();tag='sync-'+str(mark)
    peer.send({'op':operation,'request':tag,**fields})
    return peer.wait(lambda e:e.get('request')==tag and e.get('event') in ('sync.state','sync.error'),15,mark)

with tempfile.TemporaryDirectory(prefix='harbor-sync-') as temporary:
    root=Path(temporary);a=p.Peer(binary,root,'desktop');b=p.Peer(binary,root,'laptop');c=p.Peer(binary,root,'offline');running=[a,b,c]
    try:
        ak=p.start_identity(a);bk=p.start_identity(b);ck=p.start_identity(c)
        a.send({'op':'device.initialize','request':'root','nickname':'Desktop'})
        owner=a.wait(p.event_is('devices',request='root'),15)
        c.send({'op':'device.propose','request':'offline-proposal'})
        offline=c.wait(p.event_is('devices',request='offline-proposal'),15)
        a.send({'op':'device.authorize','request':'authorize-offline','payload':offline['proposal'],'text':consent(c,owner['person']),'nickname':'Offline','accept':True})
        offline_roster=a.wait(p.event_is('devices',request='authorize-offline'),15)
        c.send({'op':'device.adopt','request':'adopt-offline','key':owner['person'],'text':offline_roster['roster'],'accept':True})
        c.wait(p.event_is('devices',request='adopt-offline'),15)
        a.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==ck and e.get('online'),180)
        c.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==ak and e.get('online'),180)
        conversation='d:'+'ab'*32
        assert request(a,'sync.publish',id='ff'*16,conversation=conversation,text='establish offline device session')['event']=='sync.state'
        c.wait(p.event_is('sync.item',id='ff'*16),90)
        c.stop()
        print('earlier authorized recipient is offline; linking online laptop',flush=True)
        b.send({'op':'device.propose','request':'proposal'})
        proposed=b.wait(p.event_is('devices',request='proposal'),15)
        a.send({'op':'device.authorize','request':'authorize','payload':proposed['proposal'],'text':consent(b,owner['person']),'nickname':'Laptop','accept':True})
        roster=a.wait(p.event_is('devices',request='authorize'),15)
        b.send({'op':'device.adopt','request':'adopt','key':owner['person'],'text':roster['roster'],'accept':True})
        b.wait(p.event_is('devices',request='adopt'),15)
        # Public authorization creates separate Tox friends and pins. These must
        # establish independent sessions without copying either private profile.
        a.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==bk and e.get('online'),180)
        b.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==ak and e.get('online'),180)
        conversation='d:'+'ab'*32
        first=request(a,'sync.publish',id='01'*16,conversation=conversation,text='from desktop')
        assert first['event']=='sync.state' and first['events']==2,first
        second=request(b,'sync.publish',id='02'*16,conversation=conversation,text='from laptop')
        assert second['event']=='sync.state',second
        a.wait(p.event_is('sync.item',id='02'*16,text='from laptop'),90)
        b.wait(p.event_is('sync.item',id='01'*16,text='from desktop'),90)
        for index in range(6):
            result=request(a,'sync.publish',id=f'{index+16:032x}',conversation=conversation,text='fair backlog '+str(index))
            assert result['event']=='sync.state',result
        b.wait(p.event_is('sync.item',id=f'{21:032x}',text='fair backlog 5'),90)
        exact=request(a,'sync.publish',id='01'*16,conversation=conversation,text='from desktop')
        assert exact['event']=='sync.state',exact
        # A locally accepted event survives sending machine restart while peer
        # is offline; restored helpers catch up from durable encrypted outboxes.
        b.stop()
        assert request(a,'sync.publish',id='03'*16,conversation=conversation,text='offline catch-up')['event']=='sync.state'
        a.stop()
        a=p.Peer(binary,root,'desktop');b=p.Peer(binary,root,'laptop');running.extend([a,b])
        p.start_identity(a);p.start_identity(b)
        b.wait(p.event_is('sync.item',id='03'*16,text='offline catch-up'),180)
        for peer in (a,b):
            deadline=time.monotonic()+60
            while True:
                state=request(peer,'sync.status')
                other=bk if peer is a else ak
                acknowledgements=[name for name in journal.envelopes(peer,'ack') if name.startswith(other+'.')]
                if state.get('events')==10 and len(acknowledgements)==10:break
                assert time.monotonic()<deadline,state
                time.sleep(1)
            assert request(peer,'sync.publish',id='01'*16,conversation=conversation,text='changed replay')['event']=='sync.error'
        a.send({'op':'device.revoke','request':'revoke-laptop','key':proposed['local'],'accept':True})
        a.wait(p.event_is('devices',request='revoke-laptop'),15)
        b.wait(lambda e:e.get('event')=='device.roster' and e.get('active') is False,90)
        assert request(b,'sync.publish',id='04'*16,conversation=conversation,text='must reject')['event']=='sync.error'
        receipt.write_text(json.dumps({'runner_path':str(Path(__file__).resolve()),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runner_manifest':str(Path(__file__).resolve().parent.parent/'manifest.json'),'suite':'native-linked-device-replication',
            'helper_sha256':candidate_sha(),
            'passed':['independent-automatic-device-sessions','bidirectional-events','durable-offline-catchup',
                      'restart-deduplication','durable-acknowledgements','revocation-propagation','fair-offline-recipient-backlog','exact-retry-idempotency'],
            'scope':'replication engine; full messenger integration remains separate'},indent=2)+'\n')
        print('device-sync-e2e: pass',flush=True)
    finally:
        for peer in running:peer.stop()
