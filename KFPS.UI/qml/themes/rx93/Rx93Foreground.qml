import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "rx93Foreground"
    enabled: false
    readonly property bool motionAllowed: Theme.ambientMotion && !Theme.reducedMotion && !screenshotMode
        && visible && Window.window && Window.window.active && Window.window.visibility !== Window.Minimized
    property real carriage: 0.25
    readonly property bool compact: Theme.logical(width) < 1240 || Theme.logical(height) < 760
    readonly property real unit: Theme.chromeMetric(compact ? "compactFrameScale" : "frameScale", 0.6)
    Rectangle {
        x: 154 * root.unit
        y: 155 * root.unit
        width: Math.max(3, 9 * root.unit)
        height: Math.max(12, 48 * root.unit)
        color: "#050a0c"
        border.width: 1
        border.color: "#536570"
        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            color: "#9ce8ba"
            opacity: 0.48 + root.carriage / 2
        }
    }
    Rectangle {
        x: root.width - 218 * root.unit + root.carriage * 28 * root.unit
        y: root.height - 74 * root.unit
        width: Math.max(3, 13 * root.unit); height: Math.max(8, 27 * root.unit)
        border.width: 1; border.color: "#111923"
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "#1b2935" }
            GradientStop { position: 0.35; color: "#b8c2ca" }
            GradientStop { position: 0.5; color: "#536371" }
            GradientStop { position: 1; color: "#1e2a33" }
        }
    }
    Timer {
        running: root.motionAllowed
        interval: 50
        repeat: true
        property real elapsed: 0
        onTriggered: {
            elapsed = (elapsed + interval) % 30500
            var progress = elapsed < 8000 ? 0 : elapsed < 14000 ? (elapsed - 8000) / 6000 : elapsed < 24000 ? 1 : 1 - (elapsed - 24000) / 6500
            root.carriage = 0.25 + 0.47 * (1 - Math.cos(progress * Math.PI)) / 2
        }
    }
}
