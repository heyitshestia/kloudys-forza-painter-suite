import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "XboxControlSurface"
    property var control: null
    property string controlKind: "ghost"
    readonly property bool pressed: control ? control.down : false
    readonly property bool hovered: control ? control.hovered : false
    readonly property bool selected: control ? (controlKind === "nav" ? control.active : (control.checkedState || false)) : false
    readonly property bool focused: control ? control.visualFocus : false
    readonly property bool primary: controlKind === "primary"
    readonly property bool navigation: controlKind === "nav"
    readonly property bool lit: selected || primary
    opacity: control && !control.enabled ? 0.45 : 1

    Rectangle {
        anchors.fill: parent
        radius: root.navigation ? height / 2 : Theme.px(6)
        color: Theme.shadow
        border.color: Theme.panelInnerBorder
    }
    Rectangle {
        id: key
        x: 1
        y: root.pressed ? 2 : 0
        width: parent.width - 2
        height: parent.height - 3
        radius: root.navigation ? height / 2 : Theme.px(6)
        border.width: 1
        border.color: root.selected ? Theme.warning : (root.hovered || root.primary ? Theme.primaryButtonBorder : Theme.border)
        gradient: Gradient {
            GradientStop { position: 0; color: root.selected ? Theme.navActiveTop : (root.primary ? Theme.primaryButtonTop : Theme.surfaceRaised) }
            GradientStop { position: 0.48; color: root.selected ? Theme.navActiveMiddle : (root.primary ? Theme.primaryButtonMiddle : (root.hovered ? Theme.ghostHoverSurface : Theme.ghostSurface)) }
            GradientStop { position: 0.52; color: root.selected ? Theme.navActiveBottom : (root.primary ? Theme.primaryButtonBottom : Theme.surfaceSoft) }
            GradientStop { position: 1; color: root.selected ? Theme.navActiveMiddle : (root.primary ? Theme.primaryButtonMiddle : Theme.ghostSurface) }
        }
        Behavior on y { enabled: !Theme.reducedMotion && !screenshotMode; NumberAnimation { duration: 65 } }
        Rectangle {
            anchors.fill: parent
            anchors.margins: 3
            color: "transparent"
            radius: Math.max(0, parent.radius - 2)
            border.color: root.lit ? Theme.withAlpha(Theme.primaryText, 0.25) : Theme.withAlpha(Theme.innerHighlight, 0.35)
        }
    }
    Rectangle {
        visible: root.focused
        anchors.fill: parent
        anchors.margins: 1
        radius: key.radius
        color: "transparent"
        border.width: 2
        border.color: Theme.focusColor
    }
}
