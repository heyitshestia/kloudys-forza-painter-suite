import QtQuick
import QtQuick.Window
import Kfps.Theme 1.0

Rectangle {
    id: root
    property bool active: false
    property real phase: 0
    readonly property bool pulsing: active && visible && enabled
                                    && Theme.ambientMotion && !Theme.reducedMotion
                                    && !(typeof screenshotMode !== "undefined" && screenshotMode)
                                    && root.Window.window !== null && root.Window.window.visible
                                    && root.Window.window.visibility !== Window.Minimized

    anchors.fill: parent
    anchors.margins: Theme.px(2)
    visible: active
    z: 1
    radius: Theme.corner(Theme.framedRadius(Theme.px(Metrics.controlRadius)))
    color: "transparent"
    border.color: Theme.primaryBright
    border.width: Math.max(1, Theme.px(2))
    opacity: pulsing ? 0.25 + phase * 0.65 : 0.65
    antialiasing: true

    // Only the outline breathes; the label and hit area stay unchanged.
    SequentialAnimation {
        running: root.pulsing
        loops: Animation.Infinite
        NumberAnimation { target: root; property: "phase"; from: 0; to: 1; duration: 1100; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "phase"; from: 1; to: 0; duration: 1100; easing.type: Easing.InOutSine }
    }
}
