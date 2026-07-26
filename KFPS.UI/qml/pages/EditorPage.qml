import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    anchors.fill: parent
    clip: true

    property bool wide: Theme.logical(width) >= 1040
    property bool compactHeight: Theme.logical(height) < 720
    readonly property bool headerAlignmentAvailable: root.wide
                                                     && actionCard.width > 0
                                                     && selectedProjectCard.width > 0
    readonly property real headerSourceCenterX: actionCard.x + actionCard.width / 2
    readonly property real headerPreviewCenterX: selectedProjectCard.x + selectedProjectCard.width / 2
    readonly property real headerBannerLeftX: actionCard.x
    readonly property real headerBannerRightX: selectedProjectCard.x + selectedProjectCard.width

    GridLayout {
        anchors.fill: parent
        columns: root.wide ? 2 : 1
        columnSpacing: Theme.px(12)
        rowSpacing: Theme.px(12)

        HoverCard {
            id: actionCard
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.wide ? Theme.px(610) : -1
            Layout.minimumWidth: root.wide ? Theme.px(460) : 0
            padding: Theme.px(root.compactHeight ? 13 : 16)
            strong: true

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 7 : 10)

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(10)

                    Icon {
                        name: "editor"
                        iconSize: Theme.px(30)
                        glow: true
                        Layout.alignment: Qt.AlignVCenter
                    }

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "Vinyl Editor"
                        subtitle: "Create, recover, and reopen editable projects."
                    }

                    GhostButton {
                        dense: true
                        minimumWidth: Theme.px(82)
                        text: "Folder"
                        iconName: "folder"
                        toolTipText: "Open the editor projects folder."
                        onClicked: editorService.openProjects()
                    }
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: root.width < Theme.px(540) ? 2 : 4
                    columnSpacing: Theme.px(6)
                    rowSpacing: Theme.px(6)

                    PrimaryButton {
                        Layout.fillWidth: true
                        dense: root.compactHeight
                        text: editorService.launching ? "Starting..." : "New Canvas"
                        iconName: "editor"
                        enabled: !editorService.launching
                        toolTipText: "Open a blank vinyl canvas. The same local editor service is reused on later launches."
                        onClicked: editorService.launch()
                    }

                    GhostButton {
                        Layout.fillWidth: true
                        dense: root.compactHeight
                        text: "Import JSON"
                        iconName: "json"
                        enabled: !editorService.launching
                        toolTipText: "Open the editor directly to its JSON browser."
                        onClicked: editorService.launchJsonBrowser()
                    }

                    GhostButton {
                        Layout.fillWidth: true
                        dense: root.compactHeight
                        text: "Refresh"
                        iconName: "refresh"
                        toolTipText: "Scan the saved editor projects folder again."
                        onClicked: editorService.refresh()
                    }

                    GhostButton {
                        Layout.fillWidth: true
                        dense: root.compactHeight
                        text: "Tutorial"
                        iconName: "help"
                        toolTipText: "Reset the first-run editor tutorial, then show it on the next launch."
                        onClicked: editorService.resetTutorial()
                    }
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: statusColumn.implicitHeight + Theme.px(18)
                    soft: true

                    ColumnLayout {
                        id: statusColumn
                        anchors.fill: parent
                        anchors.margins: Theme.px(9)
                        spacing: Theme.px(3)

                        StatusRow {
                            Layout.fillWidth: true
                            dense: true
                            label: editorService.launching ? "Local editor service" : "Editor"
                            value: editorService.launching ? "Starting" : (editorService.running ? "Connected" : "Ready")
                            state: editorService.lastError.length > 0 ? "bad" : (editorService.launching ? "warn" : "ok")
                        }

                        Text {
                            Layout.fillWidth: true
                            text: editorService.status
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(9.4)
                            wrapMode: Text.Wrap
                        }

                        Text {
                            Layout.fillWidth: true
                            visible: editorService.lastError.length > 0
                            text: editorService.lastError
                            color: Theme.danger
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(9.1)
                            wrapMode: Text.Wrap
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(8)

                    KfpsTextField {
                        id: projectSearch
                        Layout.fillWidth: true
                        dense: root.compactHeight
                        placeholderText: "Search saved projects"
                        toolTipText: "Filter projects by project name or shape count."
                        text: editorService.searchText
                        onTextChanged: editorService.searchText = text
                    }

                    Text {
                        text: projects.count
                              + (projectSearch.text.length > 0 ? " shown" : " saved")
                        color: Theme.subtle
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(9.6)
                        Layout.alignment: Qt.AlignVCenter
                    }
                }

                FastListView {
                    id: projects
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: Theme.px(root.wide ? 300 : 250)
                    clip: true
                    model: editorService.projectModel
                    spacing: Theme.px(3)

                    delegate: Item {
                        required property string name
                        required property string path
                        required property string modifiedLabel
                        required property string shapeLabel
                        required property int index
                        width: projects.width
                        height: projectRow.implicitHeight

                        Rectangle {
                            anchors.fill: parent
                            visible: path === editorService.selectedPath
                            radius: Theme.framedRadius(Theme.px(6))
                            color: Theme.rowSelectedSurface
                            border.width: Math.max(1, Theme.px(1))
                            border.color: Theme.primary
                        }

                        QuickActionRow {
                            id: projectRow
                            anchors.left: parent.left
                            anchors.right: parent.right
                            dense: root.compactHeight
                            iconName: "editor"
                            title: name
                            subtitle: shapeLabel + "  •  " + modifiedLabel
                            toolTipText: "Select " + name + ". Double-clicking opens it immediately."
                            onClicked: editorService.select(index)

                            TapHandler {
                                acceptedButtons: Qt.LeftButton
                                onDoubleTapped: {
                                    editorService.select(index)
                                    editorService.launchSelected()
                                }
                            }
                        }
                    }

                    ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }

                    EmptyState {
                        anchors.centerIn: parent
                        visible: projects.count === 0
                        iconName: "editor"
                        title: projectSearch.text.length > 0 ? "No matching projects" : "No saved projects"
                        message: projectSearch.text.length > 0
                                 ? "Clear the search or try another project name."
                                 : "Start a blank canvas or import a JSON, then save it as a project."
                    }
                }
            }
        }

        HoverCard {
            id: selectedProjectCard
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.wide ? Theme.px(800) : -1
            Layout.minimumWidth: root.wide ? Theme.px(500) : 0
            padding: Theme.px(root.compactHeight ? 13 : 16)
            strong: true

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 7 : 10)

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(8)

                    SectionHeading {
                        Layout.fillWidth: true
                        title: editorService.selectedName === "—" ? "Project Preview" : editorService.selectedName
                        subtitle: editorService.selectedPath || "Select a saved project to inspect or reopen it."
                    }

                    GhostButton {
                        visible: editorService.selectedPath.length > 0
                        dense: true
                        minimumWidth: Theme.px(72)
                        text: "Clear"
                        iconName: ""
                        toolTipText: "Clear the selected project."
                        onClicked: editorService.clearSelection()
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: Theme.px(root.wide ? 390 : 300)
                    radius: Theme.corner(Theme.px(12))
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

                    ArtworkPreviewBackdrop {
                        anchors.fill: parent
                        anchors.margins: Theme.px(2)
                    }

                    Image {
                        anchors.fill: parent
                        anchors.margins: Theme.px(14)
                        source: editorService.previewUrl
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        smooth: true
                        mipmap: true
                    }

                    EmptyState {
                        visible: !editorService.previewUrl
                        anchors.centerIn: parent
                        iconName: "editor"
                        title: editorService.previewLoading
                               ? "Rendering preview..."
                               : (editorService.selectedPath.length > 0
                                  ? "Preview unavailable"
                                  : "Nothing selected")
                        message: editorService.previewLoading
                                 ? "The project stays selectable while its thumbnail is prepared."
                                 : (editorService.selectedPath.length > 0
                                    ? "The project can still be opened and edited normally."
                                    : "Choose a saved project on the left, or begin a new canvas.")
                    }
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: detailsRow.implicitHeight + Theme.px(22)
                    soft: true

                    RowLayout {
                        id: detailsRow
                        anchors.fill: parent
                        anchors.margins: Theme.px(11)
                        spacing: Theme.px(12)

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.px(2)

                            Text {
                                Layout.fillWidth: true
                                text: editorService.selectedPath.length > 0
                                      ? editorService.selectedShapes + " editable shapes"
                                      : "Projects keep groups, guides, and reference images."
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(11)
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }

                            Text {
                                Layout.fillWidth: true
                                text: editorService.selectedPath.length > 0
                                      ? "Modified " + editorService.selectedModified
                                      : "Export JSON separately when the vinyl is ready for Outputs."
                                color: Theme.subtle
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(9.4)
                                elide: Text.ElideRight
                            }
                        }

                        PrimaryButton {
                            minimumWidth: Theme.px(170)
                            text: editorService.launching ? "Opening..." : "Open Project"
                            iconName: "editor"
                            toolTipText: "Open the selected editable project in the local browser editor."
                            enabled: editorService.selectedPath.length > 0 && !editorService.launching
                            onClicked: editorService.launchSelected()
                        }
                    }
                }
            }
        }
    }
}
