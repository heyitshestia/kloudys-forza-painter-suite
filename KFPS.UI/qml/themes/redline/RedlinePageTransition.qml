import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "RedlinePageTransition"
    enabled: false
    clip: true
    property real progress: 1
    readonly property bool replayOnContentReady: true
    readonly property real contentOffsetX: 0
    readonly property real contentOffsetY: 0
    readonly property bool motionAllowed: visible && Window.window && Window.window.active && Window.window.visibility !== Window.Minimized && !Theme.reducedMotion && !screenshotMode
    function play() { if (motionAllowed) decode.restart(); else { decode.stop(); progress = 1 } }
    onMotionAllowedChanged: { if (!motionAllowed) { decode.stop(); progress = 1 } }
    SequentialAnimation {
        id: decode
        PropertyAction { target: root; property: "progress"; value: 0 }
        NumberAnimation { target: root; property: "progress"; to: 0.28; duration: 70 }
        PauseAnimation { duration: 35 }
        NumberAnimation { target: root; property: "progress"; to: 0.72; duration: 85 }
        PauseAnimation { duration: 30 }
        NumberAnimation { target: root; property: "progress"; to: 1; duration: 100 }
    }
    Repeater {
        model: 7
        Item {
            required property int index
            x: Theme.px(36)
            y: Theme.px(136) + index * (root.height - Theme.px(200)) / 7
            width: root.width - Theme.px(72)
            height: (root.height - Theme.px(200)) / 7 + 1
            clip: true
            visible: root.progress < 1
            Rectangle {
                x: parent.width * Math.min(1, Math.max(0, root.progress * 1.6 - (index % 3) * 0.18))
                width: parent.width; height: parent.height
                color: index % 3 === 0 ? "#27050d" : "#090609"
            }
            Rectangle {
                x: parent.width * Math.min(1, Math.max(0, root.progress * 1.6 - (index % 3) * 0.18))
                width: Theme.px(index % 2 ? 3 : 10); height: 1
                color: Theme.primary; opacity: 0.75
            }
        }
    }
}
