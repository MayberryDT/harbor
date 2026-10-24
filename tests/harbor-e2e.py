#!/usr/bin/env python3
"""Real TCP-relay peers: large Unicode text, history, files, and images.

Failure cases: IPC truncation/escaping; transport fragmentation/backpressure;
UTF-8 boundaries; wrong-peer assembly; ratchet envelope overflow; history loss;
oversized rejection; file offer cap; streamed-byte corruption; image validation.
The receipt contains hashes and sizes, never identity or message content.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

spec = importlib.util.spec_from_file_location('native_peers', Path(__file__).with_name('group-admin-e2e.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
start_identity, pair, event_is = module.start_identity, module.pair, module.event_is
class Peer(module.Peer):
    def send(self, operation):
        if self.process.poll() is not None:
            raise RuntimeError(f"{self.name}: helper exited {self.process.returncode}")
        self.process.stdin.write(json.dumps(operation,ensure_ascii=False,separators=(",",":"))+"\n")
        self.process.stdin.flush()
    def wait(self,*args,**kwargs):
        try: return super().wait(*args,**kwargs)
        except RuntimeError as error:
            raise RuntimeError(str(error).split('; events=')[0]) from None


binary = Path(sys.argv[1]).resolve()
receipt = Path(sys.argv[2]).resolve()
root = Path(tempfile.mkdtemp(prefix='harbor-e2e-'))
source_binary=binary
binary=root/'harbor-helper'
shutil.copy2(source_binary,binary)
peers = []
results = []
def digest(data):
    return hashlib.sha256(data).hexdigest()
def check_text(a, b, key, text, label, conv='0'):
    mark = b.mark()
    a.send(dict(op='msg.send', conversation=conv, key=key, text=text, id=label))
    if label == 'direct-64k':
        shutdown_mark=a.mark()
        a.send(dict(op='helper.shutdown_if_no_groups',id=a.instance,request='harbor-pending-shutdown'))
        a.wait(event_is('helper.shutdown_blocked',reason='pending_messages'),15,shutdown_mark,'queued shutdown protection')
        results.append(dict(check='pending-send-blocks-shutdown'))
    event = b.wait(lambda e: e.get('event') == 'message' and e.get('dir') == 'in' and e.get('text') == text,
                   180, mark, label)
    results.append(dict(check=label, bytes=len(text.encode()), sha256=digest(text.encode())))
    return event
try:
    a, b = Peer(binary, root, 'port'), Peer(binary, root, 'starboard')
    peers = [a,b]
    ak, bk = start_identity(a), start_identity(b)
    print('pairing', flush=True)
    friend = pair(a,b,bk,'harbor')
    conv = str(friend['id'])
    check_text(a,b,bk,'Harbor secure-session warmup','warmup',conv)
    text = ('航海 ⚓ café "quoted" \\ slash\n\t' * 3000).encode()[:65536]
    while True:
        try: text = text.decode(); break
        except UnicodeDecodeError: text = text[:-1]
    # Fill to the exact byte boundary with ASCII.
    text += 'x' * (65536-len(text.encode()))
    print('64 KiB encrypted Unicode', flush=True)
    message = check_text(a,b,bk,text,'direct-64k',conv)
    mark = b.mark()
    b.send(dict(op='history', conversation='0', key=ak, limit=10, id='harbor-history'))
    history = b.wait(lambda e: e.get('event') == 'history' and any(i.get('text') == text for i in e.get('items',[])),30,mark,'large history')
    results.append(dict(check='history-64k', sha256=digest(text.encode())))
    mark=b.mark()
    edited='Edited: '+text[8:]
    a.send(dict(op='message.edit',conversation=conv,key=bk,id=message['id'],text=edited))
    b.wait(event_is('message.updated',id=message['id'],text=edited),180,mark,'64 KiB edit')
    results.append(dict(check='large-edit',bytes=len(edited.encode()),sha256=digest(edited.encode())))
    mark=b.mark()
    b.send(dict(op='search',conversation='0',key=ak,text='Edited:',limit=20,id='harbor-search'))
    b.wait(lambda e:e.get('event')=='search' and any(i.get('text')==edited for i in e.get('items',[])),30,mark,'large search')
    results.append(dict(check='large-search'))
    print('group join',flush=True)
    a.send(dict(op='group.create',title='Harbor test fleet'))
    created=a.wait(event_is('group.changed',action='create'),15,description='group creation')
    gid=created['group'];mark=b.mark()
    a.send(dict(op='invite.create',kind='group',group=gid,role='member',id=conv,key=bk,request='gi-harbor-group',ttlSec=86400))
    b.wait(event_is('request',kind='group'),60,mark,'group invitation')
    b.send(dict(op='contact.decide',accept=True))
    a.wait(lambda e:e.get('event')=='group.member' and e.get('group')==gid and e.get('friendKey')==bk,180,description='group member binding')
    print('64 KiB group Unicode',flush=True)
    check_text(a,b,'',text,'group-64k',gid)
    # Exact cap and oversized rejection are checked through the real parser.
    mark = a.mark()
    a.send(dict(op='msg.send',conversation=conv,key=bk,text='x'*65537,id='too-large'))
    a.wait(lambda e: e.get('event') in ('error','message.failed'), 10, mark, 'oversize rejection')
    results.append(dict(check='oversize-rejected',bytes=65537))
    for kind,name,data in [('file','cargo.bin',os.urandom(12*1024*1024)),
                           ('image','chart.png',None)]:
        if data is None:
            # A valid PNG above the old 8 MiB cap, with incompressible RGB pixels.
            import struct,zlib
            def chunk(t,d): return struct.pack('!I',len(d))+t+d+struct.pack('!I',zlib.crc32(t+d)&0xffffffff)
            w,h=3840,2160
            pixels=b''.join(b'\0'+os.urandom(w*3) for _ in range(h))
            data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(pixels,1))+chunk(b'IEND',b'')
        source=root/name; source.write_bytes(data)
        mark=b.mark()
        print('send',kind,len(data),flush=True)
        a.send(dict(op='file.send',conversation=conv,key=bk,path=str(source),kind=kind,id='cargo-'+kind))
        offer=b.wait(event_is('file.offer'),60,mark,'large '+kind+' offer')
        b.send(dict(op='file.accept',conversation='0',key=ak,id=offer['id']))
        done=b.wait(event_is('file.done',dir='in'),300,mark,'large '+kind+' completion')
        received=Path(done['path']).read_bytes()
        if kind == 'image':
            # Compare decoded RGB pixels independently; receiver normalizes PNG encoding.
            from PIL import Image
            import io
            original=Image.open(io.BytesIO(data)).convert('RGB')
            actual=Image.open(io.BytesIO(received)).convert('RGB')
            assert original.size == actual.size and original.tobytes() == actual.tobytes(), 'image pixels mismatch'
        else:
            assert received==data, 'file content mismatch'
        a.wait(event_is('file.done',dir='out'),30,description='sender completion')
        results.append(dict(check=kind+'-over-8mib',bytes=len(data),sha256=digest(received)))
    receipt.parent.mkdir(parents=True,exist_ok=True)
    receipt.write_text(json.dumps(dict(passed=True,binary_sha256=digest(binary.read_bytes()),checks=results),indent=2)+'\n')
    print('PASS',receipt,flush=True)
finally:
    if sys.exc_info()[0]:
        receipt.parent.mkdir(parents=True,exist_ok=True)
        receipt.write_text(json.dumps(dict(passed=False,checks=results,errors=[
            dict(peer=p.name,events=[{k:e[k] for k in ('event','code','request','action') if k in e}
                 for e in p.events[-15:]]) for p in peers]),indent=2)+'\n')
    for peer in peers: peer.stop()
    shutil.rmtree(root)
