#!/usr/bin/env python3
"""Real relay file journey with separately observed stage timings and SHA-256.
Failures: sending before consent, wrong-contact transfer, corrupted bytes, wrong
received path, premature completion, indefinite offer/transfer and candidate drift.
No synthetic network speed claim: both peers run on one host through TCP relays.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import sys
import tempfile
import time

spec = importlib.util.spec_from_file_location('peers', Path(__file__).with_name('group-admin-e2e.py'))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
binary, receipt = map(lambda value: Path(value).resolve(), sys.argv[1:])
candidate = hashlib.sha256(binary.read_bytes()).hexdigest()

class TimedPeer(p.Peer):
    def _read_stdout(self):
        for line in self.process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event['_observed'] = time.monotonic()
            with self.condition:
                self.events.append(event)
                self.condition.notify_all()

results = []
with tempfile.TemporaryDirectory(prefix='harbor-file-journey-') as directory:
    root = Path(directory)
    a, b = [TimedPeer(binary, root, name) for name in ('alice', 'bob')]
    try:
        ak, bk = p.start_identity(a), p.start_identity(b)
        a.send(dict(op='invite.create', kind='direct', accept=True, request='file-invite'))
        invitation = a.wait(p.event_is('invite', request='file-invite'), 15)
        b.send(dict(op='invite.redeem', payload=invitation['url'], id='file-connect'))
        af = a.wait(lambda e: e.get('event')=='friend.info' and e.get('key')==bk and e.get('online'), 180)
        bf = b.wait(lambda e: e.get('event')=='friend.info' and e.get('key')==ak and e.get('online'), 180)
        a.send(dict(op='msg.send', conversation=str(af['id']), key=bk, id='file-channel', text='File journey ready'))
        b.wait(p.event_is('message', dir='in', text='File journey ready'), 90)
        for sender, receiver, sf, rf, sk, rk in ((a,b,af,bf,ak,bk),(b,a,bf,af,bk,ak)):
            source = root / ('sample-' + sender.name + '.bin')
            source.write_bytes(secrets.token_bytes(1024*1024))
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            sm, rm = sender.mark(), receiver.mark()
            start = time.monotonic()
            sender.send(dict(op='file.send', conversation=str(sf['id']), key=rk,
                             path=str(source), id='file-'+sender.name))
            offer = receiver.wait(lambda e:e.get('event')=='file.offer' and e.get('key')==sk, 30, rm)
            fid = offer['id']
            # Completion is impossible while the recipient has not accepted.
            time.sleep(.5)
            assert not any(e.get('event')=='file.done' and e.get('id')==fid for e in receiver.events[rm:])
            accepted = time.monotonic()
            receiver.send(dict(op='file.accept', conversation=str(rf['id']), key=sk, id=fid))
            first = receiver.wait(lambda e:e.get('event')=='file.progress' and e.get('id')==fid and e.get('done',0)>0, 60, rm)
            done = receiver.wait(lambda e:e.get('event')=='file.done' and e.get('id')==fid and e.get('dir')=='in', 300, rm)
            destination = Path(done['path'])
            assert destination.parent == receiver.download/'Harbor'
            assert destination.stat().st_size == source.stat().st_size
            assert hashlib.sha256(destination.read_bytes()).hexdigest() == digest
            sender.wait(lambda e:e.get('event')=='file.done' and e.get('request')=='file-'+sender.name, 30, sm)
            seconds = done['_observed'] - accepted
            results.append(dict(direction=sender.name+'-to-'+receiver.name,
                bytes=source.stat().st_size, sha256=digest,
                send_to_offer_seconds=round(offer['_observed']-start,4),
                offer_to_accept_seconds=round(accepted-offer['_observed'],4),
                accept_to_first_progress_seconds=round(first['_observed']-accepted,4),
                accept_to_complete_seconds=round(seconds,4),
                effective_mib_per_second=round(1/seconds,4),
                received_bytes_verified=True, consent_required=True))
        assert hashlib.sha256(binary.read_bytes()).hexdigest() == candidate
    finally:
        a.stop(); b.stop()
        receipt.write_text(json.dumps(dict(passed=sys.exc_info()[0] is None,
            candidate_sha256=candidate, network='Two helpers on Halla, TCP relay privacy mode; no direct LAN claim',
            timing='Monotonic helper-event observation; first progress is not exact first-byte instrumentation',
            transfers=results), indent=2)+'\n')
print(receipt)
