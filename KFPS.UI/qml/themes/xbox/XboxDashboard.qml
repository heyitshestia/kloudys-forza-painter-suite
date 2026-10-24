import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0
import "../../components"
import "XboxMotion.js" as Motion

FocusScope {
    id: root
    objectName: "XboxDashboard"
    property var navigation: null
    property real reveal: 1
    property bool departing: false
    readonly property bool hasEnteredWorkspace: navigation ? navigation.dashboardWorkspaceEntered : false
    property real selectionEnergy: 0
    property Item previousFocusItem: null
    signal closed()
    readonly property bool motionAllowed: !Theme.reducedMotion && !screenshotMode
    // Own the application body, not the window's modal overlay or title bar.
    parent: navigation ? navigation.parent : null
    anchors.fill: parent
    z: 30
    visible: false
    enabled: visible
    clip: true

    function open() {
        if (visible && !departing) return
        if (!visible && Window.window) previousFocusItem = Window.window.activeFocusItem
        entry.stop()
        exit.stop()
        departing = false
        if (navigation) menu.currentIndex = navigation.pageIndex(appController.currentPage)
        reveal = motionAllowed ? 0 : 1
        visible = true
        menu.forceActiveFocus()
        if (motionAllowed) entry.start()
    }
    function finishClose() {
        var focused = Window.window ? Window.window.activeFocusItem : null
        var restoreFocus = !focused
        for (var item = focused; item; item = item.parent) {
            if (item === root) { restoreFocus = true; break }
        }
        visible = false
        departing = false
        focus = false
        // A dialog opened during exit owns focus; do not move it back underneath.
        if (restoreFocus && previousFocusItem && previousFocusItem.visible && previousFocusItem.enabled)
            previousFocusItem.forceActiveFocus()
        previousFocusItem = null
        closed()
    }
    function close() {
        if (!visible || departing || !hasEnteredWorkspace) return
        entry.stop()
        departing = true
        if (motionAllowed) exit.start()
        else finishClose()
    }
    Keys.onEscapePressed: function(event) {
        if (hasEnteredWorkspace) close()
        event.accepted = true
    }
    XboxBackdrop {
        id: space
        anchors.fill: parent
        dashboard: true
        animationEnabled: root.visible
    }
    NumberAnimation {
        id: entry
        target: root; property: "reveal"; to: 1
        duration: Motion.enterDuration; easing.type: Easing.OutCubic
    }
    NumberAnimation {
        id: exit
        target: root; property: "reveal"; to: 0
        duration: Motion.exitDuration; easing.type: Easing.InCubic
        onFinished: root.finishClose()
    }

    function choose(page) {
        if (!page || !visible || departing) return
        if (navigation) {
            navigation.dashboardWorkspaceEntered = true
            navigation.route(page)
        }
        close()
    }
    SequentialAnimation {
        id: selectionPulse
        NumberAnimation { target: root; property: "selectionEnergy"; to: 1; duration: Motion.selectionDuration / 2 }
        NumberAnimation { target: root; property: "selectionEnergy"; to: 0; duration: Motion.selectionDuration * 2 }
    }
    onMotionAllowedChanged: {
        if (!motionAllowed) {
            selectionPulse.stop()
            selectionEnergy = 0
            entry.stop()
            exit.stop()
            if (departing) finishClose()
            else reveal = 1
        }
    }
    Item {
        objectName: "XboxDashboardContent"
        anchors.fill: parent
        GhostButton {
            objectName: "XboxDashboardClose"
            anchors.top: parent.top; anchors.right: parent.right
            anchors.margins: 16
            text: "Back"
            visible: root.hasEnteredWorkspace
            iconName: "chevron-left"
            toolTipText: "Return to the workspace."
            onClicked: root.close()
        }
        Row {
            width: Math.min(1080, parent.width - 64)
            height: parent.height - 112
            anchors.centerIn: parent
            spacing: 44
            Item {
                width: parent.width * 0.4
                height: parent.height
                XboxReactor {
                    id: medallion
                    anchors.centerIn: parent
                    width: Math.min(parent.width * 1.3, parent.height * 0.9)
                    height: width
                    scale: root.departing ? 1 + (1 - root.reveal) * 0.28 : 0.9 + root.reveal * 0.1
                    opacity: 0.3 + root.reveal * 0.7
                    animated: root.visible
                    selectionEnergy: root.selectionEnergy
                }
            }
            ListView {
                id: menu
                objectName: "XboxDashboardMenu"
                width: parent.width * 0.6 - parent.spacing
                height: Math.min(parent.height, contentHeight)
                anchors.verticalCenter: parent.verticalCenter
                model: root.navigation ? root.navigation.navItems : []
                clip: true
                spacing: 4
                onCurrentIndexChanged: {
                    if (root.visible && root.motionAllowed) selectionPulse.restart()
                }
                boundsBehavior: Flickable.StopAtBounds
                keyNavigationEnabled: true
                Keys.onReturnPressed: { if (currentIndex >= 0 && currentIndex < count) root.choose(model[currentIndex].page) }
                Keys.onEnterPressed: { if (currentIndex >= 0 && currentIndex < count) root.choose(model[currentIndex].page) }
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Home || event.key === Qt.Key_End) {
                        currentIndex = event.key === Qt.Key_Home ? 0 : count - 1
                        positionViewAtIndex(currentIndex, ListView.Contain)
                        event.accepted = true
                    }
                }
                delegate: XboxMenuEntry {
                    required property var modelData
                    required property int index
                    objectName: "XboxDashboardRoute:" + modelData.page
                    width: menu.width - 28
                    height: 50
                    text: modelData.label
                    active: menu.currentIndex === index
                    reveal: root.reveal
                    order: index
                    selectedIndex: menu.currentIndex
                    seconds: space.motionClock.seconds
                    onHoveredChanged: { if (hovered) menu.currentIndex = index }
                    onClicked: root.choose(modelData.page)
                }
                ScrollBar.vertical: KfpsScrollBar {}
            }
        }
        GhostButton {
            objectName: "XboxDashboardCredits"
            anchors.bottom: parent.bottom; anchors.right: parent.right
            anchors.margins: 16
            text: "Credits"
            iconName: "heart"
            onClicked: root.choose("credits")
        }
    }
}
