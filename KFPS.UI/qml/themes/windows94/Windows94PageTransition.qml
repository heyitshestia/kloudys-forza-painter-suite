import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root

    property bool playing: false
    opacity: 0

    function play() {
        if (Theme.reducedMotion)
            return
        transitionAnimation.restart()
    }

    Rectangle {
        id: frame
        color: "transparent"
        border.width: Math.max(1, Theme.px(1))
        border.color: Theme.transitionTrail
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

        PropertyAction { target: frame; property: "x"; value: root.width * 0.44 }
        PropertyAction { target: frame; property: "y"; value: root.height * 0.44 }
        PropertyAction { target: frame; property: "width"; value: root.width * 0.12 }
        PropertyAction { target: frame; property: "height"; value: root.height * 0.12 }
        ParallelAnimation {
            NumberAnimation { target: frame; property: "x"; to: 0; duration: Theme.pageTransitionDuration; easing.type: Easing.OutQuad }
            NumberAnimation { target: frame; property: "y"; to: 0; duration: Theme.pageTransitionDuration; easing.type: Easing.OutQuad }
            NumberAnimation { target: frame; property: "width"; to: root.width; duration: Theme.pageTransitionDuration; easing.type: Easing.OutQuad }
            NumberAnimation { target: frame; property: "height"; to: root.height; duration: Theme.pageTransitionDuration; easing.type: Easing.OutQuad }
        }
        PauseAnimation { duration: 30 }
    }
}
