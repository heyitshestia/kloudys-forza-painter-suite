import QtQuick 6.7
import QtQuick.Window 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Popup {
    id: root
    objectName: "ReleaseAnnouncement"
    parent: Overlay.overlay
    property var service
    property bool ready: false
    property bool blocked: false
    property bool finished: false
    property var notice: ({})
    property string claimToken: ""
    property bool acknowledged: false
    property string client: ""
    property int retryDelay: 350
    property var priorFocus: null
    width: Math.min(Theme.px(720), Math.max(0, parent.width - Theme.px(24)))
    height: Math.min(Theme.px(760), Math.max(0, parent.height - Theme.px(24)))
    x: (parent.width - width) / 2
    y: (parent.height - height) / 2
    padding: Theme.px(20)
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape

    Component.onCompleted: {
        for (let i = 0; i < 32; i++) client += Math.floor(Math.random() * 16).toString(16)
    }
    function attempt() {
        if (!ready || blocked || finished || visible || !service) return
        let result = service.dispatch({ action: "claim", client: client })
        if (result.token) {
            notice = result.content
            claimToken = result.token
            priorFocus = root.parent.Window.window ? root.parent.Window.window.activeFocusItem : null
            expiry.interval = Math.max(1, Math.min(result.remainingMs, Date.parse(result.expiresAt) - Date.now()))
            open()
            expiry.start()
        } else if (result.eligible && result.retryAfterMs) {
            retryDelay = Math.min(30500, result.retryAfterMs)
        } else {
            finished = true
        }
    }
    onOpened: {
        body.forceActiveFocus()
        confirmPaint.restart()
    }
    onClosed: {
        confirmPaint.stop()
        expiry.stop()
        if (claimToken && !acknowledged) service.dispatch({ action: "release", token: claimToken })
        claimToken = ""
        finished = true
        if (priorFocus) priorFocus.forceActiveFocus()
    }
    onReadyChanged: {
        if (!ready && visible && !acknowledged) close()
    }
    Timer {
        interval: root.retryDelay
        repeat: true
        running: root.ready && !root.blocked && !root.finished && !root.visible
        onTriggered: root.attempt()
    }
    Timer {
        id: confirmPaint
        interval: 80
        onTriggered: {
            if (!root.ready || !root.visible || root.blocked || body.width <= 0 || body.height <= 0) {
                root.close()
                return
            }
            let result = root.service.dispatch({ action: "presented", token: root.claimToken })
            root.acknowledged = result.acknowledged === true
            if (!root.acknowledged) root.close()
        }
    }
    Timer { id: expiry; onTriggered: root.close() }
    background: Rectangle {
        color: Qt.rgba(Theme.surfaceRaised.r, Theme.surfaceRaised.g, Theme.surfaceRaised.b, 1)
        border.color: Theme.borderStrong
        border.width: Theme.px(1)
        radius: Theme.corner(Theme.px(8))
    }
    Overlay.modal: Rectangle { color: Qt.rgba(Theme.backgroundA.r, Theme.backgroundA.g, Theme.backgroundA.b, 0.72) }
    contentItem: ColumnLayout {
        Accessible.role: Accessible.Dialog
        Accessible.name: root.notice.title || ""
        spacing: Theme.px(14)
        FastScrollView {
            id: messageScroll
            objectName: "ReleaseAnnouncementScroll"
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            contentHeight: body.implicitHeight
            rightPadding: Theme.px(20)
            ScrollBar.vertical: KfpsScrollBar {
                objectName: "ReleaseAnnouncementScrollBar"
                anchors.top: messageScroll.top
                anchors.right: messageScroll.right
                anchors.bottom: messageScroll.bottom
                policy: ScrollBar.AsNeeded
            }
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            clip: true
            Column {
                id: body
                width: messageScroll.availableWidth
                spacing: Theme.px(14)
                activeFocusOnTab: true
                Text {
                    width: parent.width
                    text: root.notice.title || ""
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: Theme.px(22)
                    font.bold: true
                    renderType: Text.NativeRendering
                }
                Repeater {
                    model: root.notice.blocks || []
                    delegate: Column {
                        required property var modelData
                        width: body.width
                        spacing: Theme.px(6)
                        Text {
                            visible: text.length > 0
                            width: parent.width
                            text: modelData.heading || ""
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(16)
                            font.bold: true
                            renderType: Text.NativeRendering
                        }
                        Text {
                            width: parent.width
                            text: modelData.text || ""
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(15)
                            renderType: Text.NativeRendering
                        }
                    }
                }
                Text {
                    width: parent.width
                    text: root.notice.closing || ""
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(15)
                    font.bold: true
                    renderType: Text.NativeRendering
                }
            }
        }
        GridLayout {
            id: actions
            Layout.fillWidth: true
            columns: root.width < Theme.px(430) ? 1 : 2
            columnSpacing: Theme.px(10)
            rowSpacing: Theme.px(8)
            readonly property real columnWidth: (root.availableWidth - (columns - 1) * columnSpacing) / columns
            GhostButton {
                objectName: "ReleaseAnnouncementSupport"
                Layout.fillWidth: true
                Layout.preferredWidth: actions.columnWidth
                maximumTextWidth: Math.max(0, actions.columnWidth - Theme.px(30))
                text: root.notice.supportLabel || ""
                enabled: root.acknowledged
                onClicked: root.service.dispatch({ action: "support", token: root.claimToken })
            }
            PrimaryButton {
                objectName: "ReleaseAnnouncementClose"
                Layout.fillWidth: true
                Layout.preferredWidth: actions.columnWidth
                maximumTextWidth: Math.max(0, actions.columnWidth - Theme.px(30))
                text: root.notice.closeLabel || ""
                onClicked: root.close()
            }
        }
    }
}
