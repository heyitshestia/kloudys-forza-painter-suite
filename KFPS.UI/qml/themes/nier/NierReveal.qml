import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "NierWindowReveal"
    enabled: false
    property real progress: 1
    property bool started: false
    readonly property bool motionAllowed: !Theme.reducedMotion && !screenshotMode
    function begin() {
        if (started || !Window.window || !Window.window.visible) return
        started = true
        if (motionAllowed) { progress = 0; entrance.start() }
    }
    function finish() { entrance.stop(); progress = 1 }
    Component.onCompleted: Qt.callLater(begin)
    onMotionAllowedChanged: { if (!motionAllowed) finish() }
    Connections {
        target: root.Window.window
        function onVisibleChanged() { if (root.Window.window.visible) root.begin(); else root.finish() }
        function onActiveChanged() { if (!root.Window.window.active && root.started) root.finish() }
    }
    NumberAnimation { id: entrance; target: root; property: "progress"; from: 0; to: 1; duration: 620; easing.type: Easing.OutCubic }
    Canvas {
        id: shutter
        anchors.fill: parent
        anchors.topMargin: Theme.px(Theme.chromeMetric("titleHeight", 42))
        visible: root.progress < 1
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections { target: root; function onProgressChanged() { shutter.requestPaint() } }
        onPaint: {
            var c = getContext("2d")
            c.clearRect(0, 0, width, height)
            var w = width / 3, h = height / 2
            for (var row = 0; row < 2; row++) for (var col = 0; col < 3; col++) for (var half = 0; half < 2; half++) {
                var p = Math.max(0, Math.min(1, root.progress * 1.5 - (row + col + half) * 0.1))
                if (p >= 1) continue
                c.save(); c.translate(col * w + p * w * (half ? 1 : -1), row * h + p * h * (half ? -1 : 1))
                c.globalAlpha = 1 - p; c.fillStyle = Theme.backgroundA; c.strokeStyle = Theme.text; c.lineWidth = 1
                c.beginPath()
                if (half) { c.moveTo(0, 0); c.lineTo(w, 0); c.lineTo(w, h) }
                else { c.moveTo(0, 0); c.lineTo(w, h); c.lineTo(0, h) }
                c.closePath(); c.fill(); c.stroke(); c.restore()
            }
        }
    }
}
