import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "Ps2Clock"
    property bool animated: true
    property bool compact: false
    property alias clock: clock
    Ps2MotionClock { id: clock; requested: root.animated }
    Canvas {
        id: sprites
        objectName: "Ps2ClockSprites"
        anchors.centerIn: parent
        width: Math.min(384, root.width)
        height: Math.min(320, root.height)
        scale: Math.min(root.width / Math.max(1, width), root.height / Math.max(1, height))
        antialiasing: true
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections { target: clock; function onTick() { sprites.requestPaint() } }
        Connections { target: Theme; function onPaletteChanged() { sprites.requestPaint() } }
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var t = clock.seconds, unit = Math.min(width, height)
            var points = []
            // Screen-space sprites on a slowly turning elliptical orbit. No new 3D backend.
            for (var i = 0; i < 7; ++i) {
                var a = t * (0.63 + i * 0.004) + i * Math.PI * 2 / 7
                var tilt = Math.sin(t * 0.09) * 0.45 + 0.45
                var rx = Math.cos(a), ry = Math.sin(a) * (0.62 + Math.sin(t * 0.12) * 0.23)
                points.push({x: (rx * Math.cos(tilt) - ry * Math.sin(tilt)) * unit * 0.32 + width * 0.5,
                             y: (rx * Math.sin(tilt) + ry * Math.cos(tilt)) * unit * 0.32 + height * 0.5,
                             depth: Math.sin(a + t * 0.08), angle: a})
            }
            points.sort(function(a, b) { return a.depth - b.depth })
            for (var p = 0; p < points.length; ++p) {
                var point = points[p], radius = unit * (root.compact ? 0.062 : 0.051) * (0.85 + point.depth * 0.2)
                var glow = ctx.createRadialGradient(point.x, point.y, 0, point.x, point.y, radius * 2.7)
                glow.addColorStop(0, Theme.withAlpha(Theme.primaryBright, 0.96))
                glow.addColorStop(0.18, Theme.withAlpha(Theme.primaryBright, 0.9))
                glow.addColorStop(0.39, Theme.withAlpha(Theme.primary, 0.88))
                glow.addColorStop(0.65, Theme.withAlpha(Theme.primary, 0.25))
                glow.addColorStop(1, Theme.withAlpha(Theme.primary, 0))
                ctx.fillStyle = glow
                ctx.beginPath(); ctx.arc(point.x, point.y, radius * 2.7, 0, Math.PI * 2); ctx.fill()
                ctx.fillStyle = Theme.withAlpha(Theme.text, 0.87)
                ctx.beginPath(); ctx.arc(point.x - radius * 0.16, point.y - radius * 0.2, radius * 0.21, 0, Math.PI * 2); ctx.fill()
            }
        }
    }
}
