import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Rectangle {
    id: root
    enabled: false
    color: Theme.backgroundA
    opacity: 0
    readonly property bool motionAllowed: !Theme.reducedMotion && !screenshotMode && Window.window && Window.window.active
    function play() { if (motionAllowed) fade.restart() }
    onMotionAllowedChanged: { if (!motionAllowed) { fade.stop(); opacity = 0 } }
    NumberAnimation { id: fade; target: root; property: "opacity"; from: 0.28; to: 0; duration: 220; easing.type: Easing.OutCubic }
}
