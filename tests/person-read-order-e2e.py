#!/usr/bin/env python3
"""Native receive-order probe, no application/source edits.
Failure scenario declared before probe execution:
an authenticated read arrives before its referenced message; when that message
arrives, already displayed preceding rows stay stale while history says read.
Three freshly generated identities; production receiver, frozen injector sibling,
production foreign person. Synthetic valid immutable events use the test-only
encrypted sync.inject path; this controls delivery order, not natural scheduling.
"""
import hashlib, importlib.util, json, sys, tempfile, time
from pathlib import Path
spec_journal=importlib.util.spec_from_file_location('journal_fixture',Path(__file__).with_name('journal-fixture.py'))
journal=importlib.util.module_from_spec(spec_journal);spec_journal.loader.exec_module(journal)
B=Path('/build')
R=Path(__file__).resolve().parent
def load(name):
 s=importlib.util.spec_from_file_location(name,R/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
p=load('group-admin-e2e'); c=load('device-consent-fixture')
prod=Path(sys.argv[1]).resolve()
fault=Path(sys.argv[2]).resolve()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def ask(peer,op,**fields):
 mark=peer.mark(); request='r12-'+str(mark)
 peer.send(dict(op=op,request=request,**fields))
 e=peer.wait(lambda e:e.get('request')==request and e.get('event') in ('devices','devices.error'),15,mark)
 assert e['event']=='devices',e
 return e
result={'suite':'native-r12-read-before-reference','production_sha256':sha(prod),'injector_sha256':sha(fault),'runner_sha256':sha(Path(__file__)),'controlled_delivery':True}
with tempfile.TemporaryDirectory(prefix='harbor-r12-order-') as tmp:
 root=Path(tmp);a=p.Peer(prod,root,'receiver');s=p.Peer(fault,root,'sibling');b=p.Peer(prod,root,'bob');running=[a,s,b]
 try:
  ak=p.start_identity(a);sk=p.start_identity(s);bk=p.start_identity(b)
  alice=ask(a,'device.initialize',nickname='Alice'); proposal=ask(s,'device.propose')
  roster=ask(a,'device.authorize',payload=proposal['proposal'],text=c.consent(s,alice['person']),nickname='Sibling',accept=True)
  ask(s,'device.adopt',key=alice['person'],text=roster['roster'],accept=True)
  bob=ask(b,'device.initialize',nickname='Bob')
  p.pair(a,b,bk,'r12-order')
  for peer in (a,s):peer.wait(p.event_is('person.info',key=bob['person']),180)
  s.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==ak and e.get('online'),180)
  a.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==sk and e.get('online'),180)
  b.stop()
  print('native identities established; Bob stopped to exclude repairing delivery ACKs',flush=True)
  own=alice['person'];other=bob['person'];author=proposal['local'];bobauthor=bob['local']
  def event(clock,person,author,target,kind,body):
   clock=f'{clock:016x}';route='p:'+target
   pre='Harbor-event-v1|'+clock+'|'+person+'|'+author+'|'+route+'|'+kind+chr(10)+body
   mid=hashlib.sha256(pre.encode()).digest()[:16].hex()
   wire='HS2|'+mid+'|'+clock+'|'+person+'|'+author+'|'+route+'|'+kind+chr(10)+body
   return mid,wire
  stamp=f'{int(time.time()):016x}'
  m1,w1=event(10000,own,author,other,'message',f'HM2|{own}|{other}|-|fixture-m1|{stamp}'+chr(10)+'first row')
  m2,w2=event(10001,own,author,other,'message',f'HM2|{own}|{other}|-|fixture-m2|{stamp}'+chr(10)+'reference row')
  read,wr=event(10002,other,bobauthor,own,'read',f'HA1|{other}|{own}|{own}|{m2}|fixture-read'+chr(10))
  def inject(mid,wire):
   mark=s.mark();s.send(dict(op='sync.inject',request='inject-'+mid,id=mid,key=ak,text=wire))
   s.wait(p.event_is('sync.injected',id=mid),15,mark)
  inject(m1,w1);initial=a.wait(p.event_is('message',id=m1),60)
  mark=a.mark()
  inject(read,wr)
  deadline=time.monotonic()+60
  while journal.get(a,read) is None and time.monotonic()<deadline:time.sleep(.1)
  assert journal.get(a,read)==wr.encode()
  time.sleep(.3)
  assert journal.get(a,m2) is None
  inject(m2,w2);reference=a.wait(p.event_is('message',id=m2),60,mark)
  time.sleep(6)
  updates=[{k:e[k] for k in ('event','id','state','request') if k in e} for e in a.events[mark:] if e.get('id') in (m1,m2) and e.get('event') in ('message','message.updated','receipt')]
  hmark=a.mark();a.send(dict(op='history',conversation='p:'+other,key=other,id='r12-order-history'))
  history=a.wait(p.event_is('history',request='r12-order-history'),15,hmark)
  rows={row['id']:row for row in history['items']}
  result.update(initial_state=initial['state'],reference_arrival_state=reference['state'],live_projection_events=updates,history_states=[rows[x]['state'] for x in (m1,m2)])
  result['defect_reproduced']=rows[m1]['state']=='read' and not any(e.get('id')==m1 and e.get('state')=='read' for e in updates)
  assert not result['defect_reproduced'],result
  assert all(rows[x]['state']=='read' for x in (m1,m2))
  assert any(e.get('id')==m1 and e.get('state')=='read' for e in updates),updates
  assert sha(prod)==result['production_sha256'] and sha(fault)==result['injector_sha256']
  Path(sys.argv[3]).write_text(json.dumps(result,indent=2)+chr(10))
  print(json.dumps(result,indent=2),flush=True)
 finally:
  for peer in running:peer.stop()
