#!/usr/bin/env python3
"""Native SQLite scheduling-schema upgrade retains events and pending delivery.
Failure cases: adding the retry deadline breaks old triggers; pending work drops;
old monotonic deadlines survive a reboot; upgrades regenerate request IDs/clocks.
"""
import hashlib,importlib.util,json,sqlite3,sys,tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('peers',Path(__file__).with_name('group-admin-e2e.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
old=Path(sys.argv[1]).resolve();new=Path(sys.argv[2]).resolve();receipt=Path(sys.argv[3]).resolve()
with tempfile.TemporaryDirectory(prefix='harbor-schema-upgrade-') as temporary:
    root=Path(temporary);a=p.Peer(old,root,'alice');b=p.Peer(old,root,'bob');running=[a,b]
    try:
        p.start_identity(a);bk=p.start_identity(b);identities=[]
        for peer in (a,b):
            peer.send(dict(op='device.initialize',request='init',nickname=peer.name))
            identities.append(peer.wait(p.event_is('devices',request='init'),15))
        bob=identities[1]['person'];p.pair(a,b,bk,'schema-upgrade');a.wait(p.event_is('person.info',key=bob),180)
        operation=dict(op='msg.send',conversation='p:'+bob,key=bob,id='before-schema-upgrade',text='Retain the exact original event')
        a.send(operation);original=a.wait(p.event_is('message',request=operation['id']),30)
        b.wait(p.event_is('message',id=original['id']),90)
        b.stop();a.send(dict(op='msg.send',conversation='p:'+bob,key=bob,id='pending-upgrade',text='Retain outstanding delivery'))
        pending=a.wait(p.event_is('message',request='pending-upgrade'),30);a.stop()
        database=a.home/'sync/journal.sqlite'
        with sqlite3.connect(database) as connection:
            assert connection.execute('PRAGMA user_version').fetchone()==(1,)
            wire=connection.execute('SELECT wire FROM events WHERE id=?',(original['id'],)).fetchone()[0]
        a=p.Peer(new,root,'alice');running.append(a);p.start_identity(a)
        a.send(operation);retry=a.wait(p.event_is('message',request=operation['id']),30)
        assert retry['id']==original['id']
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as connection:
            assert connection.execute('PRAGMA user_version').fetchone()==(3,)
            assert connection.execute('SELECT wire FROM events WHERE id=?',(original['id'],)).fetchone()[0]==wire
            assert 'not_before' in [row[1] for row in connection.execute('PRAGMA table_info(pending_work)')]
        a.send(dict(op='msg.send',conversation='p:'+bob,key=bob,id='after-upgrade',text='The upgraded insertion trigger works'))
        after=a.wait(p.event_is('message',request='after-upgrade'),30)
        b=p.Peer(new,root,'bob');running.append(b);p.start_identity(b)
        b.wait(p.event_is('message',id=pending['id']),180)
        b.wait(p.event_is('message',id=after['id']),90)
        receipt.write_text(json.dumps(dict(suite='native-sqlite-schema-upgrade',old_helper_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),new_helper_sha256=hashlib.sha256(new.read_bytes()).hexdigest(),runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),passed=['v1-to-v3-native-upgrade','exact-wire-and-retry-ID-retained','upgraded-trigger-inserts','outstanding-delivery-catches-up']),indent=2)+'\n')
        print('journal-schema-upgrade-e2e: pass',flush=True)
    finally:
        for peer in running:peer.stop()
