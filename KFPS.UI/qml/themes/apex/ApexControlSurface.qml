import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    property var control: null
    property string controlKind: "ghost"
    readonly property bool selected: control ? (controlKind === "nav" ? control.active : control.checkedState || false) : false
    readonly property bool primary: controlKind === "primary"
    readonly property bool hovered: control ? control.hovered : false
    readonly property bool pressed: control ? control.down : false
    readonly property bool focused: control ? control.visualFocus : false
    opacity: control && !control.enabled ? 0.45 : 1
    Rectangle {
        anchors.fill: parent
        color: root.primary ? (root.pressed ? Theme.primaryDeep : root.hovered ? Theme.primaryHot : Theme.primary)
                            : root.controlKind === "nav" && root.selected ? Theme.text
                            : root.pressed ? Theme.ghostPressedSurface
                            : root.hovered || root.selected ? Theme.ghostHoverSurface : Theme.ghostSurface
        border.width: root.focused ? Theme.px(2) : 0
        border.color: Theme.focusColor
        Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 100 } }
    }
    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: Theme.px(root.selected || root.hovered ? 3 : 1)
        color: root.primary ? Theme.primaryDeep : root.selected || root.hovered ? Theme.primary : Theme.border
    }
}
