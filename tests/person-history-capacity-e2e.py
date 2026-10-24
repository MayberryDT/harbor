#!/usr/bin/env python3
"""Native storage failures specified before replacing prototype capacity/scans:
4096-event exhaustion; maximum escaped text exceeds stdout framing; history pages
skip/duplicate rows; request retry allocates another event; restart loses history.
Disposable native helpers only. Receipt records executable and runner hashes.
"""
import hashlib, importlib.util, json, sys, tempfile, time
from pathlib import Path
spec=importlib.util.spec_from_file_location('peers',Path(__file__).with_name('group-admin-e2e.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
binary=Path(sys.argv[1]).resolve();receipt=Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory(prefix='harbor-history-capacity-') as tmp:
    root=Path(tmp);a=p.Peer(binary,root,'alice');b=p.Peer(binary,root,'bob');running=[a,b]
    try:
        ak=p.start_identity(a);bk=p.start_identity(b)
        identities=[]
        for peer in (a,b):
            peer.send({'op':'device.initialize','request':'initialize','nickname':peer.name})
            identities.append(peer.wait(p.event_is('devices',request='initialize'),15))
        other=identities[1]['person']
        p.pair(a,b,bk,'history-capacity')
        a.wait(p.event_is('person.info',key=other),180)
        b.stop()
        accepted=[];began=time.monotonic()
        # Beyond the old global journal ceiling, plus three maximally escaped
        # messages whose combined history cannot fit one stdout event.
        for index in range(4100):
            text=('\t'*65536) if index>=4097 else 'Stored message '+str(index)
            request='capacity-'+str(index);mark=a.mark()
            a.send({'op':'msg.send','conversation':'p:'+other,'key':other,'id':request,'text':text})
            result=a.wait(lambda e:e.get('request')==request and e.get('event') in ('message','message.failed'),30,mark)
            assert result['event']=='message',result
            accepted.append(result['id'])
            if index%100==0:print('published',index,'elapsed',round(time.monotonic()-began,2),flush=True)
        elapsed=time.monotonic()-began
        a.stop();a=p.Peer(binary,root,'alice');running.append(a);p.start_identity(a)
        mark=a.mark();a.send({'op':'history','conversation':'p:'+other,'key':other,'id':'invalid-page','payload':'f'*32})
        a.wait(p.event_is('history.failed',request='invalid-page',code='history_cursor_invalid'),30,mark)
        seen=[];cursor=''
        while True:
            request='page-'+str(len(seen));mark=a.mark()
            a.send({'op':'history','conversation':'p:'+other,'key':other,'id':request,'payload':cursor,'limit':100})
            page=a.wait(p.event_is('history',request=request),30,mark)
            assert page['items'],'empty page cannot advance history'
            assert len(json.dumps(page,ensure_ascii=False).encode())<400000,'history exceeds framing budget'
            ids=[row['id'] for row in page['items']]
            assert not set(ids)&set(seen),'duplicate page rows'
            seen=ids+seen;cursor=ids[0]
            if not page['hasMore']:break
        assert seen==accepted,'history omitted or reordered messages'
        for index in (0,4099):
            request='capacity-'+str(index);text=('\t'*65536) if index>=4097 else 'Stored message '+str(index)
            mark=a.mark();a.send({'op':'msg.send','conversation':'p:'+other,'key':other,'id':request,'text':text})
            retried=a.wait(p.event_is('message',request=request),30,mark)
            assert retried['id']==accepted[index],'retry changed immutable ID'
        receipt.write_text(json.dumps({'suite':'native-person-history-capacity',
            'helper_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
            'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'messages':len(accepted),'publication_seconds':elapsed,
            'passed':['beyond-prototype-capacity','escaped-message-framing','all-pages-after-restart','stable-retry-IDs']},indent=2)+'\n')
        print('person-history-capacity-e2e: pass',flush=True)
    finally:
        for peer in running:peer.stop()
