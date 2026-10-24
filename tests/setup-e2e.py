#!/usr/bin/env python3
"""Real-helper first launch, retry and restart with a sanitized receipt.

Failures: unfinished setup emits false sync errors; invalid nickname reports
success; retry replaces authority; restart loses profile; corrupt established
roster is mistaken for an uninitialized installation. Never use a live identity.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time

spec = importlib.util.spec_from_file_location('peers', Path(__file__).with_name('group-admin-e2e.py'))
peers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(peers)
binary, receipt = map(lambda p: Path(p).resolve(), sys.argv[1:])
candidate = hashlib.sha256(binary.read_bytes()).hexdigest()
checks = []

def device(peer, operation, **fields):
    marker = peer.mark()
    request = 'setup-' + str(marker)
    peer.send(dict(op=operation, request=request, **fields))
    return peer.wait(lambda e: e.get('event') in ('devices', 'devices.error') and e.get('request') == request, 15, marker)

with tempfile.TemporaryDirectory(prefix='harbor-setup-') as directory:
    root = Path(directory)
    peer = peers.Peer(binary, root, 'new')
    try:
        peers.start_identity(peer)
        time.sleep(2.2)
        assert not any(e.get('event') == 'sync.error' for e in peer.events)
        assert device(peer, 'device.status')['code'] == 'device_not_linked'
        checks.append('uninitialized-installation-is-quiet')
        first = device(peer, 'device.initialize', nickname='My computer')
        assert first['event'] == 'devices' and first['active'] is True
        assert first['items'][0]['current'] and first['items'][0]['active']
        seed_hash = hashlib.sha256((peer.home/'devices/recovery-key').read_bytes()).hexdigest()
        retry = device(peer, 'device.initialize', nickname='My computer')
        assert retry['person'] == first['person'] and retry['local'] == first['local']
        assert hashlib.sha256((peer.home/'devices/recovery-key').read_bytes()).hexdigest() == seed_hash
        checks.append('retry-reuses-person-and-device-authority')
        peer.send(dict(op='nickname.set', nickname='', id='invalid-name'))
        peer.wait(peers.event_is('error', code='nickname_invalid', request='invalid-name'), 15)
        peer.send(dict(op='nickname.set', nickname='Alice', id='save-name'))
        peer.wait(peers.event_is('nickname', value='Alice', request='save-name'), 15)
        checks.append('profile-validation-and-correlated-save')
        peer.stop()
        peer = peers.Peer(binary, root, 'new')
        peers.start_identity(peer)
        status = device(peer, 'device.status')
        assert status['person'] == first['person'] and status['local'] == first['local']
        peer.wait(peers.event_is('snapshot', nickname='Alice'), 15)
        checks.append('restart-preserves-profile-and-authority')
        peer.stop()
        (peer.home/'devices/roster').write_bytes(b'corrupt')
        peer = peers.Peer(binary, root, 'new')
        peers.start_identity(peer)
        assert device(peer, 'device.status')['event'] == 'devices.error'
        peer.wait(peers.event_is('sync.error', code='sync_state_invalid'), 15)
        checks.append('corrupt-established-state-remains-visible')
        assert hashlib.sha256(binary.read_bytes()).hexdigest() == candidate
    finally:
        peer.stop()
        receipt.write_text(json.dumps(dict(passed=sys.exc_info()[0] is None,
            candidate_sha256=candidate, checks=checks), indent=2)+'\n')
print(receipt)
