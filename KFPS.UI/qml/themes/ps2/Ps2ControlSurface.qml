import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    property var control: null
    property string controlKind: "ghost"
    readonly property bool pressed: control ? control.down : false
    readonly property bool hovered: control ? control.hovered : false
    readonly property bool selected: control ? (controlKind === "nav" ? control.active : (control.checkedState || false)) : false
    readonly property bool focused: control ? control.visualFocus : false
    readonly property bool primary: controlKind === "primary"
    opacity: control && !control.enabled ? 0.45 : 1
    Rectangle {
        anchors.fill: parent
        radius: Theme.px(3)
        border.color: root.focused || root.selected ? Theme.focusColor : (root.hovered ? Theme.primary : Theme.border)
        border.width: root.focused ? 2 : 1
        gradient: Gradient {
            GradientStop { position: 0; color: root.primary || root.selected ? Theme.primaryButtonTop : (root.hovered ? Theme.ghostHoverSurface : Theme.surfaceRaised) }
            GradientStop { position: 1; color: root.primary || root.selected ? Theme.primaryButtonBottom : (root.pressed ? Theme.ghostPressedSurface : Theme.ghostSurface) }
        }
        Behavior on border.color { enabled: !Theme.reducedMotion && !screenshotMode; ColorAnimation { duration: 120 } }
    }
}
