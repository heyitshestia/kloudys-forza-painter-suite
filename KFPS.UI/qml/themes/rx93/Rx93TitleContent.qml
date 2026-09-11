import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    enabled: false
    readonly property real windowWidth: Window.window ? Window.window.width : width
    readonly property bool compact: windowWidth < 1240 || (Window.window && Window.window.height < 760)
    readonly property real unit: Theme.chromeMetric(compact ? "compactFrameScale" : "frameScale", 0.6)
    // Follow the plaque segment in the chassis nine-slice, not the whole title bar.
    readonly property real plaqueWidth: (windowWidth - 216 * unit) * 212 / 1456
    Item {
        width: root.plaqueWidth
        height: 80 * root.unit
        Image {
            width: Math.min(parent.width - 24, root.compact ? 86 : 144)
            height: root.compact ? 17 : 34
            anchors.horizontalCenter: parent.horizontalCenter
            y: root.compact ? 0 : 1
            source: assetRoot + "/themes/rx93-psycho-frame/kfps-armored-wordmark.svg"
            sourceSize: Qt.size(540, 140)
            fillMode: Image.PreserveAspectFit
        }
        Text {
            visible: !root.compact
            width: parent.width
            y: 35
            text: "RX-93 / LONDO BELL"
            horizontalAlignment: Text.AlignHCenter
            color: "#a7b7c8"
            font.family: Theme.displayFamily
            font.pixelSize: 8
        }
    }
}
