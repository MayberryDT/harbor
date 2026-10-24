#!/usr/bin/env python3
"""R16 isolated native failure: replay must retain the latest contact name.
Failure specified before execution: pending contact replay sorted by random ID
may install an older name after a newer same-roster event. Only disposable
native profiles; preserve a public summary, never generated private state.
"""
import hashlib, importlib.util, json, sqlite3, sys, tempfile, time
from pathlib import Path
source=Path(__file__).resolve().parent.parent;binary=Path(sys.argv[1]).resolve();receipt=Path(sys.argv[2]).resolve()
spec=importlib.util.spec_from_file_location('peers',source/'tests/group-admin-e2e.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
def until(predicate):
    end=time.monotonic()+15
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.05)
    raise RuntimeError('bounded condition timed out')
with tempfile.TemporaryDirectory(prefix='harbor-r16-contact-order-') as temporary:
    root=Path(temporary);a=p.Peer(binary,root,'alice');b=p.Peer(binary,root,'bob');running=[a,b]
    try:
        identities=[]
        for peer in (a,b):
            p.start_identity(peer)
            peer.send(dict(op='device.initialize',request='init',nickname=peer.name))
            identities.append(peer.wait(p.event_is('devices',request='init'),15))
        own,bob=identities;b.stop()
        def body(name):return 'HPC1|'+name.encode().hex()+'|'+bob['roster']
        def event_id(name):return hashlib.sha256((own['local']+own['person']+body(name)).encode()).hexdigest()[:32]
        old=next('Original Bob '+str(i) for i in range(1000) if event_id('Original Bob '+str(i))[0]>='8');old_id=event_id(old)
        new=next('Renamed Bob '+str(i) for i in range(1000) if event_id('Renamed Bob '+str(i))<old_id)
        new_id=event_id(new)
        namefile=a.home/'devices/people'/(bob['person']+'.name')
        # Discover storage root from the disposable profile, not live data.
        def read_name():
            matches=list(a.home.rglob(bob['person']+'.name'))
            return matches[0].read_text() if matches else None
        for name,identifier in ((old,old_id),(new,new_id)):
            mark=a.mark();a.send(dict(op='sync.publish',request='publish-'+identifier,id=identifier,conversation='d:'+bob['person'],kind='contact',text=body(name)))
            result=a.wait(lambda e:e.get('request')=='publish-'+identifier and e.get('event') in ('sync.state','sync.error'),15,mark)
            assert result['event']=='sync.state',result
            until(lambda:read_name()==name)
        database=a.home/'sync/journal.sqlite'
        def pending():
            with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=1) as connection:
                return connection.execute('SELECT count(*) FROM pending_work').fetchone()[0]
        until(lambda:pending()==0)
        before=read_name();a.stop()
        a=p.Peer(binary,root,'alice');running.append(a);p.start_identity(a)
        until(lambda:pending()==0)
        time.sleep(.3);after=read_name()
        mark=a.mark();a.send(dict(op='sync.publish',request='invalid-card',id='08'*16,conversation='d:'+bob['person'],kind='contact',text='HPC1|00|'+bob['roster']))
        invalid=a.wait(lambda e:e.get('request')=='invalid-card' and e.get('event') in ('sync.state','sync.error'),15,mark)
        assert invalid['event']=='sync.error',invalid
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as connection:
            assert not connection.execute('SELECT 1 FROM events WHERE id=?',('08'*16,)).fetchone(), 'invalid name was journaled'
        mark=a.mark();a.send(dict(op='sync.publish',request='retry-old',id=old_id,conversation='d:'+bob['person'],kind='contact',text=body(old)))
        retried=a.wait(lambda e:e.get('request')=='retry-old' and e.get('event') in ('sync.state','sync.error'),15,mark)
        assert retried['event']=='sync.state' and read_name()==new,retried
        result={'old_retry_preserves_latest':True,'probe':'native-contact-replay-order','helper_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
            'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'runner_bundle':source.name,'old_event_id':old_id,'new_event_id':new_id,
            'before_restart':before,'after_restart':after,'expected':new,
            'retained_latest_name':after==new}
        assert after==new,result
        receipt.write_text(json.dumps(result,indent=2)+'\n');print('contact-order-e2e: pass',flush=True)
    finally:
        for peer in running:peer.stop()
