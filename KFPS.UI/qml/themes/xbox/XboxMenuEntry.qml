import QtQuick 6.7
import QtQuick.Controls 6.7
import Kfps.Theme 1.0
import "../../components"
import "XboxMotion.js" as Motion

Button {
    id: root
    property bool active: false
    property real reveal: 1
    property int order: 0
    property int selectedIndex: 0
    property real seconds: 0
    property real depthOffset: Math.min(22, Math.abs(order - selectedIndex) * 3)
    readonly property bool motionAllowed: !Theme.reducedMotion && !screenshotMode
    property real emphasis: active || hovered || visualFocus ? 1 : 0
    implicitHeight: 50
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: text
    leftPadding: 78
    rightPadding: 22
    transform: Translate { x: (1 - root.reveal) * (90 + root.order * 9) + (1 - root.emphasis) * 10 + root.depthOffset }
    opacity: Math.max(0, Math.min(1, root.reveal * 1.5 - root.order * 0.035))
    Behavior on emphasis { enabled: root.motionAllowed; NumberAnimation { duration: Motion.selectionDuration; easing.type: Easing.OutCubic } }
    Behavior on depthOffset { enabled: root.motionAllowed; NumberAnimation { duration: Motion.selectionDuration; easing.type: Easing.OutCubic } }
    background: Canvas {
        id: tab
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections {
            target: root
            function onActiveChanged() { tab.requestPaint() }
            function onHoveredChanged() { tab.requestPaint() }
            function onVisualFocusChanged() { tab.requestPaint() }
            function onSecondsChanged() { if (root.active) tab.requestPaint() }
        }
        Connections { target: Theme; function onPrimaryChanged() { tab.requestPaint() } }
        onPaint: {
            var c = getContext("2d")
            c.reset()
            c.clearRect(0, 0, width, height)
            c.beginPath()
            c.moveTo(40, height * 0.48)
            c.lineTo(52, height * 0.48)
            c.lineTo(65, 8)
            c.lineTo(width - 23, 5)
            c.quadraticCurveTo(width - 5, 5, width - 4, 19)
            c.lineTo(width - 15, height - 7)
            c.lineTo(65, height - 7)
            c.lineTo(52, height * 0.6)
            c.lineTo(40, height * 0.6)
            c.closePath()
            var fill = c.createLinearGradient(0, 0, 0, height)
            fill.addColorStop(0, root.active ? Theme.navActiveTop : Theme.withAlpha(Theme.primary, 0.22))
            fill.addColorStop(0.48, root.active ? Theme.navActiveMiddle : Theme.withAlpha(Theme.surfaceStrong, 0.90))
            fill.addColorStop(1, root.active ? Theme.navActiveBottom : Theme.withAlpha(Theme.primaryDeep, 0.65))
            c.fillStyle = fill
            c.fill()
            c.lineWidth = root.visualFocus ? 2 : 1
            c.strokeStyle = root.active || root.visualFocus ? Theme.warning : (root.hovered ? Theme.primaryBright : Theme.primary)
            c.stroke()
            // Glass socket: dark center, luminous lip and a moving highlight.
            var radius = height * 0.39
            var pod = c.createRadialGradient(21, height * 0.42, 1, 24, height / 2, radius)
            pod.addColorStop(0, root.active ? Theme.primaryBright : Theme.surfaceStrong)
            pod.addColorStop(0.42, Theme.primaryDeep)
            pod.addColorStop(0.72, Theme.backgroundA)
            pod.addColorStop(0.87, root.active ? Theme.warning : Theme.primary)
            pod.addColorStop(1, Theme.primaryDeep)
            c.beginPath(); c.arc(24, height / 2, radius, 0, Math.PI * 2)
            c.fillStyle = pod
            c.fill()
            c.strokeStyle = Theme.withAlpha(Theme.primaryBright, 0.7)
            c.stroke()
            c.beginPath()
            c.arc(24, height / 2, radius * 0.88, -2.6 + Math.sin(root.seconds * 0.9) * 0.2, -1.1)
            c.lineWidth = 2; c.strokeStyle = Theme.primaryBright; c.stroke()
        }
    }
    contentItem: Text {
        text: root.text.toUpperCase()
        color: root.active ? Theme.primaryText : Theme.primaryBright
        font.family: Theme.displayFamily
        font.pixelSize: 22
        font.weight: Font.DemiBold
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    KfpsToolTip { visible: root.hovered; text: "Open " + root.text + "." }
}
