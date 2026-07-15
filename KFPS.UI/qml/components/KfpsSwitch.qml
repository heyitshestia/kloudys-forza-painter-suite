import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Switch {
    id: root

    objectName: "KfpsSwitch:" + root.text

    property bool dense: false
    property string toolTipText: ""
    readonly property string effectiveToolTipText: toolTipText.trim().length > 0 ? toolTipText : text

    spacing: Theme.px(10)
    leftPadding: 0
    rightPadding: 0
    topPadding: Theme.px(2)
    bottomPadding: Theme.px(2)
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    KfpsToolTip {
        visible: root.hovered && root.effectiveToolTipText.length > 0
        text: root.effectiveToolTipText
    }

    implicitHeight: Math.max(
                        Theme.px(dense ? 26 : 30),
                        Math.max(switchTrack.implicitHeight, labelText.implicitHeight) + topPadding + bottomPadding)
    implicitWidth: switchTrack.implicitWidth + spacing + labelText.implicitWidth
    Layout.minimumHeight: root.implicitHeight

    indicator: Rectangle {
        id: switchTrack
        implicitWidth: Theme.px(dense ? 38 : 42)
        implicitHeight: Theme.px(dense ? 20 : 22)
        y: Math.round((root.height - height) / 2)
        radius: height / 2
        color: root.checked ? Theme.primaryDeep : Theme.switchTrackOff
        border.width: root.activeFocus ? Theme.px(2) : Theme.px(1)
        border.color: root.activeFocus ? Theme.focusColor
                                       : (root.checked ? Theme.primaryBright
                                                       : (root.hovered ? Theme.primary : Theme.borderSoft))

        Rectangle {
            width: Theme.px(dense ? 14 : 16)
            height: width
            radius: width / 2
            y: Math.round((parent.height - height) / 2)
            x: root.checked ? parent.width - width - Theme.px(3) : Theme.px(3)
            color: root.checked ? Theme.primaryText : Theme.muted

            Behavior on x {
                enabled: !Theme.reducedMotion
                NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
            }
        }
    }

    contentItem: Text {
        id: labelText
        leftPadding: switchTrack.implicitWidth + root.spacing
        text: root.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.px(dense ? 10.5 : 11.5)
        color: root.enabled ? Theme.text : Theme.subtle
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideRight
    }
}
