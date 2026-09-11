import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    property var sidebar: null
    Rectangle { anchors.fill: parent; color: "#10151d" }
    Rectangle {
        x: Theme.px(4); y: Theme.px(3)
        width: Theme.px(2); height: parent.height - Theme.px(6)
        color: "#4b5866"
    }
    Rectangle {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Theme.px(3)
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "#83909e" }
            GradientStop { position: 0.35; color: "#25313d" }
            GradientStop { position: 1; color: "#070b10" }
        }
    }
}
