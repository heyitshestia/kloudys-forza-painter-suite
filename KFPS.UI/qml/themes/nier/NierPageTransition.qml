import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    enabled: false
    clip: true
    property real progress: 1
    readonly property bool motionAllowed: !Theme.reducedMotion && !screenshotMode
    function play() { if (motionAllowed) sweep.restart() }
    onMotionAllowedChanged: { if (!motionAllowed) { sweep.stop(); progress = 1 } }
    NumberAnimation { id: sweep; target: root; property: "progress"; from: 0; to: 1; duration: 180; easing.type: Easing.OutCubic }
    Rectangle { x: root.width * root.progress; y: -root.height; width: 1; height: root.height * 3; rotation: 25; color: Theme.text; opacity: 1 - root.progress }
}
