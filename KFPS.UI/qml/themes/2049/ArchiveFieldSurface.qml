import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    property var control: parent
    readonly property bool engaged: control && control.activeFocus
    readonly property bool hovered: control && control.hovered
    enabled: false
    Rectangle {
        anchors.fill: parent
        color: root.engaged ? "#163a9f85" : root.hovered ? "#0d3a9f85" : "transparent"
    }
    Rectangle {
        x: 0; y: parent.height - 1; width: parent.width; height: 1
        color: root.engaged ? Theme.primary : Theme.signalSecondary
        opacity: root.engaged ? 1 : root.hovered ? 0.75 : 0.45
    }
    Rectangle {
        x: 0; y: parent.height - Theme.px(7); width: 1; height: Theme.px(7)
        color: root.engaged ? Theme.primary : Theme.signalSecondary
        opacity: root.engaged ? 1 : 0.45
    }
    Rectangle {
        x: parent.width - 1; y: parent.height - Theme.px(7); width: 1; height: Theme.px(7)
        color: root.engaged ? Theme.primary : Theme.signalSecondary
        opacity: root.engaged ? 1 : 0.45
    }
}
