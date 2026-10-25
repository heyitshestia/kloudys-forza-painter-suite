import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0
import "../../components"

Item {
    id: root
    property var sidebar: null
    readonly property bool compact: sidebar ? sidebar.compact : false
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
    Connections {
        target: root.Window.window
        function onVisibleChanged() { Qt.callLater(root.openInitialDashboard) }
    }
    XboxReactor {
        id: core
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 2
        width: Math.min(parent.width, parent.height - 24)
        height: width
        compact: root.compact
        animated: !dashboard.visible && !startup.visible
    }
    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        text: "MENU"
        color: Theme.muted
        font.family: Theme.displayFamily
        font.pixelSize: 12
        font.weight: Font.DemiBold
    }
    Button {
        id: dashboardButton
        objectName: "XboxDashboardLaunch"
        anchors.fill: parent
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: "Return to main menu"
        background: Rectangle {
            color: "transparent"
            radius: 6
            border.width: dashboardButton.visualFocus ? 2 : 0
            border.color: Theme.focusColor
        }
        onClicked: dashboard.open()
        KfpsToolTip {
            visible: dashboardButton.hovered
            text: "Return to main menu"
        }
    }
    XboxDashboard {
        id: dashboard
        navigation: root.sidebar
        onVisibleChanged: root.syncNavigation()
    }
    XboxStartup {
        id: startup
        navigation: root.sidebar
        service: typeof startupSequenceService !== "undefined" ? startupSequenceService : null
        onVisibleChanged: root.syncNavigation()
        onFinished: dashboard.open()
    }
}
