import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "ArchiveBackdrop"
    enabled: false
    clip: true
    readonly property bool motionAllowed: visible && Window.window && Window.window.active && Window.window.visibility !== Window.Minimized && Theme.ambientMotion && !Theme.reducedMotion && !screenshotMode
    property real sweepPosition: -0.12
    property real trackingOffset: 0
    readonly property int sweepDuration: 16000
    onMotionAllowedChanged: {
        if (!motionAllowed) { sweepPosition = -0.12; trackingOffset = 0 }
    }
    Rectangle { anchors.fill: parent; color: "#040c0d" }
    Image { anchors.fill: parent; source: assetRoot + "/themes/2049/optical-backing.png"; fillMode: Image.Stretch }
    Image { anchors.fill: parent; anchors.margins: Theme.px(18); source: assetRoot + "/themes/2049/optical-glass.png"; fillMode: Image.Tile; opacity: 0.24 }
    Image {
        anchors.fill: parent
        source: assetRoot + "/themes/2049/phosphor-raster.png"
        fillMode: Image.Tile; opacity: 0.5
        transform: Translate { y: root.trackingOffset }
    }
    Image {
        anchors.fill: parent; anchors.margins: Theme.px(32)
        source: assetRoot + "/themes/2049/analog-wear.png"
        fillMode: Image.Stretch; opacity: 0.65
    }
    Image {
        objectName: "ArchiveAnalogSweep"
        x: Theme.px(32); y: 0
        width: parent.width - Theme.px(64); height: Theme.px(80)
        visible: root.motionAllowed
        source: assetRoot + "/themes/2049/analog-sweep.png"
        fillMode: Image.Stretch; opacity: 0.62
        transform: Translate { y: root.sweepPosition * root.height }
    }
    SequentialAnimation {
        objectName: "ArchiveAnalogSweepAnimation"
        running: root.motionAllowed; loops: Animation.Infinite
        NumberAnimation { target: root; property: "sweepPosition"; from: -0.12; to: 1.08; duration: root.sweepDuration; easing.type: Easing.Linear }
        PauseAnimation { duration: 2400 }
    }
    SequentialAnimation {
        objectName: "ArchiveAnalogTrackingAnimation"
        running: root.motionAllowed; loops: Animation.Infinite
        PauseAnimation { duration: 6200 }
        NumberAnimation { target: root; property: "trackingOffset"; to: 1.5; duration: 480; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "trackingOffset"; to: -0.5; duration: 650; easing.type: Easing.InOutSine }
        NumberAnimation { target: root; property: "trackingOffset"; to: 0; duration: 800; easing.type: Easing.OutSine }
        PauseAnimation { duration: 5100 }
    }
}
