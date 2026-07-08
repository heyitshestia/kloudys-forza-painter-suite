import QtQuick 6.7
import QtQuick.Controls 6.7
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

    Connections {
        target: supporterService
        function onChanged() {
            if (!supporterService.unlocked && jsonService.sourceIndex === 3)
                jsonService.setSource(0)
        }
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
        onTapped: jsonService.clearSelection()
    }

    GridLayout {
        anchors.fill: parent
        columns: root.wide ? 3 : 1
        columnSpacing: Theme.px(12)
        rowSpacing: Theme.px(12)

        HoverCard {
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
                        subtitle: "Online uses the live probe. Offline creates a save folder."
                    }
                }

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
                            model: ["FH6", "FH5"]
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
                                text: "FH6 offline import & save library"
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
                                text: cgroupLibraryService.running ? "Scanning " + game.currentText + " saves..." : "Scan " + game.currentText + " save library"
                                iconName: "folder"
                                dense: root.compactHeight
                                enabled: !cgroupLibraryService.running
                                onClicked: cgroupLibraryService.scanSaves(game.currentText)
                            }

                            GhostButton {
                                Layout.preferredWidth: Theme.px(116)
                                minimumWidth: 0
                                text: "Open"
                                iconName: "folder"
                                dense: root.compactHeight
                                onClicked: desktop.openFolder(cgroupLibraryService.libraryFolder)
                            }
                        }

                        GhostButton {
                            Layout.fillWidth: true
                            minimumWidth: 0
                            text: cgroupLibraryService.running
                                  ? "Installing / scanning..."
                                  : (game.currentText === "FH6"
                                     ? "FH6 Offline Import Selected JSON"
                                     : "Offline Import FH5 Disabled")
                            iconName: "transfer"
                            dense: root.compactHeight
                            enabled: !cgroupLibraryService.running
                                     && game.currentText === "FH6"
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
                        text: "Refresh"
                        iconName: "refresh"
                        dense: root.compactHeight
                        onClicked: jsonService.refresh()
                    }

                    KfpsCheckBox {
                        id: clearUnused
                        Layout.fillWidth: true
                        text: "Clear unused layers"
                        checked: true
                        dense: true
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
                    text: "Online import writes into the open in-game template. FH6 offline import can also create a new save-folder vinyl with a transparent thumbnail. FH5 save scanning is next."
                    color: Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(10.2)
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: Theme.px(root.compactHeight ? 126 : 166)
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

                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        }
                    }
                }

                PrimaryButton {
                    Layout.fillWidth: true
                    text: jsonService.sourceIndex === 3 ? "Library entries are already in game" : (transferService.running ? "Working…" : "Online Import Selected JSON")
                    iconName: "transfer"
                    enabled: !transferService.running && jsonService.selectedPath.length > 0 && jsonService.sourceIndex !== 3
                    onClicked: transferService.importJson(game.currentText, jsonService.selectedPath, parseInt(layerCount.text) || 0, clearUnused.checked)
                }

                GhostButton {
                    Layout.fillWidth: true
                    text: "Online Export Current Group"
                    enabled: !transferService.running
                    onClicked: transferService.exportJson(game.currentText, parseInt(layerCount.text) || 0)
                }
            }
        }

        HoverCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.wide ? Theme.px(430) : -1
            Layout.minimumWidth: root.wide ? Theme.px(360) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 7 : 9)

                SectionHeading {
                    Layout.fillWidth: true
                    title: "2. Choose output"
                    subtitle: "Select one run/folder, then one checkpoint."
                }

                Text {
                    Layout.fillWidth: true
                    text: "Runs / folders"
                    color: Theme.primaryBright
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(12.2)
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                FastListView {
                    id: groups
                    Layout.fillWidth: true
                    Layout.preferredHeight: parent.height * 0.36
                    Layout.minimumHeight: Theme.px(150)
                    clip: true
                    model: jsonService.groupModel
                    spacing: Theme.px(5)

                    delegate: GhostButton {
                        required property string name
                        required property string displayName
                        required property string detailText
                        required property int count
                        required property int index
                        width: groups.width
                        minimumWidth: 0
                        maximumTextWidth: Math.max(Theme.px(150), width - Theme.px(48))
                        text: displayName + "  •  " + detailText
                        dense: root.compactHeight
                        onClicked: jsonService.selectGroup(index)
                    }

                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                }

                Text {
                    Layout.fillWidth: true
                    text: "Checkpoint JSON"
                    color: Theme.primaryBright
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(12.2)
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                FastListView {
                    id: files
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: Theme.px(210)
                    clip: true
                    model: jsonService.fileModel
                    spacing: Theme.px(5)

                    delegate: Rectangle {
                        id: fileRow
                        required property string name
                        required property string displayName
                        required property string path
                        required property int layers
                        required property string modifiedLabel
                        required property int index

                        width: files.width
                        height: Theme.px(root.compactHeight ? 50 : 58)
                        radius: Theme.px(9)
                        color: jsonService.selectedPath === path ? Theme.primarySoft : (rowHover.hovered ? Theme.hover : "transparent")
                        border.width: Math.max(1, Theme.px(1))
                        border.color: jsonService.selectedPath === path ? Theme.primaryBright : Theme.border
                        antialiasing: true

                        Column {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.leftMargin: Theme.px(10)
                            anchors.rightMargin: Theme.px(10)
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: Theme.px(3)

                            Text {
                                width: parent.width
                                text: fileRow.displayName
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(10.8)
                                font.weight: jsonService.selectedPath === fileRow.path ? Font.DemiBold : Font.Medium
                                elide: Text.ElideMiddle
                            }

                            Text {
                                width: parent.width
                                text: fileRow.layers + " layers  •  " + fileRow.modifiedLabel
                                color: Theme.subtle
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(9.2)
                                elide: Text.ElideRight
                            }
                        }

                        HoverHandler {
                            id: rowHover
                            cursorShape: Qt.PointingHandCursor
                        }

                        TapHandler {
                            onTapped: event => {
                                event.accepted = true
                                jsonService.selectFile(fileRow.index)
                            }
                        }
                    }

                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                }
            }
        }

        HoverCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.wide ? Theme.px(570) : -1
            Layout.minimumWidth: root.wide ? Theme.px(430) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)
            strong: true

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 7 : 9)

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(8)

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "3. Preview & details"
                        subtitle: "Verify before importing."
                    }

                    Text {
                        Layout.maximumWidth: Theme.px(190)
                        text: transferService.status
                        color: transferService.running ? Theme.warning : Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(9.8)
                        elide: Text.ElideRight
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: Theme.px(330)
                    radius: Theme.px(18)
                    color: Theme.previewSurface
                    border.width: Math.max(1, Theme.px(1))
                    border.color: Theme.borderStrong
                    clip: true

                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: Theme.px(1)
                        radius: parent.radius - Theme.px(1)
                        color: "transparent"
                        border.width: Math.max(1, Theme.px(1))
                        border.color: Theme.innerHighlight
                        opacity: 0.92
                    }

                    Image {
                        anchors.fill: parent
                        anchors.margins: Theme.px(14)
                        source: jsonService.previewUrl
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        smooth: true
                        mipmap: true
                    }

                    EmptyState {
                        visible: !jsonService.previewUrl
                        anchors.centerIn: parent
                        iconName: "json"
                        title: "Select a JSON"
                        message: "Choose a folder/run and then one checkpoint JSON."
                    }
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(root.compactHeight ? 100 : 116)
                    soft: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(11)
                        spacing: Theme.px(4)

                        Text {
                            Layout.fillWidth: true
                            text: "Name: " + jsonService.selectedName
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(10.8)
                            font.weight: Font.DemiBold
                            elide: Text.ElideMiddle
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "Layers: " + jsonService.selectedLayers
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(10.4)
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "Folder: " + jsonService.selectedFolder
                            color: Theme.subtle
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.px(9.2)
                            elide: Text.ElideMiddle
                        }
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

        background: Rectangle {
            radius: Theme.px(24)
            color: Theme.surfaceRaised
            border.width: Math.max(1, Theme.px(1))
            border.color: Theme.borderStrong
            antialiasing: true
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
                            required property string creator
                            required property string displayName
                            required property string detailText
                            required property int score
                            required property bool recommended

                            width: fm8CreatorList.width
                            height: Theme.px(76)
                            radius: Theme.px(16)
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

                            TapHandler {
                                onTapped: event => {
                                    event.accepted = true
                                    root.fm8PendingCreator = creatorRow.creator
                                    root.fm8PendingCreatorDisplay = creatorRow.displayName
                                    root.fm8PendingCreatorDetail = creatorRow.detailText
                                }
                            }
                        }

                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
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
                    text: root.fm8CreatorConfirmStep === 1 ? "Continue" : "Yes, This Is My Profile"
                    iconName: "check"
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
