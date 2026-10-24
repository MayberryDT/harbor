#!/usr/bin/env python3
"""Delivery knowledge must survive ACK/publication failure and own-device sync.
Failures: ACK removes its encrypted outbox before receipt intent is durable;
restart cannot reconcile that intent while the contact is offline; a newly linked
machine regresses delivered history to queued; importing a receipt endorses an
unverified endpoint or generates a receipt echo loop. Real encrypted peers only.
"""
import hashlib,importlib.util,json,os,sys,tempfile,time
from pathlib import Path
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
p=load('peers','group-admin-e2e.py');c=load('consent','device-consent-fixture.py');journal=load('journal','journal-fixture.py')
normal=Path(sys.argv[1]).resolve();fault=Path(sys.argv[2]).resolve();receipt=Path(sys.argv[3]).resolve()
def until(predicate,seconds=60):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.2)
    raise RuntimeError('bounded delivery-knowledge condition timed out')
with tempfile.TemporaryDirectory(prefix='harbor-delivery-sync-') as temporary:
    root=Path(temporary);failure=root/'fail-delivery'
    os.environ['HARBOR_SYNC_FAIL_DELIVERY_FILE']=str(failure)
    try:a=p.Peer(fault,root,'alice')
    finally:os.environ.pop('HARBOR_SYNC_FAIL_DELIVERY_FILE',None)
    laptop=p.Peer(normal,root,'laptop');b=p.Peer(normal,root,'bob');running=[a,laptop,b]
    try:
        ak=p.start_identity(a);lk=p.start_identity(laptop);bk=p.start_identity(b);identities=[]
        for peer in (a,b):
            peer.send(dict(op='device.initialize',request='init',nickname=peer.name))
            identities.append(peer.wait(p.event_is('devices',request='init'),15))
        own,bob=identities
        laptop.send(dict(op='device.propose',request='proposal'));proposal=laptop.wait(p.event_is('devices',request='proposal'),15)
        a.send(dict(op='device.authorize',request='authorize',payload=proposal['proposal'],text=c.consent(laptop,own['person']),nickname='Laptop',accept=True))
        roster=a.wait(p.event_is('devices',request='authorize'),15)
        laptop.send(dict(op='device.adopt',request='adopt',key=own['person'],text=roster['roster'],accept=True));laptop.wait(p.event_is('devices',request='adopt'),15)
        a.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==lk and e.get('online'),180)
        a.send(dict(op='sync.publish',request='warmup',id='ab'*16,conversation='d:'+'cd'*32,text='Prepare independent owned-device session'))
        laptop.wait(p.event_is('sync.item',id='ab'*16),90);laptop.stop()
        p.pair(a,b,bk,'delivery-sync');a.wait(p.event_is('person.info',key=bob['person']),180)
        failure.touch();a.send(dict(op='msg.send',conversation='p:'+bob['person'],key=bob['person'],id='delivered-while-laptop-offline',text='Delivered before this machine ever met Bob'))
        message=a.wait(p.event_is('message',request='delivered-while-laptop-offline',dir='out'),30)
        b.wait(p.event_is('message',id=message['id'],dir='in'),90)
        name=bk+'.'+message['id']
        until(lambda:name in journal.envelopes(a,'ack'))
        assert name in journal.envelopes(a,'outbox'),'ACK erased the only receipt-publication obligation'
        assert not any(b'|delivery\n' in wire for wire in journal.events(a).values())
        b.stop();a.stop();failure.unlink()
        a=p.Peer(normal,root,'alice');running.append(a);p.start_identity(a)
        def facts(peer):return {key:wire for key,wire in journal.events(peer).items() if b'|delivery\n' in wire}
        until(lambda:bool(facts(a)) and name not in journal.envelopes(a,'outbox'))
        expected=facts(a)
        laptop=p.Peer(normal,root,'laptop');running.append(laptop);p.start_identity(laptop)
        laptop.wait(p.event_is('person.info',key=bob['person']),180)
        until(lambda:all(journal.get(laptop,key)==wire for key,wire in expected.items()),180)
        mark=laptop.mark();laptop.send(dict(op='history',conversation='p:'+bob['person'],key=bob['person'],id='delivered-after-link'))
        history=laptop.wait(p.event_is('history',request='delivered-after-link'),30,mark)
        item=next(row for row in history['items'] if row['id']==message['id'])
        assert item['state']=='delivered',item
        until(lambda:name in journal.envelopes(laptop,'ack'))
        assert not (laptop.home/'devices/endpoint-anchors'/bk).exists(),'receipt granted an unverified endpoint authority'
        time.sleep(3)
        assert set(facts(laptop))==set(expected) and set(facts(a))==set(expected),'receipt import produced an echo'
        receipt.write_text(json.dumps(dict(suite='native-private-delivery-sync',helper_sha256=hashlib.sha256(normal.read_bytes()).hexdigest(),fault_helper_sha256=hashlib.sha256(fault.read_bytes()).hexdigest(),runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),passed=['ACK-keeps-publication-debt','restart-reconciles-with-contact-offline','new-machine-retains-delivered-state','receipt-does-not-endorse-endpoint','no-receipt-echo']),indent=2)+'\n')
        print('person-delivery-sync-e2e: pass',flush=True)
    finally:
        for peer in running:peer.stop()
