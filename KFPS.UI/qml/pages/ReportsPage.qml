import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    anchors.fill: parent
    property bool wide: Theme.logical(width) >= 930

    Loader {
        anchors.fill: parent
        sourceComponent: root.wide ? wideComponent : compactComponent
    }

    Component {
        id: wideComponent
        GridLayout {
            columns: 2
            columnSpacing: Theme.px(10)

            HoverCard {
                Layout.preferredWidth: Math.max(Theme.px(410), parent.width * 0.44)
                Layout.fillHeight: true
                padding: Theme.px(18)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(9)

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "Report details"
                        subtitle: "Keep it specific: what happened, what you expected, and the last step that worked."
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: Theme.px(10)
                        ColumnLayout {
                            Layout.fillWidth: true
                            Label {
                                text: "Type"
                            }
                            KfpsComboBox {
                                id: reportType
                                Layout.fillWidth: true
                                model: ["Bug", "Suggestion"]
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Label {
                                text: "Title"
                            }
                            KfpsTextField {
                                id: reportTitle
                                Layout.fillWidth: true
                                placeholderText: "A useful one-line title"
                            }
                        }
                    }

                    Label {
                        text: "Details"
                    }
                    KfpsTextArea {
                        id: reportDetails
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        placeholderText: "What did you click? What happened? What should have happened? Include the last relevant log line."
                    }

                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.px(122)
                        soft: true
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.px(12)
                            spacing: Theme.px(5)
                            Label {
                                text: "Include context"
                            }
                            KfpsCheckBox {
                                id: includeContext
                                text: "App version and selected theme"
                                checked: true
                            }
                            KfpsCheckBox {
                                id: includeLog
                                text: "Visible runtime log (may contain filenames)"
                                checked: false
                            }
                            KfpsCheckBox {
                                id: includePaths
                                text: "Local paths (may contain your Windows username)"
                                checked: false
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Item {
                            Layout.fillWidth: true
                        }
                        PrimaryButton {
                            text: "Preview report"
                            iconName: "reports"
                            minimumWidth: Theme.px(132)
                            onClicked: reportService.previewReport(reportType.currentText, reportTitle.text, reportDetails.text, includeContext.checked, includeLog.checked, includePaths.checked)
                        }
                        GhostButton {
                            text: "Save local report"
                            iconName: "folder"
                            minimumWidth: Theme.px(142)
                            onClicked: reportService.saveReport(reportType.currentText, reportTitle.text, reportDetails.text, includeContext.checked, includeLog.checked, includePaths.checked)
                        }
                    }
                }
            }

            HoverCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                padding: Theme.px(18)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(10)

                    RowLayout {
                        Layout.fillWidth: true
                        SectionHeading {
                            Layout.fillWidth: true
                            title: "Preview"
                            subtitle: "This is exactly what will be saved locally."
                        }
                        GhostButton {
                            text: "Open saved reports"
                            iconName: "folder"
                            minimumWidth: Theme.px(148)
                            onClicked: desktop.openReports()
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: Theme.px(10)
                        color: Theme.previewSurfaceSoft
                        border.width: Math.max(1, Theme.px(1))
                        border.color: Theme.borderSoft
                        KfpsTextArea {
                            anchors.fill: parent
                            anchors.margins: Theme.px(1)
                            text: reportService.preview
                            readOnly: true
                            font.family: Theme.monoFamily
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: reportService.latestPath
                        visible: text.length > 0
                        color: Theme.subtle
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.px(9.5)
                        elide: Text.ElideMiddle
                        ToolTip.visible: pathHover.hovered
                        ToolTip.text: text
                        HoverHandler {
                            id: pathHover
                        }
                    }
                }
            }
        }
    }

    Component {
        id: compactComponent
        FastScrollView {
            id: compactScroll
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: compactScroll.availableWidth
                spacing: Theme.px(10)

                SectionHeading {
                    Layout.fillWidth: true
                    title: "Local feedback builder"
                    subtitle: "Reports stay on this computer until you choose to share them."
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(500)
                    padding: Theme.px(16)
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Theme.px(8)
                        KfpsComboBox {
                            id: compactType
                            Layout.fillWidth: true
                            model: ["Bug", "Suggestion"]
                        }
                        KfpsTextField {
                            id: compactTitle
                            Layout.fillWidth: true
                            placeholderText: "Report title"
                        }
                        KfpsTextArea {
                            id: compactDetails
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            placeholderText: "Describe the problem or suggestion in detail."
                        }
                        KfpsCheckBox {
                            id: compactContext
                            text: "Include app version and theme"
                            checked: true
                        }
                        KfpsCheckBox {
                            id: compactLog
                            text: "Include visible runtime log"
                        }
                        KfpsCheckBox {
                            id: compactPaths
                            text: "Include local paths"
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            PrimaryButton {
                                Layout.fillWidth: true
                                text: "Preview"
                                onClicked: reportService.previewReport(compactType.currentText, compactTitle.text, compactDetails.text, compactContext.checked, compactLog.checked, compactPaths.checked)
                            }
                            GhostButton {
                                Layout.fillWidth: true
                                text: "Save"
                                onClicked: reportService.saveReport(compactType.currentText, compactTitle.text, compactDetails.text, compactContext.checked, compactLog.checked, compactPaths.checked)
                            }
                        }
                    }
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(420)
                    padding: Theme.px(16)
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Theme.px(8)
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "Preview"
                                color: Theme.primaryBright
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(14)
                                font.weight: Font.DemiBold
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                            GhostButton {
                                text: "Open reports"
                                iconName: "folder"
                                onClicked: desktop.openReports()
                            }
                        }
                        KfpsTextArea {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            text: reportService.preview
                            readOnly: true
                            font.family: Theme.monoFamily
                        }
                    }
                }
            }
        }
    }
}
