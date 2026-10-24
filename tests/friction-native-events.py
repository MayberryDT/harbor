#!/usr/bin/env python3
"""Drive external events into the running friction-native.py QML journey.

This checks real window-model state and real notification-player exits. Native
screen observations and input checks complement this receipt; it does not test
the Tox network or prove physical speaker output.
"""
import json
from pathlib import Path
import subprocess
import sys
import time

shell, receipt = map(Path, sys.argv[1:])
checks = []

def call(*args):
    return subprocess.check_output(['qs', '-p', str(shell), 'ipc', 'call',
                                    'friction', *args], text=True).strip()

def scenario(name):
    assert call('scenario', name) == 'ok', name

def check(name, **expected):
    deadline = time.monotonic() + 5
    while True:
        state = json.loads(call('state'))
        if all(state.get(k) == v for k, v in expected.items()):
            checks.append(dict(check=name, state=state))
            return
        if time.monotonic() > deadline:
            raise AssertionError((name, expected, state))
        time.sleep(.1)

try:
    check('ready', cards=0, playback=0, owner=True, floatReady=True)
    scenario('offer')
    check('file-popup-and-player', cards=1, playback=1, playbackExit=0)
    scenario('duplicate')
    check('duplicate-offer', cards=1, playback=1)
    scenario('terminal'); scenario('close'); scenario('reuse')
    check('reused-transfer-id', cards=1, playback=2, playbackExit=0)
    scenario('mute'); scenario('close'); scenario('offer')
    check('mute-keeps-popup', cards=1, playback=2)
    scenario('unmute'); scenario('close'); scenario('popup-off'); scenario('offer')
    check('popup-off-keeps-sound', cards=0, playback=3, playbackExit=0)
    scenario('popup-on'); scenario('queue')
    check('waits-for-preferences', cards=0, pending=1, playback=3)
    scenario('cancel'); scenario('release')
    check('canceled-queued-offer', cards=0, pending=0, playback=3)
    scenario('queue'); scenario('release')
    check('queued-offer-released', cards=1, pending=0, playback=4, playbackExit=0)
    scenario('close'); scenario('wrong-key')
    check('wrong-contact-rejected', cards=0, playback=4)
    scenario('invite')
    check('invitation-visible-and-player', panelOpen=True, playback=5, playbackExit=0)
    scenario('device-request')
    check('device-request-visible-and-player', panelOpen=True, devicesOpen=True,
          deviceLinkState='requested', playback=6, playbackExit=0)
    scenario('device-sent'); scenario('device-linked')
    check('device-completion-acknowledged', deviceLinkState='linked')
    scenario('device-malformed')
    check('malformed-device-list-fails-visibly', deviceError=True,
          deviceFeedback='Harbor could not read the complete device list. Refresh to try again.')
    before = json.loads(call('state'))['historyTick']
    scenario('preview-history')
    check('persisted-summary-does-not-consume-chat-history', previewText='Saved conversation',
          previewTimestamp=100, historyTick=before)
    scenario('preview-stale')
    check('live-message-wins-over-delayed-summary', previewText='Latest message', previewTimestamp=200)
    scenario('preview-replayed-message')
    check('older-message-does-not-regress-preview', previewText='Latest message', previewTimestamp=200)
    scenario('preview-delete')
    check('deleted-preview-text-removed', previewText='Message removed')
    scenario('preview-clear')
    check('cleared-preview-removed', previewText='', previewTimestamp=0)

    scenario('qr-policy')
    check('qr-retains-bearer-policy', inviteBearer=True, qrPath='/tmp/current.png')
    scenario('qr-stale')
    check('stale-qr-does-not-replace-invite', inviteUrl='harbor://invite/current', qrPath='/tmp/current.png')
    scenario('setup-start')
    check('start-creates-identity-first', setupPending=True, setupOperations=1, lastSetupOp='device.initialize', nickname='')
    scenario('setup-wrong-result')
    check('stale-setup-result-ignored', setupPending=True, setupOperations=1)
    scenario('setup-failed')
    check('failed-setup-retains-unsaved-profile', setupPending=False, setupOperations=1, nickname='', setupError='identity_setup_failed')
    scenario('setup-retry'); scenario('setup-inactive')
    check('inactive-projection-cannot-complete-setup', setupPending=False, setupOperations=1, nickname='')
    scenario('setup-retry'); scenario('setup-success')
    check('authorized-setup-saves-profile', setupPending=False, setupOperations=2, lastSetupOp='nickname.set')
    scenario('setup-nickname')
    check('profile-completion-visible', nickname='Alice')

    scenario('fallback')
    check('desktop-fallback-when-window-unavailable', desktop=1, desktopExit=0)
    scenario('fallback-restore'); scenario('close'); scenario('offer')
    time.sleep(1.2)
    check('mapped-popup-has-no-duplicate-desktop-alert', desktop=1)
    scenario('fallback-off')
    time.sleep(1.2)
    check('explicit-desktop-off-survives-fallback', desktop=1)

    scenario('fallback-message-canceled-file')
    check('canceled-offer-preserves-pending-message-alert', desktop=2, desktopExit=0)
    playback = json.loads(call('state'))['playback']
    scenario('removed-group-replay')
    check('removed-group-replay-does-not-reopen-or-ring', cards=0, playback=playback)

    scenario('fallback-restore')
    scenario('open-after-handshake')
    check('chat-opens-after-handshake', cards=1, hydrated=True, openPending=0, windowVisible=True)
    scenario('open-after-identity')
    check('chat-opens-after-identity', cards=1, hydrated=True, openPending=0, windowVisible=True)

finally:
    receipt.write_text(json.dumps(dict(passed=sys.exc_info()[0] is None,
        scope='Native QML with injected helper events', checks=checks), indent=2)+'\n')
print(receipt)
