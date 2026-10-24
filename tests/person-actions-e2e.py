#!/usr/bin/env python3
"""Four native helpers exercise person-owned message mutations and read state.
Failure cases, before implementation: sibling unable to edit an own message;
foreign person edits/deletes it; action arriving before its message is lost;
concurrent device actions diverge; replayed old reaction regresses the new one;
deleted content returns after a late edit; read state regresses after ACK/restart;
offline own machine misses mutations. Receipt binds the actual frozen executable.
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
spec_journal=importlib.util.spec_from_file_location('journal_fixture',Path(__file__).with_name('journal-fixture.py'))
journal=importlib.util.module_from_spec(spec_journal);spec_journal.loader.exec_module(journal)
binary=Path(sys.argv[1]).resolve();receipt=Path(sys.argv[2]).resolve();expected=hashlib.sha256(binary.read_bytes()).hexdigest()
fault=Path(sys.argv[3]).resolve() if len(sys.argv)>3 else None
fault_hash=hashlib.sha256(fault.read_bytes()).hexdigest() if fault else None
with tempfile.TemporaryDirectory(prefix='harbor-person-actions-') as temporary:
    root=Path(temporary);devices=[p.Peer(binary,root,name) for name in ('alice-desktop','alice-laptop','bob-desktop','bob-laptop')]
    try:
        keys=[p.start_identity(peer) for peer in devices];roots=[]
        for index in (0,2):
            owner,new=devices[index:index+2]
            owner.send({'op':'device.initialize','request':'initialize','nickname':owner.name})
            identity=owner.wait(p.event_is('devices',request='initialize'),15);roots.append(identity['person'])
            new.send({'op':'device.propose','request':'proposal'});proposal=new.wait(p.event_is('devices',request='proposal'),15)
            owner.send({'op':'device.authorize','request':'authorize','payload':proposal['proposal'],'text':c.consent(new,identity['person']),'nickname':new.name,'accept':True})
            roster=owner.wait(p.event_is('devices',request='authorize'),15)
            new.send({'op':'device.adopt','request':'adopt','key':identity['person'],'text':roster['roster'],'accept':True});new.wait(p.event_is('devices',request='adopt'),15)
        print('pairing people',flush=True)
        p.pair(devices[0],devices[2],keys[2],'actions')
        alice,bob=roots
        for index,peer in enumerate(devices):peer.wait(p.event_is('person.info',key=bob if index<2 else alice),180)
        print('all devices discovered both people',flush=True)
        badmark=devices[0].mark()
        devices[0].send({'op':'msg.send','conversation':'p:'+bob,'key':'f'*64,'id':'failed-send-correlation','text':'Invalid stale binding'})
        devices[0].wait(p.event_is('message.failed',request='failed-send-correlation',id='failed-send-correlation'),30,badmark)
        devices[1].send({'op':'msg.send','conversation':'p:'+bob,'key':bob,'id':'original','text':'Sibling reuses a device-local request'})
        sibling=devices[1].wait(p.event_is('message',request='original',dir='out'),30)
        projection=devices[0].wait(p.event_is('message',id=sibling['id']),180)
        assert projection.get('request','')=='','sibling must not complete a local request'
        devices[0].send({'op':'msg.send','conversation':'p:'+bob,'key':bob,'id':'original','text':'Original text'})
        first=devices[0].wait(p.event_is('message',request='original',dir='out'),30);mid=first['id']
        assert sibling['id']!=mid
        for peer in devices:peer.wait(p.event_is('message',id=mid),180)
        projection=devices[1].wait(p.event_is('message',id=mid),30)
        assert projection.get('request','')==''
        def action(index,op,request,**fields):
            other=bob if index<2 else alice
            devices[index].send({'op':op,'conversation':'p:'+other,'key':other,'id':mid,'request':request,**fields})
        def histories(predicate):
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                rows=[]
                for index,peer in enumerate(devices):
                    other=bob if index<2 else alice;request='history-'+str(peer.mark())
                    mark=peer.mark()
                    peer.send({'op':'history','conversation':'p:'+other,'key':other,'id':request})
                    result=peer.wait(lambda e:e.get('request')==request and e.get('event') in ('history','history.failed'),30,mark)
                    assert result['event']=='history',result
                    rows.append(next(row for row in result['items'] if row['id']==mid))
                if predicate(rows):return rows
                time.sleep(.5)
            raise AssertionError(('person projections did not converge',rows))
        print('message on all devices; editing',flush=True)
        action(1,'message.edit','sibling-edit',text='Edited from the other machine')
        histories(lambda rows:all(row['text']=='Edited from the other machine' and row.get('edited') for row in rows))
        editmarks=[peer.mark() for peer in devices]
        action(0,'message.edit','concurrent-edit-desktop',text='Desktop concurrent edit')
        action(1,'message.edit','concurrent-edit-laptop',text='Laptop concurrent edit')
        devices[0].wait(p.event_is('message.updated',id=mid,request='concurrent-edit-desktop'),30,editmarks[0])
        devices[1].wait(p.event_is('message.updated',id=mid,request='concurrent-edit-laptop'),30,editmarks[1])
        histories(lambda rows:len({row['text'] for row in rows})==1 and rows[0]['text'] in ('Desktop concurrent edit','Laptop concurrent edit'))
        action(2,'message.edit','foreign-edit',text='Unauthorized change')
        devices[2].wait(p.event_is('error',request='foreign-edit',code='forbidden'),15)
        action(3,'message.delete','foreign-delete')
        devices[3].wait(p.event_is('error',request='foreign-delete',code='forbidden'),15)
        print('edit ownership verified; reactions',flush=True)
        action(2,'message.react','reaction-first',text='👍')
        histories(lambda rows:all(row.get('reactionPeer' if index<2 else 'reactionMe')=='👍' for index,row in enumerate(rows)))
        retrymark=devices[2].mark()
        action(2,'message.react','reaction-first',text='👍')
        devices[2].wait(p.event_is('message.updated',id=mid,request='reaction-first'),30,retrymark)
        action(3,'message.react','reaction-second',text='🎉')
        histories(lambda rows:all(row.get('reactionPeer' if index<2 else 'reactionMe')=='🎉' for index,row in enumerate(rows)))
        reactionmarks=[peer.mark() for peer in devices]
        action(2,'message.react','concurrent-reaction-desktop',text='🔥')
        action(3,'message.react','concurrent-reaction-laptop',text='✅')
        devices[2].wait(p.event_is('message.updated',id=mid,request='concurrent-reaction-desktop'),30,reactionmarks[2])
        devices[3].wait(p.event_is('message.updated',id=mid,request='concurrent-reaction-laptop'),30,reactionmarks[3])
        rows=histories(lambda rows:len({row.get('reactionPeer' if index<2 else 'reactionMe') for index,row in enumerate(rows)})==1 and rows[0].get('reactionPeer') in ('🔥','✅'))
        reaction=rows[0]['reactionPeer']
        action(2,'message.react','reaction-first',text='👍')
        message_ids=[mid]
        for number in (2,3):
            devices[0].send({'op':'msg.send','conversation':'p:'+bob,'key':bob,'id':'read-through-'+str(number),'text':'Read marker message '+str(number)})
            received=devices[0].wait(p.event_is('message',request='read-through-'+str(number)),30)
            message_ids.append(received['id'])
            for peer in devices[1:]:peer.wait(p.event_is('message',id=received['id']),180)
        readmarks=[peer.mark() for peer in devices]
        devices[3].send({'op':'conversation.read','conversation':'p:'+alice,'key':alice,'id':message_ids[-1],'request':'read-bob'})
        for index in (0,1):
            for message_id in message_ids:
                devices[index].wait(p.event_is('message.updated',id=message_id,state='read'),90,readmarks[index])
        devices[3].wait(p.event_is('conversation.read',request='read-bob'),15)
        histories(lambda rows:all(row.get('state')=='read' for row in rows[:2]) and all(row.get('reactionPeer' if index<2 else 'reactionMe')==reaction for index,row in enumerate(rows)))
        if fault:
            print('crashing after durable action before response',flush=True)
            devices[1].stop()
            os.environ['HARBOR_SYNC_CRASH_AT']='after-local-action'
            try:devices[1]=p.Peer(fault,root,'alice-laptop')
            finally:os.environ.pop('HARBOR_SYNC_CRASH_AT',None)
            p.start_identity(devices[1])
            action(1,'message.edit','crash-edit',text='Edit persisted before crash')
            assert devices[1].process.wait(timeout=30)==78
            committed={key:wire for key,wire in journal.events(devices[1]).items() if b'|crash-edit\n' in wire}
            assert len(committed)==1,'one durable immutable mutation must survive'
            devices[1]=p.Peer(binary,root,'alice-laptop');p.start_identity(devices[1])
            retrymark=devices[1].mark()
            action(1,'message.edit','crash-edit',text='Edit persisted before crash')
            devices[1].wait(p.event_is('message.updated',id=mid,request='crash-edit',text='Edit persisted before crash'),30,retrymark)
            after={key:wire for key,wire in journal.events(devices[1]).items() if b'|crash-edit\n' in wire}
            assert after==committed,'retry must preserve mutation ID, clock and bytes'
            histories(lambda rows:all(row['text']=='Edit persisted before crash' for row in rows))
        print('reactions and read state converged; offline delete',flush=True)
        devices[0].stop()
        action(1,'message.delete','delete-from-sibling')
        for peer in devices[1:]:peer.wait(p.event_is('message.updated',id=mid,deleted=True),90)
        devices[0]=p.Peer(binary,root,'alice-desktop');p.start_identity(devices[0])
        rows=histories(lambda rows:all(row.get('deleted') and row['text']=='' for row in rows))
        assert all(row.get('state')=='read' for row in rows[:2])
        action(0,'message.edit','late-edit',text='Must not resurrect')
        devices[0].wait(p.event_is('error',request='late-edit',code='message_deleted'),15)
        histories(lambda rows:all(row.get('deleted') and row['text']=='' for row in rows))
        assert hashlib.sha256(binary.read_bytes()).hexdigest()==expected
        if fault:assert hashlib.sha256(fault.read_bytes()).hexdigest()==fault_hash
        receipt.write_text(json.dumps({'runner_path':str(Path(__file__).resolve()),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runner_manifest':str(Path(__file__).resolve().parent.parent/'manifest.json'),'suite':'native-person-actions','helper_sha256':expected,'fault_helper_sha256':fault_hash,
            'passed':['sibling-edits-own-person-message','foreign-edit-and-delete-rejected','one-reaction-per-person','old-action-retry-cannot-regress-reaction','read-projection-converges','offline-machine-catches-up','deletion-survives-restart-and-late-edit','read-state-does-not-regress','correlated-exact-mutation-retry','three-message-live-cumulative-read','concurrent-edit-convergence','concurrent-reaction-convergence','device-local-request-completion-isolation','failed-send-completion-correlation']+(['durable-mutation-crash-and-exact-retry'] if fault else [])},indent=2)+'\n')
        print('person-actions-e2e: pass',flush=True)
    finally:
        if sys.exc_info()[0]:
            receipt.with_suffix('.failure.json').write_text(json.dumps({peer.name:[e for e in peer.events if e.get('event') in ('error','history.failed','message.failed','sync.error','devices.error','message.updated')] for peer in devices},ensure_ascii=False,indent=2)+'\n')
        for peer in devices:peer.stop()
