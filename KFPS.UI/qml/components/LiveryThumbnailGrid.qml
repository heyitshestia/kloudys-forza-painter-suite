import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

GridView {
    id: grid
    objectName: "liveryThumbnailGrid"
    property string selectedPath: ""
    property bool loading: false
    property bool filtered: false
    signal liverySelected(string path)
    signal liveryOpened(string path)
    readonly property int columns: Math.max(1, Math.floor(width / Theme.px(260)))
    cellWidth: Math.floor(width / columns)
    cellHeight: (cellWidth - Theme.px(10)) * 376 / 670 + Theme.px(80)
    clip: true
    reuseItems: true
    cacheBuffer: cellHeight
    boundsBehavior: Flickable.StopAtBounds
    keyNavigationEnabled: false

    function navigate(event, fromIndex) {
        var next = fromIndex
        switch (event.key) {
        case Qt.Key_Left: next -= 1; break
        case Qt.Key_Right: next += 1; break
        case Qt.Key_Up: next -= columns; break
        case Qt.Key_Down: next += columns; break
        case Qt.Key_Home: next = 0; break
        case Qt.Key_End: next = count - 1; break
        default: return
        }
        event.accepted = true
        if (count === 0) return
        currentIndex = Math.max(0, Math.min(count - 1, next))
        positionViewAtIndex(currentIndex, GridView.Contain)
        if (currentItem) {
            currentItem.forceActiveFocus(Qt.TabFocusReason)
            liverySelected(currentItem.path)
        }
    }
    Keys.onPressed: event => navigate(event, currentIndex)

    delegate: AbstractButton {
        id: tile
        objectName: "liveryThumbnailTile:" + path
        required property int index
        required property string path
        required property string title
        required property string modelCode
        required property int carId
        required property int placementCount
        required property bool exportable
        required property string thumbnailUrl
        property bool pooled: false
        readonly property bool selected: path === grid.selectedPath
        width: grid.cellWidth - Theme.px(10)
        height: grid.cellHeight - Theme.px(10)
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: title + ", " + modelCode + ", car " + carId
        Accessible.description: placementCount + " placements, " + (exportable ? "export available" : "preview only")
        GridView.onPooled: pooled = true
        GridView.onReused: pooled = false
        onClicked: {
            grid.currentIndex = index
            grid.liverySelected(path)
        }
        onDoubleClicked: {
            // Finish Qt's double-click dispatch before hiding/recycling this button.
            const sourcePath = path
            Qt.callLater(function() {
                if (tile.visible && !tile.pooled && tile.path === sourcePath)
                    grid.liveryOpened(sourcePath)
            })
        }
        Keys.onReturnPressed: grid.liveryOpened(path)
        Keys.onEnterPressed: grid.liveryOpened(path)
        Keys.onPressed: event => grid.navigate(event, index)

        background: Rectangle {
            radius: Theme.framedRadius(Theme.px(6))
            color: tile.selected ? Theme.rowSelectedSurface : (tile.hovered ? Theme.rowHover : Theme.surface)
            border.width: tile.selected || tile.activeFocus ? Theme.px(2) : Math.max(1, Theme.px(1))
            border.color: tile.selected || tile.activeFocus ? Theme.primary : Theme.borderSoft
        }

        contentItem: Column {
            spacing: Theme.px(5)
            Item {
                width: parent.width
                height: width * 376 / 670
                Image {
                    id: thumbnail
                    objectName: "liveryThumbnailImage:" + tile.path
                    anchors.fill: parent
                    anchors.margins: Theme.px(2)
                    source: tile.pooled ? "" : tile.thumbnailUrl
                    sourceSize.width: 670
                    sourceSize.height: 376
                    asynchronous: true
                    cache: false
                    fillMode: Image.PreserveAspectFit
                }
                Column {
                    anchors.centerIn: parent
                    visible: thumbnail.status !== Image.Ready
                    spacing: Theme.px(6)
                    Icon {
                        anchors.horizontalCenter: parent.horizontalCenter
                        name: "images"
                        iconSize: Theme.px(28)
                    }
                    Text {
                        text: thumbnail.status === Image.Loading ? "Loading thumbnail" : "No thumbnail"
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(11)
                    }
                }
            }
            Text {
                x: Theme.px(9)
                width: parent.width - Theme.px(18)
                text: tile.title
                textFormat: Text.PlainText
                color: tile.selected && Theme.classicMode ? Theme.primaryText : Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(12)
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Text {
                x: Theme.px(9)
                width: parent.width - Theme.px(18)
                text: (tile.modelCode.length > 0 ? tile.modelCode + " | " : "") + "Car " + tile.carId
                textFormat: Text.PlainText
                color: tile.selected && Theme.classicMode ? Theme.primaryText : Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(10.5)
                elide: Text.ElideRight
            }
            Text {
                x: Theme.px(9)
                width: parent.width - Theme.px(18)
                text: tile.placementCount + " placements | " + (tile.exportable ? "Export available" : "Preview only")
                color: tile.selected && Theme.classicMode ? Theme.primaryText : (tile.exportable ? Theme.subtle : Theme.warning)
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(10)
                elide: Text.ElideRight
            }
        }
        KfpsToolTip {
            visible: tile.hovered
            text: tile.title + "\n" + (tile.modelCode.length > 0 ? tile.modelCode + " | " : "") + "Car " + tile.carId
        }
    }

    ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
    EmptyState {
        anchors.centerIn: parent
        width: Math.min(parent.width - Theme.px(30), Theme.px(400))
        visible: grid.count === 0
        iconName: "images"
        title: grid.loading ? "Scanning saves" : (grid.filtered ? "No matching liveries" : "No liveries scanned")
        message: ""
    }
}
