#!/usr/bin/env python3
"""Real helper acceptance for one-use permission; see stages/harbor2 failure cases."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
spec = importlib.util.spec_from_file_location('peers', Path(__file__).with_name('group-admin-e2e.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
binary, receipt = map(lambda value: Path(value).resolve(), sys.argv[1:])
digest = hashlib.sha256(binary.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='harbor-bearer-') as temporary:
    peers = [p.Peer(binary, Path(temporary), name) for name in ('issuer', 'recipient', 'legacy')]
    try:
        a, b, c = peers
        keys = [p.start_identity(peer) for peer in peers]
        a.send({'op':'invite.create','kind':'direct','accept':True,'request':'bearer-create'})
        invite = a.wait(p.event_is('invite',request='bearer-create'),15)
        assert invite.get('bearer') is True
        assert invite['url'].startswith('harbor://invite/')
        b.send({'op':'invite.redeem','payload':invite['url'],'id':'bearer-redeem'})
        friend = a.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==keys[1] and e.get('online'),180)
        other = b.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==keys[0] and e.get('online'),180)
        assert not any(e.get('event')=='request' and e.get('kind')=='direct' for e in a.events)
        a.send({'op':'msg.send','conversation':str(friend['id']),'key':keys[1], 'id':'bearer-message','text':'One invite, one conversation'})
        b.wait(p.event_is('message',dir='in',text='One invite, one conversation'),180)
        # The consumed capability is cleared at the same transaction boundary.
        a.send({'op':'status','id':'after-consumption'})
        a.wait(p.event_is('invite',url='',op='status'),15)
        # Legacy issuance remains an explicit request; don't change old consent.
        start = a.mark()
        a.send({'op':'invite.create','kind':'direct','request':'legacy-create'})
        legacy = a.wait(p.event_is('invite',request='legacy-create'),15,start)
        assert legacy.get('bearer') is False
        c.send({'op':'invite.redeem','payload':legacy['url'].replace('harbor://','omaq://',1),'id':'legacy-redeem'})
        request = a.wait(p.event_is('request',kind='direct',key=keys[2]),180,start)
        assert request['key']==keys[2]
        assert hashlib.sha256(binary.read_bytes()).hexdigest()==digest
        receipt.write_text(json.dumps({'status':'passed','candidate_sha256':digest,'checks':['bearer auto-accept','encrypted message delivery','token cleared','legacy approval preserved']},indent=2)+'\n')
    finally:
        for peer in peers: peer.stop()
