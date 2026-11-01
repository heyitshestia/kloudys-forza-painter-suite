import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Window 6.7
import Kfps.Theme 1.0
import "../../components"

FocusScope {
    id: root
    objectName: "ApexDashboard"
    property var navigation: null
    property int category: 0
    property int selectedIndex: 0
    property real reveal: 1
    property Item previousFocusItem: null
    readonly property bool compact: Theme.logical(height) < 710
    readonly property bool motionAllowed: visible && !Theme.reducedMotion && !screenshotMode
    readonly property var categories: ["CREATE", "LIBRARY", "SYSTEM"]
    readonly property var categoryIcons: ["generate", "json", "settings"]
    readonly property var groups: [["create", "editor", "tools"], ["outputs", "liveries", "community"], ["settings", "help", "support", "update", "credits"]]
    readonly property var names: ({create: "VINYL GENERATOR", editor: "VINYL EDITOR", tools: "IMAGE TOOLS", outputs: "OUTPUTS", liveries: "LIVERIES", community: "COMMUNITY", settings: "SETTINGS", help: "HELP", support: "SUPPORT", update: "UPDATE", credits: "CREDITS"})
    readonly property var entries: {
        var result = []
        if (navigation) for (var i = 0; i < groups[category].length; i++) {
            var page = groups[category][i]
            if (page === "credits") result.push({page: page, label: "Credits", icon: "heart"})
            else for (var j = 0; j < navigation.navItems.length; j++)
                if (navigation.navItems[j].page === page) result.push(navigation.navItems[j])
        }
        return result
    }
    readonly property var selection: entries[selectedIndex] || entries[0] || ({page: "", label: "", icon: ""})

    // This replaces the application body, never the draggable native title bar.
    parent: navigation ? navigation.parent : null
    anchors.fill: parent
    z: 30
    visible: false
    enabled: visible
    clip: true

    function open() {
        if (visible) return
        if (Window.window) previousFocusItem = Window.window.activeFocusItem
        visible = true
        forceActiveFocus()
        revealMenu()
    }
    function close() {
        if (!visible || !navigation || !navigation.dashboardWorkspaceEntered) return
        var focused = Window.window ? Window.window.activeFocusItem : null
        var restoreFocus = !focused
        for (var item = focused; item; item = item.parent) {
            if (item === root) { restoreFocus = true; break }
        }
        entrance.stop()
        reveal = 1
        visible = false
        focus = false
        if (restoreFocus && previousFocusItem && previousFocusItem.visible && previousFocusItem.enabled)
            previousFocusItem.forceActiveFocus()
        previousFocusItem = null
    }
    function choose(page) {
        if (!visible || !page || !navigation) return
        navigation.dashboardWorkspaceEntered = true
        navigation.route(page)
        close()
    }
    function revealMenu() {
        entrance.stop()
        reveal = motionAllowed ? 0 : 1
        if (motionAllowed) entrance.start()
    }
    function setCategory(index) {
        var next = (index + root.categories.length) % root.categories.length
        if (next === category) return
        category = next
        selectedIndex = 0
        revealMenu()
    }
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
    onMotionAllowedChanged: { if (!motionAllowed) { entrance.stop(); reveal = 1 } }
    NumberAnimation { id: entrance; target: root; property: "reveal"; to: 1; duration: 280; easing.type: Easing.OutCubic }

    Item {
        id: content
        anchors.fill: parent
        anchors.leftMargin: Theme.px(root.compact ? 32 : 64)
        anchors.rightMargin: anchors.leftMargin
        anchors.topMargin: Theme.px(root.compact ? 20 : 44)
        anchors.bottomMargin: Theme.px(24)
        Item {
            id: masthead
            width: parent.width
            height: Theme.px(root.compact ? 70 : 98)
            Text {
                id: brand
                text: "KFPS"
                color: Theme.primary
                font.family: Theme.displayFamily
                font.pixelSize: Theme.px(root.compact ? 52 : 68)
                font.italic: true
                font.bold: true
            }
            Text {
                anchors.left: brand.right
                anchors.leftMargin: Theme.px(20)
                anchors.baseline: brand.baseline
                text: "APEX VECTOR"
                color: Theme.text
                font.family: Theme.displayFamily
                font.pixelSize: Theme.px(18)
            }
            Text {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.topMargin: Theme.px(14)
                text: "FORZA PAINTER SUITE"
                color: Theme.subtle
                font.family: Theme.monoFamily
                font.pixelSize: Theme.px(11)
            }
        }
        Row {
            id: categories
            y: masthead.height
            width: parent.width * 0.69
            height: Theme.px(root.compact ? 96 : 132)
            spacing: Theme.px(12)
            Repeater {
                model: root.categories
                delegate: AbstractButton {
                    id: categoryButton
                    required property int index
                    required property string modelData
                    objectName: "ApexCategory:" + index
                    readonly property bool selected: root.category === index
                    width: (categories.width - 2 * categories.spacing) / 3
                    height: categories.height
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    Accessible.name: modelData
                    Accessible.role: Accessible.PageTab
                    Accessible.checked: selected
                    onClicked: root.setCategory(index)
                    background: Rectangle {
                        color: categoryButton.selected ? Theme.primary : categoryButton.hovered ? Theme.ghostHoverSurface : Theme.navHoverSurface
                        border.width: categoryButton.visualFocus ? Theme.px(3) : 0
                        border.color: Theme.focusColor
                        Behavior on color { enabled: root.motionAllowed; ColorAnimation { duration: 110 } }
                    }
                    ApexIcon {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: Theme.px(root.compact ? 14 : 21)
                        width: Theme.px(root.compact ? 34 : 52)
                        height: width
                        name: root.categoryIcons[categoryButton.index]
                        inverted: categoryButton.selected
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: Theme.px(12)
                        text: categoryButton.modelData
                        color: categoryButton.selected ? "#ffffff" : Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.px(18)
                        font.bold: true
                    }
                    Text {
                        x: Theme.px(10); y: Theme.px(7)
                        text: "0" + (categoryButton.index + 1)
                        font.family: Theme.monoFamily; font.pixelSize: Theme.px(10)
                        color: categoryButton.selected ? "#ffffff" : Theme.subtle
                    }
                }
            }
        }
        Item {
            id: body
            x: 0
            y: categories.y + categories.height + Theme.px(root.compact ? 26 : 42)
            width: parent.width
            height: Math.max(0, parent.height - y - Theme.px(42))
            opacity: root.reveal
            transform: Translate { x: (1 - root.reveal) * Theme.px(22) }
            Column {
                id: list
                width: body.width * 0.50
                spacing: Theme.px(5)
                Repeater {
                    model: root.entries
                    delegate: AbstractButton {
                        id: entry
                        required property var modelData
                        required property int index
                        objectName: "ApexRoute:" + modelData.page
                        readonly property bool selected: root.selectedIndex === index
                        width: list.width
                        height: Math.min(Theme.px(root.compact ? 42 : 56), (body.height - 4 * list.spacing) / 5)
                        hoverEnabled: true
                        focusPolicy: Qt.StrongFocus
                        Accessible.name: root.names[modelData.page] || modelData.label
                        onHoveredChanged: { if (hovered) root.selectedIndex = index }
                        onActiveFocusChanged: { if (activeFocus) root.selectedIndex = index }
                        onClicked: root.choose(modelData.page)
                        background: Rectangle {
                            color: entry.selected ? Theme.primary : Theme.withAlpha(Theme.surfaceStrong, 0.85)
                            border.width: entry.visualFocus ? Theme.px(2) : 0
                            border.color: Theme.focusColor
                            Behavior on color { enabled: root.motionAllowed; ColorAnimation { duration: 110 } }
                        }
                        Text {
                            id: number
                            x: Theme.px(14); anchors.verticalCenter: parent.verticalCenter
                            text: "0" + (entry.index + 1)
                            color: entry.selected ? "#ffffff" : Theme.subtle
                            font.family: Theme.monoFamily; font.pixelSize: Theme.px(11)
                        }
                        Text {
                            anchors.left: number.right; anchors.leftMargin: Theme.px(18)
                            anchors.right: parent.right; anchors.rightMargin: Theme.px(38)
                            anchors.verticalCenter: parent.verticalCenter
                            text: root.names[entry.modelData.page] || entry.modelData.label.toUpperCase()
                            color: entry.selected ? "#ffffff" : Theme.text
                            font.family: Theme.displayFamily; font.pixelSize: Theme.px(root.compact ? 18 : 23)
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        ApexIcon {
                            anchors.right: parent.right; anchors.rightMargin: Theme.px(12)
                            anchors.verticalCenter: parent.verticalCenter
                            width: Theme.px(18); height: width
                            name: "chevron-right"
                            inverted: entry.selected
                        }
                    }
                }
            }
            Item {
                id: signature
                x: list.width + Theme.px(44)
                width: body.width - x
                height: body.height
                ApexInsignia {
                    id: insignia
                    y: Theme.px(4)
                    width: Math.min(Theme.px(240), signature.width * 0.75)
                    height: Math.min(width * 0.76, signature.height - Theme.px(90))
                    ink: Theme.primary
                    spread: (1 - root.reveal) * Theme.px(14)
                }
                Text {
                    y: insignia.y + insignia.height + Theme.px(14)
                    width: parent.width
                    text: root.names[root.selection.page] || ""
                    color: Theme.text
                    font.family: Theme.displayFamily; font.pixelSize: Theme.px(root.compact ? 22 : 32)
                    font.bold: true
                    wrapMode: Text.WordWrap
                }
            }
        }
        Rectangle { anchors.bottom: parent.bottom; anchors.bottomMargin: Theme.px(38); width: parent.width; height: Theme.px(1); color: Theme.border }
        Text {
            anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.bottomMargin: Theme.px(6)
            text: "KFPS / " + root.categories[root.category]
            font.family: Theme.monoFamily; font.pixelSize: Theme.px(11); color: Theme.subtle
        }
        AbstractButton {
            id: resume
            objectName: "ApexResume"
            anchors.right: parent.right; anchors.bottom: parent.bottom
            width: Theme.px(120); height: Theme.px(32)
            visible: root.navigation && root.navigation.dashboardWorkspaceEntered
            hoverEnabled: true; focusPolicy: Qt.StrongFocus
            Accessible.name: "Return to workspace"
            onClicked: root.close()
            background: Rectangle { color: resume.hovered ? Theme.ghostHoverSurface : "transparent"; border.width: resume.visualFocus ? 2 : 0; border.color: Theme.focusColor }
            contentItem: Text { text: "RETURN"; color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.px(15); horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        }
    }
}
