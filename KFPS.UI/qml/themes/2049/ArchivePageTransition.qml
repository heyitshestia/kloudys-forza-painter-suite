import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "ArchivePageTransition"
    enabled: false
    clip: true
    property real progress: 1
    readonly property bool replayOnContentReady: true
    readonly property real contentOffsetX: (1 - progress) * Theme.px(48)
    readonly property real contentOffsetY: (1 - progress) * Theme.px(6)
    readonly property bool motionAllowed: visible && Window.window && Window.window.active && Window.window.visibility !== Window.Minimized && !Theme.reducedMotion && !screenshotMode
    function play() {
        if (motionAllowed) indexShift.restart()
        else { indexShift.stop(); progress = 1 }
    }
    onMotionAllowedChanged: { if (!motionAllowed) { indexShift.stop(); progress = 1 } }
    SequentialAnimation {
        id: indexShift
        NumberAnimation { target: root; property: "progress"; from: 0; to: 0.94; duration: 320; easing.type: Easing.OutCubic }
        PauseAnimation { duration: 60 }
        NumberAnimation { target: root; property: "progress"; to: 1; duration: 130; easing.type: Easing.OutCubic }
    }
    ArchiveFrame {
        x: Theme.px(10) - (1 - root.progress) * Theme.px(54)
        y: Theme.px(8)
        width: parent.width - Theme.px(34); height: parent.height - Theme.px(20)
        fill: "transparent"; stroke: Theme.signalSecondary; lineWidth: 2
        turn: Theme.px(34)
        opacity: (1 - root.progress) * 0.55
    }
    // Three mechanical index rails settle at the edges; content remains unfiltered.
    Repeater {
        model: 3
        Item {
            required property int index
            x: index === 0 ? Theme.px(2) : index === 1 ? root.width - Theme.px(7) : root.width - Theme.px(3)
            y: (1 - root.progress) * -Theme.px(70 + index * 35)
            width: 2; height: root.height
            opacity: (1 - root.progress) * 0.65
            Repeater {
                model: 8
                Rectangle {
                    required property int index
                    y: index * parent.height / 8; width: parent.width; height: Theme.px(18)
                    color: Theme.signalSecondary
                }
            }
        }
    }
    Rectangle {
        x: 0; y: 0; width: root.width * root.progress; height: 1
        color: Theme.primary; opacity: 1 - root.progress
    }
}
