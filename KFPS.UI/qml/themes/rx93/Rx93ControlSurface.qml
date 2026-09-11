import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "Rx93ControlSurface"
    property var control: null
    property string controlKind: "ghost"
    readonly property bool pressed: control ? control.down : false
    readonly property bool hovered: control ? control.hovered : false
    readonly property bool selected: control ? (controlKind === "nav" ? control.active : (control.checkedState || false)) : false
    readonly property bool available: control ? control.enabled : true
    readonly property bool focused: control ? control.visualFocus : false
    readonly property bool ceramic: controlKind === "primary" || (controlKind === "nav" && selected)
    opacity: available ? 1 : 0.45

    Rectangle { anchors.fill: parent; radius: 3; color: "#080d13" }
    Rx93ArmorPlate {
        id: cap
        x: 0
        y: root.pressed ? Theme.px(2) : 0
        width: parent.width
        height: parent.height - Theme.px(2)
        part: root.ceramic ? "ceramic-key" : "navy-key"
        Behavior on y { enabled: !Theme.reducedMotion && !screenshotMode; NumberAnimation { duration: 70; easing.type: Easing.OutCubic } }
    }
    // Edge lighting preserves the material instead of washing out the whole key.
    Rectangle {
        x: Theme.px(13); y: Theme.px(2)
        width: Math.max(0, parent.width - Theme.px(26)); height: Theme.px(1)
        color: root.ceramic ? "#ffffff" : "#bbd1e7"
        opacity: root.hovered ? 0.9 : 0
        Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 120 } }
    }
    Rectangle {
        anchors.right: parent.right
        anchors.rightMargin: Theme.px(6)
        anchors.verticalCenter: parent.verticalCenter
        width: Theme.px(2)
        height: Math.min(Theme.px(12), root.height / 3)
        color: root.selected ? "#94f7bf" : "#d9b04b"
        opacity: root.selected || root.hovered ? 1 : 0
    }
    Rectangle {
        visible: root.focused
        anchors.fill: parent
        anchors.margins: 1
        radius: 3
        color: "transparent"
        border.width: 2
        border.color: Theme.focusColor
    }
}
