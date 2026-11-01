import QtQuick 6.7
import QtQuick.Window 6.7
import QtQuick.Shapes 1.15
import Kfps.Theme 1.0

Item {
    id: root
    enabled: false
    property var control: null
    property string controlKind: "ghost"
    readonly property bool selected: control ? (controlKind === "nav" ? control.active : control.checkedState || false) : false
    readonly property bool primary: controlKind === "primary" || (controlKind === "nav" && selected)
    readonly property bool hovered: control && control.hovered
    readonly property bool pressed: control && control.down
    readonly property bool focused: control && control.visualFocus
    readonly property bool minimal: control && control.minimal === true
    readonly property bool motionAllowed: visible && Window.window && Window.window.active && Window.window.visibility !== Window.Minimized && !Theme.reducedMotion && !screenshotMode
    property real fracture: 0
    onSelectedChanged: if (selected && motionAllowed) engage.restart()
    onHoveredChanged: if (hovered && motionAllowed) engage.restart()
    onMotionAllowedChanged: { if (!motionAllowed) { engage.stop(); fracture = 0 } }
    SequentialAnimation {
        id: engage
        PropertyAction { target: root; property: "fracture"; value: 1 }
        PauseAnimation { duration: 45 }
        PropertyAction { target: root; property: "fracture"; value: -0.4 }
        PauseAnimation { duration: 35 }
        PropertyAction { target: root; property: "fracture"; value: 0 }
    }
    Shape {
        id: frame
        anchors.fill: parent
        ShapePath {
            strokeWidth: root.focused ? 2 : 1
            strokeColor: root.focused ? Theme.text : root.primary || root.hovered || root.selected ? Theme.primary : root.minimal ? "transparent" : Theme.borderSoft
            fillColor: root.primary ? root.pressed ? Theme.primaryDeep : Theme.primary : root.selected || root.hovered ? "#4a160b14" : root.minimal ? "transparent" : "#9c160a10"
            startX: 0; startY: 0
            PathLine { x: frame.width - Theme.px(9); y: 0 }
            PathLine { x: frame.width; y: Theme.px(9) }
            PathLine { x: frame.width; y: frame.height }
            PathLine { x: 0; y: frame.height }
            PathLine { x: 0; y: 0 }
        }
        ShapePath {
            strokeWidth: 0
            fillColor: root.primary ? Theme.primaryText : root.selected || root.hovered || root.focused ? Theme.primary : "#62202a"
            startX: frame.width - Theme.px(8); startY: 0
            PathLine { x: frame.width; y: Theme.px(8) }
            PathLine { x: frame.width; y: 0 }
            PathLine { x: frame.width - Theme.px(8); y: 0 }
        }
    }
    Rectangle {
        visible: root.fracture !== 0
        x: root.fracture * Theme.px(7); y: parent.height * 0.58
        width: parent.width; height: 2
        color: root.primary ? Theme.primaryText : Theme.primary
    }
    Rectangle {
        visible: root.focused
        anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
        width: 3; height: parent.height - 10; color: root.primary ? Theme.primaryText : Theme.text
    }
}
