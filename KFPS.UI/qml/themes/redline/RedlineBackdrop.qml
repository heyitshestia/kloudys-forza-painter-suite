import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "RedlineBackdrop"
    enabled: false
    clip: true
    readonly property bool motionAllowed: visible && Window.window && Window.window.active && Window.window.visibility !== Window.Minimized && Theme.ambientMotion && !Theme.reducedMotion && !screenshotMode
    property real disruption: 0
    onMotionAllowedChanged: if (!motionAllowed) disruption = 0
    Rectangle { anchors.fill: parent; color: "#090609" }
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: "#00090004" }
            GradientStop { position: 0.7; color: "#141a0008" }
            GradientStop { position: 1; color: "#5a48000f" }
        }
    }
    // Broken red transmission bands, not a rolling CRT scan.
    Repeater {
        model: 11
        Rectangle {
            required property int index
            x: (index % 2 ? -0.15 : 0.48) * root.width + root.disruption * Theme.px(index % 3 ? 18 : -34)
            y: root.height * (0.69 + index * 0.027)
            width: root.width * (index % 3 ? 0.76 : 0.44)
            height: Theme.px(index % 4 === 0 ? 5 : 1)
            color: index % 4 === 0 ? "#3b66051c" : "#235e0c20"
            opacity: 0.45 + root.disruption * 0.35
        }
    }
    Repeater {
        model: 16
        Rectangle {
            required property int index
            x: root.width - Theme.px(26 + (index % 3) * 5)
            y: root.height * 0.3 + Theme.px(index * 7)
            width: Theme.px(index % 4 ? 3 : 9); height: 1
            color: Theme.primary; opacity: 0.22
        }
    }
    SequentialAnimation on disruption {
        running: root.motionAllowed; loops: Animation.Infinite
        PauseAnimation { duration: 3100 }
        NumberAnimation { to: 1; duration: 85; easing.type: Easing.OutQuad }
        NumberAnimation { to: 0.35; duration: 110 }
        PauseAnimation { duration: 160 }
        NumberAnimation { to: 0; duration: 220 }
    }
}
