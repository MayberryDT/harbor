#!/usr/bin/env python3
"""Prepare a native UI journey with injected helper events, not a transport test.

Usage: python3 tests/friction-native.py SOURCE EMPTY_OUTPUT_DIRECTORY
Run `qs -p OUTPUT/shell.qml` on a disposable Omarchy desktop. Drive external
events with `qs -p OUTPUT/shell.qml ipc call friction scenario NAME`; use actual
mouse/keyboard input for picker, panel and chat actions. `state` returns a JSON
receipt. Keep the generated source hashes, logs, and native observations.

Failure cases: silent offers; stale/canceled offers during preference loading;
wrong contact keys; duplicate playback; muted audio; disabled popups; invitation
visibility; picker cancellation; header overflow. No private helper is started.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys

source, output = map(lambda x: Path(x).resolve(), sys.argv[1:])
output.mkdir(parents=True, exist_ok=False)
fixture = output / 'source'
fixture.mkdir()
for path in source.iterdir():
    if path.suffix in ('.qml', '.js') or path.name == 'qmldir':
        shutil.copy2(path, fixture / path.name)
for name in ('pages', 'assets', 'sounds', 'themes', 'scripts'):
    shutil.copytree(source / name, fixture / name)
hashes = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in source.rglob('*.qml')}
(output / 'source-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
for name in ('Ui', 'Commons'):
    (output / name).symlink_to('/usr/share/omarchy/shell/' + name)

def replace(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, (path, old)
    path.write_text(text.replace(old, new))

replace(fixture / 'Service.qml', '  Component.onCompleted: root.launchHelperDetached()',
        '  Component.onCompleted: {} // fixture: no private helper')
replace(fixture / 'Service.qml', '  function sendImmediateOp(obj) {',
        '  property bool fixtureCapture: false\n  property var fixtureOperations: []\n'
        '  function sendImmediateOp(obj) {\n'
        '    if (root.fixtureCapture) { root.fixtureOperations = root.fixtureOperations.concat([obj]); return true }')
replace(fixture / 'Panel.qml', '  moduleName: "io.zet.harbor"', '''  moduleName: "io.zet.harbor"
  property alias fixtureService: omaq
  property alias fixtureSurface: chatSurface
  property alias fixtureHeader: heroVisual
  property alias fixturePassword: passField''')
replace(fixture / 'ChatSurface.qml', '  Process {\n    id: sndProc\n', '  property int fixtureDesktopCount: 0\n  property int fixtureDesktopExit: -1\n  property int fixturePlaybackCount: 0\n  property int fixturePlaybackExit: -1\n  Process {\n    id: sndProc\n    onRunningChanged: if (running) root.fixturePlaybackCount++\n')
replace(fixture / 'ChatSurface.qml', '      if (code !== 0 && !root.muted)', '      root.fixturePlaybackExit = code\n      if (code !== 0 && !root.muted)')
replace(fixture / 'ChatSurface.qml', '    id: noteProc\n',
        '    id: noteProc\n    onRunningChanged: if (running) root.fixtureDesktopCount++\n')
replace(fixture / 'ChatSurface.qml', '      if (code !== 0) root.notificationWarning',
        '      root.fixtureDesktopExit = code\n      if (code !== 0) root.notificationWarning')
(output / 'shell.qml').write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import "source" as Harbor
ShellRoot {
  id: test
  readonly property string key: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  property int sequence: 0
  property var service: panel.fixtureService
  property var surface: panel.fixtureSurface
  FloatingWindow {
    title: "Harbor native journey"
    implicitWidth: 400; implicitHeight: 40
    Harbor.Panel { id: panel; anchors.fill: parent; settings: ({sound:"qq"}) }
  }
  Timer {
    interval: 1000; running: true
    onTriggered: {
      service.activeHelperProtocol = 17
      service.helperCompatibility = "compatible"
      service.friendsReady = true
      service.friends = [{id:"0", key:test.key, name:"Test friend", online:true}]
      service.selfNickname = "Native journey"
      service.connectionState = "online"
      surface.surfacesHydrated = true
      surface.autoOpenLoaded = true
      surface.autoOpenUnavailable = false
      surface.autoOpenWarning = ""
      surface.autoOpenDirectDefault = true
      surface.autoOpenRequest = ""
      console.log("FRICTION_READY")
    }
  }
  function emitOffer(key) {
    sequence++
    service.fileOffers = ({})
    service.handleLine(JSON.stringify({event:"file.offer",conversation:"0",key:key,
      id:"offer-"+sequence,name:"Holiday photo.png",kind:"image"}))
  }
  IpcHandler {
    target: "friction"
    function scenario(name: string): string {
      if (name === "offer") test.emitOffer(test.key)
      else if (name === "reuse") { sequence = 0; test.emitOffer(test.key) }
      else if (name === "terminal") service.handleLine(JSON.stringify({event:"file.canceled",
        conversation:"0",key:test.key,id:"offer-"+sequence,dir:"in"}))
      else if (name === "duplicate") service.lastFileTick++
      else if (name === "wrong-key") test.emitOffer("b".repeat(64))
      else if (name === "close") surface.clearCards()
      else if (name === "mute") service.muted = true
      else if (name === "unmute") service.muted = false
      else if (name === "popup-off") surface.autoOpenByConversation = ({["d:"+test.key]:false})
      else if (name === "popup-on") surface.autoOpenByConversation = ({})
      else if (name === "queue") { surface.autoOpenLoaded = false; test.emitOffer(test.key) }
      else if (name === "cancel") service.fileOffers = ({})
      else if (name === "release") { surface.autoOpenLoaded = true; surface.releasePendingIncoming() }
      else if (name === "panel") panel.open()
      else if (name === "open-after-handshake" || name === "open-after-identity") {
        surface.clearCards()
        surface.surfacesHydrated = false
        service.pendingOps = []
        panel.openConversation(panel.conversationRows(true)[0])
        if (name === "open-after-identity") service.identityTick++
        else service.helperHandshakeTick++
        var requested = service.pendingOps.some(function(line) {
          return JSON.parse(line).op === "surface.list"
        })
        if (requested) service.handleLine(JSON.stringify({event:"surfaces",items:[]}))
      }
      else if (name === "preview-history") {
        service.previewRequest = {conversation:"0",key:test.key,request:"preview-native",revision:service.previewRevision}
        service.handleLine(JSON.stringify({event:"history",conversation:"0",key:test.key,
          request:"preview-native",items:[{id:"older",text:"Saved conversation",ts:100,dir:"in"}]}))
      }
      else if (name === "preview-stale") {
        service.previewRequest = {conversation:"0",key:test.key,request:"preview-stale",revision:service.previewRevision}
        service.handleLine(JSON.stringify({event:"message",conversation:"0",key:test.key,
          id:"latest",text:"Latest message",ts:200,dir:"in"}))
        service.handleLine(JSON.stringify({event:"history",conversation:"0",key:test.key,
          request:"preview-stale",items:[{id:"older",text:"Stale response",ts:100,dir:"in"}]}))
      }
      else if (name === "preview-replayed-message") service.handleLine(JSON.stringify({
        event:"message",conversation:"0",key:test.key,id:"old-replay",text:"Old replay",ts:50,dir:"in"}))
      else if (name === "preview-delete") service.handleLine(JSON.stringify({
        event:"message.updated",conversation:"0",key:test.key,id:"latest",text:"",deleted:true}))
      else if (name === "preview-clear") service.completeHistoryClear("0","native-clear",true,"")
      else if (name === "device-request") {
        panel.close()
        service.pending = false
        service.supportsDeviceManagement = true
        service.handleLine(JSON.stringify({event:"device.link",state:"requested",
          request:"native-link",key:test.key,person:"b".repeat(64),code:"c".repeat(64),
          name:"Family laptop",incoming:true}))
      }
      else if (name === "device-sent") service.handleLine(JSON.stringify({event:"device.link",
        state:"sent",request:"native-link",key:test.key,person:"b".repeat(64),
        code:"c".repeat(64),name:"Family laptop",incoming:true}))
      else if (name === "device-linked") service.handleLine(JSON.stringify({event:"device.link",
        state:"linked",request:"native-link",key:test.key,person:"b".repeat(64),
        code:"c".repeat(64),name:"Family laptop",incoming:true}))
      else if (name === "device-malformed") {
        service.deviceRequest = "native-malformed"
        service.handleLine(JSON.stringify({event:"devices",request:"native-malformed",
          person:"b".repeat(64),local:"d".repeat(64),count:1,active:true,items:[null]}))
      }
      else if (name === "fallback") {
        surface.clearCards()
        surface.floatRulesReady = false
        test.emitOffer(test.key)
      }
      else if (name === "fallback-message-canceled-file") {
        panel.settings = ({sound:"qq",notifyDesktop:true})
        surface.clearCards()
        surface.floatRulesReady = false
        surface.onIncoming("0", {conversation:"0",key:test.key,id:"fallback-message",dir:"in",text:"Unread message"})
        test.emitOffer(test.key)
        service.fileOffers = ({})
      }
      else if (name === "removed-group-replay") {
        surface.clearCards()
        surface.autoOpenLoaded = false
        service.groupsReady = true
        service.groups = [{id:"g:"+"e".repeat(64),title:"Removed group"}]
        surface.onIncoming("g:"+"e".repeat(64), {conversation:"g:"+"e".repeat(64),id:"removed-group-message",dir:"in",text:"Old message"})
        service.groups = []
        surface.autoOpenLoaded = true
        surface.releasePendingIncoming()
      }
      else if (name === "fallback-restore") surface.floatRulesReady = true
      else if (name === "fallback-off") {
        panel.settings = ({sound:"qq",notifyDesktop:false})
        surface.clearCards()
        surface.floatRulesReady = false
        test.emitOffer(test.key)
      }
      else if (name === "qr-policy") {
        service.handleLine(JSON.stringify({event:"invite",url:"harbor://invite/current",expires:2000000000,bearer:true}))
        service.handleLine(JSON.stringify({event:"invite",url:"harbor://invite/current",qr:"/tmp/current.png"}))
      }
      else if (name === "qr-stale") service.handleLine(JSON.stringify({event:"invite",url:"harbor://invite/old",qr:"/tmp/old.png"}))
      else if (name === "setup-start" || name === "setup-retry") {
        service.selfNickname = ""
        service.deviceLink = null
        service.deviceRequest = ""
        service.awaitingHelperInstance = false
        service.fixtureCapture = true
        service.fixtureOperations = []
        if (!service.createIdentity("Alice", "native-setup")) return "setup-refused"
      }
      else if (name === "setup-wrong-result") service.handleLine(JSON.stringify({event:"devices.error",request:"older-setup",code:"device_io"}))
      else if (name === "setup-failed") service.handleLine(JSON.stringify({event:"devices.error",request:service.deviceRequest,code:"device_io"}))
      else if (name === "setup-inactive") service.handleLine(JSON.stringify({event:"devices",request:service.deviceRequest,
        person:"b".repeat(64),local:"d".repeat(64),count:0,active:"false",
        items:[{key:"d".repeat(64),name:"My computer",current:true,active:false}]}))
      else if (name === "setup-success") service.handleLine(JSON.stringify({event:"devices",request:service.deviceRequest,
        person:"b".repeat(64),local:"d".repeat(64),count:1,active:true,
        items:[{key:"d".repeat(64),name:"My computer",current:true,active:true}]}))
      else if (name === "setup-nickname") service.handleLine(JSON.stringify({event:"nickname",value:"Alice",request:"native-setup"}))
      else if (name === "invite") {
        panel.close()
        service.pending = false
        service.pendingGroup = true
        service.pending = true
      }
      else if (name.indexOf("settings:") === 0) { panel.openSettingsPage(name.slice(9)); panel.open() }
      else if (name === "settings-close") panel.close()
      else if (name === "prepare-computer") {
        panel.openSettingsPage("devices")
        service.awaitingHelperInstance = false
        service.helperCompatibility = "compatible"
        service.fixtureCapture = true; service.fixtureOperations = []
        service.supportsDeviceManagement = true; service.supportsBearerInvites = true
        service.deviceRequest = ""; service.deviceLink = null; service.deviceBootstrap = null
        service.linkedDevices = []; service.deviceActive = false
        service.inviteUrl = ""
        panel.addComputer()
      }
      else if (name === "computer-ready") service.handleLine(JSON.stringify({event:"devices",
        request:service.deviceRequest,person:"c".repeat(64),local:"d".repeat(64),count:1,active:true,
        items:[{key:"d".repeat(64),name:"My computer",current:true,active:true}]}))
      else if (name === "restore-select") {
        panel.openSettingsPage("recovery"); panel.open()
        service.awaitingHelperInstance = false; service.fixtureCapture = true
        service.fixtureOperations = []
        panel.fixturePassword.text = "native-test-password"
        panel.identityPickerMode = "replace"
        panel.finishIdentityPicker("/tmp/native-backup",0)
      }
      else if (name === "restore-wrong-result") service.handleLine(JSON.stringify({event:"identity",op:"inspect",request:"stale"}))
      else if (name === "restore-checked") service.handleLine(JSON.stringify({event:"identity",op:"inspect",request:panel.identityRequest}))
      else return "unknown"
      return "ok"
    }
    function state(): string {
      return JSON.stringify({settingsPage:panel.settingsPage, settingsOpen:panel.settingsOpen,
        inviteOpen:panel.inviteOpen, restoreConfirm:panel.replaceIdentityConfirm,
        restorePending:panel.restoreAfterValidation, identityBusy:panel.identityActionPending,
        restoreSecretHeld:panel.restorePassword === "native-test-password",
        cards:surface.cardCount(), pending:surface.pendingIncoming.length,
        playback:surface.fixturePlaybackCount, playbackExit:surface.fixturePlaybackExit,
        desktop:surface.fixtureDesktopCount, desktopExit:surface.fixtureDesktopExit,
        panelOpen:panel.opened, devicesOpen:panel.devicesOpen,
        deviceLinkState:service.deviceLink ? service.deviceLink.state : "",
        deviceError:service.deviceFeedbackError, deviceFeedback:service.deviceFeedback,
        previewText:service.conversationPreview("0",test.key).text,
        previewTimestamp:service.conversationPreview("0",test.key).ts,
        inviteBearer:service.inviteBearer, qrPath:service.qrPath, inviteUrl:service.inviteUrl,
        setupPending:!!service.identitySetup, setupOperations:service.fixtureOperations.length,
        lastSetupOp:service.fixtureOperations.length ? service.fixtureOperations[service.fixtureOperations.length-1].op : "",
        nickname:service.selfNickname, setupError:service.lastError,
        historyTick:service.historyTick, headerWidth:panel.fixtureHeader.width,
        filePending:service.filePending("0"), owner:surface.isSurfaceOwner,
        floatReady:surface.floatRulesReady, hydrated:surface.surfacesHydrated,
        openPending:surface.pendingSurfaceOpens.length,
        windowVisible:!!(surface.pinWindowAt(0) && surface.pinWindowAt(0).visible)})
    }
  }
}
''')
print(output / 'shell.qml')
