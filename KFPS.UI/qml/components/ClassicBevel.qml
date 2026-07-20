import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property bool sunken: false
    property bool pressed: false
    property int depth: 2
    readonly property bool inverted: sunken || pressed
    readonly property real stroke: Math.max(1, Theme.px(1))

    visible: Theme.classicMode
    enabled: false

    Rectangle {
        x: 0
        y: 0
        width: parent.width
        height: root.stroke
        color: root.inverted ? Theme.borderStrong : Theme.innerHighlight
    }
    Rectangle {
        x: 0
        y: 0
        width: root.stroke
        height: parent.height
        color: root.inverted ? Theme.borderStrong : Theme.innerHighlight
    }
    Rectangle {
        x: 0
        y: parent.height - root.stroke
        width: parent.width
        height: root.stroke
        color: root.inverted ? Theme.innerHighlight : Theme.borderStrong
    }
    Rectangle {
        x: parent.width - root.stroke
        y: 0
        width: root.stroke
        height: parent.height
        color: root.inverted ? Theme.innerHighlight : Theme.borderStrong
    }

    Rectangle {
        visible: root.depth > 1 && parent.width > root.stroke * 3
        x: root.stroke
        y: root.stroke
        width: parent.width - root.stroke * 2
        height: root.stroke
        color: root.inverted ? Theme.border : Theme.surfaceTop
    }
    Rectangle {
        visible: root.depth > 1 && parent.height > root.stroke * 3
        x: root.stroke
        y: root.stroke
        width: root.stroke
        height: parent.height - root.stroke * 2
        color: root.inverted ? Theme.border : Theme.surfaceTop
    }
    Rectangle {
        visible: root.depth > 1 && parent.width > root.stroke * 3
        x: root.stroke
        y: parent.height - root.stroke * 2
        width: parent.width - root.stroke * 2
        height: root.stroke
        color: root.inverted ? Theme.surfaceTop : Theme.border
    }
    Rectangle {
        visible: root.depth > 1 && parent.height > root.stroke * 3
        x: parent.width - root.stroke * 2
        y: root.stroke
        width: root.stroke
        height: parent.height - root.stroke * 2
        color: root.inverted ? Theme.surfaceTop : Theme.border
    }
}
