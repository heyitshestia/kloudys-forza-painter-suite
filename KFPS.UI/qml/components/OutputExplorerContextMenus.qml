pragma ComponentBehavior: Bound

import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "OutputExplorerContextMenus"

    required property var moveFolderModel
    required property string currentFolderPath
    property string contextPath: ""
    property string contextName: ""
    property bool contextIsFolder: false
    property bool contextIsSource: false
    property int contextSelectionCount: 0
    property bool contextSelectionCanMove: false
    property int contextClipboardCount: 0
    property bool contextCanPaste: false
    readonly property bool opened: contextMenu.opened || moveFolderMenu.opened
    readonly property int selectionCount: contextSelectionCount
    readonly property bool selectionCanMove: contextSelectionCanMove

    signal openFolderRequested(string path)
    signal cutRequested()
    signal copyRequested()
    signal pasteRequested(string destination)
    signal moveRequested(string destination)
    signal nameActionRequested(string mode, string target, string parentPath, string currentName)
    signal deleteRequested()

    function positionContextMenu(sceneX, sceneY) {
        var overlayPoint = contextMenu.parent.mapFromItem(root, sceneX, sceneY)
        contextMenu.x = Math.max(
                    Theme.px(8),
                    Math.min(overlayPoint.x, contextMenu.parent.width - contextMenu.width - Theme.px(8)))
        contextMenu.y = Math.max(
                    Theme.px(8),
                    Math.min(overlayPoint.y, contextMenu.parent.height - contextMenu.height - Theme.px(8)))
    }

    function openFor(path, name, isFolder, entryKind, sceneX, sceneY,
                     selectionCount, selectionCanMove, clipboardCount, canPaste) {
        contextPath = String(path || "")
        contextName = String(name || "")
        contextIsFolder = Boolean(isFolder)
        contextIsSource = String(entryKind || "") === "source"
        contextSelectionCount = Number(selectionCount || 0)
        contextSelectionCanMove = Boolean(selectionCanMove)
        contextClipboardCount = Number(clipboardCount || 0)
        contextCanPaste = Boolean(canPaste)
        contextMenu.open()
        positionContextMenu(sceneX, sceneY)
        Qt.callLater(function() { root.positionContextMenu(sceneX, sceneY) })
    }

    function closeMoveFolderMenu() {
        moveFolderMenu.close()
    }

    Popup {
        id: contextMenu
        objectName: "OutputExplorerContextMenu"
        parent: Overlay.overlay
        modal: false
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        width: Theme.px(220)
        height: contextColumn.implicitHeight + topPadding + bottomPadding
        padding: Theme.px(8)
        z: 80

        background: KfpsPopupSurface {
            surfaceColor: Theme.surfaceRaised
            outlineColor: Theme.borderStrong
            cornerRadius: Theme.px(6)
        }

        contentItem: ColumnLayout {
            id: contextColumn
            spacing: Theme.px(4)

            GhostButton {
                Layout.fillWidth: true
                visible: root.contextIsFolder
                text: "Open folder"
                iconName: "folder"
                dense: true
                toolTipText: "Open this folder in the Outputs browser."
                onClicked: {
                    contextMenu.close()
                    root.openFolderRequested(root.contextPath)
                }
            }

            GhostButton {
                Layout.fillWidth: true
                visible: root.contextPath.length > 0 && !root.contextIsSource
                         && root.contextSelectionCount > 0
                text: root.contextSelectionCount > 1
                      ? "Cut " + root.contextSelectionCount + " items" : "Cut"
                dense: true
                toolTipText: "Prepare the selected item or items to be moved when you paste them."
                onClicked: {
                    contextMenu.close()
                    root.cutRequested()
                }
            }

            GhostButton {
                Layout.fillWidth: true
                visible: root.contextPath.length > 0 && !root.contextIsSource
                         && root.contextSelectionCount > 0
                text: root.contextSelectionCount > 1
                      ? "Copy " + root.contextSelectionCount + " items" : "Copy"
                dense: true
                toolTipText: "Copy the selected item or items to both KFPS and the Windows clipboard."
                onClicked: {
                    contextMenu.close()
                    root.copyRequested()
                }
            }

            GhostButton {
                id: moveToFolderButton
                Layout.fillWidth: true
                visible: root.contextPath.length > 0 && !root.contextIsFolder
                         && root.contextSelectionCanMove
                text: root.contextSelectionCount > 1
                      ? "Move " + root.contextSelectionCount + " JSONs to folder"
                      : "Move to folder"
                showArrow: true
                dense: true
                toolTipText: "Move the selected JSON or JSONs directly into another KFPS Outputs folder."
                onClicked: {
                    var anchorPoint = moveFolderMenu.parent.mapFromItem(
                                moveToFolderButton, moveToFolderButton.width - Theme.px(4), 0)
                    var preferredX = anchorPoint.x
                    moveFolderMenu.x = preferredX + moveFolderMenu.width <= moveFolderMenu.parent.width - Theme.px(8)
                                       ? preferredX
                                       : Math.max(Theme.px(8), contextMenu.x - moveFolderMenu.width + Theme.px(4))
                    moveFolderMenu.y = Math.max(
                                Theme.px(8),
                                Math.min(anchorPoint.y,
                                         moveFolderMenu.parent.height - moveFolderMenu.height - Theme.px(8)))
                    contextMenu.close()
                    moveFolderMenu.open()
                }
            }

            GhostButton {
                Layout.fillWidth: true
                visible: root.contextIsFolder || root.currentFolderPath.length > 0
                text: root.contextClipboardCount > 0
                      ? "Paste " + root.contextClipboardCount + " item(s)" : "Paste"
                dense: true
                enabled: root.contextCanPaste
                toolTipText: root.contextIsFolder
                             ? "Paste into the folder you right-clicked."
                             : "Paste into the folder currently shown."
                onClicked: {
                    var destination = root.contextIsFolder
                                      ? root.contextPath : root.currentFolderPath
                    contextMenu.close()
                    root.pasteRequested(destination)
                }
            }

            GhostButton {
                Layout.fillWidth: true
                visible: root.contextIsFolder || root.currentFolderPath.length > 0
                text: root.contextIsFolder ? "New folder inside" : "New folder"
                iconName: "folder"
                dense: true
                toolTipText: root.contextIsFolder
                             ? "Create a new folder inside the folder you right-clicked."
                             : "Create a new folder in the location currently shown."
                onClicked: {
                    var destination = root.contextIsFolder
                                      ? root.contextPath : root.currentFolderPath
                    contextMenu.close()
                    root.nameActionRequested("new-folder", "", destination, "")
                }
            }

            GhostButton {
                Layout.fillWidth: true
                visible: root.contextIsFolder && !root.contextIsSource
                         && root.contextSelectionCount === 1
                text: "Rename folder"
                dense: true
                toolTipText: "Rename this folder without changing its contents."
                onClicked: {
                    contextMenu.close()
                    root.nameActionRequested("rename-folder", root.contextPath, "", root.contextName)
                }
            }

            GhostButton {
                Layout.fillWidth: true
                visible: root.contextPath.length > 0 && !root.contextIsFolder
                         && root.contextSelectionCount === 1
                text: "Rename JSON"
                dense: true
                toolTipText: "Rename this JSON file without changing its contents."
                onClicked: {
                    contextMenu.close()
                    root.nameActionRequested("rename-json", root.contextPath, "", root.contextName)
                }
            }

            GhostButton {
                Layout.fillWidth: true
                visible: root.contextPath.length > 0 && !root.contextIsSource
                         && root.contextSelectionCount > 0
                text: root.contextSelectionCount > 1
                      ? "Delete " + root.contextSelectionCount + " items" : "Delete"
                labelColor: Theme.danger
                dense: true
                toolTipText: "Permanently delete the selected item or items from their output folders."
                onClicked: {
                    contextMenu.close()
                    root.deleteRequested()
                }
            }
        }
    }

    Popup {
        id: moveFolderMenu
        objectName: "OutputExplorerMoveFolderMenu"
        parent: Overlay.overlay
        modal: false
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        width: Theme.px(330)
        height: Math.min(
                    root.height - Theme.px(16),
                    Theme.px(58) + Math.max(1, moveFolderList.count) * Theme.px(36))
        padding: Theme.px(8)
        z: 82

        background: KfpsPopupSurface {
            surfaceColor: Theme.surfaceRaised
            outlineColor: Theme.borderStrong
            cornerRadius: Theme.px(6)
        }

        contentItem: ColumnLayout {
            spacing: Theme.px(5)

            Text {
                Layout.fillWidth: true
                text: root.contextSelectionCount > 1
                      ? "Move selected JSONs to" : "Move selected JSON to"
                color: Theme.primaryBright
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(10.4)
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(1, Theme.px(1))
                color: Theme.borderSoft
            }

            FastListView {
                id: moveFolderList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: Theme.px(2)
                model: root.moveFolderModel

                delegate: GhostButton {
                    id: destinationRow
                    required property string displayName
                    required property string path
                    required property int depth
                    width: ListView.view.width
                    height: Theme.px(34)
                    dense: true
                    text: displayName
                    toolTipText: path
                    onClicked: {
                        root.closeMoveFolderMenu()
                        root.moveRequested(destinationRow.path)
                    }
                }

                ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
            }
        }
    }
}
