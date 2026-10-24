#!/usr/bin/env python3
"""A hostile foreign sender must not split siblings using an observed event ID.
Failures: a forged Bob message wins the laptop's empty slot for Alice's message;
legitimate later sibling replication conflicts permanently; recipient rejects all
traffic instead of rejecting only the forged origin-bound identifier.
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
spec=importlib.util.spec_from_file_location('consent',Path(__file__).with_name('device-consent-fixture.py'))
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
spec_journal=importlib.util.spec_from_file_location('journal_fixture',Path(__file__).with_name('journal-fixture.py'))
journal=importlib.util.module_from_spec(spec_journal);spec_journal.loader.exec_module(journal)
binary=Path(sys.argv[1]).resolve();receipt=Path(sys.argv[2]).resolve();fault=Path(sys.argv[3]).resolve();expected=hashlib.sha256(binary.read_bytes()).hexdigest();fault_sha=hashlib.sha256(fault.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='harbor-id-collision-') as temporary:
    root=Path(temporary);a=p.Peer(binary,root,'alice');laptop=p.Peer(binary,root,'laptop');b=p.Peer(fault,root,'bob');running=[a,laptop,b]
    def device(peer,op,**fields):
        request='collision-'+str(peer.mark());peer.send({'op':op,'request':request,**fields})
        result=peer.wait(lambda e:e.get('request')==request and e.get('event') in ('devices','devices.error'),15)
        assert result['event']=='devices',result
        return result
    try:
        ak=p.start_identity(a);lk=p.start_identity(laptop);bk=p.start_identity(b)
        alice=device(a,'device.initialize',nickname='Alice');bob=device(b,'device.initialize',nickname='Bob')
        proposal=device(laptop,'device.propose')
        roster=device(a,'device.authorize',payload=proposal['proposal'],text=c.consent(laptop,alice['person']),nickname='Laptop',accept=True)
        device(laptop,'device.adopt',key=alice['person'],text=roster['roster'],accept=True)
        p.pair(a,b,bk,'collision')
        for peer in (a,laptop):peer.wait(p.event_is('person.info',key=bob['person']),180)
        # Establish a working laptop/Bob channel before making the sibling gap.
        laptop.send({'op':'msg.send','conversation':'p:'+bob['person'],'key':bob['person'],'id':'warmup','text':'Establish laptop session'})
        b.wait(p.event_is('message',text='Establish laptop session',dir='in'),180)
        offline=a.mark();laptop.stop()
        a.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==lk and e.get('online') is False,180,offline)
        a.send({'op':'msg.send','conversation':'p:'+bob['person'],'key':bob['person'],'id':'collision-target','text':'Authentic Alice message'})
        original=a.wait(p.event_is('message',request='collision-target',dir='out'),30);mid=original['id']
        b.wait(p.event_is('message',id=mid,dir='in'),90)
        offline=b.mark();a.stop()
        b.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==ak and e.get('online') is False,180,offline)
        # Mallory controls this Bob process's disposable journal and may choose
        # every wire field, including a validly shaped victim event ID.
        body='HM2|{}|{}|-|forged-origin|000000006a000000\nForged collision'.format(bob['person'],alice['person'])
        wire='HS2|{}|0000000000002000|{}|{}|p:{}|message\n{}'.format(mid,bob['person'],bob['local'],alice['person'],body)
        laptop=p.Peer(binary,root,'laptop');running.append(laptop);p.start_identity(laptop)
        laptop.send({'op':'msg.send','conversation':'p:'+bob['person'],'key':bob['person'],'id':'restart-ready','text':'Laptop ready after restart'})
        b.wait(p.event_is('message',text='Laptop ready after restart',dir='in'),180)
        b.send({'op':'sync.inject','request':'inject-collision','key':lk,'id':mid,'text':wire})
        b.wait(p.event_is('sync.injected',id=mid),15)
        b.send({'op':'msg.send','conversation':'p:'+alice['person'],'key':alice['person'],'id':'valid-control','text':'Valid Bob control'})
        control=laptop.wait(p.event_is('message',text='Valid Bob control',dir='in'),180)
        assert journal.get(laptop,mid) is None,'forged foreign event reserved the authentic sibling ID'
        laptop.stop()
        # The malicious sender suppresses its correct copy so only the offline
        # sibling can later repair the recipient's view of this same-origin ID.
        canonical_control=journal.get(b,control['id']).decode()
        journal.delete(b,control['id'])
        journal.envelope_delete(b,'outbox',ak+'.'+control['id'])
        bmark=b.mark()
        a=p.Peer(binary,root,'alice');running.append(a);p.start_identity(a)
        b.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==ak and e.get('online'),180,bmark)
        equivocated=wire.replace(mid,control['id']).replace('forged-origin','valid-control').replace('Forged collision','Equivocated Bob control')
        b.send({'op':'sync.inject','request':'inject-equivocation','key':ak,'id':control['id'],'text':equivocated})
        b.wait(p.event_is('sync.injected',id=control['id']),15)
        for label,alternate in (
                ('trailing',canonical_control.replace('\n','|\n',1)),
                ('repeated',canonical_control.replace('HS2|','HS2||',1))):
            marker=b.mark();request='inject-encoding-'+label
            b.send({'op':'sync.inject','request':request,'key':ak,'id':control['id'],'text':alternate})
            b.wait(p.event_is('sync.injected',id=control['id']),15,marker)

        b.send({'op':'msg.send','conversation':'p:'+alice['person'],'key':alice['person'],'id':'valid-second-control','text':'Second valid Bob control'})
        a.wait(p.event_is('message',text='Second valid Bob control',dir='in'),180)
        assert journal.get(a,control['id']) is None,'equivocation reserved the original foreign ID'
        laptop=p.Peer(binary,root,'laptop');running.append(laptop);p.start_identity(laptop)


        laptop.wait(p.event_is('message',id=mid,text='Authentic Alice message',dir='out'),180)
        a.wait(p.event_is('message',id=control['id'],text='Valid Bob control',dir='in'),180)
        for peer in (a,laptop):
            peer.send({'op':'history','conversation':'p:'+bob['person'],'key':bob['person'],'id':'final-history'})
            history=peer.wait(p.event_is('history',request='final-history'),30)
            row=next(row for row in history['items'] if row['id']==mid)
            assert row['text']=='Authentic Alice message' and row['dir']=='out'
            assert next(row for row in history['items'] if row['id']==control['id'])['text']=='Valid Bob control'
        assert hashlib.sha256(binary.read_bytes()).hexdigest()==expected
        if fault:assert hashlib.sha256(fault.read_bytes()).hexdigest()==fault_sha
        receipt.write_text(json.dumps({'runner_path':str(Path(__file__).resolve()),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runner_manifest':str(Path(__file__).resolve().parent.parent/'manifest.json'),'suite':'native-person-event-id-collision','helper_sha256':expected,'hostile_helper_sha256':fault_sha,
            'passed':['foreign-observed-id-rejected-before-journal','valid-foreign-control-still-delivered','late-authentic-sibling-event-converges','same-origin-content-equivocation-cannot-fork-journal','alternate-wire-encodings-rejected-before-journal']},indent=2)+'\n')
        print('person-id-collision-e2e: pass',flush=True)
    finally:
        for peer in running:peer.stop()
