#!/usr/bin/env python3
"""Native crypto-ledger upgrade with preserved Signal sessions and queued bytes.
Failure cases specified first: ciphertext silently regenerated/lost; inbox or ACK
loss replays accepted work; unsafe legacy input partially commits or falls back;
old ledger writes split authority; restart loses pending delivery or exact retry.
Only disposable helper profiles, never copied identities or mocked encryption.
"""
import hashlib,importlib.util,json,signal,sqlite3,stat,sys,tempfile,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('peers',Path(__file__).with_name('group-admin-e2e.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
old=Path(sys.argv[1]).resolve();new=Path(sys.argv[2]).resolve();receipt=Path(sys.argv[3]).resolve()
def until(predicate,seconds=30):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.1)
    raise RuntimeError('bounded ledger condition timed out')
with tempfile.TemporaryDirectory(prefix='harbor-envelope-upgrade-') as temporary:
    root=Path(temporary);a=p.Peer(old,root,'alice');b=p.Peer(old,root,'bob');running=[a,b];paused=False
    try:
        ak=p.start_identity(a);bk=p.start_identity(b);identities=[]
        for peer in (a,b):
            peer.send(dict(op='device.initialize',request='init',nickname=peer.name))
            identities.append(peer.wait(p.event_is('devices',request='init'),15))
        alice,bob=[item['person'] for item in identities]
        p.pair(a,b,bk,'envelope-upgrade');a.wait(p.event_is('person.info',key=bob),180)
        a.send(dict(op='msg.send',conversation='p:'+bob,key=bob,id='before-ledger',text='Already delivered before ledger upgrade'))
        first=a.wait(p.event_is('message',request='before-ledger'),30);b.wait(p.event_is('message',id=first['id']),90)
        b.send(dict(op='msg.send',conversation='p:'+alice,key=alice,id='inbox-before-ledger',text='Authenticated inbox before ledger upgrade'))
        incoming=a.wait(p.event_is('message',dir='in',text='Authenticated inbox before ledger upgrade'),90)
        until(lambda:(a.home/'sync/ack'/(bk+'.'+first['id'])).exists())
        b.process.send_signal(signal.SIGSTOP);paused=True
        queued=dict(op='msg.send',conversation='p:'+bob,key=bob,id='queued-ledger',text='Keep the original encrypted envelope')
        a.send(queued);pending=a.wait(p.event_is('message',request='queued-ledger'),30)
        envelope=a.home/'sync/outbox'/(bk+'.'+pending['id'])
        until(envelope.exists);a.stop()
        b.process.send_signal(signal.SIGCONT);paused=False;b.stop()
        original={(bucket,path.name):path.read_bytes() for bucket in ('outbox','inbox','ack','rekey')
                  for path in (a.home/'sync'/bucket).glob('*') if not path.name.startswith('.')}
        assert all(any(bucket==key[0] for key in original) for bucket in ('outbox','inbox','ack'))
        # Outbox imports first. Fail on a later inbox row, so the assertion
        # below proves rollback of work already done in the same transaction.
        inbox_name=next(name for bucket,name in original if bucket=='inbox')
        unsafe=a.home/'sync/inbox'/inbox_name
        saved=unsafe.with_name('.upgrade-original');unsafe.rename(saved);unsafe.symlink_to(saved)
        a=p.Peer(new,root,'alice');running.append(a);p.start_identity(a)
        a.send(dict(op='history',conversation='p:'+bob,key=bob,id='unsafe-ledger'))
        a.wait(p.event_is('history.failed',request='unsafe-ledger'),30)
        a.stop();database=a.home/'sync/journal.sqlite'
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as connection:
            assert connection.execute('SELECT ledger_ready FROM journal_meta').fetchone()==(0,),'unsafe import committed authority'
            assert connection.execute('SELECT count(*) FROM envelopes').fetchone()==(0,),'failed import left partially committed rows'
        unsafe.unlink();saved.rename(unsafe)
        a=p.Peer(new,root,'alice');running.append(a);p.start_identity(a)
        a.send(dict(op='history',conversation='p:'+bob,key=bob,id='migrated-ledger'))
        history=a.wait(p.event_is('history',request='migrated-ledger'),30)
        assert {first['id'],incoming['id'],pending['id']}<={row['id'] for row in history['items']}
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as connection:
            assert connection.execute('SELECT ledger_ready FROM journal_meta').fetchone()==(1,)
            for (bucket,name),body in original.items():
                assert connection.execute('SELECT body FROM envelopes WHERE bucket=? AND name=?',(bucket,name)).fetchone()==(body,), 'migration changed ledger bytes'
        for bucket in ('outbox','inbox','ack','rekey'):
            assert stat.S_IMODE((a.home/'sync'/bucket).stat().st_mode)==0o500,'retired ledger remains writable'
        mark=a.mark();a.send(queued);a.wait(p.event_is('message',request='queued-ledger',id=pending['id']),30,mark)
        b=p.Peer(new,root,'bob');running.append(b);p.start_identity(b)
        def acknowledged():
            with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as connection:
                name=bk+'.'+pending['id']
                return connection.execute("SELECT 1 FROM envelopes WHERE bucket='ack' AND name=?",(name,)).fetchone() and not connection.execute("SELECT 1 FROM envelopes WHERE bucket='outbox' AND name=?",(name,)).fetchone()
        until(acknowledged,180)
        receipt.write_text(json.dumps(dict(suite='native-crypto-ledger-migration',old_helper_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),new_helper_sha256=hashlib.sha256(new.read_bytes()).hexdigest(),runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),imported_counts={bucket:sum(key[0]==bucket for key in original) for bucket in ('outbox','inbox','ack','rekey')},passed=['real-encrypted-pending-envelope','unsafe-import-no-partial-authority','exact-ciphertext-inbox-ACK-import','sealed-legacy-ledgers','stable-request-retry','queued-delivery-and-authenticated-ACK-after-upgrade']),indent=2)+'\n')
        print('envelope-migration-e2e: pass',flush=True)
    finally:
        if paused and b.process.poll() is None:b.process.send_signal(signal.SIGCONT)
        for peer in running:peer.stop()
