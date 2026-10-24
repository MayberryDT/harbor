#!/usr/bin/env python3
"""An installed contact must replicate even after an install/publication gap.
Failures: missing intent never reconciled; retry requires the foreign peer online;
restart changes the contact root; an already-journaled card produces new events.
Only disposable profiles are modified to reproduce the persisted crash window.
"""
import hashlib,importlib.util,json,sys,tempfile,time
from pathlib import Path
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
p=load('peers','group-admin-e2e.py');c=load('consent','device-consent-fixture.py');journal=load('journal','journal-fixture.py')
binary=Path(sys.argv[1]).resolve();receipt=Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory(prefix='harbor-contact-startup-') as temporary:
    root=Path(temporary);a=p.Peer(binary,root,'alice');b=p.Peer(binary,root,'bob');running=[a,b]
    try:
        ak=p.start_identity(a);bk=p.start_identity(b);identities=[]
        for peer in (a,b):
            peer.send(dict(op='device.initialize',request='init',nickname=peer.name))
            identities.append(peer.wait(p.event_is('devices',request='init'),15))
        bob=identities[1]['person'];p.pair(a,b,bk,'startup-contact');a.wait(p.event_is('person.info',key=bob),180)
        a.stop();b.stop()
        removed=[]
        for key,wire in journal.events(a).items():
            if b'|contact\n' in wire:journal.delete(a,key);removed.append(key)
        assert removed,'fixture did not reach installed-contact publication window'
        a=p.Peer(binary,root,'alice');laptop=p.Peer(binary,root,'laptop');running.extend((a,laptop))
        p.start_identity(a);lk=p.start_identity(laptop)
        laptop.send(dict(op='device.propose',request='proposal'));proposal=laptop.wait(p.event_is('devices',request='proposal'),15)
        a.send(dict(op='device.authorize',request='authorize',payload=proposal['proposal'],text=c.consent(laptop,identities[0]['person']),nickname='Laptop',accept=True))
        roster=a.wait(p.event_is('devices',request='authorize'),15)
        laptop.send(dict(op='device.adopt',request='adopt',key=identities[0]['person'],text=roster['roster'],accept=True))
        laptop.wait(p.event_is('devices',request='adopt'),15)
        laptop.wait(p.event_is('person.info',key=bob),180)
        restored={key:wire for key,wire in journal.events(a).items() if b'|contact\n' in wire}
        assert set(removed)<=set(restored),'reconciliation changed deterministic contact event IDs'
        assert all(journal.get(laptop,key)==wire for key,wire in restored.items())
        receipt.write_text(json.dumps(dict(suite='native-contact-startup-reconciliation',helper_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),passed=['installed-card-without-event-recovered','foreign-peer-remains-offline','new-sibling-receives-contact','deterministic-event-ID']),indent=2)+'\n')
        print('contact-startup-reconcile-e2e: pass',flush=True)
    finally:
        for peer in running:peer.stop()
