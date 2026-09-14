import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

ColumnLayout {
    id: root
    required property var tagService
    property var scrollContainer: null
    property var selectedTags: []
    readonly property string text: selectedTags.join(", ")
    property string errorText: ""
    property int highlightedChoice: -1
    readonly property var choices: buildChoices()
    spacing: Theme.px(6)

    function contains(tag) {
        var key = tag.toLowerCase()
        return selectedTags.some(function(value) { return value.toLowerCase() === key })
    }

    function reset(value) {
        options.close()
        search.text = ""
        errorText = ""
        selectedTags = String(value || "").split(",").map(function(tag) { return tag.trim() })
            .filter(function(tag, index, all) {
                return tag.length > 0 && all.map(function(t) { return t.toLowerCase() }).indexOf(tag.toLowerCase()) === index
            })
    }

    function add(value) {
        var result = tagService.prepareTags(selectedTags, value)
        errorText = result.error
        if (errorText.length > 0)
            return false
        selectedTags = result.tags
        search.text = ""
        return true
    }

    function commitPending() {
        if (search.inputMethodComposing)
            Qt.inputMethod.commit()
        var valid = add(search.text)
        if (!valid)
            search.forceActiveFocus()
        return valid
    }

    function remove(tag) {
        selectedTags = selectedTags.filter(function(value) { return value.toLowerCase() !== tag.toLowerCase() })
        errorText = ""
    }

    function buildChoices() {
        var query = search.text.trim().toLowerCase()
        var bank = tagService.suggestedTags
        var rows = bank.filter(function(tag) { return tag.indexOf(query) !== -1 })
            .map(function(tag) { return {tag: tag, custom: false} })
        if (query.length > 0 && bank.indexOf(query) === -1 && !contains(query))
            rows.push({tag: search.text.trim(), custom: true})
        return rows
    }

    function choose(row) {
        add(row.tag)
        search.forceActiveFocus()
    }

    onVisibleChanged: if (!visible) options.close()
    onChoicesChanged: highlightedChoice = -1
    onHeightChanged: if (options && options.visible) repositionTimer.restart()
    onWidthChanged: if (options && options.visible) repositionTimer.restart()

    Timer {
        id: repositionTimer
        interval: 0
        onTriggered: options.reposition()
    }

    Connections {
        target: root.scrollContainer
        function onContentYChanged() { if (options.visible) options.reposition() }
    }

    Flow {
        id: chips
        Layout.fillWidth: true
        visible: root.selectedTags.length > 0
        spacing: Theme.px(6)
        Repeater {
            model: root.selectedTags
            delegate: Rectangle {
                id: chip
                required property string modelData
                objectName: root.objectName + ":chip:" + modelData
                width: Math.min((chips.width - chips.spacing) / 2, label.implicitWidth + removeButton.width + Theme.px(12))
                height: Theme.px(28)
                radius: Theme.corner(Theme.px(4))
                color: Theme.surfaceRaised
                border.color: Theme.borderStrong
                HoverHandler { id: chipHover }
                KfpsToolTip { visible: chipHover.hovered && label.truncated; text: chip.modelData }
                Text {
                    id: label
                    anchors.left: parent.left
                    anchors.leftMargin: Theme.px(9)
                    anchors.right: removeButton.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: chip.modelData
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(11)
                    elide: Text.ElideRight
                }
                ToolButton {
                    id: removeButton
                    objectName: root.objectName + ":remove:" + chip.modelData
                    anchors.right: parent.right
                    width: Theme.px(28)
                    height: parent.height
                    text: "\u00d7"
                    Accessible.name: "Remove tag " + chip.modelData
                    hoverEnabled: true
                    contentItem: Text {
                        text: removeButton.text
                        color: Theme.text
                        font.family: "Segoe UI"
                        font.pixelSize: Theme.px(17)
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        radius: Theme.corner(Theme.px(4))
                        color: removeButton.hovered || removeButton.activeFocus ? Theme.fieldHoverSurface : "transparent"
                        border.width: removeButton.activeFocus ? Theme.px(1) : 0
                        border.color: Theme.focusColor
                    }
                    KfpsToolTip { visible: removeButton.hovered; text: removeButton.Accessible.name }
                    onClicked: root.remove(chip.modelData)
                }
            }
        }
    }

    KfpsTextField {
        id: search
        objectName: root.objectName + ":search"
        Layout.fillWidth: true
        placeholderText: "Search or add a tag"
        toolTipText: "Choose tags or type your own and press Enter. Up to 10 tags, 24 characters each."
        Accessible.name: "Search or add tags"
        Accessible.description: toolTipText
        rightPadding: Theme.px(34)
        onActiveFocusChanged: {
            if (activeFocus && root.visible) options.open()
            else options.close()
        }
        onTextEdited: options.open()
        TapHandler { onTapped: options.open() }
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
            if (inputMethodComposing)
                return
            if (event.key === Qt.Key_Down || event.key === Qt.Key_Up) {
                options.open()
                var step = event.key === Qt.Key_Down ? 1 : -1
                root.highlightedChoice = Math.max(0, Math.min(list.count - 1, root.highlightedChoice + step))
                list.positionViewAtIndex(root.highlightedChoice, ListView.Contain)
                event.accepted = true
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                if (options.visible && root.highlightedChoice >= 0)
                    root.choose(root.choices[root.highlightedChoice])
                else
                    root.commitPending()
                event.accepted = true
            } else if (event.key === Qt.Key_Escape && options.visible) {
                options.close()
                event.accepted = true
            } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
                options.close()
            }
        }
        ToolButton {
            id: expand
            objectName: root.objectName + ":expand"
            anchors.right: parent.right
            width: Theme.px(32)
            height: parent.height
            focusPolicy: Qt.NoFocus
            Accessible.name: "Show tag bank"
            contentItem: Icon {
                name: "chevron-right"
                rotation: options.visible ? -90 : 90
                iconSize: Theme.px(12)
                colorize: true
                tint: Theme.muted
            }
            background: Item {}
            onClicked: {
                if (options.visible) options.close()
                else { search.forceActiveFocus(); options.open() }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Text {
            objectName: root.objectName + ":error"
            Layout.fillWidth: true
            text: root.errorText
            textFormat: Text.PlainText
            color: Theme.danger
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(10)
            wrapMode: Text.Wrap
            Accessible.role: Accessible.AlertMessage
            Accessible.name: text
        }
        Text {
            Layout.alignment: Qt.AlignTop
            text: root.selectedTags.length + " / " + root.tagService.maximumTags
            color: Theme.subtle
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(10)
        }
    }

    Popup {
        id: options
        objectName: root.objectName + ":popup"
        parent: search
        width: search.width
        padding: Theme.px(4)
        focus: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        property real fieldY: 0
        function reposition() {
            if (Overlay.overlay)
                fieldY = search.mapToItem(Overlay.overlay, 0, 0).y
        }
        onAboutToShow: reposition()
        onOpened: repositionTimer.restart()
        readonly property real below: Overlay.overlay ? Overlay.overlay.height - fieldY - search.height - Theme.px(12) : Theme.px(260)
        readonly property real above: Math.max(0, fieldY - Theme.px(12))
        readonly property real desiredHeight: Math.min(Theme.px(260), list.contentHeight + padding * 2)
        readonly property bool opensAbove: below < desiredHeight && above > below
        height: Math.max(0, Math.min(desiredHeight, opensAbove ? above : below))
        y: opensAbove ? -height - Theme.px(4) : search.height + Theme.px(4)
        background: KfpsPopupSurface {
            surfaceColor: Qt.rgba(Theme.surfaceRaised.r, Theme.surfaceRaised.g, Theme.surfaceRaised.b, 1)
            outlineColor: Theme.borderStrong
            cornerRadius: Theme.px(6)
        }
        contentItem: ListView {
            id: list
            objectName: root.objectName + ":choices"
            clip: true
            model: root.choices
            currentIndex: -1
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: KfpsScrollBar {}
            delegate: ItemDelegate {
                id: choice
                required property var modelData
                required property int index
                objectName: root.objectName + ":choice:" + modelData.tag
                width: list.width
                height: Theme.px(34)
                enabled: root.contains(modelData.tag) || root.selectedTags.length < root.tagService.maximumTags
                focusPolicy: Qt.NoFocus
                hoverEnabled: true
                highlighted: root.highlightedChoice === index
                Accessible.name: root.contains(modelData.tag) ? "Selected tag: " + modelData.tag : "Add tag " + modelData.tag
                Accessible.role: Accessible.Button
                contentItem: RowLayout {
                    spacing: Theme.px(8)
                    Icon {
                        name: "check"
                        iconSize: Theme.px(13)
                        opacity: root.contains(choice.modelData.tag) ? 1 : 0
                        colorize: true
                        tint: Theme.primaryBright
                    }
                    Text {
                        Layout.fillWidth: true
                        text: choice.modelData.custom ? 'Add "' + choice.modelData.tag + '"' : choice.modelData.tag
                        textFormat: Text.PlainText
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(11)
                        color: choice.enabled ? Theme.text : Theme.subtle
                        elide: Text.ElideRight
                    }
                }
                background: Rectangle {
                    radius: Theme.corner(Theme.px(4))
                    color: choice.highlighted || choice.hovered ? Theme.fieldHoverSurface : "transparent"
                }
                onClicked: root.choose(modelData)
            }
        }
    }
}
