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
        if (!initialShown && Window.window && Window.window.visible) { initialShown = true; dashboard.open() }
    }
    Component.onCompleted: { if (sidebar) sidebar.dashboardVisible = true; Qt.callLater(begin) }
    Component.onDestruction: { if (sidebar) sidebar.dashboardVisible = false }
    Connections { target: root.Window.window; function onVisibleChanged() { Qt.callLater(root.begin) } }
    Button {
        id: button
        objectName: "NierDashboardLaunch"
        anchors.fill: parent
        anchors.margins: 6
        text: "MENU"
        font.family: Theme.displayFamily
        font.pixelSize: Theme.px(12)
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: "Return to main menu"
        contentItem: Text { text: button.text; color: Theme.text; font: button.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { color: button.hovered ? Theme.hover : Theme.surfaceSoft; border.color: Theme.border; border.width: button.visualFocus ? 2 : 1 }
        onClicked: dashboard.open()
        KfpsToolTip { visible: button.hovered; text: "Return to main menu" }
    }
    NierDashboard { id: dashboard; navigation: root.sidebar; onVisibleChanged: { if (root.sidebar) root.sidebar.dashboardVisible = visible } }
}
