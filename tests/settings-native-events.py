#!/usr/bin/env python3
"""Native QML settings journey with injected helper replies; no transport claim."""
import json, subprocess, sys, time
from pathlib import Path
shell, receipt = map(Path, sys.argv[1:])
checks=[]
def call(*args):
    return subprocess.check_output(['qs','-p',str(shell),'ipc','call','friction',*args],text=True).strip()
def scenario(name):
    assert call('scenario',name)=='ok', name
def check(name, **expected):
    deadline=time.monotonic()+5
    while True:
        state=json.loads(call('state'))
        if all(state.get(k)==v for k,v in expected.items()):
            checks.append(dict(check=name,state=state)); return
        if time.monotonic()>deadline: raise AssertionError((name,expected,state))
        time.sleep(.1)
try:
    for page in ['', 'profile','devices','notifications','appearance','recovery','advanced']:
        scenario('settings:'+page)
        check('navigate-'+(page or 'home'),settingsPage=page,settingsOpen=True)
    scenario('settings-close')
    check('close-resets-navigation',settingsOpen=False,settingsPage='')
    scenario('prepare-computer')
    check('prepare-current-profile',lastSetupOp='device.initialize',inviteOpen=False)
    scenario('computer-ready')
    check('prepared-computer-opens-invite',inviteOpen=True)
    scenario('restore-select')
    check('restore-validates-first',identityBusy=True,restoreConfirm=False,restoreSecretHeld=True)
    scenario('restore-wrong-result')
    check('stale-inspection-rejected',identityBusy=True,restoreConfirm=False)
    scenario('restore-checked')
    check('validated-secret-survives',identityBusy=False,restoreConfirm=True,restoreSecretHeld=True)
    scenario('settings-close')
    check('cancel-clears-secret',restoreConfirm=False,restoreSecretHeld=False)
    result=dict(ok=True,checks=checks)
except Exception as error:
    result=dict(ok=False,error=str(error),checks=checks)
receipt.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(ok=result['ok'],checks=len(checks),receipt=str(receipt))))
if not result['ok']: raise SystemExit(result['error'])
