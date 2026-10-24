#!/usr/bin/env python3
"""Real encrypted peer boundary with a deliberately malicious disposable sender.
Failures: a foreign person's own-author claim poisons the receiver's clock;
a genuine foreign UINT64_MAX clock prevents local sends; rejected traffic is
journaled; an apparently unchanged contact never repairs its missing sync event.
Native processes/Signal/Tox only; fixture edits are limited to disposable state.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
spec = importlib.util.spec_from_file_location('peers', Path(__file__).with_name('group-admin-e2e.py'))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
spec_journal=importlib.util.spec_from_file_location('journal_fixture',Path(__file__).with_name('journal-fixture.py'))
journal=importlib.util.module_from_spec(spec_journal);spec_journal.loader.exec_module(journal)
binary = Path(sys.argv[1]).resolve(); receipt = Path(sys.argv[2]).resolve()
expected = hashlib.sha256(binary.read_bytes()).hexdigest()
def ask(peer, op, **fields):
    marker = peer.mark(); request = 'boundary-' + str(marker)
    peer.send({'op': op, 'request': request, **fields})
    event = peer.wait(lambda e:e.get('event') in ('devices','devices.error') and e.get('request') == request, 15, marker)
    assert event['event'] == 'devices', event
    return event
with tempfile.TemporaryDirectory(prefix='harbor-boundary-') as temporary:
    root = Path(temporary); a = p.Peer(binary, root, 'alice'); b = p.Peer(binary, root, 'bob')
    try:
        ak = p.start_identity(a); bk = p.start_identity(b)
        alice = ask(a, 'device.initialize', nickname='Alice')
        bob = ask(b, 'device.initialize', nickname='Bob')
        p.pair(a, b, bk, 'boundary')
        a.wait(p.event_is('person.info', key=bob['person']), 180)
        b.wait(p.event_is('person.info', key=alice['person']), 180)
        # Create an authenticated foreign event with the victim's public author
        # label; even a foreign root endorsing that label must not make it local.
        def inject(author,request):
            body = 'HM2|{}|{}|-|{}|000000006a000000\nforeign clock fixture'.format(bob['person'],alice['person'],request)
            preimage='Harbor-event-v1|ffffffffffffffff|{}|{}|p:{}|message\n{}'.format(bob['person'],author,alice['person'],body)
            identifier=hashlib.sha256(preimage.encode()).digest()[:16].hex()
            data = 'HS2|{}|ffffffffffffffff|{}|{}|p:{}|message\n{}'.format(identifier,bob['person'],author,alice['person'],body)
            journal.put(b,data)
            return identifier
        bad = inject(alice['proposal'][:64], 'bad-author')
        time.sleep(8)
        assert journal.get(a,bad) is None, 'foreign own-author event was accepted'
        # A foreign clock is allowed to order foreign history, never exhaust ours.
        good = inject(bob['proposal'][:64], 'foreign-fixture')
        a.wait(p.event_is('message', id=good, dir='in'), 90)
        a.send({'op':'msg.send','conversation':'p:'+bob['person'],'key':bob['person'],'id':'after-clock','text':'Still able to send'})
        sent = a.wait(p.event_is('message', request='after-clock', dir='out'), 30)
        assert sent['text'] == 'Still able to send'
        # Simulate the old install-before-publication crash gap. An identical
        # periodic contact announcement must recreate the deterministic event.
        contacts={key:wire for key,wire in journal.events(a).items() if b'|contact\n' in wire}
        assert contacts
        contact,original=next(iter(contacts.items()));journal.delete(a,contact)
        deadline=time.monotonic()+45
        while journal.get(a,contact) is None and time.monotonic()<deadline:time.sleep(.2)
        assert journal.get(a,contact) is not None,'unchanged contact did not reconcile into journal'
        assert journal.get(a,contact).split(b'\n',1)[1]==original.split(b'\n',1)[1]
        assert hashlib.sha256(binary.read_bytes()).hexdigest() == expected
        receipt.write_text(json.dumps({'runner_path':str(Path(__file__).resolve()),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runner_manifest':str(Path(__file__).resolve().parent.parent/'manifest.json'),'suite':'native-person-adversarial-boundary','helper_sha256':expected,
            'passed':['foreign-own-author-rejected-before-journal','foreign-clock-cannot-exhaust-local-publishing','unchanged-contact-repairs-missing-publication']},indent=2)+'\n')
        print('person-boundary-e2e: pass',flush=True)
    finally:
        a.stop(); b.stop()
