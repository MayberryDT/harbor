#!/usr/bin/env python3
"""Four real helpers: people own conversations, devices own sessions.
Failures written first: duplicate contact/device bubbles, missing outgoing copies,
remote sender substitution, divergent concurrent ordering, cross-chat projection,
reply loss, duplicate retry, and only the original device being able to send.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
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

with tempfile.TemporaryDirectory(prefix='harbor-person-chat-') as temporary:
    root=Path(temporary);devices=[p.Peer(binary,root,name) for name in ('alice-desktop','alice-laptop','bob-desktop','bob-laptop')]
    try:
        keys=[p.start_identity(peer) for peer in devices];roots=[]
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
        p.pair(devices[0],devices[2],keys[2],'alice-bob')
        for index,peer in enumerate(devices):peer.wait(p.event_is('person.info',id='p:'+roots[1 if index<2 else 0]),180)
        alice,bob=roots
        devices[0].send({'op':'msg.send','conversation':'p:'+bob,'key':bob,'id':'alice-first','text':'One person, two machines'})
        first=devices[0].wait(p.event_is('message',request='alice-first',dir='out'),30)
        for index,peer in enumerate(devices):
            peer.wait(p.event_is('message',id=first['id'],text='One person, two machines',dir='out' if index<2 else 'in'),180)
        devices[1].send({'op':'msg.send','conversation':'p:'+bob,'key':bob,'id':'alice-laptop','reply':first['id'],'text':'Sent from the other machine'})
        devices[3].send({'op':'msg.send','conversation':'p:'+alice,'key':alice,'id':'bob-laptop','text':'Bob can do the same'})
        second=devices[1].wait(p.event_is('message',request='alice-laptop',dir='out'),30)
        third=devices[3].wait(p.event_is('message',request='bob-laptop',dir='out'),30)
        for index in (0,1):
            devices[index].send({'op':'msg.send','conversation':'p:'+bob,'key':bob,'id':'same-local-request',
                                 'text':'Concurrent device '+str(index)})
        same=[]
        for index in (0,1):
            event=devices[index].wait(p.event_is('message',request='same-local-request',text='Concurrent device '+str(index),dir='out'),30)
            same.append(event['id'])
        assert same[0]!=same[1],'independent device request namespaces must not collide'
        expected={first['id'],second['id'],third['id'],*same}
        transcripts=[]
        for index,peer in enumerate(devices):
            other=bob if index<2 else alice
            for mid in expected:peer.wait(p.event_is('message',id=mid),180)
            peer.send({'op':'history','conversation':'p:'+other,'key':other,'id':'history-check','limit':50})
            history=peer.wait(p.event_is('history',conversation='p:'+other,request='history-check'),30)
            assert {item['id'] for item in history['items']}==expected,history
            transcripts.append([item['id'] for item in history['items']])
            assert next(item for item in history['items'] if item['id']==second['id']).get('reply')==first['id']
        assert all(order==transcripts[0] for order in transcripts),transcripts
        devices[0].send({'op':'msg.send','conversation':'p:'+bob,'key':bob,'id':'alice-first','text':'One person, two machines'})
        devices[0].wait(p.event_is('message',request='alice-first',id=first['id']),15)
        # A legitimate roster extension leaves both old and new HPC events.
        # Restart must treat the verified older prefix as already projected.
        extra=p.Peer(binary,root,'bob-third');devices.append(extra);p.start_identity(extra)
        extra.send({'op':'device.propose','request':'extra-proposal'})
        proposal=extra.wait(p.event_is('devices',request='extra-proposal'),15)
        devices[2].send({'op':'device.authorize','request':'extend-bob','payload':proposal['proposal'],
                        'text':consent(extra,bob),'nickname':'Third','accept':True})
        devices[2].wait(p.event_is('devices',request='extend-bob'),15)
        devices[0].wait(p.event_is('person.info',key=bob,devices=3),90)
        contact_events=[wire for wire in journal.events(devices[0]).values()
                        if ('|p:'+bob+'|contact\n').encode() in wire]
        assert len(contact_events)>=2, 'successive contact rosters were not journaled'
        devices[0].process.kill();devices[0].process.wait(timeout=5);devices[0].stop()
        devices[0]=p.Peer(binary,root,'alice-desktop');p.start_identity(devices[0])
        devices[0].send({'op':'msg.send','conversation':'p:'+bob,'key':bob,'id':'after-roster-replay','text':'Still sending after a roster extension and restart'})
        sent=devices[0].wait(p.event_is('message',request='after-roster-replay',dir='out'),30)
        devices[2].wait(p.event_is('message',id=sent['id'],dir='in'),180)
        receipt.write_text(json.dumps({'runner_path':str(Path(__file__).resolve()),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runner_manifest':str(Path(__file__).resolve().parent.parent/'manifest.json'),'suite':'native-person-conversations','helper_sha256':candidate_sha(),
            'passed':['one-contact-four-devices','outgoing-and-incoming-copies','send-from-either-device',
                      'concurrent-transcript-convergence','reply-preservation','stable-retry-id','independent-device-request-namespaces','superseded-contact-prefix-replay-preserves-outbound-delivery'],
            'scope':'native direct person messaging; UI/groups/files/mailbox/recovery separate'},indent=2)+'\n')
        print('person-chat-e2e: pass',flush=True)
    finally:
        for peer in devices:peer.stop()
