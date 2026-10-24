#!/usr/bin/env python3
"""Failure: journaled new roster/name plus partial card install must not mint a
newer stale-name event at startup. Disposable native profiles, real fsync fault then controlled public-card crash-window fixture.
No live state, builds, or application edits."""
import hashlib,importlib.util,json,os,sqlite3,sys,tempfile,time
from pathlib import Path
runner=Path(__file__).resolve().parent.parent
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,runner/'tests'/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
p=load('peers','group-admin-e2e.py');c=load('consent','device-consent-fixture.py')
binary=Path(sys.argv[1]);shim=Path(sys.argv[2]);receipt=Path(sys.argv[3])
def until(predicate):
    end=time.monotonic()+15
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.05)
    raise RuntimeError('bounded contact condition failed')
with tempfile.TemporaryDirectory(prefix='harbor-r17-partial-card-') as temporary:
    root=Path(temporary);flag=root/'fail-contact-sync'
    os.environ.update(LD_PRELOAD=str(shim),HARBOR_E2E_FAIL_CONTACT_FSYNC=str(flag))
    try:a=p.Peer(binary,root,'alice')
    finally:
        os.environ.pop('LD_PRELOAD',None);os.environ.pop('HARBOR_E2E_FAIL_CONTACT_FSYNC',None)
    b=p.Peer(binary,root,'bob');l=p.Peer(binary,root,'laptop');running=[a,b,l]
    try:
        identities=[]
        for peer in (a,b):
            p.start_identity(peer);peer.send(dict(op='device.initialize',request='init',nickname=peer.name))
            identities.append(peer.wait(p.event_is('devices',request='init'),15))
        own,bob=identities;p.start_identity(l)
        l.send(dict(op='device.propose',request='proposal'));proposal=l.wait(p.event_is('devices',request='proposal'),15)
        b.send(dict(op='device.authorize',request='authorize',payload=proposal['proposal'],text=c.consent(l,bob['person']),nickname='Laptop',accept=True))
        extended=b.wait(p.event_is('devices',request='authorize'),15)
        b.stop();l.stop()
        def read_name():
            matches=list(a.home.rglob(bob['person']+'.name'))
            return matches[0].read_text() if matches else None
        def publish(name,roster,request):
            body='HPC1|'+name.encode().hex()+'|'+roster
            identifier=hashlib.sha256((own['local']+own['person']+body).encode()).hexdigest()[:32]
            mark=a.mark();a.send(dict(op='sync.publish',request=request,id=identifier,conversation='d:'+bob['person'],kind='contact',text=body))
            result=a.wait(lambda e:e.get('request')==request and e.get('event') in ('sync.state','sync.error'),15,mark)
            return result,identifier
        first,old_id=publish('Original Bob',bob['roster'],'old')
        assert first['event']=='sync.state'
        until(lambda:read_name()=='Original Bob')
        time.sleep(.3)
        flag.touch()
        newer,new_id=publish('Renamed Bob',extended['roster'],'new')
        assert newer['event']=='sync.error',newer['event']
        after_failed_install=read_name()
        a.stop();flag.unlink();cards=list(a.home.rglob(bob['person']+'.name'));assert len(cards)==1;cards[0].with_name(bob['person']).write_bytes(bytes.fromhex(extended['roster']))
        a=p.Peer(binary,root,'alice');running.append(a);p.start_identity(a)
        until(lambda:read_name()=='Renamed Bob')
        after_restart=read_name()
        with sqlite3.connect((a.home/'sync/journal.sqlite').as_uri()+'?mode=ro',uri=True) as connection:
            rows=connection.execute("SELECT id,clock,wire FROM events WHERE kind='contact' ORDER BY clock,author,id").fetchall()
            contacts=[dict(id=i,clock=clock,name=bytes(wire).decode().split('\n',1)[1].split('|')[1]) for i,clock,wire in rows]
        result=dict(probe='r17-native-after-roster-before-name-crash-fixture',helper_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                    shim_sha256=hashlib.sha256(shim.read_bytes()).hexdigest(),runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    runner_bundle=runner.name,new_event_id=new_id,new_event_result=newer['event'],after_failed_install=after_failed_install,
                    after_restart=after_restart,expected='Renamed Bob',retained_latest_name=after_restart=='Renamed Bob',
                    contact_events=contacts,fixture='after-stop set only public contact roster to signed extended chain; retain old name and durable new journal event')
        assert result['retained_latest_name'] and len(contacts)==2,result
        receipt.write_text(json.dumps(result,indent=2)+'\n')
        print('r17 partial-card observation:',after_restart,flush=True)
    finally:
        for peer in running:peer.stop()
