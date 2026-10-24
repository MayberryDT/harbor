"""Review fixture: isolate HD1 authorization from native relay delivery races.
Failure cases: known-revoked exact Tox/Signal sender mutates authority; fixing it
must preserve valid concurrent fork detection through a still-active sender.
No application source edits; independent helper identities remain disposable."""
import hashlib,importlib.util,json,subprocess,tempfile,sys
from pathlib import Path
base=Path('/build')
runners=Path(__file__).resolve().parent
def load(name):
 s=importlib.util.spec_from_file_location(name,runners/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
p=load('group-admin-e2e');c=load('device-consent-fixture')
binary=Path(sys.argv[1]).resolve()
driver=Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory(prefix='harbor-review-hd1-') as tmp:
 root=Path(tmp);a=p.Peer(binary,root,'owner');b=p.Peer(binary,root,'other');third=p.Peer(binary,root,'third');running=[a,b,third]
 def ask(peer,op,**fields):
  mark=peer.mark();req='boundary-'+str(mark);peer.send({'op':op,'request':req,**fields})
  e=peer.wait(lambda e:e.get('request')==req and e.get('event') in ('devices','devices.error'),15,mark)
  assert e['event']=='devices',e
  return e
 try:
  ak=p.start_identity(a);bk=p.start_identity(b);p.start_identity(third)
  owner=ask(a,'device.initialize',nickname='Owner');other=ask(b,'device.propose');extra=ask(third,'device.propose')
  ask(a,'device.authorize',payload=other['proposal'],text=c.consent(b,owner['person']),nickname='Other',accept=True)
  shared=ask(a,'device.authorize',payload=extra['proposal'],text=c.consent(third,owner['person']),nickname='Third',accept=True)
  ask(b,'device.adopt',key=owner['person'],text=shared['roster'],accept=True)
  old_roster=bytes.fromhex(shared['roster'])
  revoked=ask(a,'device.revoke',key=other['local'],accept=True)
  a.stop()
  # An adversarial endpoint can retain its own old public authorization chain.
  (b.home/'devices/roster').write_bytes(old_roster)
  divergent=ask(b,'device.revoke',key=owner['local'],accept=True)
  b.stop();third.stop()
  incoming=root/'incoming-public-roster';incoming.write_text(divergent['roster'])
  def receive():
   args=[str(driver),str(a.home),owner['proposal'][64:128],owner['proposal'][128:],other['proposal'][64:128],other['proposal'][128:],owner['person'],str(incoming)]
   return json.loads(subprocess.check_output(args,text=True))
  negative=receive()
  assert negative=={'sender_active_before':0,'status_after':'ok'},negative
  assert not (a.home/'devices/fork').exists()
  # Restore only public roster files in this disposable fixture for the control.
  (a.home/'devices/roster').write_bytes(old_roster)
  a=p.Peer(binary,root,'owner');running.append(a);p.start_identity(a)
  ask(a,'device.revoke',key=extra['local'],accept=True);a.stop()
  positive=receive()
  assert positive=={'sender_active_before':1,'status_after':'device_roster_conflict'},positive
  source=Path('/source/helper')
  hashes={n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in ('devices.c','device_link.c')}
  receipt={'scope':'decrypted HD1 receive boundary compiled from reviewed source; fixture states via frozen native helper; NOT an end-to-end survivor lockout reproduction',
   'fixture_helper_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
   'driver_sha256':hashlib.sha256(driver.read_bytes()).hexdigest(),
   'driver_source_sha256':hashlib.sha256(Path(__file__).with_name('device-link-receive-driver.c').read_bytes()).hexdigest(),
   'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
   'source_sha256':hashes,'known_revoked_sender':negative,'still_active_concurrent_sender_control':positive}
  Path(sys.argv[3]).write_text(json.dumps(receipt,indent=2)+'\n')
  print(json.dumps(receipt),flush=True)
 finally:
  for peer in running:peer.stop()
