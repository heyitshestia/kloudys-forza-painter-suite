import QtQuick 6.7
import Kfps.Theme 1.0
import "XboxMotion.js" as Motion

Item {
    id: root
    objectName: "XboxReactor"
    property bool animated: true
    property bool compact: false
    property real selectionEnergy: 0
    readonly property alias motionClock: clock
    Canvas {
        id: rear
        objectName: "XboxRearOrbits"
        width: Math.max(1, Math.min(384, root.width))
        height: width
        transform: Scale { xScale: root.width / rear.width; yScale: root.height / rear.height }
        onWidthChanged: requestPaint()
        onPaint: {
            var c = getContext("2d"); c.reset(); c.clearRect(0, 0, width, height)
            Motion.orbits(c, width, clock.seconds, false, Theme.primary, Theme.primaryBright)
        }
    }
    Image {
        id: glass
        anchors.fill: parent
        source: assetRoot + "/themes/original-xbox/core.png"
        sourceSize: Qt.size(768, 768)
        fillMode: Image.PreserveAspectFit
        mipmap: true
        scale: 1 + Math.sin(clock.seconds * 0.65) * 0.018 + root.selectionEnergy * 0.025
        rotation: Math.sin(clock.seconds * 0.25) * 4
        opacity: 0.9 + Math.sin(clock.seconds * 0.65) * 0.05
    }
    XboxMotionClock {
        id: clock
        requested: root.animated && root.width >= 80
        onTick: { rear.requestPaint(); current.requestPaint() }
    }
    Canvas {
        id: current
        objectName: "XboxReactorCurrent"
        width: Math.max(1, Math.min(384, root.width))
        height: width
        transform: Scale { xScale: root.width / current.width; yScale: root.height / current.height }
        onWidthChanged: requestPaint()
        Connections { target: Theme; function onPrimaryBrightChanged() { rear.requestPaint(); current.requestPaint() } }
        onPaint: {
            var c = getContext("2d")
            c.reset()
            c.clearRect(0, 0, width, height)
            Motion.currents(c, width, clock.seconds, Theme.primaryBright)
            Motion.orbits(c, width, clock.seconds, true, Theme.primary, Theme.primaryBright)
        }
    }
    XboxWordmark {
        anchors.centerIn: parent
        width: parent.width * (root.compact ? 0.62 : 0.48)
        height: width * 64 / 240
    }
}
