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
        opacity: 0.0
    }

    Item {
        id: carriage
        y: 0
        width: Math.max(Theme.px(116), root.width * 0.115)
        height: root.height
        x: -width

        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "#00000000" }
                GradientStop { position: 0.34; color: Theme.withAlpha(Theme.transitionSweep, 0.15) }
                GradientStop { position: 0.64; color: Theme.withAlpha(Theme.transitionSweep, 0.60) }
                GradientStop { position: 0.78; color: Theme.withAlpha(Theme.transitionSweep, 0.27) }
                GradientStop { position: 1.0; color: "#00000000" }
            }
        }

        Rectangle {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: Math.max(Theme.px(2), parent.width * 0.025)
            color: Theme.transitionSweep
            opacity: 0.88
        }

        Row {
            anchors.right: parent.left
            anchors.rightMargin: Theme.px(7)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.px(5)

            Repeater {
                model: 5
                Rectangle {
                    required property int index
                    width: Theme.px(index === 4 ? 16 : 8)
                    height: Theme.px(3)
                    radius: height / 2
                    color: index === 4 ? Theme.transitionTrail : Theme.transitionSweep
                    opacity: 0.24 + index * 0.13
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
                NumberAnimation { target: veil; property: "opacity"; from: 0; to: 0.28; duration: 70; easing.type: Easing.OutQuad }
                NumberAnimation { target: veil; property: "opacity"; from: 0.28; to: 0; duration: 250; easing.type: Easing.OutCubic }
            }
            SequentialAnimation {
                PropertyAction { target: carriage; property: "x"; value: -carriage.width }
                NumberAnimation {
                    target: carriage
                    property: "x"
                    to: root.width + carriage.width
                    duration: Theme.pageTransitionDuration
                    easing.type: Easing.InOutCubic
                }
            }
        }
    }
}
