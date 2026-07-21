import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property bool playing: false
    property real sweepPosition: -0.24
    property real disruption: 0.0
    property real veilOpacity: 0.0
    opacity: 0

    function play() {
        if (screenshotMode || Theme.reducedMotion)
            return
        transitionAnimation.restart()
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.backgroundA
        opacity: root.veilOpacity
    }

    Repeater {
        model: 11

        Rectangle {
            required property int index
            readonly property real laneOffset: (index % 3 - 1) * root.disruption * Theme.px(20)
            x: root.sweepPosition * (root.width + width) - width + laneOffset
            y: root.height * (0.06 + index * 0.083)
            width: root.width * (index % 4 === 0 ? 0.28 : (index % 3 === 0 ? 0.17 : 0.10))
            height: Theme.px(index % 4 === 0 ? 8 : (index % 2 === 0 ? 3 : 2))
            color: index === 7 || index === 2 ? Theme.transitionTrail : Theme.transitionSweep
            opacity: 0.22 + (index % 4) * 0.16
        }
    }

    Rectangle {
        x: root.sweepPosition * (root.width + width) - width
        y: 0
        width: Math.max(Theme.px(5), root.width * 0.008)
        height: root.height
        color: Theme.transitionSweep
        opacity: 0.86
    }

    Rectangle {
        x: root.sweepPosition * (root.width + width) - width - Theme.px(9)
        y: 0
        width: Math.max(Theme.px(2), root.width * 0.003)
        height: root.height
        color: Theme.transitionTrail
        opacity: Theme.glassEffects ? 0.72 : 0.0
    }

    SequentialAnimation {
        id: transitionAnimation

        onStarted: {
            root.playing = true
            root.opacity = 1
        }
        onStopped: {
            root.opacity = 0
            root.playing = false
            root.veilOpacity = 0
            root.disruption = 0
        }

        ParallelAnimation {
            SequentialAnimation {
                NumberAnimation { target: root; property: "veilOpacity"; from: 0; to: 0.44; duration: 58; easing.type: Easing.OutQuad }
                NumberAnimation { target: root; property: "veilOpacity"; to: 0.0; duration: 260; easing.type: Easing.OutCubic }
            }
            SequentialAnimation {
                PropertyAction { target: root; property: "sweepPosition"; value: -0.24 }
                NumberAnimation {
                    target: root
                    property: "sweepPosition"
                    to: 1.18
                    duration: Theme.pageTransitionDuration
                    easing.type: Easing.InOutCubic
                }
            }
            SequentialAnimation {
                PropertyAction { target: root; property: "disruption"; value: 0.0 }
                PauseAnimation { duration: 38 }
                NumberAnimation { target: root; property: "disruption"; to: 1.0; duration: 34 }
                NumberAnimation { target: root; property: "disruption"; to: -0.52; duration: 46 }
                NumberAnimation { target: root; property: "disruption"; to: 0.0; duration: 104; easing.type: Easing.OutCubic }
            }
        }
    }
}
