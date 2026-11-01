import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

FastListView {
    id: list
    property string selectedPath: ""
    property bool filtered: false
    signal packageSelected(string path)
    signal packageOpened(string path)
    spacing: Theme.px(3)
    clip: true
    reuseItems: true
    keyNavigationEnabled: false

    function navigate(event, fromIndex) {
        var next = fromIndex
        switch (event.key) {
        case Qt.Key_Up: next -= 1; break
        case Qt.Key_Down: next += 1; break
        case Qt.Key_Home: next = 0; break
        case Qt.Key_End: next = count - 1; break
        default: return
        }
        event.accepted = true
        if (count === 0) return
        currentIndex = Math.max(0, Math.min(count - 1, next))
        positionViewAtIndex(currentIndex, ListView.Contain)
        if (currentItem) {
            currentItem.forceActiveFocus(Qt.TabFocusReason)
            packageSelected(currentItem.path)
        }
    }
    Keys.onPressed: event => navigate(event, currentIndex)

    delegate: AbstractButton {
        id: row
        objectName: "liveryPackageRow:" + path
        required property int index
        required property string path
        required property string title
        required property string modelCode
        required property int carId
        required property int placementCount
        property bool pooled: false
        readonly property bool selected: path === list.selectedPath
        readonly property color foreground: selected && Theme.classicMode ? Theme.primaryText : Theme.text
        width: Math.max(0, list.width - packageScrollBar.implicitWidth - Theme.px(5))
        height: Theme.px(64)
        leftPadding: Theme.px(10)
        rightPadding: Theme.px(10)
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: title
        Accessible.description: modelCode + ", car " + carId + ", " + placementCount + " placements"
        ListView.onPooled: pooled = true
        ListView.onReused: pooled = false

        background: Rectangle {
            color: row.selected ? Theme.rowSelectedSurface : (row.hovered ? Theme.rowHover : Theme.surface)
            radius: Theme.framedRadius(Theme.px(5))
            border.width: row.selected || row.activeFocus ? Math.max(1, Theme.px(1)) : 0
            border.color: row.activeFocus ? Theme.focusColor : Theme.primary
        }
        contentItem: RowLayout {
            spacing: Theme.px(10)
            Icon { name: "monitor"; iconSize: Theme.px(20); tint: row.foreground }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: Theme.px(3)
                Text {
                    Layout.fillWidth: true
                    text: row.title
                    textFormat: Text.PlainText
                    color: row.foreground
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(12)
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    text: row.modelCode + " | Car " + row.carId + " | " + row.placementCount + " placements"
                    textFormat: Text.PlainText
                    color: row.selected && Theme.classicMode ? Theme.primaryText : Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(11)
                    elide: Text.ElideRight
                }
            }
        }
        KfpsToolTip {
            id: packageTip
            visible: row.hovered
            text: row.title + "\n" + row.modelCode + " | Car " + row.carId
            contentItem: Text {
                width: packageTip.preferredTextWidth
                text: packageTip.text
                textFormat: Text.PlainText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(10.8)
                wrapMode: Text.Wrap
            }
        }
        onClicked: {
            list.currentIndex = index
            list.packageSelected(path)
        }
        onDoubleClicked: {
            const sourcePath = path
            Qt.callLater(function() {
                if (row.visible && !row.pooled && row.path === sourcePath)
                    list.packageOpened(sourcePath)
            })
        }
        Keys.onReturnPressed: list.packageOpened(path)
        Keys.onEnterPressed: list.packageOpened(path)
        Keys.onPressed: event => list.navigate(event, index)
    }

    EmptyState {
        anchors.centerIn: parent
        width: Math.min(parent.width - Theme.px(30), Theme.px(360))
        visible: list.count === 0
        iconName: "folder"
        title: list.filtered ? "No matching packages" : "No saved packages"
        message: ""
    }
    ScrollBar.vertical: KfpsScrollBar {
        id: packageScrollBar
        policy: ScrollBar.AsNeeded
    }
}
