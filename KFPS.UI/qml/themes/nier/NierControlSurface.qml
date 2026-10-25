import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    property var control: null
    property string controlKind: "ghost"
    readonly property bool selected: control ? (controlKind === "nav" ? control.active : (control.checkedState || false)) : false
    readonly property bool primary: controlKind === "primary"
    readonly property bool hovered: control ? control.hovered : false
    readonly property bool pressed: control ? control.down : false
    readonly property bool focused: control ? control.visualFocus : false
    opacity: control && !control.enabled ? 0.45 : 1
    Rectangle {
        anchors.fill: parent
        color: root.primary || (root.selected && root.controlKind === "nav") ? Theme.primary : root.pressed ? Theme.ghostPressedSurface : root.hovered || root.selected ? Theme.ghostHoverSurface : Theme.ghostSurface
        border.color: root.focused || root.selected ? Theme.focusColor : Theme.border
        border.width: root.focused ? 2 : 1
    }
    Rectangle { x: 3; y: 3; width: 2; height: Math.max(0, parent.height - 6); color: root.primary || (root.selected && root.controlKind === "nav") ? Theme.primaryText : Theme.text; opacity: root.hovered || root.focused || root.selected ? 1 : 0.3 }
}
