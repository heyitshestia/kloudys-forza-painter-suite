import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root
    property bool playing: animation.running
    property real progress: 1
    visible: playing
    clip: true
    function play() {
        if (screenshotMode || Theme.reducedMotion || !parent || !parent.visible) return
        animation.restart()
    }
    Connections {
        target: Theme
        function onReducedMotionChanged() { if (Theme.reducedMotion) { animation.stop(); root.progress = 1 } }
    }
    Rectangle {
        id: bar
        width: root.width * 0.16
        height: Theme.px(3)
        color: Theme.primary
        transform: Translate { x: root.progress * (root.width + bar.width) - bar.width }
    }
    NumberAnimation { id: animation; target: root; property: "progress"; from: 0; to: 1; duration: Theme.pageTransitionDuration; easing.type: Easing.OutCubic }
}
