import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "rx93Backdrop"
    readonly property bool compact: Theme.logical(width) < 1240 || Theme.logical(height) < 760
    readonly property real unit: Theme.px(100) / 100 * Theme.chromeMetric(compact ? "compactFrameScale" : "frameScale", 0.6)
    Rectangle { anchors.fill: parent; color: "#10151d" }
    BorderImage {
        width: root.width / root.unit
        height: root.height / root.unit
        scale: root.unit
        transformOrigin: Item.TopLeft
        source: assetRoot + "/themes/rx93-psycho-frame/parts/chassis.png"
        border { left: 180; right: 36; top: 110; bottom: 160 }
        smooth: true
    }
}
