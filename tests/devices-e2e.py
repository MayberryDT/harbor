#!/usr/bin/env python3
"""Native helper device authorization boundary.

Failures considered before implementation: cloned transport/session keys; forged
roster/signatures; binding substitution; import into an unrelated device; rollback;
revoked-device mutation; reauthorization of a revoked key; fork acceptance; partial
writes and symlinks; unconfirmed authorization; restart identity changes. This E2E
covers the public roster/IPC boundary, not network linking or message sync.
"""
import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
import sys
import tempfile

spec = importlib.util.spec_from_file_location('peers', Path(__file__).with_name('group-admin-e2e.py'))
peers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(peers)
binary = Path(sys.argv[1]).resolve()
receipt = Path(sys.argv[2]).resolve()
expected_candidate_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
def candidate_sha():
    actual = hashlib.sha256(binary.read_bytes()).hexdigest()
    if actual != expected_candidate_sha:
        raise RuntimeError('candidate executable changed during verification')
    return actual

consent_spec=importlib.util.spec_from_file_location('consent_fixture',Path(__file__).with_name('device-consent-fixture.py'))
consent_fixture=importlib.util.module_from_spec(consent_spec);consent_spec.loader.exec_module(consent_fixture)
consent=consent_fixture.consent

results = []

def ask(peer, op, **fields):
    marker = peer.mark()
    request = 'devices-' + str(marker)
    peer.send({'op': op, 'request': request, **fields})
    return peer.wait(lambda e: e.get('event') in ('devices', 'devices.error') and e.get('request') == request,
                     15, marker, op)

def ok(event):
    assert event['event'] == 'devices', event
    return event

