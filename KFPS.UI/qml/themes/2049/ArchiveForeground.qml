import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "ArchiveForeground"
    enabled: false
    clip: true
    readonly property bool motionAllowed: visible && Window.window && Window.window.active && Window.window.visibility !== Window.Minimized && Theme.ambientMotion && !Theme.reducedMotion && !screenshotMode
    property real scanPosition: 0.2
    Image {
        anchors.fill: parent
        source: assetRoot + "/themes/2049/optical-rim.png"
        fillMode: Image.Stretch
        opacity: Theme.glassEffects ? 0.85 : 0.35
    }
    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        NumberAnimation { target: root; property: "scanPosition"; to: 0.9; duration: 12500; easing.type: Easing.Linear }
        NumberAnimation { target: root; property: "scanPosition"; to: 0.2; duration: 9000; easing.type: Easing.Linear }
    }
    // The moving reader is only four pixels wide, outside artwork and text.
    Repeater {
        model: 2
        Item {
            required property int index
            x: index === 0 ? 1 : root.width - 5
            y: Theme.px(42) + (root.height - Theme.px(110)) * (index === 0 ? root.scanPosition : 1 - root.scanPosition)
            width: 4; height: Theme.px(36)
            Rectangle { anchors.fill: parent; color: Theme.signalSecondary; opacity: 0.08 }
            Rectangle { anchors.centerIn: parent; width: 2; height: Theme.px(12); color: Theme.signalSecondary; opacity: 0.35 }
        }
    }
}
