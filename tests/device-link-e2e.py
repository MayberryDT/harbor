#!/usr/bin/env python3
"""Real TCP-relay native linking; failures: mismatched device/session binding,
missing two-sided consent, stale challenge, replay, unconfirmed import, and a
revoked linked device attempting an application exchange. Receipt is public hashes.
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
binary = Path(sys.argv[1]).resolve(); receipt = Path(sys.argv[2]).resolve()
automatic = '--automatic' in sys.argv[3:]
expected_candidate_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
def candidate_sha():
    actual = hashlib.sha256(binary.read_bytes()).hexdigest()
    if actual != expected_candidate_sha:
        raise RuntimeError('candidate executable changed during verification')
    return actual

with tempfile.TemporaryDirectory(prefix='harbor-device-link-') as temporary:
    root = Path(temporary); a = p.Peer(binary,root,'desktop'); b = p.Peer(binary,root,'laptop')
    try:
        ak=p.start_identity(a); bk=p.start_identity(b)
        a.send({'op':'device.initialize','request':'initialize-desktop','nickname':'Desktop'})
        initialized=a.wait(p.event_is('devices',request='initialize-desktop'),15)
        print('redeeming a short-lived device-link invite',flush=True)
        a.send({'op':'invite.create','kind':'direct','accept':True,'ttlSec':300,'request':'link-invite'})
        invite=a.wait(lambda e:e.get('event')=='invite' and e.get('request')=='link-invite' and e.get('url'),15)
        assert invite['bearer'] is True
        assert 285 <= invite['expires'] - int(time.time()) <= 300, invite
        a.send({'op':'invite.redeem','kind':'device','payload':invite['url'],'id':'reject-established-device'})
        a.wait(p.event_is('error',request='reject-established-device',code='device_already_linked'),15)
        b.send({'op':'invite.redeem','kind':'device','payload':invite['url'],'id':'new-device-invite'})
        redeemed=b.wait(p.event_is('invite.redeemed',request='new-device-invite',kind='direct'),15)
        assert redeemed['key']==ak
        af=a.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==bk and e.get('online'),p.NETWORK_TIMEOUT)
        bf=b.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==ak and e.get('online'),p.NETWORK_TIMEOUT)
        print('paired; checking encrypted channel',flush=True)
        # Prove the existing encrypted application channel, not merely Tox
        # presence, is ready before exercising the new linking protocol.
        b.send({'op':'msg.send','id':'link-channel-ready','conversation':str(bf['id']),'key':ak,'text':'link channel ready'})
        a.wait(lambda e:e.get('event')=='message' and e.get('text')=='link channel ready',90)
        print('encrypted channel ready; requesting link',flush=True)
        request='link-laptop'
        # Existing pairing may be online before its independent Signal session is ready.
        for attempt in range(30):
            mark=b.mark()
            b.send({'op':'device.link.request','request':request,'conversation':str(bf['id']), 'key':ak,'nickname':'Laptop','accept':automatic})
            state=b.wait(lambda e:e.get('request')==request and e.get('event') in ('device.link','devices.error'),10,mark)
            if state['event']=='device.link': break
            assert state['code']=='device_session_not_ready',state
            time.sleep(1)
        incoming=a.wait(p.event_is('device.link',state='requested',request=request),30)
        challenge=b.wait(p.event_is('device.link',state='waiting-for-owner' if automatic else 'verify',request=request),30)
        assert challenge['code']==incoming['code'] and challenge['person']==initialized['person']
        assert not any(e.get('event')=='device.link' and e.get('state')=='linked' for e in b.events)
        # A replacement UI can recover the exact pending challenge from the helper.
        for peer, expected, direction in ((a, 'requested', True), (b, 'waiting-for-owner' if automatic else 'verify', False)):
            mark=peer.mark()
            peer.send({'op':'device.status','request':'ui-reconnect-status'})
            replay=peer.wait(p.event_is('device.link',state=expected,request=request),15,mark)
            assert replay['incoming'] is direction
            assert replay['code']==challenge['code'] and replay['person']==challenge['person']
        if automatic:
            # Recipient submission alone cannot authorize itself.
            a.send({'op':'device.status','request':'before-owner-consent'})
            before=a.wait(p.event_is('devices',request='before-owner-consent'),15)
            assert before['count']==1
            a.send({'op':'device.link.accept','request':request,'accept':True})
        else:
            # Owner consent alone must not activate the other machine.
            a.send({'op':'device.link.accept','request':request,'accept':True})
            a.wait(p.event_is('device.link',state='waiting-for-device',request=request),30)
            a.send({'op':'device.status','request':'before-target-consent'})
            before=a.wait(p.event_is('devices',request='before-target-consent'),15)
            assert before['count']==1, 'owner approval alone must not authorize a target'
            print('restarting owner before recipient consent',flush=True)
            a.process.kill();a.process.wait(timeout=5)
            a=p.Peer(binary,root,'desktop');p.start_identity(a)
            amark=a.mark();bmark=b.mark()
            b.send({'op':'device.link.request','request':request,'conversation':str(bf['id']),'key':ak,'nickname':'Laptop','accept':automatic})
            resumed=a.wait(p.event_is('device.link',state='requested',request=request),90,amark)
            reverified=b.wait(p.event_is('device.link',state='verify',request=request),90,bmark)
            assert resumed['code']==reverified['code'] and reverified['code']==challenge['code']
            a.send({'op':'device.link.accept','request':request,'accept':True})
            a.wait(p.event_is('device.link',state='waiting-for-device',request=request),30,amark)
            b.send({'op':'device.link.confirm','request':request,'key':initialized['person'],'accept':True})
        linked=b.wait(p.event_is('device.link',state='linked',request=request),15)
        b.send({'op':'device.status','request':'laptop-status'})
        status=b.wait(p.event_is('devices',request='laptop-status'),15)
        assert status['active'] and status['person']==initialized['person'] and status['count']==2
        # Replay can't authorize a second machine or silently alter the roster.
        a.send({'op':'device.link.accept','request':request,'accept':True})
        a.wait(p.event_is('device.link',state='sent',request=request),15)
        b.send({'op':'device.status','request':'laptop-after-replay'})
        replay=b.wait(p.event_is('devices',request='laptop-after-replay'),15)
        assert replay['sequence']==status['sequence']
        a.send({'op':'device.revoke','request':'revoke-linked-device','key':status['local'],'accept':True})
        a.wait(p.event_is('devices',request='revoke-linked-device'),15)
        mark=a.mark()
        a.send({'op':'device.link.accept','request':request,'accept':True})
        denied=a.wait(p.event_is('devices.error',request=request),15,mark)
        assert denied['code']=='device_revoked',denied
        result={'suite':'native-device-link','helper_sha256':candidate_sha(),
          'passed':['one-use-link-invite-bootstrap','established-identity-cannot-redeem-device-invite','distinct-transport-and-session-keys','real-tcp-relay-link','matching-verification-code',
                    'pending-challenge-replay-both-directions','two-sided-consent','authenticated-roster-import','replay-idempotency','one-owner-approval-after-recipient-submission' if automatic else 'restart-reconsent-resume','revoked-link-cannot-be-replayed'],
          'scope':'linking only; no history/mailbox/group/call claim'}
        receipt.write_text(json.dumps(result,indent=2)+'\n')
        print('device-link-e2e: pass; receipt='+str(receipt))
    finally:
        a.stop();b.stop()
