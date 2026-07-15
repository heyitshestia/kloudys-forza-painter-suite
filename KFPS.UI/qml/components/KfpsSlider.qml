import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Slider {
    id: root

    objectName: "KfpsSlider"

    property string toolTipText: "Adjust this value."

    implicitWidth: Theme.px(220)
    implicitHeight: Theme.px(30)
    Layout.minimumWidth: Theme.px(120)
    Layout.minimumHeight: implicitHeight
    leftPadding: Theme.px(4)
    rightPadding: Theme.px(4)
    topPadding: 0
    bottomPadding: 0
    focusPolicy: Qt.StrongFocus
    hoverEnabled: true

    KfpsToolTip {
        visible: root.hovered && root.toolTipText.length > 0
        text: root.toolTipText
    }

    background: Rectangle {
        x: root.leftPadding
        y: Math.round((root.height - height) / 2)
        width: root.availableWidth
        height: Theme.px(5)
        radius: height / 2
        color: Theme.sliderTrack
        border.width: Math.max(1, Theme.px(1))
        border.color: root.activeFocus ? Theme.focusColor : Theme.borderSoft

        Rectangle {
            width: root.visualPosition * parent.width
            height: parent.height
            radius: parent.radius
            color: Theme.primary
        }
    }

    handle: Rectangle {
        x: root.leftPadding + root.visualPosition * (root.availableWidth - width)
        y: Math.round((root.height - height) / 2)
        width: Theme.px(18)
        height: width
        radius: width / 2
        color: root.pressed ? Theme.primaryBright : Theme.text
        border.width: Math.max(1, Theme.px(1))
        border.color: Theme.primaryBright

        Behavior on x {
            enabled: !root.pressed && !Theme.reducedMotion
            NumberAnimation { duration: 90; easing.type: Easing.OutCubic }
        }
    }
}
