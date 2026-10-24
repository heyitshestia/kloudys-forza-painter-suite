import QtQuick 6.7
import Kfps.Theme 1.0
import "XboxMotion.js" as Motion

Item {
    id: root
    objectName: "XboxBackdrop"
    property bool dashboard: false
    property bool animationEnabled: true
    readonly property alias motionClock: clock
    Rectangle { anchors.fill: parent; color: Theme.backgroundA }
    XboxMotionClock {
        id: clock
        requested: root.animationEnabled && root.width > 0 && root.height > 0
                   && (root.dashboard || !dashboardVisible)
        onTick: grid.requestPaint()
    }
    Canvas {
        id: grid
        objectName: "XboxCurvedGrid"
        width: Math.max(1, Math.min(960, root.width))
        height: Math.max(1, Math.min(540, root.height))
        transform: Scale { xScale: root.width / grid.width; yScale: root.height / grid.height }
        opacity: root.dashboard ? 0.85 : 0.24
        renderTarget: Canvas.Image
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections {
            target: Theme
            function onPrimaryChanged() { grid.requestPaint() }
        }
        onPaint: {
            var c = getContext("2d")
            c.reset()
            c.clearRect(0, 0, width, height)
            var depth = c.createLinearGradient(0, 0, width, height)
            depth.addColorStop(0, Theme.withAlpha(Theme.primaryDeep, root.dashboard ? 0.9 : 0.3))
            depth.addColorStop(0.5, Theme.backgroundA)
            depth.addColorStop(1, Theme.withAlpha(Theme.primaryDeep, root.dashboard ? 0.7 : 0.2))
            c.fillStyle = depth; c.fillRect(0, 0, width, height)
            Motion.grid(c, width, height, clock.seconds, Theme.primary)
        }
    }
    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: 8
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.border }
            GradientStop { position: 0.35; color: Theme.surfaceRaised }
            GradientStop { position: 1; color: Theme.backgroundA }
        }
    }
}
