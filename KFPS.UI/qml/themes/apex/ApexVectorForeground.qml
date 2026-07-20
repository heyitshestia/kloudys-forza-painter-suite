import QtQuick 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0

Item {
    id: root

    readonly property bool applicationActive: Window.window ? Window.window.active : true
    readonly property bool motionAllowed: Theme.ambientMotion
                                          && !Theme.reducedMotion
                                          && !screenshotMode
                                          && applicationActive
    readonly property bool compactSidebar: Theme.logical(width) < 1240
    readonly property real sidebarSeam: Theme.px(compactSidebar ? Metrics.compactSidebar : Metrics.wideSidebar)
    property real busPhase: screenshotMode ? 7.0 : 0.0
    property real seamPacketProgress: screenshotMode ? 0.34 : -0.10
    property real seamPacketStrength: screenshotMode ? 0.62 : 0.0
    property real crownPacketProgress: screenshotMode ? 0.72 : -0.12
    property real crownPacketStrength: screenshotMode ? 0.58 : 0.0

    Rectangle {
        anchors.left: parent.left
        anchors.leftMargin: root.sidebarSeam
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Math.max(1, Theme.px(1))
        color: Theme.borderStrong
        opacity: 0.32
    }

    Rectangle {
        anchors.left: parent.left
        anchors.leftMargin: root.sidebarSeam
        anchors.top: parent.top
        anchors.topMargin: Theme.px(76)
        width: Theme.px(4)
        height: Theme.px(116)
        color: Theme.signalPrimary
        opacity: 0.84
    }

    Item {
        x: root.sidebarSeam - Theme.px(2)
        y: Theme.px(76)
        width: Theme.px(5)
        height: Math.max(Theme.px(220), root.height - Theme.px(152))
        clip: true

        Column {
            y: -height
            spacing: Theme.px(3)
            opacity: root.seamPacketStrength
            transform: Translate {
                y: root.seamPacketProgress * (parent.height + parent.height * 0.16)
            }

            Rectangle {
                width: Theme.px(5)
                height: Theme.px(26)
                color: Theme.signalSecondary
            }

            Rectangle {
                width: Theme.px(5)
                height: Theme.px(8)
                color: Theme.signalPrimary
            }

            Rectangle {
                width: Theme.px(5)
                height: Theme.px(3)
                color: Theme.borderStrong
            }
        }
    }

    Item {
        x: root.sidebarSeam + Theme.px(34)
        y: Theme.px(22)
        width: Math.max(Theme.px(260), root.width - x - Theme.px(28))
        height: Theme.px(5)
        clip: true

        Row {
            x: -width
            spacing: Theme.px(3)
            opacity: root.crownPacketStrength
            transform: Translate {
                x: root.crownPacketProgress * (parent.width + parent.width * 0.18)
            }

            Rectangle {
                width: Theme.px(36)
                height: Theme.px(2)
                color: Theme.signalPrimary
            }

            Rectangle {
                width: Theme.px(9)
                height: Theme.px(2)
                color: Theme.signalSecondary
            }

            Rectangle {
                width: Theme.px(4)
                height: Theme.px(2)
                color: Theme.borderStrong
            }
        }
    }

    Column {
        anchors.left: parent.left
        anchors.leftMargin: root.sidebarSeam + Theme.px(8)
        anchors.top: parent.top
        anchors.topMargin: Theme.px(82)
        spacing: Theme.px(7)

        Repeater {
            model: 10

            Rectangle {
                required property int index
                width: Theme.px(index % 3 === 0 ? 14 : 5)
                height: Theme.px(2)
                color: index === 7 ? Theme.signalSecondary : Theme.borderStrong
                opacity: root.busPhase > index ? 0.58 : 0.10
            }
        }
    }

    Row {
        anchors.right: parent.right
        anchors.rightMargin: Theme.px(18)
        anchors.top: parent.top
        anchors.topMargin: Theme.px(48)
        spacing: Theme.px(4)

        Repeater {
            model: 8

            Rectangle {
                required property int index
                width: Theme.px(index === 5 ? 22 : (index % 3 === 0 ? 9 : 4))
                height: Theme.px(2)
                color: index === 6 ? Theme.signalPrimary : Theme.signalSecondary
                opacity: root.busPhase > index ? 0.72 : 0.12
            }
        }
    }

    Row {
        anchors.right: parent.right
        anchors.rightMargin: Theme.px(12)
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.px(4)
        spacing: Theme.px(3)

        Repeater {
            model: 13

            Rectangle {
                required property int index
                width: Theme.px(index % 4 === 0 ? 16 : 4)
                height: Theme.px(2)
                color: index === 9 ? Theme.signalPrimary : Theme.borderStrong
                opacity: root.busPhase > index ? 0.48 : 0.08
            }
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Math.max(1, Theme.px(1))
        color: Theme.borderStrong
        opacity: 0.28
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        PropertyAction { target: root; property: "busPhase"; value: 0.0 }
        NumberAnimation { target: root; property: "busPhase"; to: 13.0; duration: 1150; easing.type: Easing.OutCubic }
        PauseAnimation { duration: 6600 }
        NumberAnimation { target: root; property: "busPhase"; to: 4.0; duration: 360; easing.type: Easing.InCubic }
        PauseAnimation { duration: 8100 }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        PropertyAction { target: root; property: "seamPacketProgress"; value: -0.10 }
        PropertyAction { target: root; property: "seamPacketStrength"; value: 0.0 }
        PauseAnimation { duration: 1900 }
        NumberAnimation { target: root; property: "seamPacketStrength"; to: 0.74; duration: 140; easing.type: Easing.OutQuad }
        NumberAnimation { target: root; property: "seamPacketProgress"; to: 1.10; duration: 1650; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "seamPacketStrength"; to: 0.0; duration: 220; easing.type: Easing.InQuad }
        PauseAnimation { duration: 7200 }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        PropertyAction { target: root; property: "crownPacketProgress"; value: -0.12 }
        PropertyAction { target: root; property: "crownPacketStrength"; value: 0.0 }
        PauseAnimation { duration: 4600 }
        NumberAnimation { target: root; property: "crownPacketStrength"; to: 0.66; duration: 180; easing.type: Easing.OutQuad }
        NumberAnimation { target: root; property: "crownPacketProgress"; to: 1.12; duration: 2300; easing.type: Easing.InOutCubic }
        NumberAnimation { target: root; property: "crownPacketStrength"; to: 0.0; duration: 260; easing.type: Easing.InQuad }
        PauseAnimation { duration: 9200 }
    }
}
