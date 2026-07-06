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
    property real pendingUiScale: settings.uiScale

    function roundedUiScale(value) {
        return Math.max(0.8, Math.min(1.35, Math.round(value * 20) / 20))
    }

    Connections {
        target: settings
        function onChanged() {
            if (!uiScaleSlider.pressed)
                root.pendingUiScale = settings.uiScale
        }
    }

    GridLayout {
        anchors.fill: parent
        columns: root.wide ? 3 : 1
        columnSpacing: Theme.px(12)
        rowSpacing: Theme.px(12)

        HoverCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.wide ? Theme.px(390) : -1
            Layout.minimumWidth: root.wide ? Theme.px(330) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)
            strong: true

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 7 : 10)

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(10)

                    Icon {
                        name: "settings"
                        iconSize: Theme.px(31)
                        glow: true
                        Layout.alignment: Qt.AlignVCenter
                    }

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "Interface"
                        subtitle: "Appearance and behavior preferences."
                    }
                }

                Label { text: "Theme preset" }
                KfpsComboBox {
                    Layout.fillWidth: true
                    dense: root.compactHeight
                    model: supporterService.availableThemes
                    currentIndex: Math.max(0, supporterService.availableThemes.indexOf(settings.theme))
                    enabled: supporterService.unlocked || supporterService.availableThemes.length > 1
                    onActivated: settings.theme = currentText
                }

                Text {
                    Layout.fillWidth: true
                    text: supporterService.unlocked
                          ? "Unlocked for " + supporterService.supporterLabel + ". Thank you for supporting KFPS."
                          : "Night Blossom is active."
                    color: Theme.subtle
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(10.2)
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }

                Label { text: "UI scale  •  " + Math.round(root.pendingUiScale * 100) + "%" }
                KfpsSlider {
                    id: uiScaleSlider
                    Layout.fillWidth: true
                    from: 0.8
                    to: 1.35
                    stepSize: 0.05
                    value: root.pendingUiScale
                    onMoved: root.pendingUiScale = root.roundedUiScale(value)
                    onPressedChanged: {
                        if (!pressed)
                            settings.uiScale = root.roundedUiScale(root.pendingUiScale)
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(1, Theme.px(1))
                    color: Theme.divider
                    opacity: 0.68
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(root.compactHeight ? 106 : 124)
                    soft: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(10)
                        spacing: Theme.px(6)

                        Text {
                            Layout.fillWidth: true
                            text: supporterService.unlocked ? "Local unlock active" : "Local unlock"
                            color: supporterService.unlocked ? Theme.primaryBright : Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(12.2)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: supporterService.status
                            color: supporterService.unlocked ? Theme.muted : Theme.subtle
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(9.8)
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.px(7)

                            PrimaryButton {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                text: supporterService.unlocked ? "Replace Unlock" : "Import Unlock"
                                iconName: "settings"
                                onClicked: {
                                    if (supporterService.importKey()) {
                                        settings.theme = supporterService.preferredTheme
                                    }
                                }
                            }

                            GhostButton {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                enabled: supporterService.unlocked
                                text: "Remove"
                                onClicked: {
                                    supporterService.removeKey()
                                    settings.theme = Theme.defaultThemeName
                                }
                            }
                        }
                    }
                }

                KfpsSwitch {
                    Layout.fillWidth: true
                    text: "Manual generator overrides"
                    checked: settings.manualOverrides
                    onToggled: settings.manualOverrides = checked
                }

                KfpsSwitch {
                    Layout.fillWidth: true
                    text: "Reduce nonessential motion"
                    checked: settings.reducedMotion
                    onToggled: settings.reducedMotion = checked
                }

                KfpsSwitch {
                    Layout.fillWidth: true
                    text: "Ambient branch and petals"
                    checked: settings.ambientMotion
                    enabled: !settings.reducedMotion
                    onToggled: settings.ambientMotion = checked
                }

                KfpsSwitch {
                    Layout.fillWidth: true
                    text: "Glass shadows and effects"
                    checked: settings.glassEffects
                    onToggled: settings.glassEffects = checked
                }

                Item { Layout.fillHeight: true }
            }
        }

        HoverCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.wide ? Theme.px(520) : -1
            Layout.minimumWidth: root.wide ? Theme.px(420) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 5 : 7)

                SectionHeading {
                    Layout.fillWidth: true
                    title: "Folders"
                    subtitle: "Upper half: important folders. Lower half: bundled changelog."
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: Theme.px(root.compactHeight ? 210 : 270)
                    soft: true

                    FastScrollView {
                        id: folderScroll
                        anchors.fill: parent
                        anchors.margins: Theme.px(9)
                        clip: true
                        contentWidth: availableWidth
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        ColumnLayout {
                            width: folderScroll.availableWidth
                            spacing: Theme.px(root.compactHeight ? 5 : 7)

                            QuickActionRow {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                iconName: "folder"
                                title: "Application root"
                                subtitle: desktop.appRoot
                                onClicked: desktop.openRoot()
                            }

                            QuickActionRow {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                iconName: "images"
                                title: "Source images"
                                subtitle: desktop.sourceImagesFolder
                                onClicked: desktop.openSourceImages()
                            }

                            QuickActionRow {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                iconName: "json"
                                title: "Generated outputs"
                                subtitle: desktop.generatedFolder
                                onClicked: desktop.openGenerated()
                            }

                            QuickActionRow {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                iconName: "transfer"
                                title: "Exported JSONs"
                                subtitle: desktop.exportedFolder
                                onClicked: desktop.openExported()
                            }

                            QuickActionRow {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                iconName: "editor"
                                title: "Editor projects"
                                subtitle: desktop.editorProjectsFolder
                                onClicked: desktop.openProjects()
                            }

                            QuickActionRow {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                iconName: "reports"
                                title: "Saved reports"
                                subtitle: desktop.reportsFolder
                                onClicked: desktop.openReports()
                            }
                        }
                    }
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: Theme.px(root.compactHeight ? 190 : 250)
                    soft: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(10)
                        spacing: Theme.px(7)

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                Layout.fillWidth: true
                                text: "Changelog"
                                color: Theme.primaryBright
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(12.2)
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }
                            GhostButton {
                                dense: true
                                text: "Refresh"
                                minimumWidth: Theme.px(74)
                                onClicked: changelogService.refresh()
                            }
                        }

                        FastListView {
                            id: settingsChangelog
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            model: changelogService.model
                            spacing: Theme.px(3)

                            delegate: Item {
                                required property string version
                                required property string summary
                                width: settingsChangelog.width
                                height: Theme.px(39)

                                Column {
                                    anchors.fill: parent
                                    spacing: Theme.px(1)
                                    Text {
                                        width: parent.width
                                        text: version
                                        color: Theme.success
                                        font.family: Theme.monoFamily
                                        font.pixelSize: Theme.px(9.8)
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        width: parent.width
                                        text: summary
                                        color: Theme.muted
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(10.1)
                                        elide: Text.ElideRight
                                    }
                                }
                            }

                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        }
                    }
                }
            }
        }

        HoverCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.wide ? Theme.px(390) : -1
            Layout.minimumWidth: root.wide ? Theme.px(330) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)
            strong: true

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 8 : 10)

                SectionHeading {
                    Layout.fillWidth: true
                    title: "Maintenance"
                    subtitle: "Updates, reports, and logs stay out of the creation flow."
                }

                PrimaryButton {
                    Layout.fillWidth: true
                    text: "Check Updates"
                    iconName: "update"
                    onClicked: appController.navigate("update")
                }

                GhostButton {
                    Layout.fillWidth: true
                    text: "Create Diagnostic Report"
                    iconName: "reports"
                    onClicked: appController.navigate("reports")
                }

                GhostButton {
                    Layout.fillWidth: true
                    text: "Open Runtime Logs"
                    iconName: "folder"
                    onClicked: desktop.openRuntime()
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
