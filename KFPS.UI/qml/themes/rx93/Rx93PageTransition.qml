import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    enabled: false
    property real travel: 0
    function play() {
        if (!screenshotMode && !Theme.reducedMotion && Window.window && Window.window.active)
            engage.restart()
    }
    Rectangle {
        x: 0; y: 0
        width: parent.width * root.travel; height: 2
        color: Theme.signalSecondary
        opacity: root.travel > 0 ? 0.75 : 0
    }
    Rectangle {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        width: parent.width * root.travel; height: 2
        color: Theme.signalPrimary
        opacity: root.travel > 0 ? 0.5 : 0
    }
    SequentialAnimation {
        id: engage
        NumberAnimation { target: root; property: "travel"; from: 0; to: 1; duration: 180; easing.type: Easing.OutCubic }
        NumberAnimation { target: root; property: "travel"; to: 0; duration: 100; easing.type: Easing.InCubic }
    }
}