with tempfile.TemporaryDirectory(prefix='harbor-devices-') as directory:
    root = Path(directory)
    alice = peers.Peer(binary, root, 'alice')
    laptop = peers.Peer(binary, root, 'laptop')
    stranger = peers.Peer(binary, root, 'stranger')
    running = [alice, laptop, stranger]
    try:
        for peer in running:
            peers.start_identity(peer)
        a = ok(ask(alice, 'device.initialize', nickname='Desktop'))
        b = ok(ask(laptop, 'device.propose', nickname='Laptop'))
        c = ok(ask(stranger, 'device.propose', nickname='Stranger'))
        assert a['proposal'] != b['proposal'] != c['proposal']
        assert len(a['proposal']) == len(b['proposal']) == 192
        results.append('independent-device-bindings')
        denied = ask(alice, 'device.authorize', payload=b['proposal'], nickname='Laptop')
        assert denied['event'] == 'devices.error'
        assert ask(alice, 'device.authorize', payload=b['proposal'], nickname='Laptop', accept=True)['event'] == 'devices.error'
        proof_b = consent(laptop, a['person'])
        proof_c = consent(stranger, a['person'])
        proof_a = consent(alice, a['person'])
        wrong = proof_b[:-1] + ('0' if proof_b[-1] != '0' else '1')
        assert ask(alice, 'device.authorize', payload=b['proposal'], text=wrong, nickname='Laptop', accept=True)['event'] == 'devices.error'
        linked = ok(ask(alice, 'device.authorize', payload=b['proposal'], text=proof_b, nickname='Laptop', accept=True))
        results.extend(['subject-consent-required', 'forged-consent-rejected'])
        roster = linked['roster']
        adopted = ok(ask(laptop, 'device.adopt', text=roster, key=a['person'], accept=True))
        assert adopted['person'] == a['person'] and adopted['count'] == 2 and adopted['active']
        assert len(adopted['items']) == 2
        assert {item['key'] for item in adopted['items']} == {a['local'], b['local']}
        assert [item['key'] for item in adopted['items'] if item['current']] == [b['local']]
        assert {item['name'] for item in adopted['items']} == {'Desktop', 'Laptop'}
        results.append('helper-authored-complete-device-list')
        assert ask(stranger, 'device.adopt', text=roster, key=a['person'], accept=True)['event'] == 'devices.error'
        corrupted = roster[:-1] + ('0' if roster[-1] != '0' else '1')
        assert ask(laptop, 'device.adopt', text=corrupted, key=a['person'], accept=True)['event'] == 'devices.error'
        results.extend(['explicit-confirmation', 'authorized-device-adoption', 'unbound-device-rejected', 'tampering-rejected'])
        # Reconstruct the root-only crash window: the recovery authority reached
        # disk but the initial roster did not. Retrying must reuse that authority.
        incomplete = peers.Peer(binary, root, 'incomplete')
        running.append(incomplete); peers.start_identity(incomplete)
        first = ok(ask(incomplete, 'device.initialize', nickname='Recovery'))
        recovery_hash = hashlib.sha256((incomplete.home/'devices/recovery-key').read_bytes()).hexdigest()
        (incomplete.home/'devices/roster').unlink()
        (incomplete.home/'devices/committed').unlink()
        retried = ok(ask(incomplete, 'device.initialize', nickname='Recovery'))
        assert retried['person'] == first['person']
        assert hashlib.sha256((incomplete.home/'devices/recovery-key').read_bytes()).hexdigest() == recovery_hash
        results.append('interrupted-initialization-reuses-authority')
        # Exercise a valid competing branch that never authorized its recipient.
        omitted = peers.Peer(binary, root, 'omitted')
        running.append(omitted); peers.start_identity(omitted)
        proposal = ok(ask(omitted, 'device.propose'))
        branch_a = ok(ask(incomplete, 'device.authorize', payload=proposal['proposal'], text=consent(omitted, first['person']), nickname='Omitted', accept=True))
        ok(ask(omitted, 'device.adopt', text=branch_a['roster'], key=first['person'], accept=True))
        (incomplete.home/'devices/roster').write_bytes(bytes.fromhex(first['roster']))
        branch_b = ok(ask(incomplete, 'device.authorize', payload=c['proposal'], text=consent(stranger, first['person']), nickname='Other', accept=True))
        conflict = ask(omitted, 'device.adopt', text=branch_b['roster'], key=first['person'], accept=True)
        assert conflict.get('code') == 'device_roster_conflict', conflict
        assert ask(omitted, 'device.status').get('code') == 'device_roster_conflict'
        results.append('preauthorization-fork-persists')
        # A correctly signed roster containing invalid UTF8 must fail validation.
        signed = bytearray.fromhex(first['roster'])
        signed[170] = 255
        seed = (incomplete.home/'devices/recovery-key').read_bytes()
        fixture = root/'fixture'; fixture.mkdir(mode=0o700)
        (fixture/'key.der').write_bytes(bytes.fromhex('302e020100300506032b657004220420')+seed)
        (fixture/'message').write_bytes(b'Harbor-device-roster-v2\0'+bytes.fromhex(first['person'])+signed[:282])
        subprocess.run(['openssl','pkeyutl','-sign','-rawin','-inkey',str(fixture/'key.der'),'-keyform','DER',
                        '-in',str(fixture/'message'),'-out',str(fixture/'signature')], check=True, capture_output=True)
        signed[282:] = (fixture/'signature').read_bytes()
        malformed = ask(incomplete, 'device.adopt', text=signed.hex(), key=first['person'], accept=True)
        assert malformed.get('code') == 'device_roster_invalid', malformed
        results.append('signed-invalid-utf8-rejected')
        old = a['roster']
        assert ask(alice, 'device.adopt', text=old, key=a['person'], accept=True)['event'] == 'devices.error'
        fork = ok(ask(laptop, 'device.authorize', payload=c['proposal'], text=proof_c, nickname='Stranger', accept=True))
        revoked = ok(ask(alice, 'device.revoke', key=b['proposal'][:64], accept=True))
        assert ask(alice, 'device.adopt', text=fork['roster'], key=a['person'], accept=True)['event'] == 'devices.error'
        assert ask(alice, 'device.status')['event'] == 'devices.error', 'fork must persist across operations'
        results.extend(['rollback-rejected', 'fork-blocks-routing'])
        # A separate linked pair demonstrates revocation independently of the fork.
        # Laptop's valid branch can revoke the added stranger and refuses revoked-key reuse.
        removed = ok(ask(laptop, 'device.revoke', key=c['proposal'][:64], accept=True))
        assert ask(laptop, 'device.authorize', payload=c['proposal'], text=proof_c, nickname='Stranger', accept=True)['event'] == 'devices.error'
        # Its own revocation imports safely but prevents subsequent authorization.
        self_revoked = ok(ask(laptop, 'device.revoke', key=b['proposal'][:64], accept=True))
        assert not self_revoked['active']
        assert ask(laptop, 'device.authorize', payload=a['proposal'], text=proof_a, nickname='Desktop', accept=True)['event'] == 'devices.error'
        results.extend(['revoked-keys-not-reused', 'revoked-local-device-blocked'])
        alice.stop()
        restarted = peers.Peer(binary, root, 'alice')
        running.append(restarted)
        peers.start_identity(restarted)
        assert ask(restarted, 'device.status')['event'] == 'devices.error'
        results.append('fork-survives-restart')
        initialized_stranger = ok(ask(stranger, 'device.initialize', nickname='Stranger'))
        stranger.stop()
        shutil.rmtree(stranger.home/'ratchet')
        changed = peers.Peer(binary, root, 'stranger'); running.append(changed); peers.start_identity(changed)
        mismatch = ask(changed, 'device.initialize', nickname='Stranger')
        assert mismatch.get('code') == 'device_binding_mismatch', mismatch
        results.append('identity-replacement-cannot-reuse-roster')
        changed.stop()
        private = changed.home/'devices/key'
        private.rename(changed.home/'devices/key-original')
        private.symlink_to('key-original')
        unsafe = peers.Peer(binary, root, 'stranger'); running.append(unsafe); peers.start_identity(unsafe)
        assert ask(unsafe, 'device.status').get('code') == 'device_state_invalid'
        results.append('private-key-symlink-rejected')
        (incomplete.home/'devices/roster').unlink()
        missing=ask(incomplete,'device.initialize',nickname='Recovery')
        assert missing.get('code')=='device_roster_missing',missing
        results.append('established-roster-loss-fails-closed')
    finally:
        for peer in running:
            peer.stop()
receipt.parent.mkdir(parents=True, exist_ok=True)
receipt.write_text(json.dumps({'runner_path':str(Path(__file__).resolve()),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runner_manifest':str(Path(__file__).resolve().parent.parent/'manifest.json'),'suite': 'device-authorization-boundary', 'helper_sha256': candidate_sha(),
                               'passed': results, 'scope': 'native IPC; no network sync/UI acceptance claim'}, indent=2) + '\n')
print('devices-e2e: passed ' + str(len(results)) + ' checks; receipt=' + str(receipt))
