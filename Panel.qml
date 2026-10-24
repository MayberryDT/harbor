import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Controls as Controls
import QtQuick.Dialogs as Dialogs
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import Quickshell.Wayland
import qs.Ui
import qs.Commons
import "Model.js" as Model
import "." as Harbor

BarWidget {
  id: root
  moduleName: "io.zet.harbor"

  property bool opened: false
  property bool addOpen: false
  property bool devicesOpen: false
  property string settingsPage: ""
  property string prepareDeviceInviteRequest: ""
  property bool recoveryDetailsOpen: false
  property bool restoreAfterValidation: false
  property string restorePassword: ""

  function openSettingsPage(page) {
    root.dismissTransientSections()
    root.settingsOpen = true
    root.settingsPage = page
    root.devicesOpen = page === "devices"
    root.soundOpen = page === "notifications"
    root.themeOpen = page === "appearance"
    root.fontSizeOpen = page === "appearance"
    root.moreOpen = page === "recovery" || page === "advanced"
    root.moreSection = page === "recovery" ? "identity" : page === "advanced" ? "danger" : ""
    if (page === "devices") omaq.manageDevice("device.status", "", "", false)
  }

  function addComputer() {
    if (omaq.deviceActive) { root.openDeviceInvite(); return }
    if (omaq.manageDevice("device.initialize", "My computer", "", false))
      root.prepareDeviceInviteRequest = omaq.deviceRequest
  }

  Timer {
    id: preparedDeviceInvite
    interval: 0
    onTriggered: {
      if (root.prepareDeviceInviteRequest === "") return
      root.prepareDeviceInviteRequest = ""
      if (root.devicesOpen && omaq.deviceActive && !omaq.deviceFeedbackError)
        root.openDeviceInvite()
    }
  }
  Connections {
    target: omaq
    function onDeviceRequestChanged() {
      if (omaq.deviceRequest === "" && root.prepareDeviceInviteRequest !== "")
        preparedDeviceInvite.restart()
    }
    function onHelperInstanceGenerationChanged() { root.prepareDeviceInviteRequest = "" }
  }
  property bool deviceInviteMode: false
  property string deviceSetupChoice: ""
  property string deviceRevokeKey: ""
  property string deviceRevokeName: ""
  property string conversationQuery: ""
  property var conversationOrder: []

  function snapshotConversationOrder() {
    var rows = root.conversationRows(true)
    rows.sort(function(a, b) {
      return omaq.conversationPreview(b.id, b.key).ts - omaq.conversationPreview(a.id, a.key).ts
    })
    root.conversationOrder = rows.map(function(row) { return row.group ? row.id : "d:" + row.key })
  }
  function activityTime(timestamp) {
    if (!(timestamp > 0)) return ""
    var date = new Date(timestamp * 1000)
    var today = new Date()
    return Qt.formatDateTime(date, date.toDateString() === today.toDateString() ? "HH:mm" : "MMM d")
  }

  function conversationRows(ignoreSearch) {
    var query = ignoreSearch ? "" : root.conversationQuery.trim().toLocaleLowerCase()
    var rows = []
    var friends = omaq.friends || []
    var groups = omaq.groups || []
    for (var i = 0; i < friends.length; i++) {
      var friend = friends[i]
      var name = String(friend.name || "Friend")
      if (!query || name.toLocaleLowerCase().indexOf(query) >= 0)
        rows.push({ id: String(friend.id), name: name, group: false,
          key: root.friendKey(friend.id), avatar: friend.avatar || "",
          online: !!friend.online, status: root.friendStatus(friend) })
    }
    for (var j = 0; j < groups.length; j++) {
      var group = groups[j]
      var title = String(group.title || "Group")
      if (!query || title.toLocaleLowerCase().indexOf(query) >= 0)
        rows.push({ id: String(group.id), name: title, group: true, key: "",
          avatar: "", online: false,
          status: String(group.memberCount || 0) + " members" })
    }
    // Reorder only when opening; previews may update without moving a target.
    var order = root.conversationOrder
    rows.sort(function(a, b) {
      var ai = order.indexOf(a.group ? a.id : "d:" + a.key)
      var bi = order.indexOf(b.group ? b.id : "d:" + b.key)
      return (ai < 0 ? order.length : ai) - (bi < 0 ? order.length : bi)
    })
    return rows
  }

  function openConversation(row) {
    if (row.group)
      root.openGroup(row.id)
    else if (root.friendMatches(row.id, row.key))
      root.openFriend(row.id, row.name)
  }

  function openAdd() {
    root.dismissTransientSections()
    root.addOpen = true
  }
  property string redeemDraft: ""
  property string redeemRequest: ""
  property string redeemFeedback: ""
  property string redeemFeedbackRequest: ""
  property string redeemSafety: ""
  property string callFeedback: ""
  property bool nospamConfirm: false
  property bool removeContactConfirm: false
  property bool removeContactPickerOpen: false
  property string removeContactId: ""
  property string removeContactKey: ""
  property bool identityPrimaryConfirm: false
  property int identityPrimaryRequestSequence: 0
  property string identityPrimaryRequest: ""
  property bool directReinviteClearConfirm: false
  property int directReinviteRequestSequence: 0
  property string directReinviteRequest: ""
  property bool replaceIdentityConfirm: false
  property string replaceIdentityPath: ""
  property bool showJoin: false
  property bool chatPickerOpen: false
  property bool inviteOpen: false
  property bool inviteRequireApproval: false
  property bool inviteActionRequireApproval: false
  property int inviteActionLifetime: 86400
  property string inviteConfirmMode: ""
  property bool inviteActionPending: false
  property string inviteActionMode: ""
  property string inviteActionRequest: ""
  property int inviteActionSequence: 0
  property int inviteActionGeneration: -1
  property string inviteFeedback: ""
  property string inviteFeedbackRequest: ""
  property bool inviteFeedbackError: false
  property double inviteNow: Math.floor(Date.now() / 1000)
  property bool moreOpen: false
  property string moreSection: ""
  property bool settingsOpen: false
  property bool themeOpen: false
  property bool soundOpen: false
  property bool fontSizeOpen: false
  property int soundPickerExitCode: -1
  property bool soundPickerStreamDone: false
  property string soundActionRequest: ""
  property string soundAction: ""
  property string soundFeedback: ""
  property bool soundFeedbackError: false
  property string soundRemoveId: ""
  property string soundRemoveLabel: ""
  property string soundRemovePath: ""
  property bool soundRemoveConfirm: false
  property bool copied: false
  property bool safetyCodeVisible: false
  property bool safetyCopied: false
  property bool nicknameEditOpen: false
  property bool nicknameSubmitPending: false
  property string nicknameRequest: ""
  property int nicknameRequestSequence: 0
  property string nicknameFeedback: ""
  property string nicknameFeedbackRequest: ""
  property bool nicknameFeedbackError: false
  property bool avatarRestorePending: false
  property bool avatarRestoreMore: false
  property string groupInviteGroupId: ""
  property string groupInviteFriendId: ""
  property string groupInviteFriendKey: ""
  property string groupInviteRequest: ""
  property int groupInviteGeneration: -1
  property string groupInviteFeedback: ""
  property bool groupLeaveConfirm: false
  property string groupLeaveTarget: ""
  property bool groupDissolveConfirm: false
  property string groupDissolveTarget: ""
  property int avatarPickExitCode: -1
  property bool avatarPickStreamDone: false
  property string identityAction: ""
  property string identityRequest: ""
  property int identityRequestSequence: 0
  property string identityFeedback: ""
  property string identityFeedbackRequest: ""
  property bool identityFeedbackError: false
  property string settingsPersistenceWarning: ""
  property var settingsPersistenceExpected: ({})
  property bool settingsPersistencePending: false
  property int settingsPersistenceAttempts: 0
  property bool identityActionPending: false
  property string identityPickerMode: ""
  property int identityPickerExitCode: -1
  property bool identityPickerStreamDone: false
  property var systemColors: ["#101315", "#565d60", "#9fa5a9", "#d9dbdc", "#798186", "#aeaeae", "#707070", "#cbc2be"]
  property string systemThemeName: "System"
  readonly property var bundledNotificationSounds: [
    { id: "off", label: "Off", custom: false, path: "" },
    { id: "qq", label: "PING" },
    { id: "msn", label: "MAIL" },
    { id: "aurora", label: "Aurora" },
    { id: "glow", label: "Glow" },
    { id: "click", label: "Click" },
    { id: "knock", label: "Knock", custom: false, path: "" }
  ]
  readonly property var notificationSounds: {
    var revision = Number(omaq.soundTick || 0)
    var result = root.bundledNotificationSounds.slice()
    var custom = omaq.customSounds || []
    for (var i = 0; revision >= 0 && i < custom.length; i++)
      result.push({ id: "custom:" + String(custom[i].id || ""),
        soundId: String(custom[i].id || ""),
        label: String(custom[i].label || "Custom sound"),
        path: String(custom[i].path || ""), custom: true })
    return result
  }
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color barForeground: bar && "barForeground" in bar ? bar.barForeground : foreground
  readonly property var shibumiTokens: bar && "visualTokens" in bar ? bar.visualTokens : null
  readonly property string shellStyle: shibumiTokens && shibumiTokens.shellStyle !== undefined
    ? String(shibumiTokens.shellStyle) : "shibumi"
  readonly property bool connectedSurfaceEnabled: shellStyle !== "shibumi"
    && (barPos === "top" || barPos === "bottom")
  property real connectionReveal: 0
  property real cardHeightLimit: 0
  readonly property color panelBackground: shibumiTokens && shibumiTokens.panelBackground !== undefined
    ? shibumiTokens.panelBackground : Color.popups.background
  readonly property color panelBorder: shibumiTokens && shibumiTokens.panelBorder !== undefined
    ? shibumiTokens.panelBorder : Color.popups.border
  readonly property real panelBorderWidth: shibumiTokens && shibumiTokens.panelBorderWidth !== undefined
    ? Number(shibumiTokens.panelBorderWidth) : Math.max(1, Style.space(1))
  readonly property real panelRadius: shibumiTokens && shibumiTokens.panelRadius !== undefined
    ? Number(shibumiTokens.panelRadius) : Style.cornerRadius
  readonly property color controlForeground: bar ? bar.foreground : Color.popups.text
  readonly property color controlAccent: bar ? bar.urgent : Color.accent
  readonly property real controlRadius: {
    var themeRevision = root.systemThemeName
    return shibumiTokens && shibumiTokens.tileRadius !== undefined
      ? Number(shibumiTokens.tileRadius) : Style.cornerRadius
  }
  readonly property color controlBorder: shibumiTokens && shibumiTokens.separator !== undefined
    ? shibumiTokens.separator : Qt.rgba(controlForeground.r, controlForeground.g, controlForeground.b, 0.18)
  readonly property color controlFill: shibumiTokens && shibumiTokens.fillIdle !== undefined
    ? shibumiTokens.fillIdle : Qt.rgba(0, 0, 0, 0.12)
  readonly property color controlHoverFill: shibumiTokens && shibumiTokens.fillHover !== undefined
    ? shibumiTokens.fillHover : Qt.rgba(controlAccent.r, controlAccent.g, controlAccent.b, 0.10)
  readonly property color controlActiveFill: shibumiTokens && shibumiTokens.fillActive !== undefined
    ? shibumiTokens.fillActive : Qt.rgba(controlAccent.r, controlAccent.g, controlAccent.b, 0.18)
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property real btnGap: Style.space(6)
  readonly property real panelSectionGap: Style.space(8)
  readonly property real framePadding: Style.space(6)
  readonly property int pad: Style.spacing.popupPadding
  readonly property real nicknameControlHeight: Style.space(18)
  readonly property real nicknameEditorHeight: Style.space(30)
  readonly property int cardWidth: 400
  readonly property real railIconWidth: Style.space(30)
  readonly property real railWidth: railIconWidth * 2 + framePadding * 2
  readonly property real headerHeight: Style.space(48)
  readonly property real pendingDirectHeaderHeight: Style.space(156)
  readonly property real basePrimaryAreaHeight: Math.max(
    identityContactsFrame.implicitHeight, Style.space(160))
  readonly property real primaryAreaHeight: root.primaryMenuOpen
    ? Math.max(column.implicitHeight + root.framePadding * 2,
               root.basePrimaryAreaHeight)
    : root.basePrimaryAreaHeight
  readonly property real actionButtonHeight: Style.space(24)
  readonly property color onlineStatusColor: "#7dce6a"
  readonly property bool primaryMenuOpen: root.devicesOpen || root.addOpen || root.inviteOpen || root.showJoin ||
    root.chatPickerOpen || root.settingsOpen || root.moreOpen || omaq.locked ||
    omaq.incomingCall || root.nicknameFeedback !== ""
  readonly property int visibleUnreadCount: Math.max(omaq.unreadCount, omaq.localUnreadTotal())
  readonly property string currentSafetyCode:
    String(omaq.safetyConv || "") === String(omaq.selectedDirectId || "")
      ? String(omaq.safetyCode || "") : ""
  readonly property bool contextualErrorHandled:
    (root.identityFeedbackRequest !== "" &&
     String(omaq.lastErrorRequest || "") === root.identityFeedbackRequest &&
     omaq.identityErrorCode(omaq.lastError)) ||
    (root.nicknameFeedbackRequest !== "" &&
     String(omaq.lastErrorRequest || "") === root.nicknameFeedbackRequest) ||
    (root.inviteFeedbackRequest !== "" &&
     String(omaq.lastErrorRequest || "") === root.inviteFeedbackRequest) ||
    (root.redeemFeedbackRequest !== "" &&
     String(omaq.lastErrorRequest || "") === root.redeemFeedbackRequest) ||
    (omaq.directReinviteRequired &&
     String(omaq.lastError || "") === "direct_state_reinvite_required") ||
    (omaq.identityPrimaryUncertain &&
     String(omaq.lastError || "") === "identity_primary_uncertain")
  readonly property string barPos: bar && bar.position ? String(bar.position) : "top"
  readonly property int inviteRemainingSeconds: Math.max(0,
    Math.floor(Number(omaq.inviteExpiresAt || 0) - root.inviteNow))
  readonly property real caretDepth: 5
  readonly property real caretHalfWidth: 6 * connectionReveal
  readonly property real caretTangentControl: 3.75 * connectionReveal
  readonly property real caretTipControl: 1.75 * connectionReveal
  readonly property real anchorCenterX: {
    var win = button && button.QsWindow ? button.QsWindow.window : null
    if (!win || !button)
      return card.width / 2
    var p = button.mapToItem(win.contentItem, 0, 0)
    return p.x + button.width / 2 - card.x
  }
  readonly property real caretCenterX: Math.max(10, Math.min(card.width - 10,
    Math.round(anchorCenterX)))
  readonly property real barThickness: {
    var n = bar && bar.barSize !== undefined ? Number(bar.barSize) : NaN
    return isFinite(n) && n > 0 ? n : Style.bar.sizeHorizontal
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Behavior on connectionReveal {
    NumberAnimation {
      duration: root.opened ? 160 : 120
      easing.type: root.opened ? Easing.OutCubic : Easing.InCubic
    }
  }


  onOpenedChanged: {
    root.connectionReveal = root.opened ? 1 : 0
    Qt.callLater(root.publishConnectedGeometry)
  }
  onConnectionRevealChanged: root.publishConnectedGeometry()

  Component.onDestruction: {
    if (bar && typeof bar.clearConnectedPanel === "function")
      bar.clearConnectedPanel(root)
  }

  component AvatarPic: Item {
    id: av
    property string path: ""
    property int px: Math.round(Style.font.display * 1.2)
    property bool failed: false
    property bool online: false
    property int unreadCount: 0
    property bool badgeEnabled: true
    property int revision: 0
    signal clicked()

    implicitWidth: px
    implicitHeight: px
    onPathChanged: av.failed = false
    onRevisionChanged: av.failed = false

    Rectangle {
      anchors.fill: parent
      radius: width / 2
      clip: true
      color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.08)
      border.color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.16)
      border.width: 1

      Image {
        anchors.fill: parent
        visible: !av.failed && av.path !== ""
        source: av.path !== "" ? root.localFileUrl(av.path) + "?v=" + av.revision : ""
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: false
        smooth: true
        mipmap: true
        onStatusChanged: if (status === Image.Error)
          av.failed = true
      }

      SafeText {
        anchors.centerIn: parent
        visible: av.failed || av.path === ""
        text: Harbor.MaterialSymbols.glyph("person")
        color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.72)
        font.family: Harbor.MaterialSymbols.family
        font.pixelSize: Math.round(av.px * 0.64)
        font.variableAxes: ({ "FILL": 0, "wght": 500 })
        renderType: Text.QtRendering
        font.hintingPreference: Font.PreferNoHinting
      }
    }

    MouseArea {
      anchors.fill: parent
      cursorShape: Qt.PointingHandCursor
      onClicked: av.clicked()
    }

    Rectangle {
      width: Math.max(8, Math.round(av.px * 0.28))
      height: width
      radius: width / 2
      anchors.right: parent.right
      anchors.bottom: parent.bottom
      color: av.online ? "#7dce6a" : Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.35)
      border.color: Color.popups.background
      border.width: 1
    }

    Rectangle {
      visible: av.badgeEnabled && av.unreadCount > 0
      width: Math.max(Style.space(14), unreadText.implicitWidth + Style.space(6))
      height: Style.space(14)
      radius: height / 2
      anchors.right: parent.right
      anchors.top: parent.top
      color: root.urgent
      border.color: Color.popups.background
      border.width: 1

      SafeText {
        id: unreadText
        anchors.centerIn: parent
        text: av.unreadCount > 99 ? "99+" : String(av.unreadCount)
        color: Color.popups.background
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
      }
    }
  }

  component SettingsRow: Rectangle {
    id: settingRow
    property string label: ""
    property string value: ""
    signal clicked()
    width: parent ? parent.width : 0
    implicitHeight: Style.space(54)
    radius: root.controlRadius
    color: activeFocus || rowMouse.containsMouse ? root.controlHoverFill : "transparent"
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: label + (value ? ", " + value : "")
    Accessible.onPressAction: if (enabled) clicked()
    Keys.onReturnPressed: if (enabled) clicked()
    Keys.onEnterPressed: if (enabled) clicked()
    Keys.onSpacePressed: if (enabled) clicked()
    onActiveFocusChanged: if (activeFocus) root.ensurePanelItemVisible(settingRow)
    Column {
      anchors.left: parent.left; anchors.right: arrow.left
      anchors.margins: Style.space(10); anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(3)
      SafeText {
        width: parent.width; text: settingRow.label
        color: root.foreground; font.family: root.fontFamily
        font.pixelSize: Style.font.body; elide: Text.ElideRight
      }
      SafeText {
        width: parent.width; text: settingRow.value; visible: text !== ""
        color: root.dim; font.family: root.fontFamily
        font.pixelSize: Style.font.caption; elide: Text.ElideRight
      }
    }
    SafeText {
      id: arrow; anchors.right: parent.right; anchors.rightMargin: Style.space(10)
      anchors.verticalCenter: parent.verticalCenter
      text: Harbor.MaterialSymbols.ready ? Harbor.MaterialSymbols.glyph("chevron_right") : ""
      font.family: Harbor.MaterialSymbols.family
      font.pixelSize: Style.font.icon; color: root.dim
    }
    MouseArea { id: rowMouse; anchors.fill: parent; hoverEnabled: true
      cursorShape: Qt.PointingHandCursor; onClicked: settingRow.clicked() }
  }

  component TokenButton: BorderSurface {
    id: tokenButton
    property string text: ""
    property string iconText: ""
    property string tooltipText: ""
    property bool selected: false
    property bool active: false
    property bool focusable: false
    property bool bordered: false
    property bool borderless: false
    property string accessibleName: tooltipText !== "" ? tooltipText : text
    property color foreground: root.controlForeground
    property color accent: root.controlAccent
    property string fontFamily: root.fontFamily
    property real fontSize: Style.font.body
    property real iconSize: Style.font.icon
    property string iconFontFamily: fontFamily
    property real horizontalPadding: Style.space(6)
    property real verticalPadding: Style.space(4)
    signal clicked()

    readonly property bool hot: mouseArea.containsMouse
    readonly property color actionColor: accent
    readonly property real contentSpacing: iconText !== "" && text !== "" ? Style.space(4) : 0
    readonly property real naturalContentWidth:
      (iconText !== "" ? buttonIcon.implicitWidth : 0) +
      (text !== "" ? buttonLabel.implicitWidth : 0) + contentSpacing
    readonly property var normalBorder: bordered
      ? Border.flat(root.controlBorder, 1) : Border.none()
    readonly property var activeBorder: Border.flat(actionColor, 1)

    activeFocusOnTab: focusable
    Accessible.role: Accessible.Button
    Accessible.name: accessibleName
    Accessible.onPressAction: if (tokenButton.enabled) tokenButton.clicked()
    onActiveFocusChanged: if (activeFocus) root.ensurePanelItemVisible(tokenButton)
    Keys.onReturnPressed: if (focusable) tokenButton.clicked()
    Keys.onEnterPressed: if (focusable) tokenButton.clicked()
    Keys.onSpacePressed: if (focusable) tokenButton.clicked()

    implicitWidth: naturalContentWidth + horizontalPadding * 2
    implicitHeight: Math.max(root.actionButtonHeight,
                             Math.max(buttonIcon.implicitHeight, buttonLabel.implicitHeight) +
                             verticalPadding * 2)
    radius: root.themedRadius(height > 0 ? height : implicitHeight)
    color: borderless ? "transparent"
      : mouseArea.pressed ? root.controlActiveFill
      : selected || active ? root.controlActiveFill
      : hot ? root.controlHoverFill : root.controlFill
    borderSpec: borderless ? Border.none()
      : activeFocus || hot || selected || active ? activeBorder : normalBorder

    Behavior on color { ColorAnimation { duration: 100 } }

    Row {
      id: row
      anchors.centerIn: parent
      width: Math.min(tokenButton.naturalContentWidth,
                      Math.max(0, tokenButton.width - tokenButton.horizontalPadding * 2))
      spacing: tokenButton.contentSpacing

      SafeText {
        id: buttonIcon
        visible: tokenButton.iconText !== ""
        text: tokenButton.iconFontFamily === "Material Symbols Rounded"
          ? Harbor.MaterialSymbols.glyph(tokenButton.iconText) : tokenButton.iconText
        color: tokenButton.selected || tokenButton.hot || tokenButton.activeFocus
          ? tokenButton.actionColor : tokenButton.foreground
        font.family: tokenButton.iconFontFamily === "Material Symbols Rounded"
          ? Harbor.MaterialSymbols.family : tokenButton.iconFontFamily
        font.pixelSize: tokenButton.iconSize
        anchors.verticalCenter: parent.verticalCenter
      }

      SafeText {
        id: buttonLabel
        visible: tokenButton.text !== ""
        width: Math.max(0, row.width -
          (buttonIcon.visible ? buttonIcon.implicitWidth + row.spacing : 0))
        text: tokenButton.text
        color: tokenButton.selected || tokenButton.hot || tokenButton.activeFocus
          ? tokenButton.actionColor : tokenButton.foreground
        font.family: tokenButton.fontFamily
        font.pixelSize: tokenButton.fontSize
        font.bold: false
        elide: Text.ElideRight
        anchors.verticalCenter: parent.verticalCenter
      }
    }

    Controls.ToolTip {
      id: tokenTooltip
      visible: (tokenButton.hot ||
        (tokenButton.activeFocus &&
         (tokenButton.activeFocusReason === Qt.TabFocusReason ||
          tokenButton.activeFocusReason === Qt.BacktabFocusReason))) &&
        (tokenButton.tooltipText !== "" || buttonLabel.truncated)
      text: tokenButton.tooltipText !== "" ? tokenButton.tooltipText : tokenButton.text
      delay: 450
      timeout: 2600
      padding: Style.space(5)
      background: Rectangle {
        radius: root.themedRadius(height)
        color: Qt.darker(root.panelBackground, 1.08)
        border.color: Qt.rgba(root.foreground.r, root.foreground.g,
                              root.foreground.b, 0.24)
        border.width: 1
      }
      contentItem: SafeText {
        text: tokenTooltip.text
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
        renderType: Text.QtRendering
      }
    }

    MouseArea {
      id: mouseArea
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: {
        if (tokenButton.focusable)
          tokenButton.forceActiveFocus()
        tokenButton.clicked()
        Qt.callLater(function() {
          if (root.opened)
            panelFocus.forceActiveFocus()
        })
      }
    }
  }

  component RailIcon: Item {
    id: railIcon
    property string materialIcon: ""
    property string label: ""
    property bool selected: false
    property bool fillSelected: true
    property color activeColor: root.systemColors[3] || root.controlAccent
    signal clicked()

    implicitWidth: root.railIconWidth
    implicitHeight: Style.space(30)
    opacity: enabled ? 1 : 0.35
    activeFocusOnTab: enabled
    Accessible.role: Accessible.Button
    Accessible.name: label
    Accessible.onPressAction: if (enabled) railIcon.clicked()
    Keys.onReturnPressed: if (enabled) railIcon.clicked()
    Keys.onEnterPressed: if (enabled) railIcon.clicked()
    Keys.onSpacePressed: if (enabled) railIcon.clicked()

    SafeText {
      anchors.centerIn: parent
      text: Harbor.MaterialSymbols.glyph(railIcon.materialIcon)
      color: railIcon.selected || railHover.hovered || railIcon.activeFocus
        ? railIcon.activeColor : root.dim
      font.family: Harbor.MaterialSymbols.family
      font.pixelSize: Style.font.icon + Style.space(3)
      font.variableAxes: ({ "FILL": railIcon.selected && railIcon.fillSelected ? 1 : 0,
                            "wght": 500 })
      renderType: Text.QtRendering
      font.hintingPreference: Font.PreferNoHinting
    }

    HoverHandler { id: railHover; enabled: railIcon.enabled }
    Controls.ToolTip {
      id: railTooltip
      visible: (railHover.hovered || railIcon.activeFocus) && railIcon.label !== ""
      text: railIcon.label
      delay: 450
      timeout: 2600
      padding: Style.space(5)
      background: Rectangle {
        radius: Style.cornerRadius
        color: Qt.darker(root.panelBackground, 1.08)
        border.color: Qt.rgba(root.foreground.r, root.foreground.g,
                              root.foreground.b, 0.24)
        border.width: 1
      }
      contentItem: SafeText {
        text: railTooltip.text
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
        renderType: Text.QtRendering
      }
    }
    MouseArea {
      anchors.fill: parent
      enabled: railIcon.enabled
      cursorShape: Qt.PointingHandCursor
      onClicked: {
        railIcon.clicked()
        Qt.callLater(function() {
          if (root.opened)
            panelFocus.forceActiveFocus()
        })
      }
    }
  }

  component TokenTextField: TextField {
    id: tokenField
    foreground: root.controlForeground
    accent: root.controlAccent
    font.family: root.fontFamily
    font.pixelSize: Style.font.bodySmall
    onActiveFocusChanged: if (activeFocus) root.ensurePanelItemVisible(tokenField)
    background: BorderSurface {
      anchors.fill: parent
      color: root.controlFill
      borderSpec: Border.flat(
        parent.activeFocus || parent.hovered ? tokenField.accent : root.controlBorder, 1)
      radius: root.themedRadius(parent.height)
    }
  }

  component ActionButton: TokenButton {
    implicitHeight: root.actionButtonHeight
    foreground: root.controlForeground
    accent: root.controlAccent
    fontFamily: root.fontFamily
    bordered: true
    focusable: true
    iconSize: Style.font.icon
    fontSize: Style.font.bodySmall
    horizontalPadding: Style.space(4)
    verticalPadding: Style.space(1)
  }

  function refreshPanelLayout() {
    Qt.callLater(function() {
      inviteContent.forceLayout()
      unlockedMenus.forceLayout()
      column.forceLayout()
    })
  }

  onPrimaryMenuOpenChanged: root.refreshPanelLayout()
  onInviteOpenChanged: root.refreshPanelLayout()
  onMoreSectionChanged: {
    root.refreshPanelLayout()
    if (root.moreSection === "groups" && omaq)
      omaq.refreshGroups(true)
  }
  onThemeOpenChanged: root.refreshPanelLayout()
  onSoundOpenChanged: root.refreshPanelLayout()
  onFontSizeOpenChanged: root.refreshPanelLayout()
  onShowJoinChanged: root.refreshPanelLayout()
  onChatPickerOpenChanged: root.refreshPanelLayout()

  function ensurePanelItemVisible(item) {
    if (!item || !root.opened || !panelScroll.contentItem)
      return
    var position = item.mapToItem(panelScroll.contentItem, 0, 0)
    var margin = Style.space(4)
    var top = position.y - margin
    var bottom = position.y + item.height + margin
    if (top < panelScroll.contentY)
      panelScroll.contentY = Math.max(0, top)
    else if (bottom > panelScroll.contentY + panelScroll.height)
      panelScroll.contentY = Math.min(
        Math.max(0, panelScroll.contentHeight - panelScroll.height),
        bottom - panelScroll.height)
  }

  function open() {
    if (root.opened)
      return
    root.snapshotConversationOrder()
    root.opened = true
    omaq.refreshConversationPreviews()
    omaq.sendOp({ op: "status" })
    if (bar && typeof bar.requestPopout === "function") {
      var screenName = popup.screen ? String(popup.screen.name || "") : ""
      bar.requestPopout(root, screenName)
    }
  }

  function close() {
    if (!root.opened)
      return
    root.settingsPage = ""
    root.prepareDeviceInviteRequest = ""
    root.restoreAfterValidation = false
    root.restorePassword = ""
    root.recoveryDetailsOpen = false
    root.devicesOpen = false
    root.deviceInviteMode = false
    root.deviceSetupChoice = ""
    root.deviceRevokeKey = ""
    root.deviceRevokeName = ""
    root.addOpen = false
    root.showJoin = false
    root.redeemRequest = ""
    root.redeemFeedback = ""
    root.redeemFeedbackRequest = ""
    root.redeemSafety = ""
    root.callFeedback = ""
    panelCallFeedbackTimer.stop()
    root.chatPickerOpen = false
    root.inviteOpen = false
    root.inviteConfirmMode = ""
    if (!root.inviteActionPending) {
      omaq.clearRequestError(root.inviteFeedbackRequest)
      root.inviteFeedback = ""
      root.inviteFeedbackRequest = ""
      root.inviteFeedbackError = false
    }
    root.moreOpen = false
    root.moreSection = ""
    root.settingsOpen = false
    root.themeOpen = false
    root.soundOpen = false
    root.fontSizeOpen = false
    root.soundRemoveConfirm = false
    root.soundRemoveId = ""
    root.soundRemoveLabel = ""
    root.soundRemovePath = ""
    if (root.soundActionRequest === "" && !soundPick.visible) {
      root.soundAction = ""
      root.soundFeedback = ""
      root.soundFeedbackError = false
    }
    root.safetyCodeVisible = false
    root.safetyCopied = false
    root.copied = false
    root.nospamConfirm = false
    root.removeContactPickerOpen = false
    root.removeContactConfirm = false
    root.removeContactId = ""
    root.removeContactKey = ""
    root.identityPrimaryConfirm = false
    root.identityPrimaryRequest = ""
    root.directReinviteClearConfirm = false
    root.directReinviteRequest = ""
    root.resetIdentityControls()
    root.nicknameEditOpen = false
    root.nicknameSubmitPending = false
    root.nicknameRequest = ""
    root.nicknameFeedback = ""
    root.nicknameFeedbackRequest = ""
    root.nicknameFeedbackError = false
    nicknameField.text = omaq.selfNickname
    nicknameSubmitTimer.stop()
    root.groupInviteGroupId = ""
    root.groupInviteFriendId = ""
    root.groupInviteFriendKey = ""
    root.groupInviteRequest = ""
    root.groupInviteFeedback = ""
    root.groupLeaveConfirm = false
    root.groupLeaveTarget = ""
    root.groupDissolveConfirm = false
    root.groupDissolveTarget = ""
    root.opened = false
    if (bar && typeof bar.releasePopout === "function") {
      var screenName = popup.screen ? String(popup.screen.name || "") : ""
      bar.releasePopout(root, screenName)
    }
    if (bar && typeof bar.clearConnectedPanel === "function")
      bar.clearConnectedPanel(root)
  }

  function toggle() {
    if (root.opened)
      close()
    else
      open()
  }

  function dismissTransientSections() {
    root.settingsPage = ""
    root.prepareDeviceInviteRequest = ""
    root.restoreAfterValidation = false
    root.restorePassword = ""
    root.recoveryDetailsOpen = false
    root.devicesOpen = false
    root.deviceInviteMode = false
    root.deviceSetupChoice = ""
    root.deviceRevokeKey = ""
    root.deviceRevokeName = ""
    root.addOpen = false
    root.inviteOpen = false
    root.inviteConfirmMode = ""
    if (!root.inviteActionPending) {
      omaq.clearRequestError(root.inviteFeedbackRequest)
      root.inviteFeedback = ""
      root.inviteFeedbackRequest = ""
      root.inviteFeedbackError = false
    }
    root.showJoin = false
    root.redeemRequest = ""
    root.redeemFeedback = ""
    root.redeemFeedbackRequest = ""
    root.redeemSafety = ""
    root.chatPickerOpen = false
    root.settingsOpen = false
    root.themeOpen = false
    root.soundOpen = false
    root.fontSizeOpen = false
    root.soundRemoveConfirm = false
    root.soundRemoveId = ""
    root.soundRemoveLabel = ""
    root.soundRemovePath = ""
    if (root.soundActionRequest === "" && !soundPick.visible) {
      root.soundAction = ""
      root.soundFeedback = ""
      root.soundFeedbackError = false
    }
    root.moreOpen = false
    root.moreSection = ""
    root.safetyCodeVisible = false
    root.safetyCopied = false
    root.copied = false
    root.nicknameEditOpen = false
    root.nicknameSubmitPending = false
    root.nicknameRequest = ""
    root.nicknameFeedback = ""
    root.nicknameFeedbackRequest = ""
    root.nicknameFeedbackError = false
    nicknameField.text = omaq.selfNickname
    nicknameSubmitTimer.stop()
    root.nospamConfirm = false
    root.removeContactPickerOpen = false
    root.removeContactConfirm = false
    root.removeContactId = ""
    root.removeContactKey = ""
    root.identityPrimaryConfirm = false
    root.identityPrimaryRequest = ""
    root.directReinviteClearConfirm = false
    root.directReinviteRequest = ""
    root.resetIdentityControls()
    root.groupInviteGroupId = ""
    root.groupInviteFriendId = ""
    root.groupInviteFriendKey = ""
    root.groupInviteRequest = ""
    root.groupInviteFeedback = ""
    root.groupLeaveConfirm = false
    root.groupLeaveTarget = ""
    root.groupDissolveConfirm = false
    root.groupDissolveTarget = ""
    panelScroll.contentY = 0
  }

  function toggleSettings() {
    var open = !root.settingsOpen
    root.dismissTransientSections()
    root.settingsOpen = open
  }

  function toggleAdvanced() {
    var open = !root.moreOpen
    root.dismissTransientSections()
    root.moreOpen = open
    root.moreSection = open ? "chat" : ""
  }

  function toggleMoreSection(section) {
    if (!root.moreOpen)
      root.moreOpen = true
    root.moreSection = root.moreSection === section ? "" : section
    if (root.moreSection !== "danger") {
      root.nospamConfirm = false
      root.removeContactPickerOpen = false
      root.removeContactConfirm = false
      root.removeContactId = ""
      root.removeContactKey = ""
      root.identityPrimaryConfirm = false
      root.identityPrimaryRequest = ""
      root.directReinviteClearConfirm = false
      root.directReinviteRequest = ""
    }
    if (root.moreSection !== "identity")
      root.resetIdentityControls()
  }

  function errorText(code) {
    if (code === "locked")
      return "Unlock your identity to continue."
    if (code === "unsupported")
      return "That is not a Harbor invite."
    if (code === "helper_down")
      return "Harbor is restarting."
    if (code === "helper_incompatible")
      return "Harbor helper needs to be restarted."
    if (code === "helper_handshake_pending")
      return "Harbor is still restoring queued events."
    if (code === "helper_event_overflow")
      return "Some queued live events were compacted; history was resynchronized."
    if (code === "helper_event_invalid")
      return "Harbor received an invalid response from the running helper."
    if (code === "file_failed")
      return "File transfer failed."
    if (code === "avatar_failed")
      return "Avatar image is invalid or larger than 512 KiB."
    if (code === "nickname_invalid")
      return "Nickname must contain 1–18 valid characters."
    if (code === "nickname_update_failed")
      return "Nickname update failed. Try again."
    if (code === "nickname_group_sync_failed")
      return "Nickname saved; group updates are unconfirmed."
    if (code === "identity_changed")
      return "Identity changed. Pending actions were discarded."
    if (code === "identity_backup_failed")
      return "Could not create a safe identity backup."
    if (code === "runtime_marker_failed")
      return "Your identity change is saved, but Harbor could not update its runtime file. Free some disk space, then restart Harbor; until then, quitting may leave it running."
    if (code === "identity_backup_cleanup_failed")
      return "An old identity recovery backup could not be removed."
    if (code === "identity_passphrase_required")
      return "Enter the imported identity's passphrase first."
    if (code === "identity_import_failed")
      return "Identity file or passphrase is invalid."
    if (code === "identity_state_archive_failed")
      return "Could not archive the previous identity's local data."
    if (code === "identity_rollback_failed")
      return "Identity restore failed. The backup was kept in the Harbor data folder."
    if (code === "identity_missing")
      return "Your existing Harbor identity is unavailable. No replacement identity was created. Restore or import the original identity."
    if (code === "identity_mismatch")
      return "The active identity does not match Harbor's protected identity record. No contact state was changed."
    if (code === "identity_guard_invalid")
      return "Harbor could not verify the protected identity state and stopped before creating a replacement."
    if (code === "identity_recovery_degraded")
      return "Your active identity is saved, but its additional recovery copy could not be updated. Export an identity bundle before relying on automatic recovery."
    if (code === "identity_primary_uncertain")
      return "Harbor could not confirm that the latest identity/contact change reached disk. The helper stopped using that identity; restart Harbor and verify the result before retrying."
    if (code === "invite_self")
      return "This invite belongs to your own identity."
    if (code === "contact_exists")
      return "This person is already in your contacts. Remove the old contact on both devices before using a fresh invite."
    if (code === "contact_limit")
      return "The direct-contact limit has been reached."
    if (code === "invite_rejected")
      return "The invite could not be added. Create a fresh invite and try it once on the other device."
    if (code === "nospam_rotate_failed")
      return "The invite was cleared, but its one-use address could not be refreshed."
    if (code === "safety_key_changed")
      return "This contact's encryption identity changed. Remove the old contact state on both devices before exchanging a fresh invite."
    if (code === "group_registry_failed")
      return "Could not safely save private group state."
    if (code === "direct_state_migration_failed")
      return "Legacy direct-chat state could not be migrated safely."
    if (code === "direct_state_reinvite_required")
      return "Your Harbor identity and contacts are intact. Some older direct-chat encryption state was safely archived and requires fresh invites."
    return code
  }

  function connectionLabel() {
    if (omaq.connectionState === "online")
      return "Online"
    if (omaq.connectionState === "locked")
      return "Locked"
    if (omaq.connectionState === "reconnecting")
      return "Reconnecting…"
    return "Connecting…"
  }

  function contactStatus(online) {
    if (omaq.connectionState !== "online")
      return omaq.connectionState === "reconnecting" ? "reconnecting…" : "connecting…"
    return online ? "online" : "offline"
  }

  function shortInvite(u) {
    if (!u)
      return ""
    if (u.length <= 40)
      return u
    return u.slice(0, 20) + "…" + u.slice(-12)
  }

  function inviteRemainingText() {
    var remaining = root.inviteRemainingSeconds
    var hours = Math.floor(remaining / 3600)
    var minutes = Math.floor((remaining % 3600) / 60)
    var seconds = remaining % 60
    function two(value) { return value < 10 ? "0" + value : String(value) }
    return two(hours) + ":" + two(minutes) + ":" + two(seconds)
  }

  function nextInviteActionRequest() {
    root.inviteActionSequence++
    return "invite-" + Date.now().toString(36) + "-" +
      root.inviteActionSequence.toString(36) + "-" +
      Math.floor(Math.random() * 0x100000000).toString(36)
  }

  function failInviteAction(message) {
    inviteActionTimer.stop()
    root.inviteActionPending = false
    root.inviteActionMode = ""
    root.inviteActionRequest = ""
    root.inviteActionGeneration = -1
    root.inviteFeedback = String(message || "Invite action failed. Try again.")
    root.inviteFeedbackError = true
  }

  function startInviteCreate(mode) {
    if (root.inviteActionPending)
      return false
    omaq.clearRequestError(root.inviteFeedbackRequest)
    root.inviteFeedbackRequest = ""
    if (mode !== "replace-create") {
      root.inviteActionRequireApproval = !root.deviceInviteMode && root.inviteRequireApproval
      root.inviteActionLifetime = root.deviceInviteMode ? 300 : 86400
    }
    root.inviteActionMode = String(mode || "create")
    root.inviteActionRequest = root.nextInviteActionRequest()
    root.inviteActionGeneration = Number(omaq.reconnectGeneration || 0)
    root.inviteActionPending = true
    root.inviteFeedback = "Creating invite…"
    root.inviteFeedbackError = false
    if (!omaq.createInvite(root.inviteActionRequest, root.inviteActionRequireApproval, root.inviteActionLifetime)) {
      root.failInviteAction("Harbor is not ready to create an invite.")
      return false
    }
    inviteActionTimer.restart()
    return true
  }

  function startInviteRevoke(replaceAfter) {
    if (root.inviteActionPending)
      return false
    root.inviteConfirmMode = ""
    omaq.clearRequestError(root.inviteFeedbackRequest)
    root.inviteFeedbackRequest = ""
    if (replaceAfter) {
      root.inviteActionRequireApproval = !root.deviceInviteMode && root.inviteRequireApproval
      root.inviteActionLifetime = root.deviceInviteMode ? 300 : 86400
    }
    root.inviteActionMode = replaceAfter ? "replace-revoke" : "revoke"
    root.inviteActionRequest = root.nextInviteActionRequest()
    root.inviteActionGeneration = Number(omaq.reconnectGeneration || 0)
    root.inviteActionPending = true
    root.inviteFeedback = replaceAfter ? "Revoking old invite…" : "Revoking invite…"
    root.inviteFeedbackError = false
    if (!omaq.revokeInvite(root.inviteActionRequest)) {
      root.failInviteAction("Harbor is not ready to revoke this invite.")
      return false
    }
    inviteActionTimer.restart()
    return true
  }

  function copyInvite() {
    if (!omaq.inviteUrl || root.inviteRemainingSeconds <= 0)
      return
    Quickshell.execDetached(["wl-copy", "-n", omaq.inviteUrl])
    root.copied = true
    copiedTimer.restart()
  }

  function copySafetyCode() {
    if (root.currentSafetyCode === "")
      return
    Quickshell.execDetached([
      "bash", "-c",
      "if command -v wl-copy >/dev/null 2>&1; then printf '%s' \"$1\" | wl-copy -n; elif command -v xclip >/dev/null 2>&1; then printf '%s' \"$1\" | xclip -selection clipboard; fi",
      "omaq-copy-safety", root.currentSafetyCode
    ])
    root.safetyCopied = true
    safetyCopiedTimer.restart()
  }

  function selectSafetyContact(id) {
    if (!omaq.selectDirect(String(id || "")))
      return false
    root.safetyCopied = false
    root.safetyCodeVisible = false
    return true
  }

  function showSafetyCode() {
    root.safetyCopied = false
    root.safetyCodeVisible = true
    omaq.getSafety(omaq.selectedDirectId)
  }

  function hideSafetyCode() {
    root.safetyCodeVisible = false
    root.safetyCopied = false
  }

  function openDeviceInvite() {
    root.dismissTransientSections()
    root.settingsPage = "devices"
    root.deviceInviteMode = true
    root.inviteOpen = true
    root.inviteNow = Math.floor(Date.now() / 1000)
    if (omaq.inviteUrl) root.inviteConfirmMode = "replace"
    else root.startInviteCreate("create")
  }

  function toggleInvite() {
    var open = !root.inviteOpen
    root.dismissTransientSections()
    root.inviteOpen = open
    if (open)
      root.inviteNow = Math.floor(Date.now() / 1000)
    if (open && !omaq.inviteUrl)
      root.startInviteCreate("create")
  }

  function toggleJoin() {
    var open = !root.showJoin
    root.dismissTransientSections()
    root.showJoin = open
  }

  function openChat() {
    var open = !root.chatPickerOpen
    root.dismissTransientSections()
    root.chatPickerOpen = open
    if (open)
      omaq.sendOp({ op: "status" })
  }

  function openRailAdvanced(section) {
    var key = String(section || "chat")
    var open = !(root.moreOpen && root.moreSection === key)
    root.dismissTransientSections()
    if (open) {
      root.moreOpen = true
      root.moreSection = key
    }
  }

  function openRailFontSize() { root.openSettingsPage("appearance") }
  function openRailTheme() { root.openSettingsPage("appearance") }
  function openRailSounds() { root.openSettingsPage("notifications") }

  function friendStatus(friend) {
    if (omaq.connectionState !== "online")
      return omaq.connectionState === "reconnecting" ? "reconnecting…" : "connecting…"
    var status = String(friend && friend.status || "")
    if (status === "afk")
      return "afk"
    return friend && friend.online ? "online" : "offline"
  }

  function orderedFriendCells(columnCount) {
    var friends = omaq.friends || []
    var columns = Math.max(1, Math.floor(Number(columnCount) || 1))
    var pageSize = columns * 5
    var cells = []
    for (var page = 0; page * pageSize < friends.length; page++) {
      var remaining = Math.min(pageSize, friends.length - page * pageSize)
      var rows = Math.min(5, remaining)
      for (var row = 0; row < rows; row++)
        for (var column = 0; column < columns; column++) {
          var source = page * pageSize + column * 5 + row
          cells.push(source < Math.min(friends.length, (page + 1) * pageSize)
            ? friends[source] : null)
        }
    }
    return cells
  }

  function onlineFriendCount() {
    var friends = omaq.friends || []
    var count = 0
    for (var i = 0; i < friends.length; i++)
      if (root.friendStatus(friends[i]) === "online")
        count++
    return count
  }

  function friendStatusDotColor(friend) {
    var status = root.friendStatus(friend)
    if (status === "online")
      return root.onlineStatusColor
    if (status === "afk")
      return Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.56)
    return Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.30)
  }

  function friendStatusColor(friend) {
    var status = root.friendStatus(friend)
    if (status === "online")
      return root.foreground
    if (status === "afk")
      return Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.72)
    return Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.48)
  }

  function friendKey(id) {
    var friendId = String(id || "")
    var friends = omaq.friends || []
    for (var i = 0; i < friends.length; i++)
      if (String(friends[i].id || "") === friendId)
        return String(friends[i].key || "")
    return ""
  }

  function friendMatches(id, expectedKey) {
    var key = String(expectedKey || "")
    return /^[0-9a-f]{64}$/.test(key) && root.friendKey(id) === key
  }

  function groupInviteCandidateMatches(groupId, id, expectedKey) {
    return omaq.groupInviteCandidateMatches(String(groupId || ""),
      String(id || ""), String(expectedKey || ""))
  }

  function clearStaleGroupInviteSelection() {
    if (root.groupInviteFriendId === "" ||
        root.groupInviteCandidateMatches(omaq.lastGroup,
          root.groupInviteFriendId, root.groupInviteFriendKey))
      return
    root.groupInviteGroupId = ""
    root.groupInviteFriendId = ""
    root.groupInviteFriendKey = ""
    root.groupInviteRequest = ""
    root.groupInviteGeneration = -1
    root.groupInviteFeedback = ""
  }

  function themedRadius(height) {
    var value = Number(root.controlRadius)
    var limit = Math.max(0, Number(height || root.actionButtonHeight) / 2)
    if (!isFinite(value) || value < 0)
      value = Number(root.panelRadius)
    if (!isFinite(value) || value < 0)
      value = 0
    return Math.min(value, limit)
  }

  function localFileUrl(path) {
    var parts = String(path || "").split("/")
    var i
    for (i = 0; i < parts.length; i++)
      parts[i] = encodeURIComponent(parts[i])
    return "file://" + parts.join("/")
  }

  function selectedLocalPath(url) {
    var value = String(url || "")
    if (value.indexOf("file:///") !== 0)
      return ""
    try {
      var path = decodeURIComponent(value.slice(7))
      return path.length < 512 && path.indexOf("\u0000") < 0 ? path : ""
    } catch (error) { return "" }
  }

  function pickSelfAvatar() {
    avatarPick.identity = omaq.identityFingerprint
    avatarPick.open()
  }

  function identityPassphraseStats(value) {
    var text = String(value || "")
    var bytes = 0
    var characters = 0
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i)
      if ((code < 0x20 && code !== 9) || code === 0x7f)
        return { valid: false, bytes: bytes, characters: characters }
      if (code < 0x80) {
        bytes += 1
      } else if (code < 0x800) {
        bytes += 2
      } else if (code >= 0xd800 && code <= 0xdbff) {
        if (i + 1 >= text.length)
          return { valid: false, bytes: bytes, characters: characters }
        var low = text.charCodeAt(i + 1)
        if (low < 0xdc00 || low > 0xdfff)
          return { valid: false, bytes: bytes, characters: characters }
        bytes += 4
        i++
      } else if (code >= 0xdc00 && code <= 0xdfff) {
        return { valid: false, bytes: bytes, characters: characters }
      } else {
        bytes += 3
      }
      characters++
    }
    return { valid: bytes > 0 && bytes <= 128, bytes: bytes,
      characters: characters }
  }

  function identityPathValid(value) {
    var text = String(value || "")
    if (text.length === 0 || text.charAt(0) !== "/" || text.indexOf("..") >= 0)
      return false
    var bytes = 0
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i)
      if (code < 0x20 || code === 0x7f)
        return false
      if (code < 0x80) {
        bytes += 1
      } else if (code < 0x800) {
        bytes += 2
      } else if (code >= 0xd800 && code <= 0xdbff) {
        if (i + 1 >= text.length)
          return false
        var low = text.charCodeAt(i + 1)
        if (low < 0xdc00 || low > 0xdfff)
          return false
        bytes += 4
        i++
      } else if (code >= 0xdc00 && code <= 0xdfff) {
        return false
      } else {
        bytes += 3
      }
    }
    return bytes < 512
  }

  function identityExistingPassphraseValid(value) {
    return root.identityPassphraseStats(value).valid
  }

  function identityNewPassphraseValid(value) {
    var stats = root.identityPassphraseStats(value)
    return stats.valid && stats.characters >= 8
  }

  function identityFailureText(code) {
    if (code === "locked")
      return "The identity passphrase is incorrect."
    if (code === "identity_exists")
      return "An identity already exists. Use Import identity to continue."
    if (code === "identity_passphrase_required")
      return "Enter the imported identity's passphrase first."
    if (code === "identity_import_failed")
      return "Identity file or passphrase is invalid."
    if (code === "busy")
      return "Finish active calls, transfers, invites, or read receipts first."
    if (code === "unsupported")
      return "This identity action is not supported by the running helper."
    if (code === "forbidden") {
      if (root.identityAction === "protect")
        return omaq.saveProtected ? "Your identity already has a passphrase."
          : "Use at least 8 characters and at most 128 bytes."
      if (root.identityAction === "unprotect")
        return "The current identity passphrase is incorrect."
      if (root.identityAction === "export")
        return "The identity could not be exported to that path."
    }
    return root.errorText(code)
  }

  function clearIdentityFeedback() {
    var request = root.identityFeedbackRequest
    root.identityFeedback = ""
    root.identityFeedbackRequest = ""
    root.identityFeedbackError = false
    omaq.clearIdentityError(request)
  }

  function finishIdentityAction(success, message) {
    identityActionTimer.stop()
    root.identityActionPending = false
    root.identityFeedbackError = !success
    root.identityFeedback = String(message || "")
    root.restorePassword = ""
    root.restoreAfterValidation = false
    root.identityAction = ""
    root.identityRequest = ""
    passField.text = ""
    unlockField.text = ""
  }

  function runIdentityAction(action, path, secret) {
    if (root.identityActionPending)
      return false
    var key = String(action || "")
    if (key !== "unlock" && !omaq.supportsIdentityActions) {
      root.identityFeedbackError = true
      root.identityFeedback = "Update the local Harbor helper before changing identity settings."
      return false
    }
    var selectedPath = String(path || "").trim()
    var passphrase = secret === undefined ? passField.text : String(secret || "")
    var sent = false
    if ((key === "export" || key === "import" || key === "replace") &&
        !root.identityPathValid(selectedPath)) {
      root.identityFeedbackError = true
      root.identityFeedback = "Choose a valid absolute identity-bundle path."
      return false
    }
    if (key === "protect" && !root.identityNewPassphraseValid(passphrase)) {
      root.identityFeedbackError = true
      root.identityFeedback = "Use at least 8 characters and at most 128 bytes."
      return false
    }
    if ((key === "unlock" || key === "unprotect") &&
        !root.identityExistingPassphraseValid(passphrase)) {
      root.identityFeedbackError = true
      root.identityFeedback = "Enter the current identity passphrase."
      return false
    }
    if ((key === "import" || key === "replace") && passphrase !== "" &&
        !root.identityExistingPassphraseValid(passphrase)) {
      root.identityFeedbackError = true
      root.identityFeedback = "The imported passphrase is longer than 128 bytes or invalid."
      return false
    }
    root.identityRequestSequence = root.identityRequestSequence + 1
    root.identityRequest = Date.now().toString(36) + "-identity-" +
      root.identityRequestSequence.toString(36) + "-" +
      Math.floor(Math.random() * 0x100000000).toString(36)
    if (key === "import" && root.restoreAfterValidation)
      root.restorePassword = passphrase
    root.identityAction = key
    root.identityFeedbackRequest = root.identityRequest
    root.identityActionPending = true
    root.identityFeedbackError = false
    root.identityFeedback = key === "export" ? "Saving backup…"
      : key === "import" ? "Checking backup…"
      : key === "replace" ? "Restoring backup…"
      : key === "unprotect" ? "Removing identity protection…"
      : key === "unlock" ? "Unlocking identity…"
      : "Protecting identity…"
    if (key === "unlock")
      sent = omaq.unlockIdentity(passphrase, root.identityRequest)
    else if (key === "protect")
      sent = omaq.protectIdentity(passphrase, root.identityRequest)
    else if (key === "unprotect")
      sent = omaq.unprotectIdentity(passphrase, root.identityRequest)
    else if (key === "export")
      sent = omaq.exportIdentity(selectedPath, root.identityRequest)
    else if (key === "import")
      sent = omaq.inspectIdentity(selectedPath, passphrase, root.identityRequest)
    else if (key === "replace")
      sent = omaq.importIdentity(selectedPath, true, passphrase, root.identityRequest)
    passField.text = ""
    unlockField.text = ""
    if (!sent) {
      root.finishIdentityAction(false, "Harbor is not ready for that identity action.")
      return false
    }
    identityActionTimer.restart()
    return true
  }

  function startIdentityPicker(mode) {
    if (!omaq.supportsIdentityActions || root.identityActionPending || identityPick.visible)
      return
    root.identityPickerMode = String(mode || "import")
    root.identityPickerExitCode = -1
    root.identityPickerStreamDone = false
    root.identityActionPending = true
    omaq.clearIdentityError(root.identityFeedbackRequest)
    root.identityFeedbackRequest = ""
    root.identityFeedbackError = false
    root.identityFeedback = root.identityPickerMode === "export"
      ? "Choose where to save this computer’s backup."
      : "Choose a Harbor backup to check."
    identityPick.identity = omaq.identityFingerprint
    identityPick.open()
  }

  function finishIdentityPicker(path, code) {
    var mode = root.identityPickerMode
    root.identityPickerExitCode = -1
    root.identityPickerStreamDone = false
    root.identityPickerMode = ""
    root.identityActionPending = false
    if (code === 0 && path !== "" && !root.identityPathValid(path)) {
      root.identityFeedbackError = true
      root.identityFeedback = "The selected identity-bundle path is invalid."
      return
    }
    if (code !== 0 || path === "") {
      if (code !== 0 && code !== 1) {
        root.identityFeedbackError = true
        root.identityFeedback = "No supported file picker is available."
      } else {
        root.identityFeedbackError = false
        root.identityFeedback = ""
      }
      return
    }
    if (mode === "export") {
      root.runIdentityAction("export", path)
      return
    }
    importPath.text = path
    if (mode === "replace") {
      root.restoreAfterValidation = true
      if (!root.runIdentityAction("import", path)) root.restoreAfterValidation = false
      return
    }
    root.runIdentityAction("import", path)
  }

  function resetIdentityControls() {
    if (!root.identityActionPending && !identityPick.visible) {
      var feedbackRequest = root.identityFeedbackRequest
      root.identityAction = ""
      root.identityRequest = ""
      root.identityFeedback = ""
      root.identityFeedbackRequest = ""
      root.identityFeedbackError = false
      passField.text = ""
      unlockField.text = ""
      importPath.text = ""
      omaq.clearIdentityError(feedbackRequest)
    }
    root.replaceIdentityConfirm = false
    root.replaceIdentityPath = ""
  }

  function friendName(id) {
    var key = String(id || "")
    var friends = omaq.friends || []
    for (var i = 0; i < friends.length; i++)
      if (String(friends[i].id || "") === key)
        return String(friends[i].name || ("Friend " + key))
    return key ? "Friend " + key : ""
  }

  function openFriend(id, name) {
    if (!id || !omaq.selectDirect(String(id)))
      return
    if (chatSurface) {
      chatSurface.openConversation(String(id), name || "")
    }
    omaq.markConversationRead(String(id))
    root.close()
  }

  function openGroup(id) {
    var groupId = String(id || "")
    if (!omaq.selectGroup(groupId, true))
      return
    if (chatSurface) {
      chatSurface.openConversation(groupId, omaq.groupName(groupId))
    }
    omaq.markConversationRead(groupId)
    root.close()
  }

  function openDemo() {
    if (chatSurface)
      chatSurface.openDemo()
    root.close()
  }

  readonly property string chatTheme: {
    var v = root.settings && root.settings.chatTheme
    return v ? String(v) : "system"
  }

  function verifyPersistedSettings(raw) {
    if (!root.settingsPersistencePending)
      return
    var config
    try { config = JSON.parse(String(raw || "")) } catch (error) {
      root.settingsPersistenceWarning = "This setting is active for this session but could not be saved."
      return
    }
    var candidates = []
    var layout = config && config.bar && config.bar.layout
    var sections = ["left", "center", "right"]
    var section
    if (layout) {
      for (section = 0; section < sections.length; section++) {
        var entries = layout[sections[section]] || []
        for (var entryIndex = 0; entryIndex < entries.length; entryIndex++)
          candidates.push(entries[entryIndex])
      }
    }
    var plugins = config && Array.isArray(config.plugins) ? config.plugins : []
    for (var pluginIndex = 0; pluginIndex < plugins.length; pluginIndex++)
      candidates.push(plugins[pluginIndex])
    var expected = root.settingsPersistenceExpected || {}
    var matched = false
    for (var candidateIndex = 0; candidateIndex < candidates.length; candidateIndex++) {
      var candidate = candidates[candidateIndex]
      if (!candidate || String(candidate.id || "") !== root.moduleName)
        continue
      matched = true
      for (var key in expected)
        if (key !== "id" && candidate[key] !== expected[key]) {
          matched = false
          break
        }
      if (matched)
        break
    }
    if (!matched && root.settingsPersistenceAttempts < 4) {
      root.settingsPersistenceAttempts = root.settingsPersistenceAttempts + 1
      settingsVerifyTimer.restart()
      return
    }
    root.settingsPersistencePending = false
    root.settingsPersistenceWarning = matched ? "" :
      "This setting is active for this session but could not be saved."
  }

  function persistSettings(values) {
    var entry = { id: root.moduleName }
    var changed = false
    var existing
    for (existing in root.settings)
      if (existing !== "id")
        entry[existing] = root.settings[existing]
    var key
    for (key in values) {
      if (entry[key] !== values[key])
        changed = true
      entry[key] = values[key]
    }
    root.settings = entry
    if (!root.bar || !root.bar.shell ||
        typeof root.bar.shell.updateEntryInline !== "function") {
      root.settingsPersistencePending = false
      root.settingsPersistenceWarning = "This setting is active for this session but could not be saved."
      return false
    }
    try {
      var result = root.bar.shell.updateEntryInline(root.moduleName, entry)
      if (changed && result === false) {
        // False also means the host already has this exact entry; verify the
        // durable file before deciding whether persistence failed.
        root.settingsPersistenceExpected = entry
        root.settingsPersistenceAttempts = 0
        root.settingsPersistencePending = true
        settingsVerifyTimer.restart()
        return true
      }
      if (changed) {
        root.settingsPersistenceExpected = entry
        root.settingsPersistenceAttempts = 0
        root.settingsPersistencePending = true
        settingsVerifyTimer.restart()
      }
      return true
    } catch (error) {
      root.settingsPersistencePending = false
      root.settingsPersistenceWarning = "This setting is active for this session but could not be saved."
      return false
    }
  }

  function setTheme(name) {
    root.persistSettings({ chatTheme: name })
  }

  readonly property real messageScale: {
    var value = Number(root.settings && root.settings.messageScale)
    return [0.9, 1.0, 1.1, 1.2, 1.4].indexOf(value) >= 0 ? value : 1.0
  }

  function setMessageScale(value) {
    var scale = Number(value)
    if ([0.9, 1.0, 1.1, 1.2, 1.4].indexOf(scale) < 0)
      return
    root.persistSettings({ messageScale: scale })
  }

  readonly property string notificationSound: {
    var value = String(root.settings && root.settings.sound || "knock")
    if (value === "custom")
      return value
    for (var i = 0; i < root.bundledNotificationSounds.length; i++)
      if (String(root.bundledNotificationSounds[i].id || "") === value)
        return value
    return "knock"
  }
  readonly property string notificationSoundPath:
    String(root.settings && root.settings.soundCustomPath || "")
  readonly property string notificationSoundId:
    String(root.settings && root.settings.soundCustomId || "")

  function notificationSoundSelected(option) {
    var sound = option || ({})
    if (sound.custom)
      return root.notificationSound === "custom" &&
        ((root.notificationSoundId !== "" &&
          root.notificationSoundId === String(sound.soundId || "")) ||
         (root.notificationSoundId === "" &&
          root.notificationSoundPath === String(sound.path || "")))
    return root.notificationSound === String(sound.id || "")
  }

  function selectedCustomSoundOption() {
    for (var i = 0; i < root.notificationSounds.length; i++)
      if (root.notificationSounds[i].custom &&
          root.notificationSoundSelected(root.notificationSounds[i]))
        return root.notificationSounds[i]
    return null
  }

  function setNotificationSound(option) {
    var sound = option || ({})
    var selectedSound = sound.custom ? "custom" : String(sound.id || "off")
    var selectedPath = sound.custom ? String(sound.path || "") : ""
    if (sound.custom && (selectedPath.charAt(0) !== "/" ||
        !/^[0-9a-f]{32}$/.test(String(sound.soundId || ""))))
      return
    root.persistSettings({ sound: selectedSound, soundCustomPath: selectedPath,
      soundCustomId: sound.custom ? String(sound.soundId || "") : "" })
    root.soundRemoveConfirm = false
    if (chatSurface)
      chatSurface.previewSound(selectedSound)
  }

  function startSoundPicker() {
    if (!omaq.supportsCustomSounds || soundPick.visible ||
        root.soundActionRequest !== "")
      return
    root.soundPickerExitCode = -1
    root.soundPickerStreamDone = false
    root.soundFeedback = "Choose a PCM WAV notification sound to import."
    root.soundFeedbackError = false
    soundPick.identity = omaq.identityFingerprint
    soundPick.open()
  }

  function finishSoundPicker(path, code) {
    root.soundPickerExitCode = -1
    root.soundPickerStreamDone = false
    if (code !== 0 || path === "") {
      root.soundFeedbackError = code !== 0 && code !== 1
      root.soundFeedback = root.soundFeedbackError
        ? "No supported file picker is available." : ""
      return
    }
    if (path.charAt(0) !== "/" || path.length > 511) {
      root.soundFeedbackError = true
      root.soundFeedback = "Choose a valid absolute sound-file path."
      return
    }
    var request = omaq.nextSoundRequest("import")
    if (!omaq.importCustomSound(path, request)) {
      root.soundFeedbackError = true
      root.soundFeedback = "Harbor is not ready to import that sound."
      return
    }
    root.soundAction = "import"
    root.soundActionRequest = request
    root.soundFeedback = "Importing notification sound…"
    root.soundFeedbackError = false
    soundActionTimer.restart()
  }

  function requestSoundRemoval(option) {
    var sound = option || ({})
    if (!sound.custom || !/^[0-9a-f]{32}$/.test(String(sound.soundId || "")))
      return
    root.soundRemoveId = String(sound.soundId)
    root.soundRemoveLabel = String(sound.label || "Custom sound")
    root.soundRemovePath = String(sound.path || "")
    root.soundRemoveConfirm = true
  }

  function confirmSoundRemoval() {
    if (!root.soundRemoveConfirm || root.soundActionRequest !== "" ||
        !/^[0-9a-f]{32}$/.test(root.soundRemoveId))
      return
    var request = omaq.nextSoundRequest("remove")
    if (!omaq.removeCustomSound(root.soundRemoveId, request)) {
      root.soundFeedbackError = true
      root.soundFeedback = "Harbor is not ready to remove that sound."
      return
    }
    root.soundAction = "remove"
    root.soundActionRequest = request
    root.soundRemoveConfirm = false
    root.soundFeedback = "Removing managed notification sound…"
    root.soundFeedbackError = false
    soundActionTimer.restart()
  }

  function toggleThemeSettings() {
    root.themeOpen = !root.themeOpen
    if (root.themeOpen) {
      root.soundOpen = false
      root.fontSizeOpen = false
    }
  }

  function toggleSoundSettings() {
    root.soundOpen = !root.soundOpen
    if (root.soundOpen) {
      root.themeOpen = false
      root.fontSizeOpen = false
    }
  }

  function parseSystemColors(raw) {
    var found = ["", "", "", "", "", "", "", ""]
    var semanticIndex = {
      background: 0,
      red: 1,
      green: 2,
      yellow: 3,
      blue: 4,
      magenta: 5,
      cyan: 6,
      foreground: 7
    }
    var lines = String(raw || "").split("\n")
    var i
    for (i = 0; i < lines.length; i++) {
      var semanticMatch = lines[i].match(
        /^\s*(background|red|green|yellow|blue|magenta|cyan|foreground)\s*=\s*["']?(#[0-9A-Fa-f]{6})/)
      if (semanticMatch)
        found[semanticIndex[semanticMatch[1]]] = semanticMatch[2]
    }
    for (i = 0; i < lines.length; i++) {
      var ansiMatch = lines[i].match(/^\s*color([0-7])\s*=\s*["']?(#[0-9A-Fa-f]{6})/)
      if (ansiMatch)
        found[Number(ansiMatch[1])] = ansiMatch[2]
    }
    var n
    for (n = 0; n < 8; n++) {
      if (!found[n])
        found[n] = n === 0 ? "#101315" : (n === 7 ? "#cacccc" : "#888888")
    }
    root.systemColors = found
  }

  function paletteColors(id) {
    if (id === "system")
      return root.systemColors
    return Model.themeColors(id)
  }

  function paletteLabel(id) {
    if (id === "system") {
      if (root.systemThemeName && root.systemThemeName !== "theme" && root.systemThemeName !== "System")
        return "System · " + root.systemThemeName
      return "System"
    }
    return Model.themeName(id)
  }

  function publishConnectedGeometry() {
    if (!bar || typeof bar.publishConnectedPanel !== "function")
      return
    var screen = popup.screen
    var name = screen ? String(screen.name || "") : ""
    if (!connectedSurfaceEnabled || !opened || !screen || !name) {
      if (typeof bar.clearConnectedPanel === "function")
        bar.clearConnectedPanel(root, name)
      return
    }
    bar.publishConnectedPanel(root, name, card.x + caretCenterX, connectionReveal)
  }

  function placeCard() {
    var win = button.QsWindow ? button.QsWindow.window : null
    if (!win || !button || !popup.screen)
      return
    var p = button.mapToItem(win.contentItem, 0, 0)
    var gap = connectedSurfaceEnabled ? Style.space(6) : Style.gapsOut
    var margin = gap
    var sw = popup.screen.width
    var sh = popup.screen.height
    var horizontalBar = root.barPos === "top" || root.barPos === "bottom"
    root.cardHeightLimit = Math.max(Style.space(260),
      sh - (horizontalBar ? root.barThickness + gap + margin : margin * 2))

    var x = p.x + button.width / 2 - card.width / 2
    var y = root.barThickness + gap
    if (root.barPos === "bottom") {
      y = sh - root.barThickness - gap - card.height
    } else if (root.barPos === "left") {
      x = root.barThickness + gap
      y = p.y + button.height / 2 - card.height / 2
    } else if (root.barPos === "right") {
      x = sw - root.barThickness - gap - card.width
      y = p.y + button.height / 2 - card.height / 2
    }
    x = Math.max(margin, Math.min(x, sw - card.width - margin))
    y = Math.max(margin, Math.min(y, sh - card.height - margin))
    card.x = Math.round(x)
    card.y = Math.round(y)
  }

  FileView {
    id: settingsVerifyFile
    path: root.bar && root.bar.shell && root.bar.shell.userConfigPath
      ? String(root.bar.shell.userConfigPath) : ""
    watchChanges: true
    printErrors: false
    onLoaded: root.verifyPersistedSettings(text())
    onLoadFailed: {
      if (root.settingsPersistencePending && root.settingsPersistenceAttempts < 4) {
        root.settingsPersistenceAttempts = root.settingsPersistenceAttempts + 1
        settingsVerifyTimer.restart()
      } else if (root.settingsPersistencePending) {
        root.settingsPersistencePending = false
        root.settingsPersistenceWarning =
          "This setting is active for this session but could not be saved."
      }
    }
    onFileChanged: reload()
  }

  Timer {
    id: settingsVerifyTimer
    interval: 500
    repeat: false
    onTriggered: {
      if (root.settingsPersistencePending && settingsVerifyFile.path !== "")
        settingsVerifyFile.reload()
    }
  }

  Service {
    id: omaq
    settings: root.settings
    onFriendsReadyChanged: if (root.opened && friendsReady) refreshConversationPreviews()
    onGroupsReadyChanged: if (root.opened && groupsReady) refreshConversationPreviews()
    onDeviceLinkInvitation: {
      if (!chatSurface.isSurfaceOwner) return
      root.dismissTransientSections()
      root.devicesOpen = true
      root.open()
      chatSurface.playSound()
    }
    onNotificationMuteRequested: function(muted) {
      root.persistSettings({ notificationMuted: muted })
    }
  }

  Dialogs.FileDialog {
    id: avatarPick
    property string identity: ""
    title: "Choose your profile picture"
    fileMode: Dialogs.FileDialog.OpenFile
    nameFilters: ["Images (*.png *.jpg *.jpeg *.webp)"]
    onAccepted: {
      var path = root.selectedLocalPath(selectedFile)
      if (path && identity === omaq.identityFingerprint)
        omaq.setAvatar(path)
    }
  }

  Dialogs.FileDialog {
    id: soundPick
    property string identity: ""
    title: "Import notification sound"
    fileMode: Dialogs.FileDialog.OpenFile
    nameFilters: ["PCM WAV audio (*.wav)"]
    onAccepted: root.finishSoundPicker(root.selectedLocalPath(selectedFile),
      identity === omaq.identityFingerprint ? 0 : 1)
    onRejected: root.finishSoundPicker("", 1)
  }

  Dialogs.FileDialog {
    id: identityPick
    property string identity: ""
    title: root.identityPickerMode === "export" ? "Save Harbor backup" : "Choose a Harbor backup"
    fileMode: root.identityPickerMode === "export"
      ? Dialogs.FileDialog.SaveFile : Dialogs.FileDialog.OpenFile
    nameFilters: ["Harbor identity (*.save)", "All files (*)"]
    defaultSuffix: "save"
    onAccepted: root.finishIdentityPicker(root.selectedLocalPath(selectedFile),
      identity === omaq.identityFingerprint ? 0 : 1)
    onRejected: root.finishIdentityPicker("", 1)
  }

  Timer {
    id: inviteClock
    interval: 1000
    repeat: true
    running: root.opened && root.inviteOpen && omaq.inviteUrl !== ""
    triggeredOnStart: true
    onTriggered: {
      root.inviteNow = Math.floor(Date.now() / 1000)
      if (omaq.inviteUrl !== "" && Number(omaq.inviteExpiresAt || 0) > 0 &&
          root.inviteRemainingSeconds <= 0) {
        omaq.inviteUrl = ""
        omaq.inviteExpiresAt = 0
        omaq.qrPath = ""
        root.copied = false
        root.inviteFeedback = "Invite expired. Create a new link."
        root.inviteFeedbackError = false
      }
    }
  }

  Timer {
    id: inviteActionTimer
    interval: 10000
    repeat: false
    onTriggered: {
      root.inviteActionPending = false
      root.inviteActionMode = ""
      root.inviteActionRequest = ""
      root.inviteFeedback = "Invite action timed out. Check Harbor status and try again."
      root.inviteFeedbackError = true
    }
  }

  Timer {
    id: nicknameSubmitTimer
    interval: 30000
    repeat: false
    onTriggered: {
      root.nicknameSubmitPending = false
      root.nicknameFeedbackRequest = root.nicknameRequest
      root.nicknameFeedback = "Nickname update timed out. Try again."
      root.nicknameFeedbackError = true
      root.nicknameRequest = ""
    }
  }

  Timer {
    id: soundActionTimer
    interval: 12000
    repeat: false
    onTriggered: {
      root.soundFeedback = "The sound action is delayed. Harbor will apply its correlated result after reconnecting."
      root.soundFeedbackError = true
    }
  }

  Timer {
    id: identityActionTimer
    interval: 20000
    repeat: false
    onTriggered: root.finishIdentityAction(false,
      "The identity action timed out. Check Harbor status and try again.")
  }

  FileView {
    path: Quickshell.env("HOME") + "/.local/state/omarchy/current/theme/colors.toml"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.parseSystemColors(text())
  }

  FileView {
    path: Quickshell.env("HOME") + "/.local/state/omarchy/current/theme.name"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      var n = String(text()).replace(/^\s+|\s+$/g, "")
      if (n)
        root.systemThemeName = n
    }
  }

  Process {
    command: ["readlink", "-f", Quickshell.env("HOME") + "/.local/state/omarchy/current/theme"]
    running: true
    stdout: SplitParser {
      onRead: function(line) {
        var parts = String(line).replace(/\s+$/, "").split("/")
        var name = parts.length ? parts[parts.length - 1] : ""
        if (name && name !== "theme" && root.systemThemeName === "System")
          root.systemThemeName = name
      }
    }
  }

  ChatSurface {
    id: chatSurface
    service: omaq
    bar: root.bar
    settings: root.settings
    instanceName: button.QsWindow && button.QsWindow.window &&
      button.QsWindow.window.screen ? String(button.QsWindow.window.screen.name || "default") : "default"
    onFormatToolbarToggled: function(enabled) {
      root.persistSettings({ formatToolbar: enabled })
    }
  }

  Timer {
    id: copiedTimer
    interval: 1400
    onTriggered: root.copied = false
  }

  Timer {
    id: safetyCopiedTimer
    interval: 1400
    onTriggered: root.safetyCopied = false
  }

  Timer {
    id: panelCallFeedbackTimer
    interval: 6000
    onTriggered: root.callFeedback = ""
  }

  Connections {
    target: omaq
    function onFriendsChanged() {
      if (root.removeContactPickerOpen || root.removeContactConfirm) {
        root.removeContactPickerOpen = false
        root.removeContactConfirm = false
        root.removeContactId = ""
        root.removeContactKey = ""
      }
      root.clearStaleGroupInviteSelection()
    }
    function onGroupsChanged() {
      root.clearStaleGroupInviteSelection()
    }
    function onCallStopTickChanged() {
      if (!omaq.incomingCall || omaq.lastCallStopConfirmed)
        return
      root.callFeedback = omaq.lastCallStopCode === "call_answer_failed"
        ? "Call could not be answered" : "Call control unavailable"
      panelCallFeedbackTimer.restart()
    }
    function onSoundTickChanged() {
      if (root.soundActionRequest === "" ||
          String(omaq.lastSoundRequest || "") !== root.soundActionRequest ||
          String(omaq.lastSoundOperation || "") !== root.soundAction)
        return
      soundActionTimer.stop()
      var action = root.soundAction
      root.soundActionRequest = ""
      root.soundAction = ""
      if (!omaq.lastSoundSucceeded) {
        root.soundFeedbackError = true
        root.soundFeedback = omaq.lastSoundCode === "invalid_sound"
          ? "Choose a valid PCM WAV file up to 8 MiB and 30 seconds."
          : (omaq.lastSoundCode === "sound_remove_failed"
            ? "The managed sound copy could not be removed." :
              "Custom sound storage is unavailable.")
        if (action === "remove" && root.soundRemoveId !== "")
          root.soundRemoveConfirm = true
        return
      }
      if (action === "import") {
        var selectedId = String(omaq.lastSoundSelected || "")
        var imported = null
        var sounds = omaq.customSounds || []
        for (var i = 0; i < sounds.length; i++)
          if (String(sounds[i].id || "") === selectedId) {
            imported = sounds[i]
            break
          }
        if (!imported) {
          root.soundFeedbackError = true
          root.soundFeedback = "The imported sound could not be verified."
          return
        }
        root.persistSettings({ sound: "custom",
          soundCustomPath: String(imported.path || ""),
          soundCustomId: String(imported.id || "") })
        root.soundFeedback = "Imported " + String(imported.label || "custom sound") + "."
        root.soundFeedbackError = false
        if (chatSurface)
          chatSurface.previewSound("custom")
      } else {
        if (root.notificationSound === "custom" &&
            root.notificationSoundPath === root.soundRemovePath)
          root.persistSettings({ sound: "off", soundCustomPath: "",
            soundCustomId: "" })
        root.soundFeedback = "Removed the Harbor-managed sound copy."
        root.soundFeedbackError = false
        root.soundRemoveId = ""
        root.soundRemoveLabel = ""
        root.soundRemovePath = ""
        root.soundRemoveConfirm = false
      }
    }
    function onInviteUrlChanged() {
      root.inviteNow = Math.floor(Date.now() / 1000)
      root.refreshPanelLayout()
      if (omaq.inviteUrl !== "")
        omaq.saveQr()
    }
    function onQrPathChanged() { root.refreshPanelLayout() }
    function onInviteActionTickChanged() {
      if (!root.inviteActionPending || root.inviteActionRequest === "" ||
          String(omaq.lastInviteRequest || "") !== root.inviteActionRequest)
        return
      var op = String(omaq.lastInviteAction || "")
      inviteActionTimer.stop()
      if (op === "revoke" && root.inviteActionMode === "replace-revoke") {
        root.inviteActionPending = false
        root.inviteActionRequest = ""
        root.startInviteCreate("replace-create")
      } else if (op === "revoke") {
        root.inviteActionPending = false
        root.inviteActionMode = ""
        root.inviteActionRequest = ""
        root.inviteActionGeneration = -1
        root.inviteFeedbackRequest = ""
        root.inviteFeedback = "Invite revoked."
        root.inviteFeedbackError = false
        root.copied = false
      } else if (op === "create") {
        var replaced = root.inviteActionMode === "replace-create"
        root.inviteActionPending = false
        root.inviteActionMode = ""
        root.inviteActionRequest = ""
        root.inviteActionGeneration = -1
        root.inviteFeedbackRequest = ""
        root.inviteFeedback = replaced ? "New invite created." : "Invite ready."
        root.inviteFeedbackError = false
      }
    }
    function onIdentityPrimaryTickChanged() {
      if (root.identityPrimaryRequest !== "" &&
          String(omaq.lastIdentityPrimaryRequest || "") === root.identityPrimaryRequest) {
        root.identityPrimaryRequest = ""
        root.identityPrimaryConfirm = false
      }
    }
    function onRedeemTickChanged() {
      if (root.redeemRequest !== "" &&
          String(omaq.lastRedeemRequest || "") === root.redeemRequest) {
        root.redeemRequest = ""
        root.redeemFeedbackRequest = ""
        root.redeemFeedback = omaq.lastRedeemKind === "group"
          ? "Group invite checked. Waiting for the incoming group request."
          : "Invite checked. Waiting for the other person to accept."
        root.redeemSafety = omaq.lastRedeemKind === "direct"
          ? String(omaq.lastRedeemSafety || "") : ""
        root.redeemDraft = ""
      }
    }
    function onDirectReinviteTickChanged() {
      if (root.directReinviteRequest !== "" &&
          String(omaq.lastDirectReinviteRequest || "") === root.directReinviteRequest) {
        root.directReinviteRequest = ""
        root.directReinviteClearConfirm = false
      }
    }
    function onGroupInviteSentTickChanged() {
      if (root.groupInviteFeedback === "Sending group invite…" &&
          String(omaq.lastGroupInviteSentGroup || "") === root.groupInviteGroupId &&
          String(omaq.lastGroupInviteSentFriend || "") === root.groupInviteFriendId &&
          String(omaq.lastGroupInviteSentRequest || "") === root.groupInviteRequest)
        root.groupInviteFeedback = "Invitation sent · waiting for acceptance"
    }
    function onGroupInviteFailedTickChanged() {
      if (root.groupInviteFeedback === "Sending group invite…" &&
          String(omaq.lastGroupInviteFailedGroup || "") === root.groupInviteGroupId &&
          String(omaq.lastGroupInviteFailedFriend || "") === root.groupInviteFriendId &&
          String(omaq.lastGroupInviteFailedRequest || "") === root.groupInviteRequest)
        root.groupInviteFeedback = omaq.lastGroupInviteFailedCode === "busy"
          ? "Recipient still has a group invitation waiting for a decision"
          : "Group invite failed"
    }
    function onReconnectGenerationChanged() {
      if (root.inviteActionPending && root.inviteActionGeneration >= 0 &&
          root.inviteActionGeneration !== Number(omaq.reconnectGeneration || 0))
        root.failInviteAction("Harbor restarted before the invite action completed.")
      if (root.identityPrimaryRequest !== "") {
        root.identityPrimaryRequest = ""
        root.identityPrimaryConfirm = false
      }
      if (root.directReinviteRequest !== "") {
        root.directReinviteRequest = ""
        root.directReinviteClearConfirm = false
      }
      if (root.redeemRequest !== "") {
        root.redeemFeedback = "Connection changed before the invite result was confirmed. Check your contacts before trying again."
        root.redeemFeedbackRequest = root.redeemRequest
        root.redeemSafety = ""
        root.redeemRequest = ""
      }
    }
    function onHelperInstanceGenerationChanged() {
      if (root.identityPrimaryRequest !== "") {
        root.identityPrimaryRequest = ""
        root.identityPrimaryConfirm = false
      }
      if (root.directReinviteRequest !== "") {
        root.directReinviteRequest = ""
        root.directReinviteClearConfirm = false
      }
      if (root.redeemRequest !== "") {
        root.redeemFeedback = "Harbor restarted before the invite result was confirmed. Check your contacts before trying again."
        root.redeemFeedbackRequest = root.redeemRequest
        root.redeemSafety = ""
        root.redeemRequest = ""
      }
      if (root.groupInviteFeedback === "Sending group invite…" &&
          root.groupInviteGeneration >= 0 &&
          root.groupInviteGeneration !== Number(omaq.helperInstanceGeneration || 0)) {
          root.groupInviteFeedback = "Group invite failed"
          root.groupInviteRequest = ""
          root.groupInviteGeneration = -1
        }
    }
    function onHelperCompatibilityChanged() {
      if (root.inviteActionPending && omaq.helperCompatibility === "incompatible")
        root.failInviteAction("The running helper does not support this invite action.")
      if (root.groupInviteFeedback === "Sending group invite…" &&
          omaq.helperCompatibility === "incompatible") {
        root.groupInviteFeedback = "Group invite failed"
        root.groupInviteRequest = ""
        root.groupInviteGeneration = -1
      }
    }
    function onIdentityActionTickChanged() {
      if (!root.identityActionPending || root.identityRequest === "")
        return
      var op = String(omaq.lastIdentityOp || "")
      var legacyUnlock = root.identityAction === "unlock" &&
        !omaq.supportsIdentityActions && op === "unlock"
      if (!legacyUnlock &&
          String(omaq.lastIdentityRequest || "") !== root.identityRequest)
        return
      if (root.identityAction === "unlock" && op === "unlock")
        root.finishIdentityAction(true, "Identity unlocked.")
      else if (root.identityAction === "protect" && op === "protect")
        root.finishIdentityAction(true, "Password protection enabled.")
      else if (root.identityAction === "unprotect" &&
               (op === "unprotect" || (op === "protect" && !omaq.lastIdentityProtected)))
        root.finishIdentityAction(true, "Password protection removed.")
      else if (root.identityAction === "export" && op === "export")
        root.finishIdentityAction(true, "Backup saved to " +
          String(omaq.lastIdentityPath || "the selected file") + ".")
      else if (root.identityAction === "import" && op === "inspect") {
        var restore = root.restoreAfterValidation
        var checkedPassword = root.restorePassword
        root.restoreAfterValidation = false
        root.finishIdentityAction(true, "Backup checked.")
        if (restore && root.settingsPage === "recovery") {
          root.restorePassword = checkedPassword
          root.replaceIdentityPath = importPath.text.trim()
          root.replaceIdentityConfirm = root.replaceIdentityPath !== ""
        }
      }
      else if (root.identityAction === "replace" && op === "import")
        root.finishIdentityAction(true,
          "Identity imported. Existing direct contacts must be removed on both sides and re-invited before messaging.")
    }
    function onLastErrorTickChanged() {
      if (root.inviteActionPending && root.inviteActionRequest !== "" &&
          String(omaq.lastErrorRequest || "") === root.inviteActionRequest) {
        var inviteError = String(omaq.lastError || "")
        root.inviteFeedbackRequest = root.inviteActionRequest
        root.failInviteAction(inviteError === "locked"
          ? "Unlock your identity before changing the invite."
          : inviteError === "no_ratchet"
            ? "Secure invitation setup is unavailable."
            : inviteError === "identity_changed"
              ? "Identity changed before the invite action completed."
              : inviteError === "unsupported"
                ? "This invite action is not supported by the running helper."
                : "Invite action failed. Try again.")
      }
      if (root.redeemRequest !== "" &&
          String(omaq.lastErrorRequest || "") === root.redeemRequest) {
        root.redeemFeedbackRequest = root.redeemRequest
        root.redeemFeedback = root.errorText(omaq.lastError)
        root.redeemSafety = ""
        root.redeemRequest = ""
      }
      if (root.identityPrimaryRequest !== "" &&
          String(omaq.lastErrorRequest || "") === root.identityPrimaryRequest) {
        root.identityPrimaryRequest = ""
        root.identityPrimaryConfirm = false
      }
      if (root.directReinviteRequest !== "" &&
          String(omaq.lastErrorRequest || "") === root.directReinviteRequest) {
        root.directReinviteRequest = ""
        root.directReinviteClearConfirm = false
      }
      if (root.identityActionPending && root.identityAction !== "" &&
          root.identityRequest !== "" &&
          String(omaq.lastErrorRequest || "") === root.identityRequest)
        root.finishIdentityAction(false, root.identityFailureText(omaq.lastError))
      else if (root.identityActionPending && root.identityAction === "unlock" &&
               !omaq.supportsIdentityActions &&
               String(omaq.lastErrorRequest || "") === "" &&
               ["locked", "forbidden"].indexOf(String(omaq.lastError || "")) >= 0)
        root.finishIdentityAction(false, root.identityFailureText(omaq.lastError))
    }
  }

  Connections {
    target: bar
    ignoreUnknownSignals: true
    function onActivePopoutChanged() {
      if (root.opened && bar.activePopout && bar.activePopout !== root)
        root.close()
    }
  }

  IpcHandler {
    target: "io.zet.harbor"
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function invite(): string { omaq.createInvite(); return "ok" }
    function demo(): string { root.openDemo(); return "ok" }
    function status(): string { return omaq.statusText }
    function unread(): string { return String(root.visibleUnreadCount) }
  }

  BarIconButton {
    id: button
    property real callPulseOpacity: 1.0
    slotSize: Math.max(Style.bar.iconCanvas + Style.space(6),
                       Style.bar.iconSlot - Style.space(2))
    opticalSize: Style.bar.iconCanvas + Style.space(2)
    anchors.fill: parent
    bar: root.bar
    text: omaq.incomingCall ? (Harbor.MaterialSymbols.ready ? "\ue0b0" : "?") : (omaq.pending ? "" : Harbor.MaterialSymbols.glyph("anchor"))
    fontFamily: omaq.incomingCall || !omaq.pending ? Harbor.MaterialSymbols.family : "monospace"
    active: omaq.incomingCall || omaq.pending
    activeColor: omaq.pending && !omaq.incomingCall
      ? (root.systemColors[1] || root.urgent)
      : (root.systemColors[1] || root.urgent)
    opacity: omaq.incomingCall ? callPulseOpacity : 1.0
    tooltipText: omaq.incomingCall
      ? "Incoming call"
      : (omaq.pending
        ? (omaq.pendingGroup ? "Group invite received" : "Friend request received")
        : "Harbor")
    onPressed: function(b) {
      if (b === Qt.RightButton)
        return
      if (omaq.incomingCall && omaq.lastCallConv) {
        root.openFriend(omaq.lastCallConv, root.friendName(omaq.lastCallConv))
        return
      }
      root.toggle()
    }

    SequentialAnimation on callPulseOpacity {
      running: omaq.incomingCall
      loops: Animation.Infinite
      NumberAnimation { to: 0.38; duration: 520; easing.type: Easing.InOutSine }
      NumberAnimation { to: 1.0; duration: 520; easing.type: Easing.InOutSine }
      onRunningChanged: if (!running) button.callPulseOpacity = 1.0
    }
  }

  Rectangle {
    id: unreadBadge
    visible: root.visibleUnreadCount > 0 &&
      (!root.settings || root.settings.notifyBadge !== false)
    width: Math.max(Style.space(12), unreadBadgeText.implicitWidth + Style.space(6))
    height: Style.space(12)
    radius: height / 2
    color: root.systemColors[1] || root.urgent
    border.width: 0
    anchors.verticalCenter: button.verticalCenter
    anchors.verticalCenterOffset: -Style.space(6)
    anchors.horizontalCenter: button.horizontalCenter
    anchors.horizontalCenterOffset: Style.space(7)
    z: 100

    SafeText {
      id: unreadBadgeText
      anchors.centerIn: parent
      text: root.visibleUnreadCount > 99 ? "99" : String(root.visibleUnreadCount)
      color: root.bar && "background" in root.bar ? root.bar.background : Color.background
      font.family: root.fontFamily
      font.pixelSize: Style.space(7)
      font.bold: true
    }
  }

  PanelWindow {
    id: popup
    visible: root.opened
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    screen: button.QsWindow && button.QsWindow.window ? button.QsWindow.window.screen : null

    property bool observedActiveFocus: false
    readonly property bool backingWindowActive: {
      var window = panelFocus.QsWindow.window
      return !!(window && window.active)
    }

    WlrLayershell.namespace: "harbor-panel"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: root.opened ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None

    anchors { top: true; bottom: true; left: true; right: true }

    // A stuck panel must never retain a desktop-sized Wayland input region.
    // Only the visible card is clickable; clicks elsewhere pass through.
    mask: Region { item: card }

    HyprlandFocusGrab {
      id: clickAwayGrab
      active: root.opened && popup.visible && !root.avatarRestorePending &&
        root.identityPickerMode === "" && !avatarPick.visible && !identityPick.visible &&
        !soundPick.visible
      windows: [popup]
      onCleared: if (root.opened && !root.avatarRestorePending &&
                     root.identityPickerMode === "" &&
                     !avatarPick.visible && !identityPick.visible && !soundPick.visible)
        root.close()
    }

    onVisibleChanged: {
      if (!visible) {
        observedActiveFocus = false
        return
      }
      root.cardHeightLimit = 0
      Qt.callLater(function() {
        if (!root.opened)
          return
        root.placeCard()
        root.publishConnectedGeometry()
        panelFocus.forceActiveFocus()
      })
    }
    onBackingWindowActiveChanged: {
      if (backingWindowActive) {
        observedActiveFocus = true
        return
      }
      if (!observedActiveFocus || !root.opened || avatarPick.visible ||
          identityPick.visible || soundPick.visible)
        return
      Qt.callLater(function() {
        if (root.opened && !popup.backingWindowActive &&
            !avatarPick.visible && !identityPick.visible && !soundPick.visible)
          root.close()
      })
    }

    Connections {
      target: popup.screen
      function onGeometryChanged() { if (root.opened) root.placeCard() }
    }

    Item {
      id: connectedSurface
      x: card.x
      y: root.barPos === "bottom" ? card.y : card.y - root.caretDepth
      width: card.width
      height: card.height
      visible: root.connectedSurfaceEnabled && root.opened && root.connectionReveal > 0
      z: 0

      Shape {
        anchors.left: parent.left
        anchors.top: parent.top
        width: parent.width
        height: parent.height + root.caretDepth
        visible: root.barPos !== "bottom"
        antialiasing: true
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
          strokeColor: root.panelBorder
          strokeWidth: root.panelBorderWidth
          fillColor: root.panelBackground
          capStyle: ShapePath.FlatCap
          joinStyle: ShapePath.MiterJoin
          startX: root.panelRadius
          startY: root.caretDepth + 0.5
          PathLine {
            x: root.caretCenterX - root.caretHalfWidth
            y: root.caretDepth + 0.5
          }
          PathCubic {
            x: root.caretCenterX
            y: root.caretDepth - root.caretDepth * root.connectionReveal + 0.5
            control1X: root.caretCenterX - root.caretTangentControl
            control1Y: root.caretDepth + 0.5
            control2X: root.caretCenterX - root.caretTipControl
            control2Y: root.caretDepth - root.caretDepth * root.connectionReveal + 0.5
          }
          PathCubic {
            x: root.caretCenterX + root.caretHalfWidth
            y: root.caretDepth + 0.5
            control1X: root.caretCenterX + root.caretTipControl
            control1Y: root.caretDepth - root.caretDepth * root.connectionReveal + 0.5
            control2X: root.caretCenterX + root.caretTangentControl
            control2Y: root.caretDepth + 0.5
          }
          PathLine {
            x: connectedSurface.width - root.panelRadius
            y: root.caretDepth + 0.5
          }
          PathArc {
            x: connectedSurface.width - 0.5
            y: root.panelRadius + root.caretDepth
            radiusX: root.panelRadius
            radiusY: root.panelRadius
          }
          PathLine {
            x: connectedSurface.width - 0.5
            y: connectedSurface.height + root.caretDepth - 0.5 - root.panelRadius
          }
          PathArc {
            x: connectedSurface.width - root.panelRadius
            y: connectedSurface.height + root.caretDepth - 0.5
            radiusX: root.panelRadius
            radiusY: root.panelRadius
          }
          PathLine {
            x: root.panelRadius
            y: connectedSurface.height + root.caretDepth - 0.5
          }
          PathArc {
            x: 0.5
            y: connectedSurface.height + root.caretDepth - 0.5 - root.panelRadius
            radiusX: root.panelRadius
            radiusY: root.panelRadius
          }
          PathLine {
            x: 0.5
            y: root.panelRadius + root.caretDepth
          }
          PathArc {
            x: root.panelRadius
            y: root.caretDepth + 0.5
            radiusX: root.panelRadius
            radiusY: root.panelRadius
          }
        }
      }

      Shape {
        anchors.left: parent.left
        anchors.top: parent.top
        width: parent.width
        height: parent.height + root.caretDepth
        visible: root.barPos === "bottom"
        antialiasing: true
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
          strokeColor: root.panelBorder
          strokeWidth: root.panelBorderWidth
          fillColor: root.panelBackground
          capStyle: ShapePath.FlatCap
          joinStyle: ShapePath.MiterJoin
          startX: root.panelRadius
          startY: 0.5
          PathLine {
            x: connectedSurface.width - root.panelRadius
            y: 0.5
          }
          PathArc {
            x: connectedSurface.width - 0.5
            y: root.panelRadius + 0.5
            radiusX: root.panelRadius
            radiusY: root.panelRadius
          }
          PathLine {
            x: connectedSurface.width - 0.5
            y: connectedSurface.height - root.panelRadius - 0.5
          }
          PathArc {
            x: connectedSurface.width - root.panelRadius
            y: connectedSurface.height - 0.5
            radiusX: root.panelRadius
            radiusY: root.panelRadius
          }
          PathLine {
            x: root.caretCenterX + root.caretHalfWidth
            y: connectedSurface.height - 0.5
          }
          PathCubic {
            x: root.caretCenterX
            y: connectedSurface.height - 0.5 + root.caretDepth * root.connectionReveal
            control1X: root.caretCenterX + root.caretTangentControl
            control1Y: connectedSurface.height - 0.5
            control2X: root.caretCenterX + root.caretTipControl
            control2Y: connectedSurface.height - 0.5 + root.caretDepth * root.connectionReveal
          }
          PathCubic {
            x: root.caretCenterX - root.caretHalfWidth
            y: connectedSurface.height - 0.5
            control1X: root.caretCenterX - root.caretTipControl
            control1Y: connectedSurface.height - 0.5 + root.caretDepth * root.connectionReveal
            control2X: root.caretCenterX - root.caretTangentControl
            control2Y: connectedSurface.height - 0.5
          }
          PathLine {
            x: root.panelRadius
            y: connectedSurface.height - 0.5
          }
          PathArc {
            x: 0.5
            y: connectedSurface.height - root.panelRadius - 0.5
            radiusX: root.panelRadius
            radiusY: root.panelRadius
          }
          PathLine {
            x: 0.5
            y: root.panelRadius + 0.5
          }
          PathArc {
            x: root.panelRadius
            y: 0.5
            radiusX: root.panelRadius
            radiusY: root.panelRadius
          }
        }
      }
    }

    BorderSurface {
      id: card
      width: root.cardWidth
      height: Math.min(heroVisual.height + root.panelSectionGap +
                       root.primaryAreaHeight + root.pad * 2,
                       root.cardHeightLimit > 0 ? root.cardHeightLimit :
                         (popup.screen ? Math.max(Style.space(260),
                           popup.screen.height - Style.space(24)) : Style.space(720)))
      color: root.connectedSurfaceEnabled ? "transparent" : root.panelBackground
      borderSpec: root.connectedSurfaceEnabled
        ? Border.flat("transparent", 0) : Border.flat(root.panelBorder, root.panelBorderWidth)
      radius: root.panelRadius

      onXChanged: root.publishConnectedGeometry()
      onWidthChanged: {
        if (root.opened)
          root.placeCard()
        root.publishConnectedGeometry()
      }
      onHeightChanged: {
        if (root.opened)
          root.placeCard()
        root.publishConnectedGeometry()
      }

      MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onClicked: panelFocus.forceActiveFocus()
      }

      FocusScope {
        id: panelFocus
        anchors.fill: parent
        focus: root.opened
        Keys.onEscapePressed: root.close()

        Rectangle {
          id: heroVisual
          anchors.top: parent.top
          anchors.topMargin: root.pad
          anchors.left: parent.left
          anchors.leftMargin: root.pad
          width: Math.max(0, parent.width - root.pad * 2)
          height: omaq.pending && !omaq.pendingGroup &&
            omaq.supportsInviteRequestSafety
            ? root.pendingDirectHeaderHeight : root.headerHeight
          radius: root.themedRadius(height)
          color: omaq.pending
            ? Qt.rgba((root.systemColors[3] || root.controlAccent).r,
                (root.systemColors[3] || root.controlAccent).g,
                (root.systemColors[3] || root.controlAccent).b,
                pendingHeaderHover.hovered ? 0.16 : 0.09)
            : "transparent"
          border.color: omaq.pending
            ? (root.systemColors[3] || root.controlAccent) : root.controlBorder
          border.width: 1
          clip: true
          z: 20

          // Disabled controls must not pass clicks to the card's dismiss/reset area.
          MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
          }

          HoverHandler {
            id: pendingHeaderHover
            enabled: omaq.pending
          }

          Row {
            id: heroHeaderRow
            anchors.fill: parent
            anchors.margins: root.framePadding
            spacing: Style.space(8)

            AvatarPic {
              id: selfHeaderAvatar
              visible: !omaq.pending
              anchors.verticalCenter: parent.verticalCenter
              px: Style.space(34)
              path: omaq.selfAvatar
              online: omaq.selfOnline
              revision: omaq.avatarTick
              onClicked: root.pickSelfAvatar()
            }

            Column {
              id: selfHeaderContent
              visible: !omaq.pending
              width: Math.max(0, parent.width - selfHeaderAvatar.width - (headerActions.visible ? headerActions.width : 0) -
                              parent.spacing * 2)
              anchors.verticalCenter: parent.verticalCenter
              spacing: 0

              SafeText {
                visible: omaq.selfNickname !== "" && !root.nicknameEditOpen
                width: parent.width
                height: root.nicknameControlHeight
                text: omaq.selfNickname
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                MouseArea {
                  anchors.fill: parent
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    root.nicknameEditOpen = true
                    Qt.callLater(function() { nicknameField.forceActiveFocus() })
                  }
                }
              }

              Row {
                visible: omaq.selfNickname === "" || root.nicknameEditOpen
                width: parent.width
                height: root.nicknameEditorHeight
                spacing: root.btnGap
                TokenTextField {
                  id: nicknameField
                  width: parent.width - nicknameButton.implicitWidth - root.btnGap
                  height: parent.height
                  foreground: root.controlForeground
                  accent: root.nicknameFeedbackError ? root.urgent : root.controlAccent
                  font.pixelSize: Style.font.body
                  placeholderText: "Nickname · max 18"
                  maximumLength: 36
                  text: omaq.selfNickname
                  onTextEdited: {
                    root.nicknameEditOpen = true
                    omaq.clearRequestError(root.nicknameFeedbackRequest)
                    root.nicknameFeedback = ""
                    root.nicknameFeedbackRequest = ""
                    root.nicknameFeedbackError = false
                    var limited = omaq.limitNickname(text, 18)
                    if (limited !== text)
                      text = limited
                  }
                  onAccepted: if (nicknameButton.enabled) nicknameButton.clicked()

                }
                TokenButton {
                  id: nicknameButton
                  iconText: "check"
                  iconFontFamily: "Material Symbols Rounded"
                  text: omaq.selfNickname === "" ? "Start" : ""
                  width: implicitWidth
                  height: parent.height
                  focusable: true
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  tooltipText: "Save nickname"
                  accessibleName: "Save nickname"
                  enabled: !root.nicknameSubmitPending &&
                    omaq.nicknameValid(nicknameField.text)
                  onClicked: {
                    if (root.nicknameSubmitPending || !nicknameButton.enabled)
                      return
                    omaq.clearRequestError(root.nicknameFeedbackRequest)
                    root.nicknameFeedback = ""
                    root.nicknameFeedbackRequest = ""
                    root.nicknameFeedbackError = false
                    root.nicknameRequestSequence++
                    root.nicknameRequest = Date.now().toString(36) + "-nickname-" +
                      root.nicknameRequestSequence.toString(36) + "-" +
                      Math.floor(Math.random() * 0x100000000).toString(36)
                    root.nicknameSubmitPending = omaq.selfNickname === ""
                      ? omaq.createIdentity(nicknameField.text, root.nicknameRequest)
                      : omaq.setNickname(nicknameField.text, root.nicknameRequest)
                    if (root.nicknameSubmitPending) {
                      nicknameSubmitTimer.restart()
                    } else {
                      root.nicknameFeedback = omaq.locked
                        ? root.errorText("locked")
                        : omaq.helperCompatibility === "incompatible"
                          ? root.errorText("helper_incompatible")
                          : "Harbor's helper is not ready. Finish installation or check the helper status."
                      root.nicknameFeedbackError = true
                      root.nicknameRequest = ""
                    }
                  }
                }
              }

              RowLayout {
                id: selfStatusRow
                visible: root.nicknameFeedback === "" &&
                  omaq.selfNickname !== "" && !root.nicknameEditOpen
                width: parent.width
                height: Style.space(16)
                spacing: Style.space(3)

                SafeText {
                  Layout.fillWidth: true
                  Layout.alignment: Qt.AlignVCenter
                  text: "YOU · " + root.connectionLabel().toUpperCase()
                  color: omaq.connectionState === "online"
                    ? root.onlineStatusColor : root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: omaq.connectionState !== "online"
                  font.letterSpacing: 0.8
                  elide: Text.ElideRight
                }
              }

              SafeText {
                id: nicknameFeedbackText
                visible: root.nicknameFeedback !== "" &&
                  omaq.selfNickname !== "" && !root.nicknameEditOpen
                width: parent.width
                height: Style.space(16)
                verticalAlignment: Text.AlignVCenter
                text: root.nicknameFeedback
                color: root.nicknameFeedbackError ? root.urgent
                  : (root.systemColors[3] || root.onlineStatusColor)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
              }
            }

            Row {
              id: headerActions
              visible: !omaq.pending && !root.nicknameEditOpen && omaq.selfNickname !== ""
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(4)
              ActionButton {
                text: "Add"
                enabled: !omaq.locked
                onClicked: root.openAdd()
              }
              RailIcon {
                materialIcon: "settings"
                label: "Settings"
                onClicked: root.toggleSettings()
              }
            }

            RowLayout {
              id: pendingRequestContent
              visible: omaq.pending
              width: parent.width
              height: parent.height
              spacing: Style.space(5)
              Accessible.name: omaq.pendingGroup
                ? "Group invitation. Join a private group."
                : (omaq.supportsInviteRequestSafety
                  ? "Friend request. Compare the safety code with your friend before accepting."
                  : "Friend request. Connect as a friend.")

              ColumnLayout {
                id: pendingRequestDetails
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: 0

                SafeText {
                  id: pendingRequestTitle
                  Layout.fillWidth: true
                  text: omaq.pendingGroup ? "Group invite" : "Friend request"
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  font.bold: true
                  elide: Text.ElideRight
                }

                SafeText {
                  id: pendingRequestContext
                  visible: omaq.pendingGroup || !omaq.supportsInviteRequestSafety
                  Layout.fillWidth: true
                  text: omaq.pendingGroup ? "Private group" : "New contact"
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  elide: Text.ElideRight
                }

                SafeText {
                  id: pendingRequestSafety
                  visible: !omaq.pendingGroup && omaq.supportsInviteRequestSafety &&
                    omaq.pendingRequestSafety !== ""
                  Layout.fillWidth: true
                  text: omaq.pendingRequestSafety.replace(" / ", "\n")
                  color: root.systemColors[3] || root.controlAccent
                  font.family: "monospace"
                  font.pixelSize: Style.font.caption
                  wrapMode: Text.Wrap
                }

                SafeText {
                  id: pendingRequestGuidance
                  visible: pendingRequestSafety.visible
                  Layout.fillWidth: true
                  text: "Compare this code with your friend before accepting"
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  wrapMode: Text.WordWrap
                }

                SafeText {
                  id: pendingRequestConflict
                  visible: !omaq.pendingGroup && omaq.supportsInviteRequestSafety &&
                    omaq.pendingRequestConflictKey !== ""
                  Layout.fillWidth: true
                  text: "Another device used this invite link"
                  color: root.urgent
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                  wrapMode: Text.WordWrap
                }
              }

              TokenButton {
                id: pendingAcceptButton
                Layout.minimumWidth: Style.space(28)
                Layout.preferredWidth: Style.space(28)
                Layout.maximumWidth: Style.space(28)
                Layout.minimumHeight: Style.space(28)
                Layout.preferredHeight: Style.space(28)
                Layout.maximumHeight: Style.space(28)
                iconText: "check"
                iconFontFamily: "Material Symbols Rounded"
                tooltipText: omaq.pendingGroup
                  ? "Accept group invitation" : "Accept friend request"
                accessibleName: tooltipText
                focusable: true
                foreground: root.foreground
                accent: root.systemColors[3] || root.controlAccent
                selected: true
                horizontalPadding: Style.space(2)
                verticalPadding: Style.space(2)
                onClicked: omaq.decide(true)
              }

              TokenButton {
                id: pendingDeclineButton
                Layout.minimumWidth: Style.space(28)
                Layout.preferredWidth: Style.space(28)
                Layout.maximumWidth: Style.space(28)
                Layout.minimumHeight: Style.space(28)
                Layout.preferredHeight: Style.space(28)
                Layout.maximumHeight: Style.space(28)
                iconText: "close"
                iconFontFamily: "Material Symbols Rounded"
                tooltipText: omaq.pendingGroup
                  ? "Decline group invitation" : (omaq.supportsInviteRequestSafety
                    ? "Decline and revoke link" : "Decline friend request")
                accessibleName: tooltipText
                focusable: true
                foreground: root.foreground
                accent: root.systemColors[3] || root.controlAccent
                horizontalPadding: Style.space(2)
                verticalPadding: Style.space(2)
                onClicked: omaq.decide(false)
              }
            }
          }
        }

        Connections {
          target: omaq
          function onPendingChanged() {
            if (!omaq.pending)
              return
            Qt.callLater(function() {
              if (omaq.pending && chatSurface.isSurfaceOwner) {
                root.open()
                chatSurface.playSound()
              }
            })
            root.nicknameEditOpen = false
            if (!root.nicknameSubmitPending)
              nicknameField.text = omaq.selfNickname
          }
          function onSelfNicknameChanged() {
            if (!root.nicknameEditOpen && !root.nicknameSubmitPending)
              nicknameField.text = omaq.selfNickname
          }
          function onNicknameTickChanged() {
            if (root.nicknameSubmitPending && root.nicknameRequest !== "" &&
                String(omaq.lastNicknameRequest || "") === root.nicknameRequest) {
              root.nicknameSubmitPending = false
              omaq.clearRequestError(root.nicknameFeedbackRequest)
              root.nicknameFeedback = ""
              root.nicknameFeedbackRequest = ""
              root.nicknameFeedbackError = false
              root.nicknameRequest = ""
              nicknameField.text = omaq.selfNickname
              nicknameSubmitTimer.stop()
              root.nicknameEditOpen = false
            }
          }
          function onLastErrorTickChanged() {
            if (!root.nicknameSubmitPending)
              return
            var correlated = root.nicknameRequest !== "" &&
              String(omaq.lastErrorRequest || "") === root.nicknameRequest
            var helperFailure = ["helper_down", "helper_incompatible",
              "identity_changed"].indexOf(omaq.lastError) !== -1
            if (correlated || helperFailure) {
              root.nicknameSubmitPending = false
              root.nicknameFeedbackRequest = correlated ? root.nicknameRequest : ""
              root.nicknameFeedback = omaq.lastError === "identity_setup_failed"
                ? (omaq.deviceFeedback || "Identity setup failed. Try again.")
                : omaq.lastError === "unsupported"
                ? "Nickname update is unavailable."
                : omaq.lastError === "nickname_invalid"
                  ? "Nickname must contain 1–18 valid characters."
                  : omaq.lastError === "nickname_group_sync_failed"
                    ? root.errorText(omaq.lastError)
                    : "Nickname update failed. Try again."
              root.nicknameFeedbackError = true
              root.nicknameRequest = ""
              nicknameSubmitTimer.stop()
            }
          }
        }

        Rectangle {
          id: activeMenuFrame
          visible: root.primaryMenuOpen
          anchors.top: parent.top
          anchors.topMargin: root.pad + heroVisual.height + root.panelSectionGap
          anchors.left: parent.left
          anchors.leftMargin: root.pad
          width: panelScroll.width
          height: panelScroll.height
          radius: root.themedRadius(height)
          color: "transparent"
          border.color: root.controlBorder
          border.width: 1
          z: 10
        }

        Flickable {
          id: panelScroll
          anchors.top: parent.top
          anchors.topMargin: root.pad + heroVisual.height + root.panelSectionGap
          anchors.left: parent.left
          anchors.leftMargin: root.pad
          anchors.right: parent.right
          anchors.rightMargin: root.pad
          height: Math.max(0, card.height - root.pad * 2 - heroVisual.height -
                           root.panelSectionGap)
          contentWidth: width
          contentHeight: column.y + column.implicitHeight +
            (root.primaryMenuOpen ? root.framePadding : 0)
          clip: true
          boundsBehavior: Flickable.StopAtBounds
          flickableDirection: Flickable.VerticalFlick

          Controls.ScrollBar.vertical: Controls.ScrollBar {
            id: panelScrollbar
            anchors.right: parent.right
            anchors.rightMargin: 0
            visible: panelScroll.contentHeight > panelScroll.height + 1
            policy: visible ? Controls.ScrollBar.AlwaysOn : Controls.ScrollBar.AlwaysOff
            width: Style.space(3)
            opacity: panelScroll.moving || hovered ? 0.5 : 0.14
            Behavior on opacity { NumberAnimation { duration: 180 } }
            contentItem: Rectangle {
              implicitWidth: Style.space(2)
              radius: width / 2
              color: root.systemColors[3]
            }
          }

          MouseArea {
            width: panelScroll.width
            height: Math.max(panelScroll.height, column.implicitHeight)
            acceptedButtons: Qt.LeftButton
            onClicked: {
              panelFocus.forceActiveFocus()
            }
          }

          Column {
            id: column
            x: root.primaryMenuOpen ? root.framePadding : 0
            y: root.primaryMenuOpen ? root.framePadding : 0
            width: Math.max(0, panelScroll.width -
                            (root.primaryMenuOpen ? root.framePadding * 2 : 0))
            spacing: root.panelSectionGap

          ActionButton {
            visible: root.primaryMenuOpen && !omaq.locked
            text: root.settingsPage !== "" ? "Back to Settings" : "Back to conversations"
            borderless: true
            onClicked: root.settingsPage !== "" ? root.openSettingsPage("") : root.dismissTransientSections()
          }

          Column {
            visible: root.addOpen
            width: parent.width
            spacing: root.btnGap
            PanelSectionHeader {
              text: "Add someone"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }
            ActionButton {
              width: parent.width
              text: "Share a one-use invite"
              onClicked: root.toggleInvite()
            }
            SafeText {
              width: parent.width
              text: omaq.inviteUrl !== "" ? (omaq.inviteBearer
                ? "Your current link lets its holder add you once."
                : "Your current link requires your approval.")
                : omaq.supportsBearerInvites && !root.inviteRequireApproval
                ? "Anyone with your link can add you once. Share it privately."
                : "You will review the request before connecting."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }
            ActionButton {
              visible: omaq.supportsBearerInvites
              width: parent.width
              enabled: omaq.inviteUrl === "" && !root.inviteActionPending
              text: (omaq.inviteUrl !== "" ? !omaq.inviteBearer : root.inviteRequireApproval)
                ? "Require my approval: On" : "Require my approval: Off"
              onClicked: root.inviteRequireApproval = !root.inviteRequireApproval
            }
            ActionButton {
              width: parent.width
              text: "Use an invite"
              onClicked: root.toggleJoin()
            }
            ActionButton {
              width: parent.width
              text: "Create a group"
              onClicked: root.openRailAdvanced("groups")
            }
          }

          Column {
            visible: root.settingsOpen && root.settingsPage === ""
            width: parent.width
            spacing: Style.space(2)
            PanelSectionHeader { text: "Settings"; foreground: root.foreground; fontFamily: root.fontFamily }
            SettingsRow { label: "Profile"; value: omaq.selfNickname || "Choose your name"
              onClicked: root.openSettingsPage("profile") }
            SettingsRow { label: "Devices"; value: "This computer and your linked computers"
              onClicked: root.openSettingsPage("devices") }
            SettingsRow { label: "Notifications"; value: omaq.muted ? "Sounds muted" : "Sounds on"
              onClicked: root.openSettingsPage("notifications") }
            SettingsRow { label: "Appearance"; value: "Theme and message size"
              onClicked: root.openSettingsPage("appearance") }
            SettingsRow { label: "Recovery"; value: "Back up or restore this computer"
              onClicked: root.openSettingsPage("recovery") }
            PanelSeparator { foreground: root.foreground }
            TokenButton { text: "Advanced"; borderless: true; focusable: true
              onClicked: root.openSettingsPage("advanced") }
          }

          Column {
            visible: root.settingsOpen && root.settingsPage === "profile"
            width: parent.width; spacing: root.btnGap
            PanelSectionHeader { text: "Profile"; foreground: root.foreground; fontFamily: root.fontFamily }
            SafeText {
              width: parent.width; text: "The name and picture your friends see."
              color: root.dim; font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }
            SettingsRow { label: "Name"; value: omaq.selfNickname || "Choose your name"
              onClicked: { root.nicknameEditOpen = true; nicknameField.forceActiveFocus() } }
            SettingsRow { label: "Picture"; value: "Choose a photo"
              onClicked: root.pickSelfAvatar() }
          }

          Column {
            visible: root.devicesOpen
            width: parent.width
            spacing: root.btnGap
            PanelSectionHeader {
              text: "Devices"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }
            SafeText {
              width: parent.width
              visible: !omaq.supportsDeviceManagement || omaq.deviceFeedback !== ""
              text: !omaq.supportsDeviceManagement ? "Update Harbor to manage linked devices."
                : omaq.deviceFeedback
              color: omaq.deviceFeedbackError ? root.urgent : root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }
            SafeText {
              width: parent.width
              text: omaq.linkedDevices.length === 0 ? "You’re using Harbor on this computer. Add another computer to use the same profile there." : "Computers connected to your profile."
              color: root.dim; font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }
            ActionButton {
              visible: omaq.selfNickname !== "" && omaq.supportsBearerInvites && !omaq.deviceLink && !omaq.deviceBootstrap
              width: parent.width
              text: root.prepareDeviceInviteRequest !== "" ? "Preparing…" : "Add a computer"
              enabled: omaq.deviceRequest === "" && root.prepareDeviceInviteRequest === ""
              onClicked: root.addComputer()
            }
            SafeText {
              visible: !!omaq.deviceBootstrap
              width: parent.width
              text: "Connecting to your other computer… Keep Harbor open on both computers."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }
            Column {
              visible: omaq.selfNickname === "" && omaq.supportsDeviceManagement && omaq.linkedDevices.length === 0 &&
                !omaq.deviceLink && !omaq.deviceBootstrap && root.deviceSetupChoice === ""
              width: parent.width
              spacing: root.btnGap
              ActionButton {
                width: parent.width
                text: "Start a new profile"
                enabled: omaq.deviceRequest === ""
                onClicked: root.deviceSetupChoice = "create"
              }
              ActionButton {
                width: parent.width
                text: "Use my existing profile"
                enabled: omaq.deviceRequest === ""
                onClicked: root.deviceSetupChoice = "link"
              }
            }
            TokenTextField {
              id: deviceNameField
              visible: omaq.supportsDeviceManagement && omaq.linkedDevices.length === 0 && !omaq.deviceLink && !omaq.deviceBootstrap && root.deviceSetupChoice !== ""
              width: parent.width
              height: Style.space(32)
              placeholderText: "Name this computer"
              text: "My computer"
              maximumLength: 47
            }
            ActionButton {
              visible: deviceNameField.visible && root.deviceSetupChoice === "create"
              width: parent.width
              text: "Continue"
              enabled: deviceNameField.text.trim() !== "" && omaq.deviceRequest === "" && !omaq.deviceLink
              onClicked: omaq.manageDevice("device.initialize", deviceNameField.text.trim(), "", false)
            }
            TokenTextField {
              id: deviceInviteField
              visible: deviceNameField.visible && root.deviceSetupChoice === "link"
              width: parent.width
              height: Style.space(32)
              placeholderText: "Paste a device-link invite"
              maximumLength: 511
            }
            ActionButton {
              visible: deviceInviteField.visible
              width: parent.width
              text: "Link this computer"
              enabled: deviceNameField.text.trim() !== "" && deviceInviteField.text.trim() !== ""
              onClicked: omaq.beginDeviceLink(deviceInviteField.text, deviceNameField.text)
            }
            SafeText {
              width: parent.width
              visible: deviceInviteField.visible && !omaq.deviceLink
              text: "On your existing computer, open Settings → Devices → Add a computer. Paste its link here, then approve on that computer."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }
            SafeText {
              visible: omaq.deviceLinkError !== "" || !!omaq.deviceLink
              width: parent.width
              text: omaq.deviceLinkError !== "" ? omaq.deviceLinkError
                : !omaq.deviceLink ? "" : omaq.deviceLink.state === "linked"
                  ? (omaq.deviceLink.incoming ? "“" + omaq.deviceLink.name + "” is linked." : "This computer is linked.")
                : omaq.deviceLink.state === "sent" ? "Device authorization sent. Check the new computer."
                : omaq.deviceLink.state === "declined" ? "Device linking declined."
                : !omaq.deviceLink.incoming && omaq.deviceLink.state === "waiting-for-owner"
                  ? "Compare this code on your existing computer and approve the link there."
                : (omaq.deviceLink.state === "requested" || omaq.deviceLink.state === "verify")
                  ? "Link “" + omaq.deviceLink.name + "”? Compare the complete code on both computers. Continue only if they match. Only approve a computer you own."
                  : "Waiting for the other computer…"
              color: omaq.deviceLinkError !== "" ? root.urgent : root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }
            SafeText {
              visible: !!omaq.deviceLink && omaq.deviceLink.code !== "" &&
                ["requested", "verify", "working", "waiting-for-device", "waiting-for-owner"].indexOf(omaq.deviceLink.state) >= 0
              width: parent.width
              text: omaq.deviceLink ? (omaq.deviceLink.code.match(/.{1,8}/g) || []).join(" ") : ""
              color: root.controlAccent
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WrapAnywhere
            }
            ActionButton {
              visible: !!omaq.deviceLink && (omaq.deviceLink.state === "requested" || omaq.deviceLink.state === "verify")
              width: parent.width
              text: "Approve this computer"
              onClicked: omaq.decideDeviceLink(true)
            }
            ActionButton {
              visible: !!omaq.deviceLink && omaq.deviceLink.incoming && omaq.deviceLink.state === "requested"
              text: "Decline"
              onClicked: omaq.decideDeviceLink(false)
            }
            ActionButton {
              visible: !!omaq.deviceLink && ["linked", "sent", "declined"].indexOf(omaq.deviceLink.state) >= 0
              text: "Done"
              onClicked: omaq.deviceLink = null
            }
            Repeater {
              model: omaq.linkedDevices
              delegate: ActionButton {
                required property var modelData
                width: parent ? parent.width : 0
                text: modelData.name + (modelData.current ? " · This device"
                  : modelData.active ? " · Remove" : " · Removed")
                enabled: modelData.active && !modelData.current && omaq.deviceRequest === ""
                onClicked: {
                  root.deviceRevokeKey = String(modelData.key)
                  root.deviceRevokeName = String(modelData.name)
                }
              }
            }
            SafeText {
              visible: root.deviceRevokeKey !== ""
              width: parent.width
              text: "Remove “" + root.deviceRevokeName + "”? It will lose future access after other devices learn of the removal. Existing copies remain on that computer."
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }
            Row {
              visible: root.deviceRevokeKey !== ""
              spacing: root.btnGap
              ActionButton {
                text: "Cancel"
                onClicked: root.deviceRevokeKey = ""
              }
              ActionButton {
                text: "Remove device"
                enabled: omaq.deviceRequest === ""
                onClicked: {
                  if (omaq.manageDevice("device.revoke", "", root.deviceRevokeKey, true))
                    root.deviceRevokeKey = ""
                }
              }
            }
            ActionButton {
              visible: omaq.supportsDeviceManagement
              text: "Refresh"
              enabled: omaq.deviceRequest === ""
              onClicked: omaq.manageDevice("device.status", "", "", false)
            }
          }

          Column {
            id: identityContactsFrame
            visible: !root.primaryMenuOpen
            width: parent.width
            spacing: root.btnGap

            ActionButton {
              visible: omaq.selfNickname === ""
              width: parent.width
              text: "Use Harbor from another computer"
              onClicked: {
                root.dismissTransientSections()
                root.devicesOpen = true
                root.deviceSetupChoice = "link"
                omaq.manageDevice("device.status", "", "", false)
              }
            }
            SafeText {
              visible: omaq.selfNickname === ""
              width: parent.width
              text: "Welcome to Harbor. Choose a nickname above to get started."
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.WordWrap
            }
            ActionButton {
              visible: omaq.selfNickname === ""
              text: "Restore a backup"
              onClicked: root.openSettingsPage("recovery")
            }
            TokenTextField {
              id: conversationSearch
              width: parent.width
              height: Style.space(32)
              placeholderText: "Find a conversation"
              onTextChanged: root.conversationQuery = text
            }

            SafeText {
              visible: conversationList.count === 0
              width: parent.width
              text: !omaq.friendsReady ? "Loading conversations…"
                : root.conversationQuery !== "" ? "No matching conversations"
                : "Your people, within reach. Add someone to start a conversation."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.WordWrap
            }

            ListView {
              id: conversationList
              width: parent.width
              height: Math.min(count * Style.space(56), Style.space(320))
              clip: true
              boundsBehavior: Flickable.StopAtBounds
              model: root.conversationRows()
              delegate: Rectangle {
                id: conversationRow
                required property var modelData
                required property int index
                width: conversationList.width
                height: Style.space(56)
                radius: root.controlRadius
                color: conversationHover.hovered || activeFocus ? root.controlHoverFill : "transparent"
                activeFocusOnTab: true
                readonly property int unread: omaq.unreadFor(modelData.id)
                readonly property var preview: omaq.conversationPreview(modelData.id, modelData.key)
                Accessible.role: Accessible.Button
                Accessible.name: modelData.name + ", " + modelData.status +
                  (unread > 0 ? ", " + unread + " unread" : "")
                Accessible.onPressAction: root.openConversation(modelData)
                Keys.onReturnPressed: root.openConversation(modelData)
                Keys.onEnterPressed: root.openConversation(modelData)
                Keys.onSpacePressed: root.openConversation(modelData)
                onActiveFocusChanged: if (activeFocus)
                  conversationList.positionViewAtIndex(index, ListView.Contain)
                HoverHandler { id: conversationHover }
                AvatarPic {
                  id: conversationAvatar
                  anchors.left: parent.left
                  anchors.leftMargin: root.framePadding
                  anchors.verticalCenter: parent.verticalCenter
                  px: Style.space(34)
                  path: conversationRow.modelData.avatar
                  online: conversationRow.modelData.online
                  revision: omaq.avatarTick
                  onClicked: root.openConversation(conversationRow.modelData)
                }
                Column {
                  anchors.left: conversationAvatar.right
                  anchors.leftMargin: Style.space(8)
                  anchors.right: activityInfo.left
                  anchors.rightMargin: Style.space(8)
                  anchors.verticalCenter: parent.verticalCenter
                  SafeText {
                    width: parent.width
                    text: conversationRow.modelData.name
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.body
                    font.bold: conversationRow.unread > 0
                    elide: Text.ElideRight
                  }
                  SafeText {
                    width: parent.width
                    text: conversationRow.preview.text || conversationRow.modelData.status
                    color: root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    elide: Text.ElideRight
                  }
                }
                Column {
                  id: activityInfo
                  anchors.right: parent.right
                  anchors.rightMargin: root.framePadding
                  anchors.verticalCenter: parent.verticalCenter
                  spacing: Style.space(2)
                  SafeText {
                    text: root.activityTime(conversationRow.preview.ts)
                    color: root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  SafeText {
                    anchors.right: parent.right
                    text: conversationRow.unread > 0 ? String(conversationRow.unread) : ""
                    color: root.controlAccent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                }
                MouseArea {
                  anchors.fill: parent
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.openConversation(conversationRow.modelData)
                }
              }
              Controls.ScrollBar.vertical: Controls.ScrollBar {}
            }
          }

          Column {
            visible: root.settingsOpen && root.fontSizeOpen
            width: parent.width
            spacing: Style.space(6)

            PanelSectionHeader {
              text: "Message size"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Row {
              width: parent.width
              spacing: Style.space(4)

              Repeater {
                model: [
                  { label: "90%", value: 0.9 },
                  { label: "100%", value: 1.0 },
                  { label: "110%", value: 1.1 },
                  { label: "120%", value: 1.2 },
                  { label: "140%", value: 1.4 }
                ]
                delegate: ActionButton {
                  required property var modelData
                  width: Math.max(0, (parent.width - parent.spacing * 4) / 5)
                  text: String(modelData.label)
                  selected: root.messageScale === Number(modelData.value)
                  tooltipText: "Chat messages: " + text
                  onClicked: root.setMessageScale(modelData.value)
                }
              }
            }

            Rectangle {
              width: parent.width
              implicitHeight: messageScalePreview.implicitHeight + Style.space(14)
              height: implicitHeight
              radius: root.themedRadius(height)
              color: Qt.rgba(root.controlAccent.r, root.controlAccent.g,
                root.controlAccent.b, 0.16)
              border.color: root.controlBorder
              border.width: 1

              SafeText {
                id: messageScalePreview
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.margins: Style.space(7)
                text: "This is how a chat message will look."
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Math.max(Style.font.caption,
                  Math.round(Style.font.body * root.messageScale))
                wrapMode: Text.WordWrap
              }
            }

            SafeText {
              width: parent.width
              text: "Changes message text and text typed in the composer."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }
          }

          Column {
            visible: root.settingsOpen && root.themeOpen
            width: parent.width
            spacing: Style.space(8)

            SafeText {
              width: parent.width
              text: "Chat theme. The panel follows your desktop theme."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }

            Repeater {
              model: Model.CHAT_THEME_IDS
              delegate: Item {
                id: pal
                required property string modelData
                width: parent ? parent.width : 0
                implicitHeight: palCol.implicitHeight

                Column {
                  id: palCol
                  width: parent.width
                  spacing: Style.space(4)

                  SafeText {
                    width: parent.width
                    text: root.paletteLabel(pal.modelData)
                    color: root.chatTheme === pal.modelData ? Color.accent : root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    font.bold: true
                    elide: Text.ElideRight
                  }

                  Row {
                    width: parent.width
                    spacing: Style.space(3)

                    Repeater {
                      model: root.paletteColors(pal.modelData)
                      Rectangle {
                        required property string modelData
                        width: Math.max(Style.space(12), (pal.width - Style.space(3) * 7) / 8)
                        height: Style.space(16)
                        radius: Style.cornerRadius
                        color: modelData
                        border.width: 1
                        border.color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.2)
                      }
                    }
                  }
                }

                MouseArea {
                  anchors.fill: parent
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.setTheme(pal.modelData)
                }
              }
            }
          }

          Column {
            visible: root.settingsOpen && root.soundOpen
            width: parent.width
            spacing: Style.space(6)

            SettingsRow {
              label: "Message sounds"; value: omaq.muted ? "Off" : "On"
              onClicked: chatSurface.toggleMute()
            }
            ActionButton {
              text: "Test sound"; enabled: !omaq.muted
              onClicked: chatSurface.previewSound(root.notificationSound)
            }
            SafeText {
              visible: chatSurface.soundWarning !== "" || chatSurface.notificationWarning !== ""
              width: parent.width; text: chatSurface.soundWarning || chatSurface.notificationWarning
              color: root.urgent; font.family: root.fontFamily; font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }
            PanelSectionHeader {
              text: "Sound"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            GridLayout {
              id: soundGrid
              width: parent.width
              columns: 3
              columnSpacing: Style.space(4)
              rowSpacing: Style.space(4)
              readonly property real optionWidth: Math.max(0,
                (width - columnSpacing * (columns - 1)) / columns)

              Repeater {
                model: root.notificationSounds
                delegate: ActionButton {
                  required property var modelData
                  Layout.minimumWidth: soundGrid.optionWidth
                  Layout.preferredWidth: soundGrid.optionWidth
                  Layout.maximumWidth: soundGrid.optionWidth
                  Layout.minimumHeight: root.actionButtonHeight
                  Layout.preferredHeight: root.actionButtonHeight
                  Layout.maximumHeight: root.actionButtonHeight
                  iconText: ""
                  text: String(modelData.label)
                  fontSize: Style.font.bodySmall
                  horizontalPadding: Style.space(3)
                  selected: root.notificationSoundSelected(modelData)
                  tooltipText: modelData.custom
                    ? "Use imported sound " + String(modelData.label) : ""
                  onClicked: root.setNotificationSound(modelData)
                }
              }
            }

            SafeText {
              visible: !omaq.supportsCustomSounds
              width: parent.width
              text: "Update the local Harbor helper to import or remove custom sounds."
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }

            ActionButton {
              width: parent.width
              text: soundPick.visible ? "Choosing sound…" : "Import sound"
              iconText: "audio_file"
              iconFontFamily: "Material Symbols Rounded"
              enabled: omaq.supportsCustomSounds && !soundPick.visible &&
                root.soundActionRequest === ""
              onClicked: root.startSoundPicker()
            }

            ActionButton {
              visible: !!root.selectedCustomSoundOption() && !root.soundRemoveConfirm
              width: parent.width
              text: "Remove selected sound"
              iconText: "delete"
              iconFontFamily: "Material Symbols Rounded"
              enabled: root.soundActionRequest === ""
              onClicked: root.requestSoundRemoval(root.selectedCustomSoundOption())
            }

            SafeText {
              visible: root.soundRemoveConfirm
              width: parent.width
              text: "Remove " + root.soundRemoveLabel +
                " from Harbor? The original source file stays unchanged."
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            GridLayout {
              visible: root.soundRemoveConfirm
              width: parent.width
              columns: 2
              columnSpacing: root.btnGap

              ActionButton {
                Layout.fillWidth: true
                text: "Cancel"
                enabled: root.soundActionRequest === ""
                onClicked: {
                  root.soundRemoveConfirm = false
                  root.soundRemoveId = ""
                  root.soundRemoveLabel = ""
                  root.soundRemovePath = ""
                }
              }

              ActionButton {
                Layout.fillWidth: true
                text: "Remove"
                iconText: "delete"
                iconFontFamily: "Material Symbols Rounded"
                accent: root.urgent
                enabled: root.soundActionRequest === ""
                onClicked: root.confirmSoundRemoval()
              }
            }

            SafeText {
              visible: root.soundFeedback !== ""
              width: parent.width
              text: root.soundFeedback
              color: root.soundFeedbackError ? root.urgent : root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }
          }

          Column {
            visible: omaq.identityPrimaryUncertain
            width: parent.width
            spacing: Style.space(6)

            PanelSectionHeader {
              text: "VERIFY IDENTITY STATE"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            SafeText {
              width: parent.width
              text: "Harbor could not confirm whether the latest identity, contact, or group change reached disk before restarting. Messaging and mutations are paused. Review your nickname and contacts first; group recovery stays paused and is reconciled only after confirmation."
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            GridLayout {
              visible: !root.identityPrimaryConfirm
              width: parent.width
              columns: 2
              columnSpacing: root.btnGap

              ActionButton {
                Layout.fillWidth: true
                text: "Show contacts"
                iconText: "manage_accounts"
                iconFontFamily: "Material Symbols Rounded"
                onClicked: panelFocus.forceActiveFocus()
              }

              ActionButton {
                Layout.fillWidth: true
                text: "Mark verified"
                iconText: "verified"
                iconFontFamily: "Material Symbols Rounded"
                enabled: root.identityPrimaryRequest === ""
                onClicked: root.identityPrimaryConfirm = true
              }
            }

            SafeText {
              visible: root.identityPrimaryConfirm
              width: parent.width
              text: "Clear this warning? Confirm only after checking whether the intended identity and contact change is present."
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            GridLayout {
              visible: root.identityPrimaryConfirm
              width: parent.width
              columns: 2
              columnSpacing: root.btnGap

              ActionButton {
                Layout.fillWidth: true
                text: "Cancel"
                enabled: root.identityPrimaryRequest === ""
                onClicked: root.identityPrimaryConfirm = false
              }

              ActionButton {
                Layout.fillWidth: true
                text: "Clear warning"
                iconText: "verified"
                iconFontFamily: "Material Symbols Rounded"
                accent: root.urgent
                enabled: root.identityPrimaryRequest === ""
                onClicked: {
                  root.identityPrimaryRequestSequence++
                  var request = Date.now().toString(36) + "-primary-" +
                    root.identityPrimaryRequestSequence.toString(36) + "-" +
                    Math.floor(Math.random() * 0x100000000).toString(36)
                  if (omaq.acknowledgeIdentityPrimary(request))
                    root.identityPrimaryRequest = request
                  else
                    omaq.lastError = "helper_incompatible"
                }
              }
            }
          }

          Column {
            visible: omaq.directReinviteRequired
            width: parent.width
            spacing: Style.space(6)

            PanelSectionHeader {
              text: "DIRECT CHAT RECOVERY"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            SafeText {
              width: parent.width
              text: "Your Harbor identity and contact list are intact. Older direct-chat encryption state could not be safely assigned to current contacts and was archived. Remove affected contacts on both devices, exchange one fresh invite, and verify that the new chat works."
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            SafeText {
              visible: !omaq.supportsDirectRecovery
              width: parent.width
              text: "Update the local Harbor helper before marking recovery complete. Existing contacts remain available."
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            GridLayout {
              visible: !root.directReinviteClearConfirm
              width: parent.width
              columns: 2
              columnSpacing: root.btnGap

              ActionButton {
                Layout.fillWidth: true
                text: "Review contacts"
                iconText: "manage_accounts"
                iconFontFamily: "Material Symbols Rounded"
                onClicked: {
                  root.dismissTransientSections()
                  root.moreOpen = true
                  root.moreSection = "danger"
                }
              }

              ActionButton {
                Layout.fillWidth: true
                text: "Mark complete"
                iconText: "task_alt"
                iconFontFamily: "Material Symbols Rounded"
                enabled: omaq.supportsDirectRecovery && root.directReinviteRequest === ""
                onClicked: root.directReinviteClearConfirm = true
              }
            }

            SafeText {
              visible: root.directReinviteClearConfirm
              width: parent.width
              text: "Clear this recovery warning? Continue only after affected contacts were removed on both devices, re-invited, and the new direct chat was verified."
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            GridLayout {
              visible: root.directReinviteClearConfirm
              width: parent.width
              columns: 2
              columnSpacing: root.btnGap

              ActionButton {
                Layout.fillWidth: true
                text: "Cancel"
                enabled: root.directReinviteRequest === ""
                onClicked: root.directReinviteClearConfirm = false
              }

              ActionButton {
                Layout.fillWidth: true
                text: "Clear warning"
                iconText: "task_alt"
                iconFontFamily: "Material Symbols Rounded"
                accent: root.urgent
                enabled: root.directReinviteRequest === ""
                onClicked: {
                  root.directReinviteRequestSequence++
                  var request = Date.now().toString(36) + "-reinvite-" +
                    root.directReinviteRequestSequence.toString(36) + "-" +
                    Math.floor(Math.random() * 0x100000000).toString(36)
                  if (omaq.clearDirectReinvite(request))
                    root.directReinviteRequest = request
                  else
                    omaq.lastError = "helper_incompatible"
                }
              }
            }
          }

          SafeText {
            visible: root.nicknameFeedback !== "" || root.settingsPersistenceWarning !== "" ||
              omaq.unreadWarning !== "" ||
              (chatSurface && chatSurface.autoOpenWarning !== "") ||
              (omaq.lastError !== "" && !(omaq.locked && omaq.lastError === "locked") &&
               !root.contextualErrorHandled)
            width: parent.width
            text: root.nicknameFeedback !== "" ? root.nicknameFeedback
              : root.settingsPersistenceWarning !== "" ? root.settingsPersistenceWarning
              : (omaq.lastError !== "" && !(omaq.locked && omaq.lastError === "locked") &&
                 !root.contextualErrorHandled
                ? root.errorText(omaq.lastError)
                : (omaq.unreadWarning !== "" ? omaq.unreadWarning
                  : (chatSurface && chatSurface.autoOpenWarning !== ""
                    ? chatSurface.autoOpenWarning : "")))
            color: root.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }

          Column {
            visible: omaq.locked
            width: parent.width
            spacing: Style.space(8)

            SafeText {
              width: parent.width
              text: "Identity is locked."
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.WordWrap
            }

            TokenTextField {
              id: unlockField
              width: parent.width
              foreground: root.controlForeground
              password: true
              maximumLength: 128
              placeholderText: "Passphrase"
              onTextEdited: if (!root.identityActionPending) root.clearIdentityFeedback()
            }

            ActionButton {
              width: parent.width
              iconText: "lock_open"
              iconFontFamily: "Material Symbols Rounded"
              text: "Unlock"
              focusable: true
              enabled: !root.identityActionPending &&
                root.identityExistingPassphraseValid(unlockField.text)
              onClicked: root.runIdentityAction("unlock", "", unlockField.text)
            }

            SafeText {
              visible: root.identityFeedback !== ""
              width: parent.width
              text: root.identityFeedback
              color: root.identityFeedbackError ? root.urgent
                : (root.systemColors[3] || root.onlineStatusColor)
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }
          }

          Column {
            id: unlockedMenus
            visible: !omaq.locked && root.primaryMenuOpen
            width: parent.width
            height: {
              var total = 0
              var visibleCount = 0
              for (var childIndex = 0; childIndex < children.length; childIndex++) {
                var child = children[childIndex]
                if (!child.visible)
                  continue
                if (visibleCount > 0)
                  total += spacing
                total += child.height
                visibleCount++
              }
              return total
            }
            spacing: Style.space(12)

            Row {
              visible: omaq.incomingCall
              spacing: root.btnGap
              TokenButton {
                text: "Answer"
                enabled: !omaq.callEndingFor(omaq.lastCallConv) &&
                  !omaq.callActionPending
                bordered: true
                focusable: true
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: {
                  if (omaq.answerCall(omaq.lastCallConv, omaq.lastCallKey)) {
                    root.callFeedback = ""
                    panelCallFeedbackTimer.stop()
                    Harbor.CallTone.stopAll()
                  } else {
                    root.callFeedback = "Call control unavailable"
                    panelCallFeedbackTimer.restart()
                  }
                }
              }
              TokenButton {
                text: omaq.callEndingFor(omaq.lastCallConv) ? "Ending…" : "Decline call"
                enabled: !omaq.callEndingFor(omaq.lastCallConv) &&
                  !omaq.callActionPending
                focusable: true
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: {
                  if (omaq.stopCall(omaq.lastCallConv, omaq.lastCallKey)) {
                    root.callFeedback = ""
                    panelCallFeedbackTimer.stop()
                    Harbor.CallTone.stopAll()
                  } else {
                    root.callFeedback = "Call control unavailable"
                    panelCallFeedbackTimer.restart()
                  }
                }
              }
            }

            SafeText {
              visible: omaq.incomingCall && root.callFeedback !== ""
              width: parent.width
              text: root.callFeedback
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }

            Column {
              id: inviteContent
              visible: root.inviteOpen && omaq.inviteUrl !== ""
              width: parent.width
              spacing: Style.space(8)

              PanelSectionHeader {
                visible: root.deviceInviteMode
                text: "LINK A COMPUTER"
                foreground: root.foreground
                fontFamily: root.fontFamily
              }
              PanelSectionHeader {
                visible: !root.deviceInviteMode
                text: "YOUR INVITE"
                foreground: root.foreground
                fontFamily: root.fontFamily
              }

              Item {
                id: inviteQr
                visible: true
                width: parent.width
                height: omaq.qrPath !== "" ? 148 : 0

                Image {
                  visible: omaq.qrPath !== ""
                  anchors.left: parent.left
                  width: 148
                  height: 148
                  fillMode: Image.PreserveAspectFit
                  source: omaq.qrPath !== "" ? root.localFileUrl(omaq.qrPath) : ""
                  asynchronous: true
                  smooth: false
                }
              }

              SafeText {
                width: parent.width
                text: root.shortInvite(omaq.inviteUrl)
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WrapAnywhere
              }

              SafeText {
                width: parent.width
                text: "Valid for " + root.inviteRemainingText()
                color: root.inviteRemainingSeconds <= 300 ? root.urgent : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Column {
                id: inviteSteps
                visible: root.inviteConfirmMode === ""
                width: parent.width
                spacing: Style.space(4)

                Repeater {
                  id: inviteStepsRepeater
                  model: root.deviceInviteMode ? [
                    { number: "1", text: "Keep this link private. Its holder can connect once, but cannot join your identity without your confirmation." },
                    { number: "2", text: "On the new computer, choose Link my existing identity and paste this link." },
                    { number: "3", text: "Compare the code shown on both computers, then confirm the link." }
                  ] : omaq.inviteBearer ? [
                    { number: "1", text: "Share privately. Anyone with this link can add you once." },
                    { number: "2", text: "They add you and the conversation is ready." }
                  ] : [
                    { number: "1", text: "Send the link or QR through a trusted channel" },
                    { number: "2", text: "They redeem the invite once" },
                    { number: "3", text: "Verify and accept the request" }
                  ]

                  delegate: Item {
                    required property var modelData
                    width: inviteSteps.width
                    height: Math.max(inviteStepNumber.implicitHeight,
                                     inviteStepText.implicitHeight)

                    SafeText {
                      id: inviteStepNumber
                      anchors.left: parent.left
                      anchors.top: parent.top
                      width: Style.space(14)
                      text: modelData.number
                      color: root.dim
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.bodySmall
                    }

                    SafeText {
                      id: inviteStepText
                      anchors.left: inviteStepNumber.right
                      anchors.right: parent.right
                      anchors.top: parent.top
                      anchors.leftMargin: Style.space(6)
                      text: modelData.text
                      color: root.foreground
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.bodySmall
                      wrapMode: Text.WordWrap
                    }
                  }
                }
              }

              GridLayout {
                visible: root.inviteConfirmMode === ""
                width: parent.width
                columns: 2
                columnSpacing: root.btnGap
                rowSpacing: Style.space(4)

                ActionButton {
                  Layout.fillWidth: true
                  text: root.copied ? "Copied" : "Copy link"
                  enabled: !root.inviteActionPending && root.inviteRemainingSeconds > 0
                  onClicked: root.copyInvite()
                }
                ActionButton {
                  Layout.fillWidth: true
                  text: "New link"
                  enabled: !root.inviteActionPending
                  onClicked: root.inviteConfirmMode = "replace"
                }
                ActionButton {
                  Layout.columnSpan: 2
                  Layout.fillWidth: true
                  text: "Revoke"
                  accent: root.urgent
                  enabled: !root.inviteActionPending
                  onClicked: root.inviteConfirmMode = "revoke"
                }
              }

              SafeText {
                visible: root.inviteConfirmMode !== ""
                width: parent.width
                text: root.inviteConfirmMode === "replace"
                  ? "Revoke this invite and create a new link?"
                  : "Revoke this invite? It cannot be used again."
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }

              GridLayout {
                visible: root.inviteConfirmMode !== ""
                width: parent.width
                columns: 2
                columnSpacing: root.btnGap
                ActionButton {
                  Layout.fillWidth: true
                  text: "Cancel"
                  onClicked: root.inviteConfirmMode = ""
                }
                ActionButton {
                  Layout.fillWidth: true
                  text: root.inviteConfirmMode === "replace" ? "New link" : "Revoke"
                  accent: root.urgent
                  onClicked: root.startInviteRevoke(root.inviteConfirmMode === "replace")
                }
              }

              SafeText {
                visible: root.inviteFeedback !== ""
                width: parent.width
                text: root.inviteFeedback
                color: root.inviteFeedbackError ? root.urgent : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                wrapMode: Text.WordWrap
              }
            }

            Column {
              visible: root.inviteOpen && omaq.inviteUrl === ""
              width: parent.width
              spacing: Style.space(8)

              PanelSectionHeader {
                text: "INVITATION"
                foreground: root.foreground
                fontFamily: root.fontFamily
              }
              SafeText {
                visible: root.inviteFeedback !== ""
                width: parent.width
                text: root.inviteFeedback
                color: root.inviteFeedbackError ? root.urgent : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }
              ActionButton {
                width: parent.width
                text: "Create new invite"
                enabled: !root.inviteActionPending
                onClicked: root.startInviteCreate("create")
              }
            }

            Column {
              visible: root.showJoin
              width: parent.width
              spacing: Style.space(8)

              PanelSectionHeader {
                text: "JOIN"
                foreground: root.foreground
                fontFamily: root.fontFamily
              }

              TokenTextField {
                id: redeemField
                width: parent.width
                foreground: root.controlForeground
                placeholderText: "Paste an invite link"
                text: root.redeemDraft
                enabled: root.redeemRequest === ""
                onTextEdited: {
                  root.redeemDraft = text
                  if (root.redeemRequest === "") {
                    root.redeemFeedback = ""
                    root.redeemFeedbackRequest = ""
                    root.redeemSafety = ""
                  }
                }
                onAccepted: if (joinBtn.enabled) joinBtn.clicked()
              }

              TokenButton {
                id: joinBtn
                width: parent.width
                text: "Join chat"
                bordered: true
                focusable: true
                foreground: root.foreground
                fontFamily: root.fontFamily
                enabled: root.redeemRequest === ""
                onClicked: {
                  root.redeemSafety = ""
                  var invite = Model.parseInvite(root.redeemDraft)
                  if (invite) {
                    var request = omaq.redeem(invite.url)
                    if (request === "legacy") {
                      root.redeemFeedbackRequest = ""
                      root.redeemFeedback = "Invite submitted to the older helper. Check your contacts before trying it again."
                    } else if (request !== "") {
                      root.redeemRequest = request
                      root.redeemFeedbackRequest = request
                      root.redeemFeedback = "Checking invite…"
                    } else {
                      root.redeemFeedback = "Harbor is not ready to check this invite."
                    }
                  } else {
                    root.redeemFeedback = root.errorText("unsupported")
                  }
                }
              }

              SafeText {
                visible: root.redeemFeedback !== ""
                width: parent.width
                text: root.redeemFeedback
                color: root.redeemFeedback === "Checking invite…"
                  ? root.dim : (root.redeemFeedback.indexOf("Waiting") >= 0
                    ? (root.systemColors[3] || root.onlineStatusColor) : root.urgent)
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }

              SafeText {
                id: redeemedInviteSafety
                visible: root.redeemSafety !== ""
                width: parent.width
                text: root.redeemSafety.replace(" / ", "\n")
                color: root.systemColors[3] || root.controlAccent
                font.family: "monospace"
                font.pixelSize: Style.font.caption
                wrapMode: Text.Wrap
                Accessible.name: "Redeemed invite safety code " + root.redeemSafety
              }

              SafeText {
                visible: redeemedInviteSafety.visible
                width: parent.width
                text: "Compare this code with your friend before they accept"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                wrapMode: Text.WordWrap
              }
            }

            TokenButton {
              visible: false
              text: root.moreOpen ? "Hide advanced" : "Advanced"
              iconText: "tune"
              iconFontFamily: "Material Symbols Rounded"
              focusable: true
              bordered: true
              selected: root.moreOpen
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.toggleAdvanced()
            }

            Column {
              visible: root.moreOpen
              width: parent.width
              spacing: Style.space(8)

              GridLayout {
                visible: false
                width: parent.width
                columns: 2
                columnSpacing: root.btnGap
                rowSpacing: Style.space(4)

                ActionButton {
                  Layout.fillWidth: true
                  iconText: "shield"
                  iconFontFamily: "Material Symbols Rounded"
                  text: "Safety code"
                  selected: root.moreSection === "chat"
                  onClicked: root.toggleMoreSection("chat")
                }
                ActionButton {
                  Layout.fillWidth: true
                  iconText: "󰡉"
                  iconFontFamily: "monospace"
                  text: "Groups"
                  selected: root.moreSection === "groups"
                  onClicked: root.toggleMoreSection("groups")
                }
                ActionButton {
                  Layout.fillWidth: true
                  iconText: "󰈙"
                  text: "Identity"
                  selected: root.moreSection === "identity"
                  onClicked: root.toggleMoreSection("identity")
                }
                ActionButton {
                  Layout.fillWidth: true
                  iconText: "󰀦"
                  text: "Danger"
                  selected: root.moreSection === "danger"
                  accent: root.urgent
                  onClicked: root.toggleMoreSection("danger")
                }
              }

              PanelSectionHeader {
                visible: root.moreSection === "chat"
                text: "SAFETY CODE"
                foreground: root.foreground
                fontFamily: root.fontFamily
              }

              SafeText {
                id: safetyContactEmpty
                visible: root.moreSection === "chat" && (!omaq.friends || omaq.friends.length === 0)
                width: parent.width
                text: "Add a direct contact before comparing safety codes."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                wrapMode: Text.WordWrap
              }

              Flow {
                id: safetyContactChoices
                visible: root.moreSection === "chat" && omaq.friends && omaq.friends.length > 0
                width: parent.width
                spacing: Style.space(4)

                Repeater {
                  model: omaq.friends || []
                  delegate: TokenButton {
                    required property var modelData
                    width: Math.min(implicitWidth, safetyContactChoices.width)
                    text: String(modelData.name || ("Friend " + modelData.id))
                    selected: String(modelData.id || "") === String(omaq.selectedDirectId || "")
                    focusable: true
                    foreground: root.foreground
                    fontFamily: root.fontFamily
                    onClicked: root.selectSafetyContact(modelData.id)
                  }
                }
              }

              ActionButton {
                id: safetyShowButton
                visible: root.moreSection === "chat" && omaq.selectedDirectId !== "" &&
                  (!root.safetyCodeVisible || root.currentSafetyCode === "")
                width: parent.width
                iconText: "󰌾"
                text: "Show safety code"
                onClicked: root.showSafetyCode()
              }

              SafeText {
                visible: root.moreSection === "chat" && omaq.selectedDirectId !== "" &&
                  (!root.safetyCodeVisible || root.currentSafetyCode === "")
                width: parent.width
                text: "Matching codes verify the same two transport identities."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                wrapMode: Text.WordWrap
              }

              Column {
                visible: root.moreSection === "chat" && root.safetyCodeVisible &&
                  root.currentSafetyCode !== ""
                width: parent.width
                spacing: Style.space(6)

                PanelSectionHeader {
                  text: "SAFETY CODE"
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                }

                SafeText {
                  width: parent.width
                  text: root.currentSafetyCode
                  color: root.foreground
                  font.family: "monospace"
                  font.pixelSize: Style.font.bodySmall
                  wrapMode: Text.WordWrap
                }

                Row {
                  width: parent.width
                  spacing: root.btnGap
                  ActionButton {
                    width: (parent.width - root.btnGap) / 2
                    iconText: root.safetyCopied ? "check" : "content_copy"
                    iconFontFamily: "Material Symbols Rounded"
                    text: root.safetyCopied ? "Copied" : "Copy"
                    onClicked: root.copySafetyCode()
                  }
                  ActionButton {
                    width: (parent.width - root.btnGap) / 2
                    iconText: "visibility_off"
                    iconFontFamily: "Material Symbols Rounded"
                    text: "Hide"
                    onClicked: root.hideSafetyCode()
                  }
                }
              }

              PanelSeparator {
                visible: root.moreSection === "chat" && root.safetyCodeVisible &&
                  root.currentSafetyCode !== ""
                foreground: root.foreground
              }

              PanelSectionHeader {
                visible: root.moreSection === "groups"
                text: "GROUPS"
                foreground: root.foreground
                fontFamily: root.fontFamily
              }

              Column {
                visible: root.moreSection === "groups"
                width: parent.width
                spacing: root.btnGap

                TokenTextField {
                  id: groupNameField
                  width: parent.width
                  foreground: root.controlForeground
                  placeholderText: "Group name"
                  onAccepted: createGroupButton.clicked()
                }

                ActionButton {
                  id: createGroupButton
                  width: parent.width
                  height: root.actionButtonHeight
                  text: "Create"
                  enabled: omaq.groupTitleOk(groupNameField.text)
                  onClicked: {
                    if (omaq.createGroup(groupNameField.text.trim()))
                      groupNameField.text = ""
                  }
                }
              }

              SafeText {
                visible: root.moreSection === "groups" &&
                  (!omaq.groups || omaq.groups.length === 0)
                width: parent.width
                text: !omaq.groupsReady
                  ? (omaq.groupProjectionFailed
                    ? "Groups could not be loaded — close and reopen Groups to retry"
                    : "Loading groups…")
                  : "No groups yet"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Column {
                visible: root.moreSection === "groups" && omaq.groups && omaq.groups.length > 0
                width: parent.width
                spacing: Style.space(4)

                Repeater {
                  model: omaq.groups || []
                  delegate: TokenButton {
                    required property var modelData
                    width: parent ? parent.width : 0
                    text: String(modelData.title || "Group") + " · " +
                      String(modelData.memberCount || 0) + "/" + String(modelData.limit || 10)
                    selected: String(modelData.id || "") === String(omaq.lastGroup || "")
                    enabled: root.groupInviteFeedback !== "Sending group invite…"
                    bordered: true
                    focusable: true
                    foreground: root.foreground
                    fontFamily: root.fontFamily
                    onClicked: {
                      omaq.selectGroup(modelData.id)
                      root.groupInviteGroupId = ""
                      root.groupInviteFriendId = ""
                      root.groupInviteFriendKey = ""
                      root.groupInviteRequest = ""
                      root.groupInviteGeneration = -1
                      root.groupInviteFeedback = ""
                      root.groupLeaveConfirm = false
                      root.groupLeaveTarget = ""
                      root.groupDissolveConfirm = false
                      root.groupDissolveTarget = ""
                    }
                  }
                }
              }

              ActionButton {
                visible: root.moreSection === "groups" && omaq.lastGroup !== ""
                width: parent.width
                iconText: "chat"
                iconFontFamily: "Material Symbols Rounded"
                text: "Open " + omaq.groupName(omaq.lastGroup)
                onClicked: root.openGroup(omaq.lastGroup)
              }

              PanelSectionHeader {
                visible: root.moreSection === "groups" && omaq.lastGroup !== ""
                text: "INVITE CONTACT TO GROUP"
                foreground: root.foreground
                fontFamily: root.fontFamily
              }

              Flow {
                visible: root.moreSection === "groups" && omaq.lastGroup !== "" &&
                  omaq.groupInviteCandidates(omaq.lastGroup).length > 0
                width: parent.width
                spacing: Style.space(4)

                Repeater {
                  model: omaq.groupInviteCandidates(omaq.lastGroup)
                  delegate: TokenButton {
                    required property var modelData
                    text: String(modelData.name || ("Friend " + modelData.id))
                    selected: String(modelData.id || "") === root.groupInviteFriendId
                    enabled: root.groupInviteFeedback !== "Sending group invite…"
                    focusable: true
                    foreground: root.foreground
                    fontFamily: root.fontFamily
                    onClicked: {
                      root.groupInviteFriendId = String(modelData.id || "")
                      root.groupInviteFriendKey = String(modelData.key || "")
                      root.groupInviteRequest = ""
                      root.groupInviteGeneration = -1
                      root.groupInviteFeedback = ""
                    }
                  }
                }
              }

              ActionButton {
                visible: root.moreSection === "groups" && omaq.lastGroup !== ""
                width: parent.width
                text: root.groupInviteFriendId
                  ? "Invite contact · " + root.friendName(root.groupInviteFriendId)
                  : "Select a contact"
                enabled: root.friendMatches(root.groupInviteFriendId,
                  root.groupInviteFriendKey) &&
                  root.groupInviteCandidateMatches(omaq.lastGroup,
                    root.groupInviteFriendId, root.groupInviteFriendKey) &&
                  root.groupInviteFeedback !== "Sending group invite…"
                onClicked: {
                  root.groupInviteGroupId = String(omaq.lastGroup || "")
                  root.groupInviteRequest = omaq.nextGroupInviteRequest()
                  root.groupInviteGeneration = Number(omaq.helperInstanceGeneration || 0)
                  root.groupInviteFeedback = "Sending group invite…"
                  if (!omaq.inviteToGroup(root.groupInviteFriendId,
                        root.groupInviteFriendKey, root.groupInviteGroupId,
                        root.groupInviteRequest))
                    root.groupInviteFeedback = "Group invite failed"
                }
              }

              SafeText {
                visible: root.moreSection === "groups" && root.groupInviteFeedback !== ""
                width: parent.width
                text: root.groupInviteFeedback
                color: root.groupInviteFeedback.indexOf("sent") >= 0 ||
                  root.groupInviteFeedback.indexOf("Sending") === 0
                  ? root.systemColors[3] : root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }

              SafeText {
                visible: root.moreSection === "groups" && root.groupLeaveConfirm
                width: parent.width
                text: "Leave " + omaq.groupName(root.groupLeaveTarget) + "?"
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }

              Row {
                visible: root.moreSection === "groups" && omaq.lastGroup !== ""
                width: parent.width
                spacing: root.btnGap

                ActionButton {
                  width: root.groupLeaveConfirm
                    ? (parent.width - parent.spacing) / 2 : parent.width
                  text: root.groupLeaveConfirm ? "Cancel" : "Leave " + omaq.groupName(omaq.lastGroup)
                  accent: root.groupLeaveConfirm ? root.controlAccent : root.urgent
                  onClicked: {
                    root.groupDissolveConfirm = false
                    root.groupDissolveTarget = ""
                    root.groupLeaveConfirm = !root.groupLeaveConfirm
                    root.groupLeaveTarget = root.groupLeaveConfirm
                      ? String(omaq.lastGroup || "") : ""
                  }
                }
                ActionButton {
                  visible: root.groupLeaveConfirm
                  width: visible ? (parent.width - parent.spacing) / 2 : 0
                  text: "Leave now"
                  accent: root.urgent
                  onClicked: {
                    var target = root.groupLeaveTarget
                    root.groupLeaveConfirm = false
                    root.groupLeaveTarget = ""
                    omaq.leaveGroup(target)
                  }
                }
              }

              SafeText {
                visible: root.moreSection === "groups" && root.groupDissolveConfirm
                width: parent.width
                text: "Dissolve " + omaq.groupName(root.groupDissolveTarget) + " for every member?"
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }

              Row {
                visible: root.moreSection === "groups" && omaq.lastGroup !== "" &&
                  omaq.groupSelfRole(root.groupDissolveConfirm
                    ? root.groupDissolveTarget : omaq.lastGroup) === "owner"
                width: parent.width
                spacing: root.btnGap

                ActionButton {
                  width: root.groupDissolveConfirm
                    ? (parent.width - parent.spacing) / 2 : parent.width
                  text: root.groupDissolveConfirm ? "Cancel" : "Dissolve group"
                  accent: root.groupDissolveConfirm ? root.controlAccent : root.urgent
                  onClicked: {
                    root.groupLeaveConfirm = false
                    root.groupLeaveTarget = ""
                    root.groupDissolveConfirm = !root.groupDissolveConfirm
                    root.groupDissolveTarget = root.groupDissolveConfirm
                      ? String(omaq.lastGroup || "") : ""
                  }
                }
                ActionButton {
                  visible: root.groupDissolveConfirm
                  width: visible ? (parent.width - parent.spacing) / 2 : 0
                  text: "Dissolve now"
                  accent: root.urgent
                  onClicked: {
                    var target = root.groupDissolveTarget
                    root.groupDissolveConfirm = false
                    root.groupDissolveTarget = ""
                    omaq.dissolveGroup(target)
                  }
                }
              }

              PanelSeparator {
                visible: root.moreSection === "groups"
                foreground: root.foreground
              }

              PanelSectionHeader {
                visible: root.moreSection === "identity"
                text: "Recovery"
                foreground: root.foreground
                fontFamily: root.fontFamily
              }

              SafeText {
                visible: root.moreSection === "identity"
                width: parent.width
                text: omaq.saveProtected ? "This computer’s backup is password-protected." : "This computer’s backup is not password-protected."
                color: omaq.saveProtected ? root.onlineStatusColor
                  : (root.systemColors[1] || root.dim)
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: true
              }

              SafeText {
                visible: root.moreSection === "identity" && !omaq.supportsIdentityActions
                width: parent.width
                text: "Update Harbor to use backups on this computer."
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }

              TokenTextField {
                id: passField
                visible: root.moreSection === "identity"
                width: parent.width
                foreground: root.controlForeground
                password: true
                maximumLength: 128
                placeholderText: omaq.saveProtected
                  ? "Backup password"
                  : "Password for a protected backup, if needed"
                enabled: omaq.supportsIdentityActions && !root.identityActionPending
                onTextEdited: if (!root.identityActionPending)
                  root.clearIdentityFeedback()
              }

              SafeText {
                visible: root.moreSection === "identity" && root.recoveryDetailsOpen && !omaq.saveProtected
                width: parent.width
                text: "For a new password, use 8–128 bytes."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                wrapMode: Text.WordWrap
              }

              SafeText {
                visible: root.moreSection === "identity"
                width: parent.width
                text: "This backup saves this computer’s connection identity. It does not include chat history or linked-profile recovery. To add a computer, use Devices instead."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                wrapMode: Text.WordWrap
              }

              TokenTextField {
                id: importPath
                visible: false
                width: parent.width
                foreground: root.controlForeground
                maximumLength: 511
                placeholderText: "Selected identity bundle"
                enabled: omaq.supportsIdentityActions && !root.identityActionPending
                onTextEdited: if (!root.identityActionPending)
                  root.clearIdentityFeedback()
                onTextChanged: {
                  if (root.replaceIdentityConfirm && text.trim() !== root.replaceIdentityPath) {
                    root.replaceIdentityConfirm = false
                    root.replaceIdentityPath = ""
                  }
                }
              }

              GridLayout {
                id: identityActions
                visible: root.moreSection === "identity" && !root.replaceIdentityConfirm
                width: parent.width
                columns: 2
                columnSpacing: root.btnGap
                rowSpacing: root.btnGap
                readonly property real actionWidth: Math.max(0,
                  (width - columnSpacing) / columns)

                ActionButton {
                  Layout.fillWidth: true
                  Layout.preferredWidth: identityActions.actionWidth
                  Layout.preferredHeight: root.actionButtonHeight
                  iconText: omaq.saveProtected ? "lock_open" : "lock"
                  iconFontFamily: "Material Symbols Rounded"
                  text: omaq.saveProtected ? "Remove password" : "Set password"
                  visible: root.recoveryDetailsOpen
                  focusable: true
                  enabled: omaq.supportsIdentityActions && !root.identityActionPending &&
                    (omaq.saveProtected
                      ? root.identityExistingPassphraseValid(passField.text)
                      : root.identityNewPassphraseValid(passField.text))
                  onClicked: root.runIdentityAction(
                    omaq.saveProtected ? "unprotect" : "protect", "")
                }

                ActionButton {
                  Layout.fillWidth: true
                  Layout.preferredWidth: identityActions.actionWidth
                  Layout.preferredHeight: root.actionButtonHeight
                  iconText: "file_upload"
                  iconFontFamily: "Material Symbols Rounded"
                  text: "Save backup"
                  focusable: true
                  enabled: omaq.supportsIdentityActions && !root.identityActionPending
                  onClicked: root.startIdentityPicker("export")
                }

                ActionButton {
                  Layout.fillWidth: true
                  Layout.preferredWidth: identityActions.actionWidth
                  Layout.preferredHeight: root.actionButtonHeight
                  iconText: "file_open"
                  iconFontFamily: "Material Symbols Rounded"
                  text: "Check backup"
                  visible: false
                  focusable: true
                  enabled: omaq.supportsIdentityActions && !root.identityActionPending
                  onClicked: {
                    root.replaceIdentityConfirm = false
                    root.replaceIdentityPath = ""
                    var path = importPath.text.trim()
                    if (path !== "")
                      root.runIdentityAction("import", path)
                    else
                      root.startIdentityPicker("import")
                  }
                }

                ActionButton {
                  Layout.fillWidth: true
                  Layout.preferredWidth: identityActions.actionWidth
                  Layout.preferredHeight: root.actionButtonHeight
                  iconText: "published_with_changes"
                  iconFontFamily: "Material Symbols Rounded"
                  text: "Restore backup"
                  focusable: true
                  accent: root.urgent
                  enabled: omaq.supportsIdentityActions && !root.identityActionPending
                  onClicked: root.startIdentityPicker("replace")
                }
              }

              TokenButton {
                visible: root.moreSection === "identity" && !root.replaceIdentityConfirm
                text: root.recoveryDetailsOpen ? "Hide password settings" : "Password settings"
                borderless: true; focusable: true
                onClicked: root.recoveryDetailsOpen = !root.recoveryDetailsOpen
              }

              SafeText {
                visible: root.moreSection === "identity" && root.identityFeedback !== ""
                width: parent.width
                text: root.identityFeedback
                color: root.identityFeedbackError ? root.urgent
                  : (root.systemColors[3] || root.onlineStatusColor)
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WrapAnywhere
              }

              SafeText {
                visible: root.moreSection === "identity" && root.replaceIdentityConfirm
                width: parent.width
                text: "Replace the profile on this computer with the checked backup? Your existing contacts will need new invites. This does not restore chat history."
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WrapAnywhere
              }

              GridLayout {
                id: identityReplaceActions
                visible: root.moreSection === "identity" && root.replaceIdentityConfirm
                width: parent.width
                columns: 2
                columnSpacing: root.btnGap
                rowSpacing: root.btnGap
                readonly property real actionWidth: Math.max(0,
                  (width - columnSpacing) / columns)

                ActionButton {
                  Layout.fillWidth: true
                  Layout.preferredWidth: identityReplaceActions.actionWidth
                  Layout.preferredHeight: root.actionButtonHeight
                  iconText: "close"
                  iconFontFamily: "Material Symbols Rounded"
                  text: "Cancel"
                  focusable: true
                  enabled: !root.identityActionPending
                  onClicked: {
                    root.replaceIdentityConfirm = false
                    root.replaceIdentityPath = ""
                    root.identityFeedback = ""
                    root.restorePassword = ""
                    passField.text = ""
                  }
                }

                ActionButton {
                  Layout.fillWidth: true
                  Layout.preferredWidth: identityReplaceActions.actionWidth
                  Layout.preferredHeight: root.actionButtonHeight
                  iconText: "published_with_changes"
                  iconFontFamily: "Material Symbols Rounded"
                  text: "Restore backup"
                  focusable: true
                  accent: root.urgent
                  enabled: omaq.supportsIdentityActions && !root.identityActionPending &&
                    root.replaceIdentityPath !== ""
                  onClicked: {
                    var path = root.replaceIdentityPath
                    root.replaceIdentityConfirm = false
                    root.replaceIdentityPath = ""
                    root.runIdentityAction("replace", path, root.restorePassword)
                    root.restorePassword = ""
                  }
                }
              }

              PanelSeparator {
                visible: root.moreSection === "identity"
                foreground: root.foreground
              }

              PanelSectionHeader {
                visible: root.moreSection === "danger"
                text: "DANGER"
                foreground: root.foreground
                fontFamily: root.fontFamily
              }

              GridLayout {
                visible: root.moreSection === "danger" &&
                  !root.nospamConfirm && !root.removeContactPickerOpen &&
                  !root.removeContactConfirm
                width: parent.width
                columns: 2
                columnSpacing: root.btnGap
                rowSpacing: Style.space(4)

                ActionButton {
                  visible: omaq.friends && omaq.friends.length > 0
                  Layout.fillWidth: true
                  iconText: "person_remove"
                  iconFontFamily: "Material Symbols Rounded"
                  text: "Remove"
                  tooltipText: "Remove contact"
                  onClicked: {
                    root.removeContactId = ""
                    root.removeContactKey = ""
                    root.removeContactPickerOpen = true
                  }
                }

                ActionButton {
                  Layout.fillWidth: true
                  iconText: "󰒭"
                  text: "Rotate ID"
                  tooltipText: "Rotate personal ID"
                  onClicked: root.nospamConfirm = true
                }
              }

              Column {
                visible: root.moreSection === "danger" && root.removeContactPickerOpen
                width: parent.width
                spacing: Style.space(4)

                SafeText {
                  width: parent.width
                  text: "Select the contact to remove"
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.bodySmall
                  font.bold: true
                }

                Repeater {
                  model: omaq.friends || []
                  delegate: ActionButton {
                    required property var modelData
                    width: parent ? parent.width : 0
                    iconText: "person"
                    iconFontFamily: "Material Symbols Rounded"
                    text: String(modelData && modelData.name ||
                      ("Friend " + String(modelData && modelData.id || "")))
                    tooltipText: text
                    enabled: /^[0-9a-f]{64}$/.test(String(modelData && modelData.key || ""))
                    onClicked: {
                      root.removeContactId = String(modelData && modelData.id || "")
                      root.removeContactKey = String(modelData && modelData.key || "")
                      root.removeContactPickerOpen = false
                      root.removeContactConfirm = root.friendMatches(
                        root.removeContactId, root.removeContactKey)
                    }
                  }
                }

                ActionButton {
                  width: parent.width
                  text: "Cancel"
                  onClicked: {
                    root.removeContactPickerOpen = false
                    root.removeContactId = ""
                    root.removeContactKey = ""
                  }
                }
              }

              SafeText {
                visible: root.moreSection === "danger" && root.removeContactConfirm
                width: parent.width
                text: "Remove " + root.friendName(root.removeContactId) +
                  "? Chat history stays in local storage."
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }

              GridLayout {
                visible: root.moreSection === "danger" && root.removeContactConfirm
                width: parent.width
                columns: 2
                columnSpacing: root.btnGap
                rowSpacing: Style.space(4)
                ActionButton {
                  Layout.fillWidth: true
                  text: "Cancel"
                  onClicked: {
                    root.removeContactConfirm = false
                    root.removeContactId = ""
                    root.removeContactKey = ""
                  }
                }
                ActionButton {
                  Layout.fillWidth: true
                  iconText: "person_remove"
                  iconFontFamily: "Material Symbols Rounded"
                  text: "Remove"
                  accent: root.urgent
                  enabled: root.friendMatches(root.removeContactId, root.removeContactKey)
                  onClicked: {
                    var selectedContact = root.removeContactId
                    var selectedKey = root.removeContactKey
                    if (root.friendMatches(selectedContact, selectedKey))
                      omaq.removeContact(selectedContact, selectedKey)
                    root.removeContactConfirm = false
                    root.removeContactId = ""
                    root.removeContactKey = ""
                    root.safetyCodeVisible = false
                  }
                }
              }

              SafeText {
                visible: root.moreSection === "danger" && root.nospamConfirm
                width: parent.width
                text: "Rotate your personal ID? This voids every open invite."
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }

              GridLayout {
                visible: root.moreSection === "danger" && root.nospamConfirm
                width: parent.width
                columns: 2
                columnSpacing: root.btnGap
                rowSpacing: Style.space(4)
                ActionButton {
                  Layout.fillWidth: true
                  text: "Cancel"
                  onClicked: root.nospamConfirm = false
                }
                ActionButton {
                  Layout.fillWidth: true
                  iconText: "󰒭"
                  text: "Rotate"
                  accent: root.urgent
                  onClicked: {
                    omaq.rotateNospam()
                    root.nospamConfirm = false
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
}
