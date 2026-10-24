import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: 2; color: Theme.border
    }
    Row {
        x: Theme.px(16)
        anchors.verticalCenter: parent.verticalCenter
        spacing: 14
        XboxWordmark {
            width: Theme.px(62)
            height: Theme.px(17)
            anchors.verticalCenter: parent.verticalCenter
            luminous: true
        }
        Text {
            text: "|"
            color: Theme.border
            font.pixelSize: 16
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: root.Window.window ? root.Window.window.title : appController.windowTitle
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: 12
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
