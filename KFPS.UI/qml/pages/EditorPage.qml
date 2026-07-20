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
    readonly property bool headerAlignmentAvailable: root.wide
                                                     && actionCard.width > 0
                                                     && selectedProjectCard.width > 0
    readonly property real headerSourceCenterX: actionCard.x + actionCard.width / 2
    readonly property real headerPreviewCenterX: selectedProjectCard.x + selectedProjectCard.width / 2
    readonly property real headerBannerLeftX: actionCard.x
    readonly property real headerBannerRightX: selectedProjectCard.x + selectedProjectCard.width

    GridLayout {
        anchors.fill: parent
        columns: root.wide ? 3 : 1
        columnSpacing: Theme.px(12)
        rowSpacing: Theme.px(12)

        HoverCard {
            id: actionCard
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.wide ? Theme.px(330) : -1
            Layout.minimumWidth: root.wide ? Theme.px(300) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)
            strong: true

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 8 : 10)

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(10)

                    Icon {
                        name: "editor"
                        iconSize: Theme.px(31)
                        glow: true
                        Layout.alignment: Qt.AlignVCenter
                    }

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "1. Editor actions"
                        subtitle: "Open the editor or refresh projects."
                    }
                }

                PrimaryButton {
                    Layout.fillWidth: true
                    text: "New Project"
                    iconName: "editor"
                    toolTipText: "Open the manual editor with a blank project in a new browser window."
                    onClicked: editorService.launch()
                }

                GhostButton {
                    Layout.fillWidth: true
                    text: "Refresh Projects"
                    iconName: "refresh"
                    toolTipText: "Scan the projects folder again and update this list."
                    onClicked: editorService.refresh()
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(root.compactHeight ? 130 : 152)
                    soft: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(12)
                        spacing: Theme.px(6)

                        Text {
                            Layout.fillWidth: true
                            text: "Project files vs exports"
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(13)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            text: "Projects preserve editor state and overlays. Export JSONs from the editor, then use Outputs to import them into the game template. Folder shortcuts live in Settings."
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(10.5)
                            wrapMode: Text.Wrap
                            elide: Text.ElideRight
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }

        HoverCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.wide ? Theme.px(430) : -1
            Layout.minimumWidth: root.wide ? Theme.px(340) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 7 : 9)

                SectionHeading {
                    Layout.fillWidth: true
                    title: "2. Project browser"
                    subtitle: "Select exactly one saved editor project."
                }

                FastListView {
                    id: projects
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: Theme.px(360)
                    clip: true
                    model: editorService.projectModel
                    spacing: Theme.px(5)

                    delegate: GhostButton {
                        required property string name
                        required property string modifiedLabel
                        required property int index
                        width: projects.width
                        minimumWidth: 0
                        maximumTextWidth: Math.max(Theme.px(160), width - Theme.px(40))
                        text: name + "  •  " + modifiedLabel
                        toolTipText: "Select this saved editor project."
                        dense: root.compactHeight
                        onClicked: editorService.select(index)
                    }

                    ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
                }
            }
        }

        HoverCard {
            id: selectedProjectCard
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.wide ? Theme.px(620) : -1
            Layout.minimumWidth: root.wide ? Theme.px(430) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)
            strong: true

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 7 : 9)

                SectionHeading {
                    Layout.fillWidth: true
                    title: editorService.selectedName === "—" ? "3. Selected project" : "3. " + editorService.selectedName
                    subtitle: editorService.selectedPath || "Select a project from the browser."
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
                        title: "Select a project"
                        message: "A rendered project preview will appear here."
                    }
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(root.compactHeight ? 84 : 96)
                    soft: true

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(11)
                        spacing: Theme.px(10)

                        Text {
                            Layout.fillWidth: true
                            text: "Shapes: " + editorService.selectedShapes
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(10.8)
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }

                        PrimaryButton {
                            minimumWidth: Theme.px(170)
                            text: "Open Project"
                            toolTipText: "Open the selected project in the manual editor."
                            enabled: editorService.selectedPath.length > 0
                            onClicked: editorService.launchSelected()
                        }
                    }
                }
            }
        }
    }
}
