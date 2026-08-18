import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Dialogs 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    anchors.fill: parent
    clip: true

    property bool wide: Theme.logical(width) >= 1120
    property bool compactHeight: Theme.logical(height) < 720
    property int fm8CreatorConfirmStep: 1
    property string fm8PendingCreator: ""
    property string fm8PendingCreatorDisplay: ""
    property string fm8PendingCreatorDetail: ""
    property string infoCardName: ""
    property string infoCardDetail: ""
    property string infoCardFolder: ""
    property string infoCardPath: ""
    property string infoCardPreview: ""
    property string outputNameDialogMode: ""
    property string outputNameDialogTarget: ""
    property string outputNameDialogParent: ""
    readonly property bool headerAlignmentAvailable: root.wide
                                                     && importSetupCard.width > 0
                                                     && browseOutputsCard.width > 0
    readonly property real headerSourceCenterX: importSetupCard.x + importSetupCard.width / 2
    readonly property real headerPreviewCenterX: browseOutputsCard.x + browseOutputsCard.width / 2
    readonly property real headerBannerLeftX: importSetupCard.x
    readonly property real headerBannerRightX: browseOutputsCard.x + browseOutputsCard.width

    function openOutputContextMenu(path, name, isFolder, entryKind, sceneX, sceneY) {
        outputContextMenus.openFor(path, name, isFolder, entryKind, sceneX, sceneY)
    }

    function openOutputNameDialog(mode, target, parentPath, currentName) {
        root.outputNameDialogMode = mode
        root.outputNameDialogTarget = String(target || "")
        root.outputNameDialogParent = String(parentPath || jsonService.currentFolder)
        jsonService.clearManagementStatus()
        outputNameInput.text = mode === "new-folder" ? "" : String(currentName || "")
        outputNameDialog.open()
        Qt.callLater(function() {
            outputNameInput.forceActiveFocus()
            outputNameInput.selectAll()
        })
    }

    function submitOutputName() {
        var succeeded = false
        if (root.outputNameDialogMode === "new-folder")
            succeeded = jsonService.createFolderIn(root.outputNameDialogParent, outputNameInput.text)
        else
            succeeded = jsonService.renameEntry(root.outputNameDialogTarget, outputNameInput.text)
        if (succeeded)
            outputNameDialog.close()
    }

    Connections {
        target: cgroupLibraryService
        function onFm8CreatorPromptRequested() {
            root.fm8CreatorConfirmStep = 1
            root.fm8PendingCreator = ""
            root.fm8PendingCreatorDisplay = ""
            root.fm8PendingCreatorDetail = ""
            fm8CreatorDialog.open()
        }
    }

    TapHandler {
        acceptedButtons: Qt.LeftButton
        gesturePolicy: TapHandler.ReleaseWithinBounds
        grabPermissions: PointerHandler.ApprovesTakeOverByAnything
        onTapped: {
            jsonService.clearExplorerSelection()
            jsonService.clearSelection()
        }
    }

    GridLayout {
        anchors.fill: parent
        columns: root.wide ? 3 : 1
        columnSpacing: Theme.px(12)
        rowSpacing: Theme.px(12)

        HoverCard {
            id: importSetupCard
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.wide ? Theme.px(360) : -1
            Layout.minimumWidth: root.wide ? Theme.px(330) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)
            strong: true

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 7 : 9)

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(10)

                    Icon {
                        name: "json"
                        iconSize: Theme.px(31)
                        glow: true
                        Layout.alignment: Qt.AlignVCenter
                    }

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "1. Import setup"
                        subtitle: "Online edits the running game. Offline edits supported local save files."
                    }
                }

                ScrollView {
                    id: importSetupScroll
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                    ColumnLayout {
                        width: importSetupScroll.availableWidth
                        spacing: Theme.px(root.compactHeight ? 7 : 9)

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: Theme.px(9)
                            rowSpacing: Theme.px(6)

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: Theme.px(3)
                                Label { text: "Game target" }
                                KfpsComboBox {
                                    id: game
                                    Layout.fillWidth: true
                                    dense: root.compactHeight
                                    model: ["FH6", "FH5", "FH4", "FM8"]
                                    toolTipText: "Choose the game whose live editor or local save files you want to use."
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: Theme.px(3)
                                Label { text: "Template layers" }
                                KfpsTextField {
                                    id: layerCount
                                    Layout.fillWidth: true
                                    dense: root.compactHeight
                                    text: "3000"
                                    placeholderText: "Layer count"
                                    inputMethodHints: Qt.ImhDigitsOnly
                                    toolTipText: "For online transfer, enter the exact number of editable layers in the template currently open in the game."
                                }
                            }
                        }

                        Label { text: "Output source" }
                        KfpsComboBox {
                            id: source
                            Layout.fillWidth: true
                            dense: root.compactHeight
                            model: supporterService.unlocked
                                   ? ["Generated finals", "Editor exports", "Game exports", "Library"]
                                   : ["Generated finals", "Editor exports", "Game exports"]
                            currentIndex: jsonService.sourceIndex
                            toolTipText: "Choose which KFPS folder or scanned game library is shown in the output browser."
                            onActivated: jsonService.setSource(currentIndex)
                        }

                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Theme.px(root.compactHeight ? 148 : 176)
                            soft: true
                            visible: supporterService.unlocked
                            border.color: cgroupLibraryService.running ? Theme.warning : Theme.borderSoft

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: Theme.px(10)
                                spacing: Theme.px(6)

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.px(8)

                            Text {
                                Layout.fillWidth: true
                                text: "FH4/FH5/FH6/FM8 save library"
                                color: Theme.primaryBright
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(12.4)
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }

                            Text {
                                Layout.maximumWidth: Theme.px(130)
                                text: cgroupLibraryService.running ? "Scanning" : cgroupLibraryService.status
                                color: cgroupLibraryService.running ? Theme.warning : Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(9.4)
                                elide: Text.ElideRight
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: cgroupLibraryService.summary
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(9.4)
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.px(8)

                            PrimaryButton {
                                Layout.fillWidth: true
                                minimumWidth: 0
                                text: cgroupLibraryService.running ? "Scanning " + game.currentText + "..." : "Scan " + game.currentText + " Saves"
                                iconName: "folder"
                                dense: root.compactHeight
                                toolTipText: "Find vinyl groups in the selected game's local save files and add them to the Library view."
                                enabled: !cgroupLibraryService.running
                                onClicked: cgroupLibraryService.scanSaves(game.currentText)
                            }

                            GhostButton {
                                Layout.preferredWidth: Theme.px(116)
                                minimumWidth: 0
                                text: "Folder"
                                iconName: "folder"
                                dense: root.compactHeight
                                toolTipText: "Open KFPS's scanned game-library folder in File Explorer."
                                onClicked: desktop.openFolder(cgroupLibraryService.libraryFolder)
                            }
                        }

                        GhostButton {
                            Layout.fillWidth: true
                            minimumWidth: 0
                            text: cgroupLibraryService.running
                                  ? "Working..."
                                  : (game.currentText === "FH6"
                                     ? "Offline Import to FH6"
                                     : (game.currentText === "FH4"
                                        ? "Offline Import to FH4"
                                     : (game.currentText === "FM8"
                                        ? "Offline Import to FM8"
                                        : game.currentText + " Offline Import Unavailable")))
                            iconName: "transfer"
                            dense: root.compactHeight
                            toolTipText: game.currentText === "FH5"
                                         ? "FH5 local save-file importing is not available. Use online import with FH5 running."
                                         : (game.currentText === "FH4"
                                            ? "With FH4 fully closed, create a new vinyl in the Microsoft Store/Xbox WGS save after backing up the complete local slot."
                                            : "Write the selected JSON into the selected game's local save library without opening the game.")
                            enabled: !cgroupLibraryService.running
                                     && (game.currentText === "FH4" || game.currentText === "FH6" || game.currentText === "FM8")
                                     && jsonService.selectedPath.length > 0
                            onClicked: cgroupLibraryService.createLayerGroupFromSelectedJson(jsonService.selectedPath, game.currentText)
                        }
                            }
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: Theme.px(8)

                    GhostButton {
                        Layout.fillWidth: true
                        minimumWidth: 0
                        text: "Add JSON"
                        iconName: "folder"
                        dense: root.compactHeight
                        toolTipText: "Choose a JSON file manually. KFPS detects supported formats and keeps the original file unchanged."
                        onClicked: jsonService.browseManual()
                    }

                    GhostButton {
                        Layout.fillWidth: true
                        minimumWidth: 0
                        text: "Refresh Outputs"
                        iconName: "refresh"
                        dense: root.compactHeight
                        toolTipText: "Scan the selected output source again and update the list."
                        onClicked: jsonService.refresh()
                    }

                    KfpsCheckBox {
                        id: clearUnused
                        Layout.columnSpan: 2
                        Layout.fillWidth: true
                        text: "Clear Extra Template Layers"
                        checked: true
                        dense: true
                        toolTipText: "After online import, hide placeholder layers that were not replaced by JSON shapes. Leave this on for normal use."
                    }
                        }

                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Theme.px(root.compactHeight ? 96 : 116)
                            soft: true
                            border.color: jsonService.selectedPath.length > 0 ? Theme.borderStrong : Theme.borderSoft

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(10)
                        spacing: Theme.px(5)

                        Text {
                            Layout.fillWidth: true
                            text: "Selected JSON"
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(11.2)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            text: jsonService.selectedPath || "Select one folder/run, then one checkpoint JSON."
                            color: jsonService.selectedPath.length > 0 ? Theme.subtle : Theme.muted
                            font.family: jsonService.selectedPath.length > 0 ? Theme.monoFamily : Theme.fontFamily
                            font.pixelSize: Theme.px(9.2)
                            wrapMode: Text.Wrap
                            maximumLineCount: 3
                            elide: Text.ElideMiddle
                        }
                    }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "Online import/export works with FH4, FH5, FH6, and FM8 while the selected game is running. FH4, FH6, and FM8 also support offline import; all four support offline save-library scanning."
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(10.2)
                            wrapMode: Text.Wrap
                            maximumLineCount: 3
                            elide: Text.ElideRight
                        }

                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Theme.px(root.compactHeight ? 126 : 166)
                            soft: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(11)
                        spacing: Theme.px(7)

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.px(8)

                            Text {
                                Layout.fillWidth: true
                                text: "Live import/export log"
                                color: Theme.primaryBright
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(12.6)
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }

                            Text {
                                Layout.maximumWidth: Theme.px(130)
                                text: transferService.running ? "Running" : transferService.status
                                color: transferService.running ? Theme.warning : Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(9.4)
                                elide: Text.ElideRight
                            }
                        }

                        Flickable {
                            id: transferLiveLogScroll
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            contentWidth: width
                            contentHeight: Math.max(height, transferLiveLogText.height)

                            function pinToBottom() {
                                contentY = Math.max(0, contentHeight - height)
                            }

                            Timer {
                                id: transferLiveLogPinTimer
                                interval: 0
                                repeat: false
                                onTriggered: transferLiveLogScroll.pinToBottom()
                            }

                            TextEdit {
                                id: transferLiveLogText
                                width: transferLiveLogScroll.width
                                height: Math.max(contentHeight + Theme.px(10), transferLiveLogScroll.height)
                                text: transferService.liveLog
                                readOnly: true
                                selectByMouse: true
                                persistentSelection: true
                                wrapMode: TextEdit.Wrap
                                textFormat: TextEdit.PlainText
                                color: Theme.muted
                                selectedTextColor: Theme.primaryText
                                selectionColor: Theme.primary
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.px(10.3)

                                onTextChanged: transferLiveLogPinTimer.restart()
                            }

                            ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
                        }
                        }
                    }
                }
                }

                PrimaryButton {
                    Layout.fillWidth: true
                    text: jsonService.selectedIsGameLibraryItem ? "Already in Game Library" : (transferService.running ? "Working…" : "Online Import to " + game.currentText)
                    iconName: "transfer"
                    toolTipText: jsonService.selectedIsGameLibraryItem
                                 ? "Library items already came from game save files and cannot be imported through live memory from this view."
                                 : "Replace layers in the template currently open in the running game with the selected JSON."
                    enabled: !transferService.running && jsonService.selectedPath.length > 0 && !jsonService.selectedIsGameLibraryItem
                    onClicked: transferService.importJson(game.currentText, jsonService.selectedPath, parseInt(layerCount.text) || 0, clearUnused.checked)
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: Theme.px(8)

                    GhostButton {
                        Layout.fillWidth: true
                        minimumWidth: 0
                        text: "Open Output Folder"
                        iconName: "folder"
                        dense: root.compactHeight
                        toolTipText: "Open the main output folder containing generated vinyls, editor exports, and game exports."
                        onClicked: desktop.openJsonFolders()
                    }

                    GhostButton {
                        Layout.fillWidth: true
                        minimumWidth: 0
                        text: "Online Export from Game"
                        iconName: "transfer"
                        dense: root.compactHeight
                        toolTipText: "Read the vinyl group currently open in the running game and save it as a KFPS JSON."
                        enabled: !transferService.running
                        onClicked: transferService.exportJson(game.currentText, parseInt(layerCount.text) || 0)
                    }
                }
            }
        }

        HoverCard {
            id: browseOutputsCard
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.columnSpan: root.wide ? 2 : 1
            Layout.minimumWidth: root.wide ? Theme.px(720) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)
            strong: true

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 8 : 10)

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(8)

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "2. Browse outputs"
                        subtitle: "Browse folders, manage JSONs, and open vinyl previews without leaving KFPS."
                    }

                    GhostButton {
                        Layout.preferredWidth: Theme.px(132)
                        minimumWidth: Theme.px(118)
                        dense: true
                        iconName: "folder"
                        text: backupService.running ? "Backing up..." : "Backup imgs"
                        enabled: !backupService.running
                        toolTipText: backupService.status
                                     + (backupService.destination.length > 0
                                        ? "\nDestination: " + backupService.destination
                                        : "\nChoose a destination once; KFPS will remember it.")
                                     + "\nEach run adds a complete snapshot. Existing backups are never deleted."
                        onClicked: backupService.backupImgs()
                    }
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    soft: true
                    border.color: jsonService.selectedPath.length > 0 ? Theme.borderStrong : Theme.borderSoft

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(10)
                        spacing: Theme.px(8)

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.px(8)

                                Text {
                                    Layout.fillWidth: true
                                    text: "Files and folders"
                                    color: Theme.primaryBright
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(12.2)
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }

                                Text {
                                    Layout.maximumWidth: Theme.px(420)
                                    text: jsonService.managementStatus.length > 0
                                          ? jsonService.managementStatus
                                          : (jsonService.thumbnailStatus.length > 0 ? jsonService.thumbnailStatus : (jsonService.indexing ? jsonService.indexStatus : (jsonService.selectedName === "—" ? "Double-click a thumbnail for details." : jsonService.selectedName)))
                                    color: Theme.muted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(9.6)
                                    elide: Text.ElideMiddle
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.px(6)

                                GhostButton {
                                    id: explorerBackButton
                                    minimumWidth: Theme.px(40)
                                    Layout.preferredWidth: Theme.px(40)
                                    dense: true
                                    text: ""
                                    enabled: jsonService.canGoBack
                                    toolTipText: "Return to the previous output folder."
                                    onClicked: jsonService.goBack()
                                    contentItem: Item {
                                        implicitWidth: Theme.px(14)
                                        implicitHeight: Theme.px(14)
                                        Icon {
                                            anchors.centerIn: parent
                                            name: "chevron-left"
                                            iconSize: Theme.px(14)
                                            colorize: false
                                            iconOpacity: explorerBackButton.enabled ? 0.96 : 0.34
                                        }
                                        Text {
                                            anchors.centerIn: parent
                                            visible: !Theme.iconGlyphsVisible
                                            text: "<"
                                            color: explorerBackButton.enabled ? Theme.text : Theme.muted
                                            opacity: explorerBackButton.enabled ? 1.0 : 0.48
                                            font.family: Theme.monoFamily
                                            font.pixelSize: Theme.px(12)
                                            font.weight: Font.Bold
                                        }
                                    }
                                }

                                GhostButton {
                                    id: explorerForwardButton
                                    minimumWidth: Theme.px(40)
                                    Layout.preferredWidth: Theme.px(40)
                                    dense: true
                                    text: ""
                                    enabled: jsonService.canGoForward
                                    toolTipText: "Go forward to the folder you left."
                                    onClicked: jsonService.goForward()
                                    contentItem: Item {
                                        implicitWidth: Theme.px(14)
                                        implicitHeight: Theme.px(14)
                                        Icon {
                                            anchors.centerIn: parent
                                            name: "chevron-right"
                                            iconSize: Theme.px(14)
                                            colorize: false
                                            iconOpacity: explorerForwardButton.enabled ? 0.96 : 0.34
                                        }
                                        Text {
                                            anchors.centerIn: parent
                                            visible: !Theme.iconGlyphsVisible
                                            text: ">"
                                            color: explorerForwardButton.enabled ? Theme.text : Theme.muted
                                            opacity: explorerForwardButton.enabled ? 1.0 : 0.48
                                            font.family: Theme.monoFamily
                                            font.pixelSize: Theme.px(12)
                                            font.weight: Font.Bold
                                        }
                                    }
                                }

                                GhostButton {
                                    id: explorerUpButton
                                    minimumWidth: Theme.px(40)
                                    Layout.preferredWidth: Theme.px(40)
                                    dense: true
                                    text: ""
                                    enabled: jsonService.canGoUp
                                    toolTipText: "Open the parent folder without leaving the selected output source."
                                    onClicked: jsonService.goUp()
                                    contentItem: Item {
                                        implicitWidth: Theme.px(14)
                                        implicitHeight: Theme.px(14)
                                        Icon {
                                            anchors.centerIn: parent
                                            name: "arrow-up"
                                            iconSize: Theme.px(14)
                                            colorize: false
                                            iconOpacity: explorerUpButton.enabled ? 0.96 : 0.34
                                        }
                                        Text {
                                            anchors.centerIn: parent
                                            visible: !Theme.iconGlyphsVisible
                                            text: "^"
                                            color: explorerUpButton.enabled ? Theme.text : Theme.muted
                                            opacity: explorerUpButton.enabled ? 1.0 : 0.48
                                            font.family: Theme.monoFamily
                                            font.pixelSize: Theme.px(12)
                                            font.weight: Font.Bold
                                        }
                                    }
                                }

                                KfpsComboBox {
                                    id: explorerFolderPicker
                                    objectName: "OutputFolderJump"
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: Theme.px(130)
                                    dense: true
                                    model: jsonService.folderModel
                                    textRole: "displayName"
                                    currentIndex: jsonService.currentFolderIndex
                                    toolTipText: "Jump to Outputs, an output category, or any folder created inside KFPS."
                                    onActivated: {
                                        var folder = jsonService.folderModel.get(currentIndex)
                                        jsonService.jumpToFolder(String(folder.path || ""))
                                        files.positionViewAtBeginning()
                                    }
                                }

                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.px(8)

                                KfpsTextField {
                                    id: outputSearch
                                    Layout.fillWidth: true
                                    dense: true
                                    enabled: jsonService.currentFolder.length > 0
                                    placeholderText: enabled ? "Search current source by vinyl name" : "Open an output category to search"
                                    toolTipText: "Filter the current output source by vinyl name. Empty the box to show everything again."
                                    Component.onCompleted: text = jsonService.searchQuery
                                    onTextEdited: {
                                        jsonService.setSearchQuery(text)
                                        files.positionViewAtBeginning()
                                    }
                                    Connections {
                                        target: jsonService
                                        function onChanged() {
                                            if (outputSearch.text !== jsonService.searchQuery)
                                                outputSearch.text = jsonService.searchQuery
                                        }
                                    }
                                }

                                KfpsComboBox {
                                    id: outputSort
                                    objectName: "OutputSort"
                                    Layout.preferredWidth: Theme.px(178)
                                    Layout.minimumWidth: Theme.px(150)
                                    dense: true
                                    enabled: jsonService.currentFolder.length > 0
                                    model: ["Date made", "Alphabetical", "Least shapes", "Most shapes"]
                                    currentIndex: jsonService.sortMode === "name-asc" ? 1
                                                  : (jsonService.sortMode === "shapes-asc" ? 2
                                                     : (jsonService.sortMode === "shapes-desc" ? 3 : 0))
                                    toolTipText: "Choose how JSONs are ordered. Folders always stay together before JSON files."
                                    onActivated: {
                                        var modes = ["date-desc", "name-asc", "shapes-asc", "shapes-desc"]
                                        jsonService.setSortMode(modes[currentIndex])
                                        files.positionViewAtBeginning()
                                    }
                                }

                                Text {
                                    Layout.maximumWidth: Theme.px(180)
                                    text: jsonService.explorerSummary
                                    color: Theme.subtle
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(9.4)
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideRight
                                }
                            }

                            Item {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true

                                GridView {
                                    id: files
                                    anchors.fill: parent
                                    clip: true
                                    model: jsonService.explorerModel
                                    boundsBehavior: Flickable.StopAtBounds
                                    maximumFlickVelocity: 100000
                                    flickDeceleration: 12000
                                    focus: true
                                    property int columns: Math.max(1, Math.floor(width / Theme.px(root.compactHeight ? 148 : 180)))
                                    cellWidth: Math.max(Theme.px(138), width / columns)
                                    cellHeight: Theme.px(root.compactHeight ? 158 : 186)

                                    Keys.onPressed: event => {
                                        if (event.key === Qt.Key_C && (event.modifiers & Qt.ControlModifier)) {
                                            jsonService.copySelection()
                                            event.accepted = true
                                        } else if (event.key === Qt.Key_X && (event.modifiers & Qt.ControlModifier)) {
                                            jsonService.cutSelection()
                                            event.accepted = true
                                        } else if (event.key === Qt.Key_V && (event.modifiers & Qt.ControlModifier)) {
                                            jsonService.pasteIntoCurrentFolder()
                                            event.accepted = true
                                        } else if (event.key === Qt.Key_Left && (event.modifiers & Qt.AltModifier)) {
                                            jsonService.goBack()
                                            event.accepted = true
                                        } else if (event.key === Qt.Key_Right && (event.modifiers & Qt.AltModifier)) {
                                            jsonService.goForward()
                                            event.accepted = true
                                        } else if (event.key === Qt.Key_A && (event.modifiers & Qt.ControlModifier)) {
                                            jsonService.selectAllExplorerEntries()
                                            event.accepted = true
                                        } else if (event.key === Qt.Key_Delete && jsonService.fileOperationSelectionCount > 0) {
                                            deleteSelectedEntriesDialog.open()
                                            event.accepted = true
                                        } else if (event.key === Qt.Key_Escape) {
                                            jsonService.clearExplorerSelection()
                                            jsonService.clearSelection()
                                            event.accepted = true
                                        }
                                    }

                                    delegate: Rectangle {
                                        id: fileCard
                                        required property string displayName
                                        required property string path
                                        required property int layers
                                        required property string modifiedLabel
                                        required property string previewUrl
                                        required property string detailText
                                        required property string folder
                                        required property string entryKind
                                        required property bool isFolder
                                        required property bool selected
                                        required property int index
                                        readonly property bool hovered: cardHover.hovered
                                        readonly property bool pressed: cardMouse.pressed
                                        readonly property bool selectedInExplorer: fileCard.selected
                                        readonly property bool activeTile: fileCard.selectedInExplorer
                                                                           || (jsonService.explorerSelectionCount === 0
                                                                               && !fileCard.isFolder
                                                                               && jsonService.selectedPath === fileCard.path)

                                        objectName: (fileCard.isFolder ? "OutputFolderTile:" : "JsonTile:") + fileCard.displayName

                                        width: files.cellWidth - Theme.px(8)
                                        height: files.cellHeight - Theme.px(8)
                                        radius: Theme.framedRadius(Theme.px(16))
                                        color: Theme.classicMode && fileCard.activeTile
                                               ? Theme.primary
                                               : (fileCard.activeTile
                                               ? (cardHover.hovered ? Theme.primaryDeep : Theme.primarySoft)
                                               : (cardHover.hovered ? Theme.helpTopicHover : Theme.panelGradientTop(false, false)))
                                        border.width: Theme.classicMode
                                                      ? 0
                                                      : (Theme.customFrameExclusive
                                                      ? 0
                                                      : Math.max(1, Theme.px(fileCard.activeTile ? 2 : 1)))
                                        border.color: fileCard.activeTile ? Theme.primaryBright : Theme.borderSoft
                                        antialiasing: true
                                        scale: Theme.classicMode ? 1.0 : (cardMouse.pressed ? 0.985 : 1.0)
                                        Behavior on scale { enabled: !Theme.reducedMotion; NumberAnimation { duration: 75; easing.type: Easing.OutCubic } }
                                        Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 110 } }

                                        Column {
                                            anchors.fill: parent
                                            anchors.margins: Theme.px(8)
                                            spacing: Theme.px(6)

                                            Rectangle {
                                                width: parent.width
                                                height: Math.max(Theme.px(72), fileCard.height - Theme.px(root.compactHeight ? 70 : 78))
                                                radius: Theme.corner(Theme.px(12))
                                                color: Theme.previewSurface
                                                border.width: Math.max(1, Theme.px(1))
                                                border.color: Theme.border
                                                clip: true

                                                ClassicBevel {
                                                    anchors.fill: parent
                                                    sunken: true
                                                    z: 20
                                                }

                                                ArtworkPreviewBackdrop {
                                                    anchors.fill: parent
                                                    anchors.margins: Theme.px(5)
                                                    visible: !fileCard.isFolder && String(fileCard.previewUrl || "").length > 0
                                                }

                                                Image {
                                                    anchors.fill: parent
                                                    anchors.margins: Theme.px(5)
                                                    visible: !fileCard.isFolder
                                                    source: fileCard.previewUrl
                                                    fillMode: Image.PreserveAspectFit
                                                    asynchronous: true
                                                    smooth: true
                                                    mipmap: false
                                                }

                                                EmptyState {
                                                    visible: !fileCard.isFolder && !fileCard.previewUrl
                                                    anchors.centerIn: parent
                                                    iconName: "json"
                                                    title: ""
                                                    message: "No preview"
                                                }

                                                Item {
                                                    visible: fileCard.isFolder
                                                    anchors.fill: parent
                                                    anchors.margins: Theme.px(8)

                                                    Icon {
                                                        anchors.centerIn: parent
                                                        anchors.verticalCenterOffset: -Theme.px(7)
                                                        visible: Theme.iconGlyphsVisible && !Theme.angularControlsEnabled
                                                        name: "folder"
                                                        iconSize: Theme.px(root.compactHeight ? 48 : 58)
                                                        colorize: false
                                                        glow: fileCard.hovered
                                                        glowColor: Theme.primary
                                                    }

                                                    Text {
                                                        anchors.centerIn: parent
                                                        anchors.verticalCenterOffset: -Theme.px(7)
                                                        visible: !Theme.iconGlyphsVisible || Theme.angularControlsEnabled
                                                        text: "[DIR]"
                                                        color: fileCard.hovered ? Theme.primaryBright : Theme.text
                                                        font.family: Theme.monoFamily
                                                        font.pixelSize: Theme.px(15)
                                                        font.weight: Font.Bold
                                                    }

                                                    Text {
                                                        anchors.left: parent.left
                                                        anchors.right: parent.right
                                                        anchors.bottom: parent.bottom
                                                        text: "Open folder"
                                                        color: Theme.muted
                                                        font.family: Theme.fontFamily
                                                        font.pixelSize: Theme.px(8.8)
                                                        horizontalAlignment: Text.AlignHCenter
                                                        elide: Text.ElideRight
                                                    }
                                                }
                                            }

                                            Text {
                                                width: parent.width
                                                text: fileCard.displayName
                                                color: Theme.classicMode && fileCard.activeTile ? Theme.primaryText : Theme.text
                                                font.family: Theme.fontFamily
                                                font.pixelSize: Theme.px(10.4)
                                                font.weight: Font.DemiBold
                                                elide: Text.ElideMiddle
                                                maximumLineCount: 1
                                            }

                                            Text {
                                                width: parent.width
                                                text: fileCard.detailText
                                                color: Theme.classicMode && fileCard.activeTile ? Theme.primaryText : Theme.subtle
                                                font.family: Theme.fontFamily
                                                font.pixelSize: Theme.px(9.2)
                                                elide: Text.ElideRight
                                            }
                                        }

                                        ClassicBevel {
                                            anchors.fill: parent
                                            pressed: cardMouse.pressed || fileCard.activeTile
                                            z: 30
                                        }

                                        HoverHandler {
                                            id: cardHover
                                            cursorShape: Qt.PointingHandCursor
                                        }

                                        KfpsToolTip {
                                            visible: cardHover.hovered
                                            text: fileCard.isFolder
                                                  ? "Click to select. Double-click to open. Use Shift or Ctrl for multiple items; right-click for actions."
                                                  : "Click to select. Double-click for details. Use Shift or Ctrl for multiple items; right-click for actions."
                                        }

                                        MouseArea {
                                            id: cardMouse
                                            anchors.fill: parent
                                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                                            onClicked: mouse => {
                                                mouse.accepted = true
                                                files.forceActiveFocus()
                                                if (mouse.button === Qt.RightButton) {
                                                    if (!jsonService.isExplorerEntrySelected(fileCard.path))
                                                        jsonService.selectExplorerEntry(fileCard.index, false, false)
                                                    var contextPoint = fileCard.mapToItem(root, mouse.x, mouse.y)
                                                    root.openOutputContextMenu(fileCard.path, fileCard.displayName, fileCard.isFolder, fileCard.entryKind, contextPoint.x, contextPoint.y)
                                                } else {
                                                    jsonService.selectExplorerEntry(
                                                        fileCard.index,
                                                        (mouse.modifiers & Qt.ControlModifier) !== 0,
                                                        (mouse.modifiers & Qt.ShiftModifier) !== 0)
                                                }
                                            }
                                            onDoubleClicked: mouse => {
                                                mouse.accepted = true
                                                if (mouse.button !== Qt.LeftButton)
                                                    return
                                                if (fileCard.isFolder) {
                                                    jsonService.openExplorerFolder(fileCard.path)
                                                    files.positionViewAtBeginning()
                                                    return
                                                }
                                                jsonService.selectExplorerEntry(fileCard.index, false, false)
                                                root.infoCardName = fileCard.displayName
                                                root.infoCardDetail = fileCard.detailText
                                                root.infoCardFolder = fileCard.folder
                                                root.infoCardPath = fileCard.path
                                                root.infoCardPreview = fileCard.previewUrl
                                                jsonInfoPopup.open()
                                            }
                                        }
                                    }

                                    TapHandler {
                                        acceptedButtons: Qt.RightButton
                                        gesturePolicy: TapHandler.ReleaseWithinBounds
                                        onTapped: eventPoint => {
                                            if (outputContextMenus.opened)
                                                return
                                            if (jsonService.currentFolder.length === 0)
                                                return
                                            jsonService.clearExplorerSelection()
                                            jsonService.clearSelection()
                                            var contextPoint = files.mapToItem(root, eventPoint.position.x, eventPoint.position.y)
                                            root.openOutputContextMenu("", "", false, "", contextPoint.x, contextPoint.y)
                                        }
                                    }

                                    WheelHandler {
                                        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                                        target: null
                                        onWheel: event => {
                                            var delta = event.pixelDelta.y
                                            if (delta === 0)
                                                delta = (event.angleDelta.y / 120.0) * Theme.px(96)
                                            if (delta === 0)
                                                return
                                            files.contentY = Math.max(0, Math.min(files.contentY - delta, Math.max(0, files.contentHeight - files.height)))
                                            event.accepted = true
                                        }
                                    }

                                    ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
                                }

                                EmptyState {
                                    visible: files.count === 0
                                    anchors.centerIn: parent
                                    iconName: jsonService.searchQuery.length > 0 ? "json" : "folder"
                                    title: jsonService.currentSourceIndexing ? "Indexing outputs" : (jsonService.searchQuery.length > 0 ? "No matching vinyls" : "Empty folder")
                                    message: jsonService.currentSourceIndexing
                                             ? "Scanning this source in the background. Cached results will appear automatically."
                                             : (jsonService.searchQuery.length > 0
                                             ? "No vinyl name in this source matches the search."
                                             : "Right-click here to create a folder or paste copied items.")
                                }
                            }

                            GlassPanel {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Theme.px(root.compactHeight ? 68 : 80)
                                visible: root.wide || !root.compactHeight
                                soft: true

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: Theme.px(9)
                                    spacing: Theme.px(3)

                                    Text {
                                        Layout.fillWidth: true
                                        text: jsonService.explorerSelectionCount > 1
                                              ? jsonService.explorerSelectionCount + " items selected"
                                              : (jsonService.explorerSelectionCount === 1
                                                 ? "Selected: " + jsonService.explorerSelectionName
                                                 : (jsonService.selectedName === "—"
                                                 ? "Folder: " + jsonService.currentFolderDisplay
                                                 : "Selected: " + jsonService.selectedName))
                                        color: Theme.text
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(10.6)
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideMiddle
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: jsonService.explorerSelectionCount > 1
                                              ? "Right-click any selected item to copy, cut, or delete the complete selection."
                                              : (jsonService.explorerSelectionCount === 1 && jsonService.selectedName === "—"
                                                 ? "Double-click the selected folder to open it. Right-click for folder actions."
                                                 : (jsonService.selectedName === "—"
                                                 ? jsonService.currentFolder
                                                 : "Layers: " + jsonService.selectedLayers + "  •  Folder: " + jsonService.selectedFolder))
                                        color: Theme.subtle
                                        font.family: Theme.monoFamily
                                        font.pixelSize: Theme.px(9.0)
                                        elide: Text.ElideMiddle
                                    }
                                }
                            }
                        }
                    }
                }
        }
    }

    OutputExplorerContextMenus {
        id: outputContextMenus
        anchors.fill: parent
        jsonService: jsonService
        onFolderOpened: files.positionViewAtBeginning()
        onNameActionRequested: function(mode, target, parentPath, currentName) {
            root.openOutputNameDialog(mode, target, parentPath, currentName)
        }
        onDeleteRequested: deleteSelectedEntriesDialog.open()
    }
    Popup {
        id: outputNameDialog
        modal: true
        focus: true
        dim: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(root.width - Theme.px(40), Theme.px(460))
        height: Theme.px(250)
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: Theme.px(16)
        z: 90

        background: KfpsPopupSurface {
            surfaceColor: Theme.surfaceRaised
            outlineColor: Theme.borderStrong
            cornerRadius: Theme.px(8)
        }

        contentItem: ColumnLayout {
            spacing: Theme.px(10)

            SectionHeading {
                Layout.fillWidth: true
                title: root.outputNameDialogMode === "new-folder"
                       ? "Create folder"
                       : (root.outputNameDialogMode === "rename-folder" ? "Rename folder" : "Rename JSON")
                subtitle: root.outputNameDialogMode === "new-folder"
                          ? "The folder will be created inside the chosen Outputs location."
                          : "Only the item name changes; its contents stay intact."
            }

            Label {
                text: root.outputNameDialogMode === "new-folder" ? "Folder name" : "New name"
            }

            KfpsTextField {
                id: outputNameInput
                Layout.fillWidth: true
                maximumLength: 180
                placeholderText: root.outputNameDialogMode === "rename-json" ? "Vinyl name.json" : "Folder name"
                toolTipText: "Use a Windows-compatible name without slashes, colons, a trailing period, or reserved device names."
                onAccepted: root.submitOutputName()
            }

            Text {
                Layout.fillWidth: true
                text: jsonService.managementStatus
                color: Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(9.4)
                wrapMode: Text.Wrap
                visible: outputNameDialog.opened && jsonService.managementStatus.length > 0
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true

                GhostButton {
                    text: "Cancel"
                    toolTipText: "Close this window without creating or renaming anything."
                    onClicked: outputNameDialog.close()
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: root.outputNameDialogMode === "new-folder" ? "Create" : "Rename"
                    iconName: root.outputNameDialogMode === "new-folder" ? "folder" : "editor"
                    enabled: outputNameInput.text.trim().length > 0
                    toolTipText: root.outputNameDialogMode === "new-folder"
                                 ? "Create the folder with the entered name."
                                 : "Apply the entered name to this item."
                    onClicked: root.submitOutputName()
                }
            }
        }
    }

    MessageDialog {
        id: deleteSelectedEntriesDialog
        title: jsonService.fileOperationSelectionCount === 1 ? "Delete selected item?" : "Delete selected items?"
        text: "Permanently delete " + jsonService.fileOperationSelectionCount
              + (jsonService.fileOperationSelectionCount === 1 ? " selected item" : " selected items")
              + "? Folders and everything inside them will be removed. This cannot be undone."
        buttons: MessageDialog.Ok | MessageDialog.Cancel
        onAccepted: jsonService.deleteSelectedEntries()
    }

    Popup {
        id: jsonInfoPopup
        modal: true
        focus: true
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        width: Math.min(root.width - Theme.px(34), Theme.px(1040))
        height: Math.min(root.height - Theme.px(34), Theme.px(800))
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: Theme.px(18)

        background: KfpsPopupSurface {
            surfaceColor: Theme.surfaceRaised
            outlineColor: Theme.borderStrong
            cornerRadius: Theme.px(24)
        }

        contentItem: ColumnLayout {
            spacing: Theme.px(12)

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(10)

                SectionHeading {
                    Layout.fillWidth: true
                    title: root.infoCardName || "Vinyl JSON"
                    subtitle: root.infoCardDetail || "Preview and file information."
                }

                GhostButton {
                    Layout.preferredWidth: Theme.px(110)
                    text: "Close"
                    toolTipText: "Close the vinyl preview and return to Outputs."
                    onClicked: jsonInfoPopup.close()
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: Theme.px(460)
                radius: Theme.corner(Theme.px(18))
                color: Theme.angularControlsEnabled ? "transparent" : Theme.previewSurface
                border.width: Theme.angularControlsEnabled ? 0 : Math.max(1, Theme.px(1))
                border.color: Theme.borderStrong
                clip: true

                AngularControlFrame {
                    anchors.fill: parent
                    fillColor: Theme.previewSurface
                    borderColor: Theme.borderStrong
                    accentColor: Theme.signalSecondary
                    panelFrame: true
                    enclosedPanel: true
                }

                ClassicBevel {
                    anchors.fill: parent
                    sunken: true
                    z: 20
                }

                ArtworkPreviewBackdrop {
                    anchors.fill: parent
                    anchors.margins: Theme.px(16)
                    visible: root.infoCardPreview.length > 0
                }

                Image {
                    anchors.fill: parent
                    anchors.margins: Theme.px(16)
                    source: root.infoCardPreview
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    smooth: true
                    mipmap: false
                }

                EmptyState {
                    visible: !root.infoCardPreview
                    anchors.centerIn: parent
                    iconName: "json"
                    title: "No preview"
                    message: "The JSON can still be imported, but no thumbnail was available."
                }
            }

            GlassPanel {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.px(96)
                soft: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.px(11)
                    spacing: Theme.px(4)

                    Text {
                        Layout.fillWidth: true
                        text: root.infoCardDetail
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(11)
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "Folder: " + root.infoCardFolder
                        color: Theme.subtle
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.px(9.4)
                        elide: Text.ElideMiddle
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "JSON: " + root.infoCardPath
                        color: Theme.subtle
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.px(9.4)
                        elide: Text.ElideMiddle
                    }
                }
            }
        }
    }

    Popup {
        id: fm8CreatorDialog
        modal: true
        focus: true
        dim: true
        closePolicy: Popup.NoAutoClose
        width: Math.min(root.width - Theme.px(48), Theme.px(860))
        height: Math.min(root.height - Theme.px(48), Theme.px(620))
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: Theme.px(18)

        background: KfpsPopupSurface {
            surfaceColor: Theme.surfaceRaised
            outlineColor: Theme.borderStrong
            cornerRadius: Theme.px(24)
        }

        contentItem: ColumnLayout {
            spacing: Theme.px(14)

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(12)

                Icon {
                    name: "folder"
                    iconSize: Theme.px(34)
                    glow: true
                    Layout.alignment: Qt.AlignVCenter
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(2)

                    Text {
                        Layout.fillWidth: true
                        text: root.fm8CreatorConfirmStep === 1 ? "Choose Your FM8 Profile" : "Confirm This Is You"
                        color: Theme.primaryBright
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(20)
                        font.weight: Font.Bold
                        elide: Text.ElideRight
                    }

                    Text {
                        Layout.fillWidth: true
                        text: cgroupLibraryService.creatorPromptSummary
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(11.5)
                        wrapMode: Text.Wrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                height: Math.max(1, Theme.px(1))
                color: Theme.borderSoft
                opacity: 0.9
            }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(10)
                    visible: root.fm8CreatorConfirmStep === 1

                    Text {
                        Layout.fillWidth: true
                        text: "Pick the creator name that belongs to your local FM8 profile. KFPS will use it privately to hide downloaded/community vinyls from the offline library."
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(12.4)
                        wrapMode: Text.Wrap
                    }

                    ListView {
                        id: fm8CreatorList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: Theme.px(8)
                        model: cgroupLibraryService.creatorCandidateModel

                        delegate: Rectangle {
                            id: creatorRow
                            objectName: "Fm8CreatorRow:" + creatorRow.displayName
                            required property string creator
                            required property string displayName
                            required property string detailText
                            required property int score
                            required property bool recommended
                            readonly property bool hovered: creatorHover.hovered
                            readonly property bool pressed: creatorTap.pressed

                            width: fm8CreatorList.width
                            height: Theme.px(76)
                            radius: Theme.corner(Theme.px(16))
                            color: root.fm8PendingCreator === creator ? Theme.primarySoft : (creatorHover.hovered ? Theme.hover : Theme.panelGradientTop(false, false))
                            border.width: Math.max(1, Theme.px(root.fm8PendingCreator === creator ? 2 : 1))
                            border.color: root.fm8PendingCreator === creator ? Theme.primaryBright : (recommended ? Theme.warning : Theme.borderSoft)
                            antialiasing: true

                            Column {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: Theme.px(14)
                                anchors.rightMargin: Theme.px(14)
                                spacing: Theme.px(4)

                                Text {
                                    width: parent.width
                                    text: displayName
                                    color: Theme.text
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(13.8)
                                    font.weight: Font.Bold
                                    elide: Text.ElideRight
                                }

                                Text {
                                    width: parent.width
                                    text: detailText
                                    color: Theme.muted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(10.6)
                                    elide: Text.ElideRight
                                }
                            }

                            HoverHandler {
                                id: creatorHover
                                cursorShape: Qt.PointingHandCursor
                            }

                            KfpsToolTip {
                                visible: creatorHover.hovered
                                text: "Select this FM8 creator profile for private offline-library filtering."
                            }

                            TapHandler {
                                id: creatorTap
                                onTapped: event => {
                                    event.accepted = true
                                    root.fm8PendingCreator = creatorRow.creator
                                    root.fm8PendingCreatorDisplay = creatorRow.displayName
                                    root.fm8PendingCreatorDetail = creatorRow.detailText
                                }
                            }
                        }

                        ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
                    }
                }

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(16)
                    visible: root.fm8CreatorConfirmStep === 2

                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.px(190)
                        soft: true
                        border.color: Theme.warning

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.px(18)
                            spacing: Theme.px(10)

                            Text {
                                Layout.fillWidth: true
                                text: root.fm8PendingCreator
                                color: Theme.primaryBright
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(22)
                                font.weight: Font.Bold
                                horizontalAlignment: Text.AlignHCenter
                                elide: Text.ElideRight
                            }

                            Text {
                                Layout.fillWidth: true
                                text: root.fm8PendingCreatorDetail
                                color: Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(12)
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.Wrap
                                maximumLineCount: 3
                                elide: Text.ElideRight
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "Please check this twice. After confirmation, KFPS stores only a private hash and will not show this profile name again. If this is wrong, the offline library may hide your own vinyls or include the wrong cached files."
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(13)
                        wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter
                    }

                    Item { Layout.fillHeight: true }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(10)

                GhostButton {
                    Layout.preferredWidth: Theme.px(132)
                    text: root.fm8CreatorConfirmStep === 1 ? "Cancel" : "Back"
                    toolTipText: root.fm8CreatorConfirmStep === 1
                                 ? "Cancel this scan without choosing a profile."
                                 : "Return to the FM8 profile list."
                    onClicked: {
                        if (root.fm8CreatorConfirmStep === 1) {
                            cgroupLibraryService.cancelFm8CreatorPrompt()
                            fm8CreatorDialog.close()
                        } else {
                            root.fm8CreatorConfirmStep = 1
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    Layout.preferredWidth: Theme.px(root.fm8CreatorConfirmStep === 1 ? 180 : 260)
                    text: root.fm8CreatorConfirmStep === 1 ? "Continue" : "Confirm My Profile"
                    iconName: "check"
                    toolTipText: root.fm8CreatorConfirmStep === 1
                                 ? "Review the selected profile before saving it."
                                 : "Confirm the selected creator is your local FM8 profile."
                    enabled: root.fm8PendingCreator.length > 0
                    onClicked: {
                        if (root.fm8CreatorConfirmStep === 1) {
                            root.fm8CreatorConfirmStep = 2
                        } else if (cgroupLibraryService.confirmFm8Creator(root.fm8PendingCreator)) {
                            fm8CreatorDialog.close()
                        }
                    }
                }
            }
        }
    }
}
