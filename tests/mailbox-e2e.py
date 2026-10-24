#!/usr/bin/env python3
"""Real HTTP service + SQLite restart E2E, written before service implementation.
Failure cases: unauthorized write/read/grant, oversized or mismatched body, mixed
sender collision, duplicate admission at capacity, nondestructive fetch, restart
loss, credential plaintext in DB, ACK-before-fetch, writer revocation and quota.
This verifies opaque storage, not native encryption or mailbox-client integration.
"""
import hashlib
import http.client
import json
import secrets
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

server=Path(sys.argv[1]).resolve();receipt=Path(sys.argv[2]).resolve()
recipient='12'*32;sender='34'*32;other='56'*32
with tempfile.TemporaryDirectory(prefix='harbor-mailbox-e2e-') as temporary:
    root=Path(temporary);data=root/'mailbox';credentials=root/'reader.json'
    subprocess.run([sys.executable,str(server),'init','--data',str(data),'--recipient',recipient,'--credentials',str(credentials)],check=True,capture_output=True)
    reader=json.loads(credentials.read_text())['token']
    original=credentials.read_bytes()
    # Emulate the durable-file / uncommitted-database crash boundary.
    with sqlite3.connect(data/'mailbox.sqlite3') as db:
        db.execute('DELETE FROM recipients WHERE id=?',(recipient,));db.commit()
    subprocess.run([sys.executable,str(server),'init','--data',str(data),'--recipient',recipient,'--credentials',str(credentials)],check=True,capture_output=True)
    assert credentials.read_bytes()==original
    subprocess.run([sys.executable,str(server),'init','--data',str(data),'--recipient',recipient,'--credentials',str(credentials)],check=True,capture_output=True)
    assert credentials.read_bytes()==original
    process=None
    def start():
        global process
        process=subprocess.Popen([sys.executable,str(server),'serve','--data',str(data),'--port','0','--max-messages','2'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        ready=json.loads(process.stdout.readline());assert ready['event']=='ready',ready
        return ready['port']
    port=start()
    def call(method,path,token=None,body=b''):
        conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
        headers={'Content-Length':str(len(body))}
        if token:headers['Authorization']='Bearer '+token
        conn.request(method,path,body=body,headers=headers)
        response=conn.getresponse();payload=response.read();status=response.status;conn.close()
        return status,payload
    base='/v1/'+recipient
    try:
        assert call('GET',base+'/messages')[0]==403
        assert call('PUT',base+'/writers/'+sender,'bad')[0]==403
        status,payload=call('PUT',base+'/writers/'+sender,reader)
        assert status==201
        writer=json.loads(payload)['token']
        assert call('GET',base+'/messages',writer)[0]==403
        opaque=secrets.token_bytes(1536);identifier=hashlib.sha256(opaque).hexdigest()
        path=base+'/messages/'+sender+'/'+identifier
        assert call('PUT',path,reader,opaque)[0]==403
        assert call('PUT',path,writer,opaque)[0]==201
        assert call('PUT',path,writer,opaque)[0]==200
        assert call('PUT',path,writer,b'changed')[0]==400
        assert call('PUT',base+'/messages/'+other+'/'+identifier,writer,opaque)[0]==403
        status,listing=call('GET',base+'/messages',reader)
        assert status==200 and len(json.loads(listing)['items'])==1
        fetched=call('GET',base+'/messages/'+identifier,reader)
        assert fetched==(200,opaque)
        assert len(json.loads(call('GET',base+'/messages',reader)[1])['items'])==1
        second=secrets.token_bytes(32);second_id=hashlib.sha256(second).hexdigest()
        assert call('PUT',base+'/messages/'+sender+'/'+second_id,writer,second)[0]==201
        third=secrets.token_bytes(32);third_id=hashlib.sha256(third).hexdigest()
        third_path=base+'/messages/'+sender+'/'+third_id
        assert call('PUT',third_path,writer,third)[0]==429
        assert call('PUT',path,writer,opaque)[0]==200,'exact retry remains valid at capacity'
        huge=b'x'*(134000+1)
        assert call('PUT',base+'/messages/'+sender+'/'+hashlib.sha256(huge).hexdigest(),writer,huge)[0]==413
        process.terminate();process.wait(timeout=5);port=start()
        assert call('GET',base+'/messages/'+identifier,reader)==(200,opaque)
        assert call('DELETE',base+'/messages/'+identifier,reader)[0]==204
        assert call('GET',base+'/messages/'+identifier,reader)[0]==404
        assert call('PUT',third_path,writer,third)[0]==201
        assert call('DELETE',base+'/writers/'+sender,reader)[0]==204
        assert call('PUT',third_path,writer,third)[0]==403
        for index in range(64):
            extra=f'{1000+index:064x}'
            status,_=call('PUT',base+'/writers/'+extra,reader)
            assert status==201,(index,status)
        assert call('PUT',base+'/writers/'+f'{2000:064x}',reader)[0]==429
        with sqlite3.connect(data/'mailbox.sqlite3') as db:
            expiration=db.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
            assert expiration==2
            # Simulate time passing at the storage boundary without waiting days.
            db.execute('UPDATE messages SET expires=0');db.commit()
        assert json.loads(call('GET',base+'/messages',reader)[1])['items']==[]
        database=(data/'mailbox.sqlite3').read_bytes()
        assert reader.encode() not in database and writer.encode() not in database
        receipt.write_text(json.dumps({'suite':'opaque-mailbox-http-storage','payload_sha256':identifier,
            'passed':['separate-read-write-capabilities','authenticated-writer-grant','immutable-idempotent-storage',
                      'hash-size-validation','non-destructive-fetch','quota-and-retry-at-capacity','restart-persistence',
                      'recipient-ack-removal','writer-revocation','expiry','hashed-credentials','credential-initialization-resume','writer-grant-capacity'],
            'scope':'localhost HTTP/storage; TLS deployment and native client integration unverified'},indent=2)+'\n')
        print('mailbox-e2e: pass',flush=True)
    finally:
        if process and process.poll() is None:process.terminate();process.wait(timeout=5)
