import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

GlassPanel {
    id: root

    property bool compact: false

    width: Math.min(parent ? parent.width - Theme.px(28) : Theme.px(540),
                    Theme.px(compact ? 460 : 540))
    implicitHeight: content.implicitHeight + Theme.px(compact ? 20 : 24)
    height: implicitHeight
    radius: Theme.px(8)
    strong: true
    raised: true
    visible: supporterService.problemVisible
    opacity: visible ? 1 : 0
    border.color: Theme.danger
    border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1.5))

    Behavior on opacity {
        NumberAnimation {
            duration: Theme.reducedMotion ? 0 : 170
            easing.type: Easing.OutCubic
        }
    }

    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Theme.px(root.compact ? 10 : 12)
        spacing: Theme.px(7)

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.px(9)

            Icon {
                name: "help"
                iconSize: Theme.px(root.compact ? 17 : 19)
                tint: Theme.danger
                glowColor: Theme.danger
                glow: true
                Layout.alignment: Qt.AlignVCenter
            }

            Text {
                Layout.fillWidth: true
                text: supporterService.problemTitle
                color: Theme.danger
                font.family: Theme.displayFamily
                font.pixelSize: Theme.px(root.compact ? 12.2 : 13.2)
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            GhostButton {
                dense: true
                text: "Dismiss"
                minimumWidth: Theme.px(70)
                toolTipText: "Hide this supporter-key message until the state changes or KFPS restarts."
                onClicked: supporterService.dismissProblem()
            }
        }

        Text {
            Layout.fillWidth: true
            text: supporterService.problemMessage
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.compact ? 9.8 : 10.5)
            wrapMode: Text.WordWrap
            maximumLineCount: 3
            elide: Text.ElideRight
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.px(7)

            Text {
                Layout.fillWidth: true
                text: "Support code  " + supporterService.supportCode
                color: Theme.muted
                font.family: Theme.monoFamily
                font.pixelSize: Theme.px(root.compact ? 9.2 : 9.8)
                elide: Text.ElideRight
            }

            GhostButton {
                dense: true
                visible: supporterService.canRepair
                enabled: supporterService.canRepair
                text: "Retry"
                iconName: "refresh"
                toolTipText: "Try supporter-key registration or repair again."
                onClicked: supporterService.repairActivation()
            }

            GhostButton {
                dense: true
                text: "Copy Code"
                toolTipText: "Copy the support code so it can be included in a help request."
                onClicked: supporterService.copySupportCode()
            }
        }
    }
}
