#!/usr/bin/env python3
"""Native contact import retries a real fsync failure without receiver restart.
Failures: durable HPC acknowledged while projection failed; duplicates skip
projection forever; a sender discards its debt before the contact is usable.
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
binary=Path(sys.argv[1]).resolve();shim=Path(sys.argv[2]).resolve();receipt=Path(sys.argv[3]).resolve();expected=hashlib.sha256(binary.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='harbor-projection-') as temporary:
    root=Path(temporary);failure=root/'fail-contact'
    a=p.Peer(binary,root,'alice');b=p.Peer(binary,root,'bob')
    os.environ.update(LD_PRELOAD=str(shim),HARBOR_E2E_FAIL_CONTACT_FSYNC=str(failure))
    try:laptop=p.Peer(binary,root,'laptop')
    finally:
        os.environ.pop('LD_PRELOAD',None);os.environ.pop('HARBOR_E2E_FAIL_CONTACT_FSYNC',None)
    try:
        ak=p.start_identity(a);bk=p.start_identity(b);lk=p.start_identity(laptop)
        for peer in (a,b):
            peer.send({'op':'device.initialize','request':'init','nickname':peer.name});peer.wait(p.event_is('devices',request='init'),15)
        a.send({'op':'device.status','request':'owner'});owner=a.wait(p.event_is('devices',request='owner'),15)
        b.send({'op':'device.status','request':'bob'});bob=b.wait(p.event_is('devices',request='bob'),15)
        laptop.send({'op':'device.propose','request':'proposal'});proposal=laptop.wait(p.event_is('devices',request='proposal'),15)
        a.send({'op':'device.authorize','request':'authorize','payload':proposal['proposal'],'text':c.consent(laptop,owner['person']),'nickname':'Laptop','accept':True})
        roster=a.wait(p.event_is('devices',request='authorize'),15)
        laptop.send({'op':'device.adopt','request':'adopt','key':owner['person'],'text':roster['roster'],'accept':True});laptop.wait(p.event_is('devices',request='adopt'),15)
        a.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==lk and e.get('online'),180)
        failure.touch();p.pair(a,b,bk,'projection')
        deadline=time.monotonic()+180;contact=None
        while time.monotonic()<deadline:
            candidates=journal.events(laptop)
            contact=next((key for key,wire in candidates.items() if b'|contact\n' in wire),None)
            if contact:break
            time.sleep(.2)
        assert contact is not None,'contact never reached durable replica journal'
        assert not (lk+'.'+contact in journal.envelopes(a,'ack')), 'failed projection was acknowledged'
        pid=laptop.process.pid;failure.unlink()
        laptop.wait(p.event_is('person.info',key=bob['person']),90)
        deadline=time.monotonic()+60
        while not (lk+'.'+contact in journal.envelopes(a,'ack')) and time.monotonic()<deadline:time.sleep(.2)
        assert (lk+'.'+contact in journal.envelopes(a,'ack'))
        assert laptop.process.pid==pid and laptop.process.poll() is None
        assert hashlib.sha256(binary.read_bytes()).hexdigest()==expected
        receipt.write_text(json.dumps({'runner_path':str(Path(__file__).resolve()),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runner_manifest':str(Path(__file__).resolve().parent.parent/'manifest.json'),'suite':'native-contact-projection-retry','helper_sha256':expected,'shim_sha256':hashlib.sha256(shim.read_bytes()).hexdigest(),
            'passed':['failed-projection-keeps-sender-debt','already-journaled-contact-retries-without-restart','ack-only-after-successful-projection']},indent=2)+'\n')
        print('contact-projection-e2e: pass',flush=True)
    finally:
        for peer in (a,b,laptop):peer.stop()
