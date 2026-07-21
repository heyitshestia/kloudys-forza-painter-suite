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
        height: Theme.px(Theme.classicMode ? 6 : (Theme.terminalMode ? 3 : 5))
        radius: Theme.corner(height / 2)
        color: Theme.angularControlsEnabled ? "transparent" : (root.hovered ? Theme.checkboxHoverSurface : Theme.sliderTrack)
        border.width: Theme.classicMode
                      ? 0
                      : (Theme.angularControlsEnabled
                      ? 0
                      : (root.activeFocus
                      ? Theme.px(2)
                      : (Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1)))))
        border.color: root.activeFocus ? Theme.focusColor : Theme.borderSoft
        Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 110 } }

        Rectangle {
            visible: Theme.angularControlsEnabled
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            height: Math.max(1, Theme.px(root.activeFocus ? 2 : 1))
            color: root.activeFocus ? Theme.signalSecondary : (root.hovered ? Theme.primary : Theme.borderStrong)
        }

        Row {
            visible: Theme.angularControlsEnabled
            anchors.right: parent.right
            anchors.rightMargin: Theme.px(2)
            anchors.bottom: parent.top
            anchors.bottomMargin: Theme.px(2)
            spacing: Theme.px(2)

            Repeater {
                model: 4
                Rectangle {
                    required property int index
                    width: Theme.px(index === 3 ? 7 : 2)
                    height: Math.max(1, Theme.px(1))
                    color: index === 3 ? Theme.signalSecondary : Theme.signalPrimary
                    opacity: 0.72
                }
            }
        }

        Rectangle {
            visible: !Theme.classicMode
            width: root.visualPosition * parent.width
            height: parent.height
            radius: Theme.angularControlsEnabled ? 0 : Theme.corner(parent.radius)
            color: root.hovered ? Theme.primaryBright : Theme.primary
            Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 110 } }
        }

        ClassicBevel {
            anchors.fill: parent
            sunken: true
            depth: 1
        }
    }

    handle: Rectangle {
        x: root.leftPadding + root.visualPosition * (root.availableWidth - width)
        y: Math.round((root.height - height) / 2)
        width: Theme.px(Theme.classicMode ? 11 : (Theme.terminalMode ? 10 : 18))
        height: Theme.px(Theme.classicMode ? 21 : (Theme.terminalMode ? 10 : 18))
        radius: Theme.corner(width / 2)
        color: Theme.angularControlsEnabled
               ? "transparent"
               : (Theme.classicMode ? Theme.surface : (root.pressed ? Theme.primaryBright : (root.hovered ? Theme.primaryHot : Theme.text)))
        border.width: Theme.classicMode || Theme.angularControlsEnabled ? 0 : (Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1)))
        border.color: Theme.primaryBright
        scale: Theme.classicMode ? 1.0 : (root.pressed ? 0.88 : (root.hovered ? 1.10 : 1.0))

        AngularControlFrame {
            anchors.fill: parent
            fillColor: root.pressed ? Theme.primaryBright : (root.hovered ? Theme.primaryHot : Theme.text)
            borderColor: root.activeFocus ? Theme.focusColor : Theme.signalSecondary
            accentColor: Theme.signalSecondary
            hovered: root.hovered
            pressed: root.pressed
            selected: root.activeFocus
            focused: root.activeFocus
            cutOverride: Theme.px(4)
            notchOverride: Theme.px(2)
        }

        ClassicBevel {
            anchors.fill: parent
            pressed: root.pressed
        }

        ClassicFocusRect {
            anchors.fill: parent
            anchors.margins: Theme.px(3)
            active: root.activeFocus && !root.pressed
        }

        Behavior on x {
            enabled: !root.pressed && !Theme.reducedMotion
            NumberAnimation { duration: 90; easing.type: Easing.OutCubic }
        }
        Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 100 } }
        Behavior on scale { enabled: !Theme.reducedMotion; NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
    }
}
