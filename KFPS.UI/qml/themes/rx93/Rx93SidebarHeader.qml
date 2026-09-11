import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    property var sidebar: null
    readonly property bool compact: sidebar ? sidebar.compact : false
    readonly property bool motionAllowed: Theme.ambientMotion && !Theme.reducedMotion && !screenshotMode
        && visible && Window.window && Window.window.active && Window.window.visibility !== Window.Minimized
    property real intensity: 0.4
    Rx93ArmorPlate { anchors.fill: parent; part: "navy-key" }
    Image {
        x: Theme.px(12)
        anchors.verticalCenter: parent.verticalCenter
        width: Theme.px(root.compact ? 32 : 42); height: width
        source: assetRoot + "/themes/rx93-psycho-frame/rx93-mark.svg"
        sourceSize: Qt.size(84, 84)
    }
    Column {
        visible: !root.compact
        x: Theme.px(62)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.px(2)
        Text { text: "RX-93"; color: "#f1f3f7"; font.family: Theme.displayFamily; font.pixelSize: Theme.px(23); font.weight: Font.DemiBold }
        Text { text: "PSYCHO-FRAME"; color: "#e7c460"; font.family: Theme.displayFamily; font.pixelSize: Theme.px(9) }
    }
    Rectangle {
        anchors.right: parent.right
        anchors.rightMargin: Theme.px(7)
        anchors.verticalCenter: parent.verticalCenter
        width: Theme.px(2); height: Theme.px(16)
        color: "#84eeb0"
        opacity: root.intensity
    }
    Timer {
        running: root.motionAllowed
        interval: 50
        repeat: true
        property real phase: 0
        onTriggered: {
            phase = (phase + interval) % 6400
            root.intensity = 0.4 + 0.25 * (1 - Math.cos(phase / 6400 * Math.PI * 2))
        }
    }
}
