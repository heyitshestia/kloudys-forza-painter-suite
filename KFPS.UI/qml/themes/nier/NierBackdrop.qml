import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    enabled: false
    Rectangle { anchors.fill: parent; color: Theme.backgroundA }
    Canvas {
        id: pattern
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections { target: Theme; function onPaletteChanged() { pattern.requestPaint() } }
        onPaint: {
            var c = getContext("2d")
            c.clearRect(0, 0, width, height)
            c.strokeStyle = Theme.border; c.lineWidth = 1; c.globalAlpha = 0.06
            c.beginPath()
            for (var x = 0.5; x < width; x += 8) { c.moveTo(x, 0); c.lineTo(x, height) }
            for (var y = 0.5; y < height; y += 8) { c.moveTo(0, y); c.lineTo(width, y) }
            c.stroke()
            c.globalAlpha = 0.5
            c.beginPath()
            for (var i = 0; i < 3; i++) { c.moveTo(0, height - 16 - i * 5); c.lineTo(width, height - 16 - i * 5) }
            c.stroke()
            c.fillStyle = Theme.text
            for (var d = 24; d < width; d += 96) {
                c.beginPath(); c.moveTo(d, height - 29); c.lineTo(d + 4, height - 24); c.lineTo(d, height - 19); c.lineTo(d - 4, height - 24); c.closePath(); c.fill()
            }
            c.globalAlpha = 1
        }
    }
}
