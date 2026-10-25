import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0
import "../../components"

FocusScope {
    id: root
    objectName: "NierDashboard"
    property var navigation: null
    property int category: 0
    property int selectedIndex: 0
    property real reveal: 1
    property Item previousFocusItem: null
    readonly property bool motionAllowed: !Theme.reducedMotion && !screenshotMode
    readonly property var categories: ["WORKSPACE", "LIBRARY", "SYSTEM"]
    readonly property var groups: [["create", "editor", "tools"], ["outputs", "liveries", "community"], ["settings", "help", "support", "update", "credits"]]
    readonly property var entries: {
        var result = []
        if (navigation) for (var i = 0; i < groups[category].length; i++) {
            var page = groups[category][i]
            if (page === "credits") result.push({page: "credits", label: "Credits", icon: "heart"})
            for (var j = 0; j < navigation.navItems.length; j++) if (navigation.navItems[j].page === page) result.push(navigation.navItems[j])
        }
        return result
    }
    readonly property var selection: entries[selectedIndex] || entries[0] || ({ label: "", page: "", icon: "" })
    readonly property var names: ({create:"VINYL GENERATION", editor:"VINYL EDITOR", tools:"IMAGE TOOLS", outputs:"VINYL ARCHIVE", liveries:"LIVERY WORKSHOP", community:"COMMUNITY HUB", settings:"SYSTEM CONFIGURATION", help:"REFERENCE MANUAL", support:"SUPPORT KFPS", update:"SOFTWARE UPDATE", credits:"ACKNOWLEDGEMENTS"})
    parent: navigation ? navigation.parent : null
    anchors.fill: parent
    z: 30
    visible: false
    enabled: visible
    clip: true
    function open() {
        if (visible) return
        if (Window.window) previousFocusItem = Window.window.activeFocusItem
        visible = true; reveal = motionAllowed ? 0 : 1
        forceActiveFocus()
        if (motionAllowed) entrance.restart()
    }
    function close() {
        if (!visible || !navigation || !navigation.dashboardWorkspaceEntered) return
        entrance.stop(); reveal = 1; visible = false; focus = false
        if (previousFocusItem && previousFocusItem.visible && previousFocusItem.enabled) previousFocusItem.forceActiveFocus()
        previousFocusItem = null
    }
    function choose(page) {
        if (!visible || !page || !navigation) return
        navigation.dashboardWorkspaceEntered = true
        navigation.route(page)
        close()
    }
    function setCategory(index) { category = (index + root.categories.length) % root.categories.length; selectedIndex = 0 }
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Left) setCategory(category - 1)
        else if (event.key === Qt.Key_Right) setCategory(category + 1)
        else if (event.key === Qt.Key_Down) selectedIndex = (selectedIndex + 1) % entries.length
        else if (event.key === Qt.Key_Up) selectedIndex = (selectedIndex + entries.length - 1) % entries.length
        else if (event.key === Qt.Key_Home) selectedIndex = 0
        else if (event.key === Qt.Key_End) selectedIndex = entries.length - 1
        else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) choose(selection.page)
        else if (event.key === Qt.Key_Escape) close()
        else return
        event.accepted = true
    }
    NumberAnimation { id: entrance; target: root; property: "reveal"; to: 1; duration: 360; easing.type: Easing.OutCubic }
    onMotionAllowedChanged: { if (!motionAllowed) { entrance.stop(); reveal = 1 } }
    NierBackdrop { anchors.fill: parent }
    Item {
        id: content
        anchors.fill: parent
        anchors.leftMargin: Theme.px(44); anchors.rightMargin: Theme.px(44)
        anchors.topMargin: Theme.px(28); anchors.bottomMargin: Theme.px(48)
        opacity: root.reveal
        Text { id: heading; text: "KFPS"; color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.px(44) }
        Text { anchors.left: heading.right; anchors.leftMargin: 18; anchors.baseline: heading.baseline; text: "FORZA PAINTER SUITE"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: Theme.px(14) }
        Row {
            id: categories
            y: Theme.px(78); width: parent.width; spacing: Theme.px(14)
            Repeater {
                model: root.categories
                delegate: AbstractButton {
                    id: categoryButton
                    required property string modelData
                    required property int index
                    objectName: "NierCategory:" + index
                    width: (categories.width - 2 * categories.spacing) / 3; height: Theme.px(44)
                    hoverEnabled: true; focusPolicy: Qt.StrongFocus
                    Accessible.name: modelData
                    onClicked: root.setCategory(index)
                    background: Rectangle { color: root.category === categoryButton.index ? Theme.text : categoryButton.hovered ? Theme.hover : Theme.surfaceSoft; border.width: categoryButton.visualFocus ? 2 : 1; border.color: Theme.border }
                    contentItem: Text { text: categoryButton.modelData; color: root.category === categoryButton.index ? Theme.primaryText : Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.px(18); verticalAlignment: Text.AlignVCenter; leftPadding: Theme.px(18) }
                }
            }
        }
        Rectangle { x: 0; y: categories.y + categories.height + 12; width: parent.width; height: 1; color: Theme.border }
        Rectangle { x: 0; y: categories.y + categories.height + 17; width: parent.width; height: 2; color: Theme.border }
        Item {
            id: body
            x: 0; y: categories.y + categories.height + Theme.px(52)
            width: parent.width; height: Math.max(0, parent.height - y - Theme.px(48))
            Column {
                id: list
                width: Math.min(Theme.px(330), body.width * 0.38)
                spacing: Theme.px(10)
                Repeater {
                    model: root.entries
                    delegate: AbstractButton {
                        id: entry
                        required property var modelData
                        required property int index
                        objectName: "NierDashboardRoute:" + modelData.page
                        width: list.width; height: Math.min(Theme.px(48), Math.max(Theme.px(34), (body.height - (root.entries.length - 1) * list.spacing) / root.entries.length))
                        x: (1 - root.reveal) * -24
                        hoverEnabled: true; focusPolicy: Qt.StrongFocus
                        Accessible.name: modelData.label
                        onHoveredChanged: { if (hovered) root.selectedIndex = index }
                        onActiveFocusChanged: { if (activeFocus) root.selectedIndex = index }
                        onClicked: root.choose(modelData.page)
                        background: Rectangle { color: root.selectedIndex === entry.index ? Theme.text : Theme.surfaceSoft; border.color: Theme.border; border.width: entry.visualFocus ? 2 : 1 }
                        contentItem: Row {
                            spacing: Theme.px(14); leftPadding: Theme.px(14)
                            Rectangle { width: Theme.px(10); height: width; color: root.selectedIndex === entry.index ? Theme.primaryText : Theme.text; anchors.verticalCenter: parent.verticalCenter }
                            Text { text: entry.modelData.label; color: root.selectedIndex === entry.index ? Theme.primaryText : Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.px(21); anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                }
            }
            Rectangle { x: list.width + Theme.px(24); width: 1; height: parent.height; color: Theme.border }
            Item {
                id: detail
                x: list.width + Theme.px(58); width: Math.max(0, parent.width - x); height: parent.height
                Rectangle { width: parent.width; height: Theme.px(34); color: Theme.text }
                Text { x: 12; y: Theme.px(7); text: "KFPS / " + root.categories[root.category]; color: Theme.primaryText; font.family: Theme.fontFamily; font.pixelSize: Theme.px(14) }
                Text { id: detailTitle; y: Theme.px(66); width: parent.width; text: root.names[root.selection.page] || ""; wrapMode: Text.WordWrap; color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.px(28) }
                Canvas {
                    id: insignia
                    y: detailTitle.y + detailTitle.height + Theme.px(28)
                    width: Theme.px(136); height: Math.min(width, Math.max(0, detail.height - y - 70))
                    onWidthChanged: requestPaint()
                    onHeightChanged: requestPaint()
                    onPaint: {
                        var c = getContext("2d")
                        c.clearRect(0, 0, width, height)
                        if (height < 70) return
                        c.strokeStyle = Theme.text; c.fillStyle = Theme.text; c.lineWidth = 1.5
                        var cx = width / 2, cy = height / 2, size = Math.min(width, height) * 0.43
                        for (var i = 0; i < 3; i++) {
                            var r = size * (1 - i * 0.24)
                            c.beginPath(); c.moveTo(cx, cy - r); c.lineTo(cx + r, cy); c.lineTo(cx, cy + r); c.lineTo(cx - r, cy); c.closePath(); c.stroke()
                        }
                        c.beginPath(); c.moveTo(cx, cy - size); c.lineTo(cx, cy + size); c.moveTo(cx - size, cy); c.lineTo(cx + size, cy); c.stroke()
                        c.fillRect(cx - 4, cy - 4, 8, 8)
                    }
                }
                Rectangle { y: Math.max(Theme.px(220), parent.height - 52); width: parent.width; height: 1; color: Theme.border }
                Text { y: Math.max(Theme.px(230), parent.height - 42); text: "STATUS: READY"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: Theme.px(12) }
            }
        }
        Text { anchors.left: parent.left; anchors.bottom: parent.bottom; text: "SYSTEM / " + root.selection.label.toUpperCase(); color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.px(13) }
        Button {
            id: resume
            objectName: "NierResume"
            anchors.right: parent.right; anchors.bottom: parent.bottom
            visible: root.navigation && root.navigation.dashboardWorkspaceEntered
            text: "Return"; width: Theme.px(110); height: Theme.px(32)
            onClicked: root.close()
            background: Rectangle { color: resume.hovered ? Theme.hover : Theme.surfaceSoft; border.color: Theme.border }
            contentItem: Text { text: resume.text; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.px(14); horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        }
    }
}
