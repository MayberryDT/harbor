#!/usr/bin/env python3
"""A real encrypted HP1 rename must be journaled before cached installation.
Failures: same-head rename saved without intent; a crash after journal commit
loses the rename; offline foreign peer is required to repair the surviving card.
"""
import hashlib,importlib.util,json,os,sys,tempfile
from pathlib import Path
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
p=load('peers','group-admin-e2e.py');journal=load('journal','journal-fixture.py')
normal=Path(sys.argv[1]).resolve();fault=Path(sys.argv[2]).resolve();receipt=Path(sys.argv[3]).resolve()
with tempfile.TemporaryDirectory(prefix='harbor-contact-receive-') as temporary:
    root=Path(temporary);crash=root/'crash-contact'
    os.environ['HARBOR_SYNC_CRASH_CONTACT_FILE']=str(crash)
    try:a=p.Peer(fault,root,'alice')
    finally:os.environ.pop('HARBOR_SYNC_CRASH_CONTACT_FILE',None)
    b=p.Peer(fault,root,'bob');running=[a,b]
    try:
        ak=p.start_identity(a);bk=p.start_identity(b);identities=[]
        for peer in (a,b):
            peer.send(dict(op='device.initialize',request='init',nickname=peer.name))
            identities.append(peer.wait(p.event_is('devices',request='init'),15))
        bob=identities[1];p.pair(a,b,bk,'receive-recovery');a.wait(p.event_is('person.info',key=bob['person']),180)
        names=list(a.home.rglob(bob['person']+'.name'));assert len(names)==1
        old=names[0].read_text();renamed='Journal first rename';assert old!=renamed
        crash.touch();identifier='71'*16
        b.send(dict(op='sync.inject',request='rename',id=identifier,key=ak,kind='legacy',text='HP1|'+renamed.encode().hex()+'|'+bob['roster']))
        b.wait(p.event_is('sync.injected',id=identifier),30)
        assert a.process.wait(timeout=30)==78,'receiver did not reach the durable-before-projection crash point'
        assert names[0].read_text()==old,'rename was projected before the fault after durable publication'
        accepted=[(key,wire) for key,wire in journal.events(a).items() if ('HPC1|'+renamed.encode().hex()+'|').encode() in wire]
        assert len(accepted)==1,'complete rename intent was not durably recorded'
        b.stop();a=p.Peer(normal,root,'alice');running.append(a);p.start_identity(a)
        a.wait(lambda e:e.get('event')=='person.info' and e.get('key')==bob['person'] and e.get('name')==renamed,60)
        assert names[0].read_text()==renamed
        assert journal.get(a,accepted[0][0])==accepted[0][1],'restart rewrote immutable rename intent'
        receipt.write_text(json.dumps(dict(suite='native-contact-receive-journal-first',helper_sha256=hashlib.sha256(normal.read_bytes()).hexdigest(),fault_helper_sha256=hashlib.sha256(fault.read_bytes()).hexdigest(),runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),passed=['real-encrypted-same-head-rename','durable-intent-before-cache-projection','crash-recovery-with-foreign-peer-offline','exact-intent-bytes-retained']),indent=2)+'\n')
        print('contact-receive-recovery-e2e: pass',flush=True)
    finally:
        for peer in running:peer.stop()
