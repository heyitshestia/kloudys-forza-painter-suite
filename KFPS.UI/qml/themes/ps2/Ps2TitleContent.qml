import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    clip: true
    Row {
        x: Theme.px(16)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.px(18)
        Text {
            text: "KFPS"
            color: Theme.primary
            font.family: Theme.displayFamily
            font.pixelSize: Theme.px(19)
            font.weight: Font.Medium
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: root.Window.window ? root.Window.window.title : appController.windowTitle
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(12)
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
