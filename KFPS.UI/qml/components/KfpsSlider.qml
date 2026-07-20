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
        height: Theme.px(Theme.terminalMode ? 3 : 5)
        radius: Theme.corner(height / 2)
        color: root.hovered ? Theme.checkboxHoverSurface : Theme.sliderTrack
        border.width: root.activeFocus
                      ? Theme.px(2)
                      : (Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1)))
        border.color: root.activeFocus ? Theme.focusColor : Theme.borderSoft
        Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 110 } }

        Rectangle {
            width: root.visualPosition * parent.width
            height: parent.height
            radius: Theme.corner(parent.radius)
            color: root.hovered ? Theme.primaryBright : Theme.primary
            Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 110 } }
        }
    }

    handle: Rectangle {
        x: root.leftPadding + root.visualPosition * (root.availableWidth - width)
        y: Math.round((root.height - height) / 2)
        width: Theme.px(Theme.terminalMode ? 10 : 18)
        height: width
        radius: Theme.corner(width / 2)
        color: root.pressed ? Theme.primaryBright : (root.hovered ? Theme.primaryHot : Theme.text)
        border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
        border.color: Theme.primaryBright
        scale: root.pressed ? 0.88 : (root.hovered ? 1.10 : 1.0)

        Behavior on x {
            enabled: !root.pressed && !Theme.reducedMotion
            NumberAnimation { duration: 90; easing.type: Easing.OutCubic }
        }
        Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 100 } }
        Behavior on scale { enabled: !Theme.reducedMotion; NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
    }
}
