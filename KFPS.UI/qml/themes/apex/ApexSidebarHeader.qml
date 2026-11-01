import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0
import "../../components"
Item {
    id: root
    property var sidebar: null
    property bool initialShown: false
    function begin() {
        if (!initialShown && sidebar && Window.window && Window.window.visible) {
            initialShown = true
            dashboard.open()
        }
    }
    Component.onCompleted: { if (sidebar) sidebar.dashboardVisible = true; Qt.callLater(begin) }
    onSidebarChanged: Qt.callLater(begin)
    Component.onDestruction: { if (sidebar) sidebar.dashboardVisible = false }
    Connections { target: root.Window.window; function onVisibleChanged() { Qt.callLater(root.begin) } }
    AbstractButton {
        id: launcher
        objectName: "ApexDashboardLaunch"
        anchors.fill: parent
        hoverEnabled: true; focusPolicy: Qt.StrongFocus
        Accessible.name: "Main menu"
        background: Rectangle {
            color: launcher.hovered ? Theme.ghostHoverSurface : Theme.surfaceStrong
            border.width: launcher.visualFocus ? Theme.px(2) : 0; border.color: Theme.focusColor
        }
        ApexIcon { anchors.centerIn: parent; width: Theme.px(28); height: width; name: "home" }
        onClicked: dashboard.open()
        KfpsToolTip { visible: launcher.hovered; text: "Main menu" }
    }
    ApexDashboard {
        id: dashboard
        navigation: root.sidebar
        onVisibleChanged: { if (root.sidebar) root.sidebar.dashboardVisible = visible }
    }
}
