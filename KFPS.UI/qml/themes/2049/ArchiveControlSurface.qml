import QtQuick 6.7
import QtQuick.Window 6.7
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
    readonly property bool pale: primary || (controlKind === "nav" && selected)
    readonly property bool motionAllowed: visible && Window.window && Window.window.active && Window.window.visibility !== Window.Minimized && !Theme.reducedMotion && !screenshotMode
    property real registration: 1
    opacity: control && !control.enabled ? 0.45 : 1
    onSelectedChanged: {
        if (selected && motionAllowed) engage.restart()
        else { engage.stop(); registration = 1 }
    }
    onMotionAllowedChanged: { if (!motionAllowed) { engage.stop(); registration = 1 } }
    NumberAnimation { id: engage; target: root; property: "registration"; from: 0; to: 1; duration: 140; easing.type: Easing.OutCubic }

    Rectangle {
        anchors.fill: parent
        radius: 2
        color: root.pale ? (root.pressed ? Theme.primaryDeep : root.hovered ? Theme.primaryHot : Theme.primary)
                        : root.pressed ? Theme.ghostPressedSurface
                        : root.selected || root.hovered ? Theme.ghostHoverSurface : Theme.ghostSurface
        border.color: root.focused ? Theme.focusColor : root.pale ? Theme.primary : root.hovered || root.selected ? Theme.borderStrong : Theme.border
        border.width: 1
        Image { anchors.fill: parent; anchors.margins: 2; source: assetRoot + "/themes/2049/phosphor-raster.png"; fillMode: Image.Tile; opacity: root.pale ? 0.38 : 0.12 }
    }
    Rectangle {
        x: Theme.px(4); y: Theme.px(4)
        width: Theme.px(2)
        height: Math.max(0, (parent.height - Theme.px(8)) * root.registration)
        color: root.pale ? Theme.primaryText : Theme.signalSecondary
        opacity: root.selected || root.primary || root.hovered ? 0.9 : 0.25
    }
    Rectangle {
        visible: root.focused
        anchors.fill: parent; anchors.margins: Theme.px(3)
        color: "transparent"; border.color: root.pale ? Theme.primaryText : Theme.focusColor
        border.width: 1
    }
}
