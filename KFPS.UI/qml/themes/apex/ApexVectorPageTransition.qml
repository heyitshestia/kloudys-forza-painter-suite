import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property bool playing: false
    opacity: 0

    function play() {
        if (screenshotMode || Theme.reducedMotion)
            return
        transitionAnimation.restart()
    }

    Rectangle {
        id: veil
        anchors.fill: parent
        color: Theme.backgroundA
        opacity: 0
    }

    Item {
        id: sweep
        x: -width
        width: Math.max(Theme.px(240), root.width * 0.22)
        height: root.height

        Rectangle {
            anchors.fill: parent
            color: Theme.withAlpha(Theme.transitionSweep, 0.10)
        }

        Rectangle {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: Math.max(Theme.px(2), parent.width * 0.012)
            color: Theme.transitionSweep
            opacity: 0.86
        }

        Rectangle {
            anchors.right: parent.right
            anchors.rightMargin: Theme.px(5)
            y: root.height * 0.27
            width: parent.width * 0.78
            height: Theme.px(7)
            color: Theme.transitionTrail
            opacity: 0.88
        }

        Rectangle {
            anchors.right: parent.right
            anchors.rightMargin: Theme.px(5)
            y: root.height * 0.63
            width: parent.width * 0.48
            height: Theme.px(3)
            color: Theme.signalSecondary
            opacity: 0.72
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: Theme.px(12)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.px(4)

            Repeater {
                model: 7

                Rectangle {
                    required property int index
                    width: Theme.px(index === 5 ? 24 : 7)
                    height: Theme.px(3)
                    color: index === 6 ? Theme.transitionTrail : Theme.transitionSweep
                    opacity: 0.18 + index * 0.09
                }
            }
        }
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
        }

        ParallelAnimation {
            SequentialAnimation {
                NumberAnimation { target: veil; property: "opacity"; from: 0; to: 0.44; duration: 72; easing.type: Easing.OutQuad }
                NumberAnimation { target: veil; property: "opacity"; from: 0.44; to: 0; duration: 230; easing.type: Easing.OutCubic }
            }
            SequentialAnimation {
                PropertyAction { target: sweep; property: "x"; value: -sweep.width }
                NumberAnimation {
                    target: sweep
                    property: "x"
                    to: root.width + sweep.width
                    duration: Theme.pageTransitionDuration
                    easing.type: Easing.InOutCubic
                }
            }
        }
    }
}
