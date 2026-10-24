"""Native revocation failures: retained pins must not authorize a revoked sender;
local revocation must reject business egress; legacy unlinked channels still work.
Uses disposable real Signal/Tox helpers and writes a hashed receipt."""
import hashlib,importlib.util,json,tempfile,time,signal,sys
from pathlib import Path
base=Path('/build')
runners=Path(__file__).resolve().parent
def load(name):
 s=importlib.util.spec_from_file_location(name,runners/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
p=load('group-admin-e2e');c=load('device-consent-fixture')
binary=Path(sys.argv[1]).resolve()
checks={}
with tempfile.TemporaryDirectory(prefix='harbor-review-revocation-') as tmp:
 root=Path(tmp);a=p.Peer(binary,root,'owner');b=p.Peer(binary,root,'revoked');running=[a,b]
 def ask(peer,op,**fields):
  mark=peer.mark();req='review-'+str(mark);peer.send({'op':op,'request':req,**fields})
  e=peer.wait(lambda e:e.get('request')==req and e.get('event') in ('devices','devices.error'),15,mark)
  assert e['event']=='devices',e
  return e
 try:
  ak=p.start_identity(a);bk=p.start_identity(b)
  owner=ask(a,'device.initialize',nickname='Owner');proposed=ask(b,'device.propose')
  roster=ask(a,'device.authorize',payload=proposed['proposal'],text=c.consent(b,owner['person']),nickname='Other',accept=True)
  ask(b,'device.adopt',key=owner['person'],text=roster['roster'],accept=True)
  af=a.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==bk and e.get('online'),180)
  bf=b.wait(lambda e:e.get('event')=='friend.info' and e.get('key')==ak and e.get('online'),180)
  b.send({'op':'msg.send','id':'warmup','conversation':str(bf['id']),'key':ak,'text':'review pre-revocation control'})
  a.wait(p.event_is('message',text='review pre-revocation control',dir='in'),90)
  print('native pinned channel established',flush=True)
  old_roster=(b.home/'devices/roster').read_bytes()
  revoked=ask(a,'device.revoke',key=proposed['local'],accept=True)
  b.wait(lambda e:e.get('event')=='device.roster' and e.get('active') is False,90)
  assert ask(b,'device.status')['active'] is False
  assert ask(a,'device.status')['sequence']==revoked['sequence']
  mark=a.mark()
  b.send({'op':'msg.send','id':'revoked-legacy','conversation':str(bf['id']),'key':ak,'text':'review message after learned revocation'})
  denied=b.wait(lambda e:e.get('event')=='message.failed' and e.get('request')=='revoked-legacy',30)
  time.sleep(3)
  assert not any(e.get('event')=='message' and e.get('text')=='review message after learned revocation' for e in a.events[mark:])
  assert ask(a,'device.status')['active'] is True
  # A revoked machine controls its own old public roster and may run hostile
  # software. Inject through its actual Signal/Tox channel, bypassing UI policy.
  a.process.send_signal(signal.SIGSTOP)
  (b.home/'devices/roster').write_bytes(old_roster)
  divergent=ask(b,'device.revoke',key=owner['local'],accept=True)
  attackmark=a.mark()
  for index,plain in enumerate(('OQM1|revoked-injected|-|hostile retained-key message',
                              'HD1|update|'+owner['person']+'|'+divergent['roster'])):
   injected=('%032x' % (index+1))
   b.send({'op':'sync.inject','request':'hostile-'+str(index),'id':injected,
           'key':ak,'kind':'legacy','text':plain})
   b.wait(p.event_is('sync.injected',id=injected),15)
  a.process.send_signal(signal.SIGCONT)
  # A transport delivery interval plus status and restart prove no fork marker.
  time.sleep(8)
  assert not any(e.get('event')=='message' and e.get('text')=='hostile retained-key message' for e in a.events[attackmark:])
  assert ask(a,'device.status')['active'] is True
  assert not (a.home/'devices/fork').exists()
  a.stop();a=p.Peer(binary,root,'owner');running.append(a);p.start_identity(a)
  assert ask(a,'device.status')['active'] is True
  checks['retained_key_legacy_and_roster_attack_rejected']=True
  checks['revoked_legacy_egress_rejected']=True
  checks['no_legacy_delivery_after_revocation']=True
  receipt={'suite':'native-legacy-revocation','helper_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
   'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'passed':checks}
  Path(sys.argv[2]).write_text(json.dumps(receipt,indent=2)+'\n')
  print('legacy-revocation-e2e: pass',flush=True)
 finally:
  for peer in running:peer.stop()
