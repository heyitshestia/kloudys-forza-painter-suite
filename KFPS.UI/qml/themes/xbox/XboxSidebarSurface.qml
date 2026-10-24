import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    property var sidebar: null
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Theme.backgroundA }
            GradientStop { position: 0.46; color: Theme.backgroundC }
            GradientStop { position: 0.88; color: Theme.backgroundB }
            GradientStop { position: 1; color: Theme.backgroundA }
        }
    }
    Repeater {
        model: Math.max(0, Math.ceil(root.height / 12))
        Rectangle {
            required property int index
            x: 8; y: index * 12
            width: root.width - 16; height: 1
            color: Theme.border; opacity: 0.12
        }
    }
    Rectangle {
        anchors.right: parent.right
        height: parent.height; width: 4
        color: Theme.backgroundA
        Rectangle { width: 1; height: parent.height; color: Theme.border }
    }
}
