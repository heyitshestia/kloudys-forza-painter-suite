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
                        subtitle: "Target game and template layer count."
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
                            model: ["FH6", "FH5", "FM8"]
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
                    model: ["Generated finals", "Editor exports", "Exported game JSONs"]
                    onActivated: jsonService.setSource(currentIndex)
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
                    text: "Import sends the selected JSON into the prepared in-game template. Export reads the current in-game group."
                    color: Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(10.2)
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }

                Item { Layout.fillHeight: true }

                PrimaryButton {
                    Layout.fillWidth: true
                    text: transferService.running ? "Working…" : "Import Selected JSON"
                    iconName: "transfer"
                    enabled: !transferService.running && jsonService.selectedPath.length > 0
                    onClicked: transferService.importJson(game.currentText, jsonService.selectedPath, parseInt(layerCount.text) || 0, clearUnused.checked)
                }

                GhostButton {
                    Layout.fillWidth: true
                    text: "Export Current Group"
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
                        required property int count
                        required property int index
                        width: groups.width
                        minimumWidth: 0
                        maximumTextWidth: Math.max(Theme.px(150), width - Theme.px(48))
                        text: name + "  (" + count + ")"
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
                                text: fileRow.name
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
}
