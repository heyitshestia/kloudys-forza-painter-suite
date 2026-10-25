import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0
import "../../components"

Item {
    id: root
    property var sidebar: null
    property bool initialDashboardShown: false
    function openInitialDashboard() {
        if (!initialDashboardShown && Window.window && Window.window.visible) {
            initialDashboardShown = true
            if (!startup.begin()) dashboard.open()
        }
    }
    function syncNavigation() {
        if (sidebar) sidebar.dashboardVisible = dashboard.visible || startup.visible
    }
    Component.onCompleted: {
        if (sidebar) sidebar.dashboardVisible = true
        Qt.callLater(openInitialDashboard)
    }
    Component.onDestruction: { if (sidebar) sidebar.dashboardVisible = false }
    Connections { target: root.Window.window; function onVisibleChanged() { Qt.callLater(root.openInitialDashboard) } }
    Ps2Clock {
        width: 62; height: 62
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        compact: true
        animated: !dashboard.visible
    }
    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        text: "MENU"
        font.family: Theme.displayFamily
        font.pixelSize: 12
        color: Theme.muted
    }
    Button {
        id: button
        objectName: "Ps2DashboardLaunch"
        anchors.fill: parent
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: "Return to main menu"
        background: Rectangle {
            color: "transparent"
            radius: 3
            border.width: button.visualFocus ? 2 : 0
            border.color: Theme.focusColor
        }
        onClicked: dashboard.open()
        KfpsToolTip { visible: button.hovered; text: "Return to main menu" }
    }
    Ps2Dashboard {
        id: dashboard
        navigation: root.sidebar
        onVisibleChanged: root.syncNavigation()
    }
    Ps2Startup {
        id: startup
        navigation: root.sidebar
        service: typeof startupSequenceService !== "undefined" ? startupSequenceService : null
        onVisibleChanged: root.syncNavigation()
        onFinished: dashboard.open()
    }
}
