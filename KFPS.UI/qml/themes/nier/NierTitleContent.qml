import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    clip: true
    Row {
        x: Theme.px(16); anchors.verticalCenter: parent.verticalCenter; spacing: Theme.px(16)
        Rectangle { width: 8; height: 8; rotation: 45; color: Theme.text; anchors.verticalCenter: parent.verticalCenter }
        Text { text: "KFPS"; color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.px(18); anchors.verticalCenter: parent.verticalCenter }
        Text { text: root.Window.window ? root.Window.window.title.replace("KFPS - ", "") : ""; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: Theme.px(12); anchors.verticalCenter: parent.verticalCenter }
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.border }
}
