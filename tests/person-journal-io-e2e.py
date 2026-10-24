#!/usr/bin/env python3
"""Native send/history under real sync failures and a mid-query SQLite error.
Failures: acknowledge retry without durable directory entry; emit successful
incomplete history after a mid-query failure. Only disposable journal storage is faulted.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
spec=importlib.util.spec_from_file_location('peers',Path(__file__).with_name('group-admin-e2e.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
binary=Path(sys.argv[1]).resolve();shim=Path(sys.argv[2]).resolve();receipt=Path(sys.argv[3]).resolve()
expected=hashlib.sha256(binary.read_bytes()).hexdigest()
fault=Path(sys.argv[4]).resolve() if len(sys.argv)>4 else None
fault_sha=hashlib.sha256(fault.read_bytes()).hexdigest() if fault else None
with tempfile.TemporaryDirectory(prefix='harbor-journal-io-') as temporary:
    root=Path(temporary); fail_sync=root/'fail-sync';fail_scan=root/'fail-scan';fail_reread=root/'fail-reread'
    seen=root/'fault-seen';hit_log=root/'sqlite-hits'
    def alice():
        os.environ.update(LD_PRELOAD=str(shim),HARBOR_E2E_FAIL_EVENT_FSYNC=str(fail_sync),HARBOR_E2E_FAIL_EVENT_SCAN=str(fail_scan),HARBOR_SYNC_FAIL_REQUEST_REREAD_FILE=str(fail_reread),HARBOR_E2E_ANCHOR_FAULT_SEEN=str(seen),HARBOR_E2E_SQLITE_FAULT_HITS=str(hit_log))
        try:return p.Peer(fault or binary,root,'alice')
        finally:
            for key in ('LD_PRELOAD','HARBOR_E2E_FAIL_EVENT_FSYNC','HARBOR_E2E_FAIL_EVENT_SCAN','HARBOR_SYNC_FAIL_REQUEST_REREAD_FILE','HARBOR_E2E_ANCHOR_FAULT_SEEN','HARBOR_E2E_SQLITE_FAULT_HITS'):os.environ.pop(key,None)
    a=alice()
    b=p.Peer(binary,root,'bob')
    try:
        ak=p.start_identity(a);bk=p.start_identity(b)
        for peer in (a,b):
            peer.send({'op':'device.initialize','request':'initialize','nickname':peer.name})
            peer.wait(p.event_is('devices',request='initialize'),15)
        b.send({'op':'device.status','request':'bob-root'});bob=b.wait(p.event_is('devices',request='bob-root'),15)['person']
        p.pair(a,b,bk,'journal-io');a.wait(p.event_is('person.info',key=bob),180)
        operation={'op':'msg.send','conversation':'p:'+bob,'key':bob,'id':'durable-retry','request':'durable-retry','text':'Survives a storage sync failure'}
        baseline={}
        for index in range(2):
            request='before-io-'+str(index);text='Retained earlier message '+str(index)
            a.send(dict(op='msg.send',conversation='p:'+bob,key=bob,id=request,text=text))
            item=a.wait(p.event_is('message',request=request,dir='out'),30)
            baseline[item['id']]=text
        fail_sync.touch();hits=[]
        for attempt in range(2):
            marker=a.mark();a.send(operation)
            error=a.wait(lambda e:e.get('event')=='message.failed' and e.get('request')=='durable-retry',15,marker)
            assert not any(e.get('event')=='message' and e.get('request')=='durable-retry' for e in a.events[marker:]),error
            hits=hit_log.read_text().splitlines()
        assert {'sqlite-wal-sync','sqlite-main-sync'}<=set(hits),hits
        a.stop();a=alice()
        marker=a.mark();a.send(operation)
        a.wait(p.event_is('message.failed',request='durable-retry'),30,marker)
        fail_sync.unlink();a.send(operation);sent=a.wait(p.event_is('message',request='durable-retry',dir='out'),15)
        baseline[sent['id']]=operation['text']
        if fault:
            b.wait(p.event_is('message',id=sent['id'],dir='in'),90)
            fail_reread.touch();marker=a.mark();a.send(operation)
            a.wait(p.event_is('message.failed',request='durable-retry',code='message_retry_unavailable'),15,marker)
            fail_reread.unlink();marker=a.mark();a.send(operation)
            a.wait(p.event_is('message',id=sent['id'],request='durable-retry'),15,marker)
            a.send({'op':'history','id':'one-message','conversation':'p:'+bob,'key':bob})
            history=a.wait(p.event_is('history',request='one-message'),15)
            assert {row['id']:row['text'] for row in history['items']}==baseline, 'failed reread duplicated or lost a request'
        fail_scan.touch();marker=a.mark()
        a.send({'op':'history','id':'failed-scan','conversation':'p:'+bob,'key':bob})
        a.wait(lambda e:e.get('event')=='history.failed' and e.get('request')=='failed-scan',15,marker)
        assert not any(e.get('event')=='history' and e.get('request')=='failed-scan' for e in a.events[marker:])
        assert 'sqlite-query-error' in hit_log.read_text().splitlines(),'query fault was not reached'
        fail_scan.unlink();a.send({'op':'history','id':'complete-scan','conversation':'p:'+bob,'key':bob})
        complete=a.wait(p.event_is('history',request='complete-scan'),15)
        assert {row['id']:row['text'] for row in complete['items']}==baseline
        a.stop();a=p.Peer(binary,root,'alice');p.start_identity(a)
        a.send(dict(op='history',id='after-restart',conversation='p:'+bob,key=bob))
        restored=a.wait(p.event_is('history',request='after-restart'),30)
        assert {row['id']:row['text'] for row in restored['items']}==baseline
        mark=a.mark();a.send(operation);a.wait(p.event_is('message',request='durable-retry',id=sent['id']),30,mark)
        assert hashlib.sha256(binary.read_bytes()).hexdigest()==expected
        if fault:assert hashlib.sha256(fault.read_bytes()).hexdigest()==fault_sha
        receipt.write_text(json.dumps({'runner_path':str(Path(__file__).resolve()),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runner_manifest':str(Path(__file__).resolve().parent.parent/'manifest.json'),'suite':'native-person-journal-io','helper_sha256':expected,'shim_sha256':hashlib.sha256(shim.read_bytes()).hexdigest(),'fault_helper_sha256':fault_sha,
            'fault_hits':sorted(set(hit_log.read_text().splitlines())),'passed':['restart-while-sync-fault-active','multirow-history-exact-after-recovery-and-restart','retry-remains-failed-until-storage-sync-succeeds','mid-scan-error-rejects-incomplete-history','history-recovers-after-io-restored']+(['failed-request-reread-never-duplicates'] if fault else [])},indent=2)+'\n')
        print('person-journal-io-e2e: pass',flush=True)
    finally:a.stop();b.stop()
