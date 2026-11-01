import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    clip: true
    Text {
        id: brand
        x: Theme.px(14); anchors.verticalCenter: parent.verticalCenter
        text: "KFPS / 2049"; color: Theme.primary
        font.family: Theme.monoFamily; font.pixelSize: Theme.px(12); font.letterSpacing: 0
    }
    Rectangle { x: brand.x + brand.width + Theme.px(14); anchors.verticalCenter: parent.verticalCenter; width: 1; height: Theme.px(14); color: Theme.border }
    Text {
        anchors.left: brand.right; anchors.leftMargin: Theme.px(30)
        anchors.right: parent.right; anchors.rightMargin: Theme.px(12)
        anchors.verticalCenter: parent.verticalCenter
        text: root.Window.window ? root.Window.window.title.replace(/^KFPS\s*[-\u2013\u2014]\s*/, "").toUpperCase() : ""
        color: Theme.muted
        font.family: Theme.monoFamily; font.pixelSize: Theme.px(11); font.letterSpacing: 0
        elide: Text.ElideRight
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.borderSoft; opacity: 0.55 }
}
