"""Independent R11 native regression probes, output only under /build.
Failure scenarios declared before execution:
- unlinked, pinned legacy messaging stops working;
- anchor read error is misclassified as absence and permits business traffic;
- survivor cannot read/clear pre-existing local history after contact revocation;
- learned-local-revoked device still sends a fresh avatar to legacy contact.
- in-flight chunks/audio continue after membership is unavailable/revoked;
  explicit local cancellation/termination must remain available.
  Audio requires the later native call acceptance journey.
All identities and state are newly generated disposable fixtures.
"""
import hashlib,importlib.util,json,struct,sys,tempfile,time,zlib
from pathlib import Path
BUILD=Path('/build'); RUN=Path(__file__).resolve().parent
def load(name):
 s=importlib.util.spec_from_file_location(name,RUN/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
p=load('group-admin-e2e');c=load('device-consent-fixture')
binary=Path(sys.argv[1]).resolve()
results={}
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def png():
 def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',4,4,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x12\xab\x34'*4)*4))+chunk(b'IEND',b'')
with tempfile.TemporaryDirectory(prefix='harbor-r11-') as tmp:
 root=Path(tmp);a=p.Peer(binary,root,'owner');b=p.Peer(binary,root,'linked');u=p.Peer(binary,root,'legacy');running=[a,b,u]
 def ask(peer,op,**fields):
  mark=peer.mark();req='r11-'+str(mark);peer.send(dict(op=op,request=req,**fields))
  e=peer.wait(lambda e:e.get('request')==req and e.get('event') in ('devices','devices.error'),15,mark)
  assert e['event']=='devices',e
  return e
 try:
  ak=p.start_identity(a);bk=p.start_identity(b);uk=p.start_identity(u)
  bu=p.pair(b,u,uk,'r11-unlinked')
  ub=u.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==bk and e.get('online'),180)
  b.send(dict(op='msg.send',id='r11-legacy-warmup',conversation=str(bu['id']),key=uk,text='r11 unlinked legacy control'))
  u.wait(p.event_is('message',dir='in',text='r11 unlinked legacy control'),90)
  results['unlinked_legacy_message_delivered']=True
  # Existing unreadable anchor is authority error, not unmanaged fallback.
  anchor=b.home/'endpoint-anchors'/uk
  anchor.symlink_to(root/'nonexistent-anchor-target')
  mark=b.mark();b.send(dict(op='msg.send',id='r11-authority-error',conversation=str(bu['id']),key=uk,text='must reject anchor read error'))
  e=b.wait(p.event_is('message.failed',request='r11-authority-error'),15,mark)
  results['anchor_read_error_rejected']=e['code'];anchor.unlink()
  print('legacy compatibility and anchor read error controls passed',flush=True)
  owner=ask(a,'device.initialize',nickname='Owner');other=ask(b,'device.propose')
  roster=ask(a,'device.authorize',payload=other['proposal'],text=c.consent(b,owner['person']),nickname='Linked',accept=True)
  ask(b,'device.adopt',key=owner['person'],text=roster['roster'],accept=True)
  af=a.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==bk and e.get('online'),180)
  bf=b.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==ak and e.get('online'),180)
  b.send(dict(op='msg.send',id='r11-roster-warmup',conversation=str(bf['id']),key=ak,text='r11 existing local history'))
  a.wait(p.event_is('message',dir='in',text='r11 existing local history'),90)
  mark=a.mark();a.send(dict(op='history',id='r11-history-before',conversation=str(af['id']),key=bk))
  before=a.wait(lambda e:e.get('event') in ('history','history.failed'),15,mark)
  assert before['event']=='history',before
  results['local_history_before_revocation_readable']=True
  data=root/'pending-transfer.bin';data.write_bytes(b'r11 post-revocation private bytes' * 32768);data.chmod(0o600)
  mark=u.mark();b.send(dict(op='file.send',id='r11-pending-transfer',conversation=str(bu['id']),key=uk,path=str(data)))
  offer=u.wait(lambda e:e.get('event')=='file.offer',45,mark)
  results['file_offer_admitted_before_revocation']=True
  ask(a,'device.revoke',key=other['local'],accept=True)
  b.wait(lambda e:e.get('event')=='device.roster' and e.get('active') is False,90)
  assert ask(b,'device.status')['active'] is False
  mark=a.mark();a.send(dict(op='history',id='r11-history-after',conversation=str(af['id']),key=bk))
  after=a.wait(lambda e:e.get('event') in ('history','history.failed'),15,mark)
  assert after['event']=='history',after
  results['local_history_after_revocation_event']=after['event']
  mark=a.mark();a.send(dict(op='history.clear',id='r11-clear-after',conversation=str(af['id']),key=bk))
  clear=a.wait(lambda e:e.get('event') in ('history.clear.succeeded','history.cleared','history.clear.failed','history.clear.result','error'),15,mark)
  assert clear['event'] in ('history.clear.succeeded','history.cleared'),clear
  results['local_history_clear_after_revocation']={k:clear[k] for k in ('event','code') if k in clear}
  mark=u.mark();u.send(dict(op='file.accept',id=offer['id'],conversation=str(ub['id']),key=bk))
  stopped=u.wait(lambda e:e.get('event') in ('file.failed','file.canceled') and e.get('id')==offer['id'],60,mark)
  assert not any(e.get('event')=='file.done' and e.get('id')==offer['id'] for e in u.events[mark:])
  results['offered_file_stopped_after_revocation']=True
  image=root/'new-avatar.png';image.write_bytes(png());image.chmod(0o600)
  mark=u.mark();b.send(dict(op='avatar.set',path=str(image)))
  b.wait(p.event_is('avatar',id='self'),15)
  time.sleep(8)
  assert not any(e.get('event')=='avatar' and e.get('id')==str(ub['id']) and e.get('path') for e in u.events[mark:])
  assert ask(b,'device.status')['active'] is False
  results['fresh_avatar_not_transmitted']=True
  Path(sys.argv[2]).write_text(json.dumps(dict(suite='native-revocation-io',helper_sha256=digest(binary),runner_sha256=digest(Path(__file__)),passed=results),indent=2)+'\n')
  print('revocation-io-e2e: pass',flush=True)

 finally:
  for peer in running:peer.stop()
