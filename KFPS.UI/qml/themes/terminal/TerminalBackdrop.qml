import QtQuick 6.7
import Kfps.Theme 1.0

Rectangle {
    anchors.fill: parent
    color: Theme.backgroundA

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Math.max(1, Theme.px(1))
        color: Theme.divider
        opacity: 0.55
    }
}
