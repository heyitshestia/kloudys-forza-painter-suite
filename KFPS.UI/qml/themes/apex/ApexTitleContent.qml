import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0
Item {
    id: root
    clip: true
    Rectangle { width: Theme.px(5); height: parent.height; color: Theme.primary }
    Text {
        id: brand
        x: Theme.px(18); anchors.verticalCenter: parent.verticalCenter
        text: "KFPS"; color: Theme.primary
        font.family: Theme.displayFamily; font.pixelSize: Theme.px(19); font.italic: true; font.bold: true
    }
    Text {
        anchors.left: brand.right; anchors.leftMargin: Theme.px(18)
        anchors.right: parent.right; anchors.rightMargin: Theme.px(12)
        anchors.verticalCenter: parent.verticalCenter
        text: root.Window.window ? root.Window.window.title.replace("KFPS - ", "").toUpperCase() : ""
        font.family: Theme.fontFamily; font.pixelSize: Theme.px(11)
        color: Theme.muted; elide: Text.ElideRight
    }
}
