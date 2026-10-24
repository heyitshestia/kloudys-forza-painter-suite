import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0
import "XboxMotion.js" as Motion

Item {
    id: root
    objectName: "XboxPageTransition"
    enabled: false
    property real progress: 1
    property bool applicationActive: Window.window ? Window.window.active : false
    readonly property bool motionAllowed: !Theme.reducedMotion && !screenshotMode
                                         && applicationActive
    function play() {
        if (motionAllowed) travel.restart()
    }
    onMotionAllowedChanged: {
        if (!motionAllowed) { travel.stop(); progress = 1 }
    }
    Repeater {
        model: 2
        Rectangle {
            required property int index
            width: root.width
            height: 2
            y: index === 0 ? root.height * 0.18 : root.height * 0.82
            color: Theme.primary
            opacity: (1 - root.progress) * 0.45
            transform: Translate { x: (index === 0 ? -1 : 1) * root.width * root.progress }
        }
    }
    NumberAnimation {
        id: travel
        target: root
        property: "progress"
        from: 0
        to: 1
        duration: Motion.enterDuration
        easing.type: Easing.OutCubic
    }
}
