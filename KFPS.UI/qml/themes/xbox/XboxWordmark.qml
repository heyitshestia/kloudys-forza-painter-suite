import QtQuick 6.7
import Kfps.Theme 1.0

Canvas {
    id: root
    objectName: "XboxWordmark"
    property bool luminous: false
    readonly property color faceTop: luminous ? Theme.primaryBright : Theme.primaryDeep
    readonly property color faceBottom: luminous ? Theme.primary : Theme.primaryText
    readonly property color edgeColor: Theme.primaryBright
    readonly property color shadowColor: Theme.backgroundA
    implicitWidth: 240
    implicitHeight: 64
    Accessible.role: Accessible.StaticText
    Accessible.name: "KFPS"
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onFaceTopChanged: requestPaint()
    onFaceBottomChanged: requestPaint()
    onEdgeColorChanged: requestPaint()
    onShadowColorChanged: requestPaint()

    onPaint: {
        var c = getContext("2d")
        c.reset()
        c.clearRect(0, 0, width, height)
        c.scale(width / 240, height / 64)
        // Original chamfered lettering, independent of installed or proprietary fonts.
        var letters = [
            [[3,4],[14,4],[14,25],[33,4],[47,4],[25,30],[49,60],[34,60],[14,36],[14,60],[3,60]],
            [[58,4],[103,4],[103,15],[70,15],[70,27],[97,27],[97,38],[70,38],[70,60],[58,60]],
            [[114,4],[150,4],[161,15],[161,30],[150,41],[126,41],[126,60],[114,60]],
            [[184,4],[235,4],[235,15],[188,15],[188,27],[224,27],[235,38],[235,49],[224,60],[173,60],[173,49],[221,49],[221,38],[185,38],[173,27],[173,15]]
        ]
        var fill = c.createLinearGradient(0, 4, 0, 60)
        fill.addColorStop(0, root.faceTop)
        fill.addColorStop(0.48, root.faceBottom)
        fill.addColorStop(1, root.faceTop)
        for (var i = 0; i < letters.length; i++) {
            var polygon = letters[i]
            c.beginPath()
            c.moveTo(polygon[0][0], polygon[0][1])
            for (var j = 1; j < polygon.length; j++) c.lineTo(polygon[j][0], polygon[j][1])
            c.closePath()
            if (i === 2) {
                // Reverse winding preserves the open counter in P.
                c.moveTo(126,15); c.lineTo(126,30); c.lineTo(146,30)
                c.lineTo(149,27); c.lineTo(149,18); c.lineTo(146,15); c.closePath()
            }
            c.lineJoin = "bevel"
            c.strokeStyle = Theme.withAlpha(root.shadowColor, 0.6)
            c.lineWidth = 3
            c.stroke()
            c.fillStyle = fill
            c.fill()
            c.strokeStyle = Theme.withAlpha(root.edgeColor, root.luminous ? 0.5 : 0.85)
            c.lineWidth = 0.8
            c.stroke()
        }
    }
}
