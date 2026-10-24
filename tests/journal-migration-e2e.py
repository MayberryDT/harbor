#!/usr/bin/env python3
"""Upgrade actual disposable native profiles without cloning any device.
Failures: partial import loses acknowledged messages; retries change immutable
IDs; upgraded/old peers cannot communicate; unsafe/missing/corrupt databases
silently fall back to stale event files or start empty history.
"""
import hashlib, importlib.util, json, sys, tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('peers',Path(__file__).with_name('group-admin-e2e.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
old=Path(sys.argv[1]).resolve();new=Path(sys.argv[2]).resolve();receipt=Path(sys.argv[3]).resolve()
with tempfile.TemporaryDirectory(prefix='harbor-journal-upgrade-') as temporary:
    root=Path(temporary);a=p.Peer(old,root,'alice');b=p.Peer(old,root,'bob');running=[a,b]
    try:
        ak=p.start_identity(a);bk=p.start_identity(b);identities=[]
        for peer in (a,b):
            peer.send({'op':'device.initialize','request':'initialize','nickname':peer.name})
            identities.append(peer.wait(p.event_is('devices',request='initialize'),15))
        bob=identities[1]['person'];p.pair(a,b,bk,'journal-upgrade')
        a.wait(p.event_is('person.info',key=bob),180)
        before=dict(op='msg.send',conversation='p:'+bob,key=bob,id='before-upgrade',text='Retained before the storage upgrade')
        a.send(before);first=a.wait(p.event_is('message',request='before-upgrade',dir='out'),30)
        b.wait(p.event_is('message',id=first['id'],dir='in'),180)
        a.stop();a=p.Peer(new,root,'alice');running.append(a);p.start_identity(a)
        def history(request,success=True):
            mark=a.mark();a.send(dict(op='history',conversation='p:'+bob,key=bob,id=request))
            result=a.wait(lambda e:e.get('request')==request and e.get('event') in ('history','history.failed'),30,mark)
            assert (result['event']=='history') is success,result
            return result
        migrated=history('after-upgrade')
        assert any(row['id']==first['id'] and row['text']==before['text'] for row in migrated['items'])
        assert (a.home/'sync/events'/first['id']).exists(),'verified legacy input must remain a recoverable source'
        database=a.home/'sync/journal.sqlite';assert database.is_file()
        mark=a.mark();a.send(before);retry=a.wait(p.event_is('message',request='before-upgrade'),30,mark)
        assert retry['id']==first['id']
        a.send(dict(op='msg.send',conversation='p:'+bob,key=bob,id='after-upgrade',text='New store and old peer interoperate'))
        second=a.wait(p.event_is('message',request='after-upgrade'),30)
        b.wait(p.event_is('message',id=second['id'],dir='in'),180)
        a.stop();a=p.Peer(old,root,'alice');running.append(a);p.start_identity(a)
        mark=a.mark();a.send(dict(op='msg.send',conversation='p:'+bob,key=bob,id='downgrade-write',text='Must not fork the retired journal'))
        denied=a.wait(lambda e:e.get('event')=='message.failed' and
            (e.get('id')=='downgrade-write' or e.get('request')=='downgrade-write'),30,mark)
        assert denied.get('code')=='sync_persist_failed',denied
        a.stop();a=p.Peer(new,root,'alice');running.append(a);p.start_identity(a)
        history('after-downgrade-denial')
        a.stop();saved=database.with_name('journal.saved');database.rename(saved)
        database.symlink_to(root/'missing-journal')
        a=p.Peer(new,root,'alice');running.append(a);p.start_identity(a)
        history('unsafe-store',False);a.stop()
        database.unlink();saved.rename(database)
        a=p.Peer(new,root,'alice');running.append(a);p.start_identity(a)
        restored=history('healed-store')
        assert {first['id'],second['id']}<={row['id'] for row in restored['items']}
        a.stop();original=database.read_bytes();database.write_bytes(b'not a database\0')
        a=p.Peer(new,root,'alice');running.append(a);p.start_identity(a)
        history('corrupt-store',False);a.stop()
        database.write_bytes(original);database.chmod(0o600)
        a=p.Peer(new,root,'alice');running.append(a);p.start_identity(a)
        final=history('after-corruption-healed')
        assert {first['id'],second['id']}<={row['id'] for row in final['items']}
        receipt.write_text(json.dumps({'suite':'native-journal-migration',
            'old_helper_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),
            'new_helper_sha256':hashlib.sha256(new.read_bytes()).hexdigest(),
            'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'passed':['native-legacy-event-import','stable-request-retry-after-upgrade',
                'old-peer-interoperability','retired-journal-rejects-old-writes','unsafe-database-no-legacy-fallback',
                'corrupt-database-no-empty-reset','healed-storage-retains-both-generations']},indent=2)+'\n')
        print('journal-migration-e2e: pass',flush=True)
    finally:
        for peer in running:peer.stop()
