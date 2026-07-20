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
    property real dataPhase: screenshotMode ? 6.4 : 0.0
    property real heartbeatLevel: screenshotMode ? 0.82 : 0.22

    function segmentOpacity(index, idleOpacity) {
        var distance = Math.abs(index - dataPhase)
        return Math.max(idleOpacity, 0.92 - distance * 0.46)
    }

    // Exposed bus lights sit directly on the sidebar/workspace seam.
    Column {
        anchors.left: parent.left
        anchors.leftMargin: root.sidebarSeam
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.px(13)

        Repeater {
            model: 11

            Rectangle {
                required property int index
                width: Theme.px(index % 4 === 0 ? 4 : 2)
                height: Theme.px(index % 3 === 0 ? 6 : 3)
                radius: Math.min(width, height) / 2
                color: index === 8 ? Theme.signalSecondary : Theme.signalPrimary
                opacity: root.segmentOpacity(index, index % 4 === 0 ? 0.26 : 0.10)
            }
        }
    }

    // A narrow diagnostic ladder remains visible along the outside chassis rail.
    Column {
        anchors.right: parent.right
        anchors.rightMargin: Theme.px(4)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.px(8)

        Repeater {
            model: 14

            Rectangle {
                required property int index
                width: Theme.px(index % 5 === 0 ? 4 : 2)
                height: Theme.px(index % 2 === 0 ? 5 : 3)
                radius: width / 2
                color: index === 11 ? Theme.signalSecondary : Theme.signalPrimary
                opacity: root.segmentOpacity(13 - index, index % 5 === 0 ? 0.24 : 0.09)
            }
        }
    }

    Row {
        anchors.left: parent.left
        anchors.leftMargin: root.sidebarSeam + Theme.px(14)
        anchors.top: parent.top
        anchors.topMargin: Theme.px(92)
        spacing: Theme.px(7)

        Repeater {
            model: [Theme.signalSuccess, Theme.signalSecondary, Theme.signalDanger]

            Rectangle {
                required property color modelData
                width: Theme.px(4)
                height: width
                radius: width / 2
                color: modelData
                opacity: root.heartbeatLevel

                Rectangle {
                    anchors.centerIn: parent
                    width: parent.width + Theme.px(4)
                    height: width
                    radius: width / 2
                    color: parent.color
                    opacity: 0.11
                }
            }
        }
    }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.px(4)
        spacing: Theme.px(5)

        Repeater {
            model: 13

            Rectangle {
                required property int index
                width: Theme.px(index % 4 === 0 ? 9 : 4)
                height: Theme.px(2)
                radius: height / 2
                color: index === 10 ? Theme.signalSecondary : Theme.signalPrimary
                opacity: root.segmentOpacity(index, index % 4 === 0 ? 0.20 : 0.08)
            }
        }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        PropertyAction { target: root; property: "dataPhase"; value: -1.0 }
        NumberAnimation {
            target: root
            property: "dataPhase"
            to: 14.0
            duration: 1850
            easing.type: Easing.InOutCubic
        }
        PauseAnimation { duration: 7600 }
        NumberAnimation {
            target: root
            property: "dataPhase"
            to: 4.0
            duration: 520
            easing.type: Easing.OutCubic
        }
        PauseAnimation { duration: 11200 }
    }

    SequentialAnimation {
        running: root.motionAllowed
        loops: Animation.Infinite
        PropertyAction { target: root; property: "heartbeatLevel"; value: 0.20 }
        PauseAnimation { duration: 3400 }
        NumberAnimation { target: root; property: "heartbeatLevel"; to: 0.92; duration: 95 }
        NumberAnimation { target: root; property: "heartbeatLevel"; to: 0.24; duration: 180 }
        PauseAnimation { duration: 130 }
        NumberAnimation { target: root; property: "heartbeatLevel"; to: 0.72; duration: 90 }
        NumberAnimation { target: root; property: "heartbeatLevel"; to: 0.20; duration: 260 }
        PauseAnimation { duration: 9100 }
    }
}
