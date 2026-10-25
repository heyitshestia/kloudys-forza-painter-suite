import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0
import "../../components"

FocusScope {
    id: root
    objectName: "Ps2Dashboard"
    property var navigation: null
    property int level: 0
    property int homeIndex: 0
    property real reveal: 1
    property bool departing: false
    property Item previousFocusItem: null
    readonly property bool hasEnteredWorkspace: navigation ? navigation.dashboardWorkspaceEntered : false
    readonly property bool motionAllowed: !Theme.reducedMotion && !screenshotMode
    signal closed()
    parent: navigation ? navigation.parent : null
    anchors.fill: parent
    z: 30
    visible: false
    enabled: visible
    clip: true

    function open() {
        if (visible && !departing) return
        if (!visible && Window.window) previousFocusItem = Window.window.activeFocusItem
        entrance.stop(); exit.stop()
        departing = false; level = 0; homeIndex = 0
        browser.currentIndex = navigation ? navigation.pageIndex(appController.currentPage) : 0
        reveal = motionAllowed ? 0 : 1
        visible = true
        home.forceActiveFocus()
        if (motionAllowed) entrance.start()
    }
    function finishClose() {
        var focused = Window.window ? Window.window.activeFocusItem : null
        var restoreFocus = !focused
        for (var item = focused; item; item = item.parent) {
            if (item === root) { restoreFocus = true; break }
        }
        visible = false; departing = false; focus = false
        if (restoreFocus && previousFocusItem && previousFocusItem.visible && previousFocusItem.enabled)
            previousFocusItem.forceActiveFocus()
        previousFocusItem = null
        closed()
    }
    function close() {
        if (!visible || departing || !hasEnteredWorkspace) return
        entrance.stop(); departing = true
        if (motionAllowed) exit.start()
        else finishClose()
    }
    function showBrowser() {
        if (departing) return
        level = 1
        browser.forceActiveFocus()
        browser.positionViewAtIndex(browser.currentIndex, GridView.Contain)
    }
    function back() {
        if (departing) return
        if (level === 1) { level = 0; home.forceActiveFocus() }
        else if (hasEnteredWorkspace) close()
    }
    function choose(page) {
        if (!visible || departing || !page) return
        if (navigation) {
            navigation.dashboardWorkspaceEntered = true
            navigation.route(page)
        }
        close()
    }
    function homeChoose() { if (homeIndex === 0) showBrowser(); else choose("settings") }
    Keys.onEscapePressed: function(event) { back(); event.accepted = true }
    Ps2Backdrop { anchors.fill: parent }
    NumberAnimation { id: entrance; target: root; property: "reveal"; to: 1; duration: 280; easing.type: Easing.OutCubic }
    NumberAnimation { id: exit; target: root; property: "reveal"; to: 0; duration: 160; easing.type: Easing.InCubic; onFinished: root.finishClose() }
    onMotionAllowedChanged: {
        if (!motionAllowed) {
            entrance.stop(); exit.stop()
            if (departing) finishClose()
            else reveal = 1
        }
    }
    Item {
        anchors.fill: parent
        opacity: root.reveal
        FocusScope {
            id: home
            objectName: "Ps2HomeMenu"
            anchors.fill: parent
            visible: root.level === 0
            enabled: visible
            Keys.onPressed: function(event) {
                if ([Qt.Key_Up, Qt.Key_Down, Qt.Key_Home, Qt.Key_End].indexOf(event.key) >= 0) {
                    root.homeIndex = event.key === Qt.Key_Home ? 0 : event.key === Qt.Key_End ? 1 : 1 - root.homeIndex
                    event.accepted = true
                } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                    root.homeChoose(); event.accepted = true
                }
            }
            Item {
                width: Math.min(720, parent.width - 64)
                height: Math.min(440, parent.height - 140)
                anchors.centerIn: parent
                Ps2Clock {
                    objectName: "Ps2HomeClock"
                    width: 270; height: 240
                    x: parent.width * 0.2 - width / 2
                    y: parent.height * 0.36 - height / 2
                    animated: root.visible && root.level === 0
                }
                Column {
                    x: parent.width * 0.29
                    y: parent.height * 0.51
                    width: parent.width * 0.71
                    spacing: 6
                    Ps2MenuText {
                        objectName: "Ps2HomeBrowser"
                        width: parent.width
                        text: "Browser"
                        selected: root.homeIndex === 0
                        onHoveredChanged: { if (hovered) root.homeIndex = 0 }
                        onClicked: root.showBrowser()
                    }
                    Ps2MenuText {
                        objectName: "Ps2HomeConfiguration"
                        width: parent.width
                        text: "System Configuration"
                        selected: root.homeIndex === 1
                        onHoveredChanged: { if (hovered) root.homeIndex = 1 }
                        onClicked: root.choose("settings")
                    }
                }
            }
        }
        Item {
            anchors.fill: parent
            anchors.margins: 40
            visible: root.level === 1
            enabled: visible
            Text {
                id: browserTitle
                text: "Browser"
                color: Theme.text
                font.family: Theme.displayFamily
                font.pixelSize: 24
                anchors.left: parent.left
                anchors.top: parent.top
            }
            Text {
                anchors.top: parent.top; anchors.right: parent.right
                text: browser.currentIndex >= 0 && root.navigation ? root.navigation.navItems[browser.currentIndex].label : ""
                font.family: Theme.displayFamily
                font.pixelSize: 24
                color: Theme.primary
            }
            GridView {
                id: browser
                objectName: "Ps2BrowserMenu"
                width: Math.min(1000, parent.width)
                height: Math.min(400, parent.height - 110)
                anchors.centerIn: parent
                cellWidth: width / (width < 700 ? 4 : 5)
                cellHeight: 176
                model: root.navigation ? root.navigation.navItems : []
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                keyNavigationEnabled: true
                Keys.onReturnPressed: root.choose(model[currentIndex].page)
                Keys.onEnterPressed: root.choose(model[currentIndex].page)
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Home || event.key === Qt.Key_End) {
                        currentIndex = event.key === Qt.Key_Home ? 0 : count - 1
                        positionViewAtIndex(currentIndex, GridView.Contain)
                        event.accepted = true
                    }
                }
                delegate: AbstractButton {
                    id: itemButton
                    required property var modelData
                    required property int index
                    objectName: "Ps2DashboardRoute:" + modelData.page
                    width: browser.cellWidth
                    height: browser.cellHeight
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    Accessible.name: modelData.label
                    readonly property bool selected: browser.currentIndex === index
                    onHoveredChanged: { if (hovered) browser.currentIndex = index }
                    onClicked: root.choose(modelData.page)
                    background: Item {}
                    Rectangle {
                        id: memoryIcon
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: itemButton.selected ? 12 : 20
                        width: 86; height: 104
                        radius: 3
                        color: itemButton.selected ? Theme.primaryDeep : Theme.surfaceSoft
                        border.width: itemButton.selected ? 2 : 1
                        border.color: itemButton.selected ? Theme.primaryBright : Theme.border
                        Behavior on y { enabled: root.motionAllowed; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                        Rectangle { x: 10; y: 8; width: parent.width - 20; height: 2; color: itemButton.selected ? Theme.primary : Theme.border }
                        Icon { anchors.centerIn: parent; name: itemButton.modelData.icon; iconSize: 38; colorize: false }
                        Rectangle { x: 15; y: parent.height - 14; width: parent.width - 30; height: 4; color: Theme.border }
                    }
                    Text {
                        width: parent.width - 12
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 128
                        text: itemButton.modelData.label
                        horizontalAlignment: Text.AlignHCenter
                        color: itemButton.selected ? Theme.primaryBright : Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: 19
                        elide: Text.ElideRight
                    }
                    Rectangle {
                        anchors.fill: parent; anchors.margins: 5
                        visible: itemButton.visualFocus
                        color: "transparent"; border.color: Theme.focusColor; radius: 3
                    }
                }
                ScrollBar.vertical: KfpsScrollBar {}
            }
        }
    }
}
