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
    readonly property bool activationNeedsRepair: [
        "duplicate", "not_eligible", "network_error", "service_error", "deactivated", "revoked"
    ].indexOf(supporterService.activationState) >= 0
    readonly property bool headerAlignmentAvailable: root.wide
                                                     && interfaceCard.width > 0
                                                     && foldersCard.width > 0
    readonly property real headerSourceCenterX: interfaceCard.x + interfaceCard.width / 2
    readonly property real headerPreviewCenterX: foldersCard.x + foldersCard.width / 2
    readonly property real headerBannerLeftX: interfaceCard.x
    readonly property real headerBannerRightX: foldersCard.x + foldersCard.width

    FastScrollView {
        id: pageScroll
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

    GridLayout {
        width: pageScroll.availableWidth
        height: root.wide ? pageScroll.availableHeight : implicitHeight
        columns: root.wide ? 3 : 1
        columnSpacing: Theme.px(12)
        rowSpacing: Theme.px(12)

        HoverCard {
            id: interfaceCard
            Layout.fillWidth: true
            Layout.fillHeight: root.wide
            Layout.preferredHeight: root.wide
                                    ? -1
                                    : Math.max(Theme.px(610), interfaceContent.implicitHeight + padding * 2)
            Layout.preferredWidth: root.wide ? Theme.px(390) : -1
            Layout.minimumWidth: root.wide ? Theme.px(330) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)
            strong: true

            ColumnLayout {
                id: interfaceContent
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
                    toolTipText: "Choose the app's color and surface style. Extra themes become available with a supporter key."
                    onActivated: settings.theme = currentText
                }

                Text {
                    Layout.fillWidth: true
                    text: supporterService.unlocked
                          ? "Unlocked for " + supporterService.supporterLabel + ". Thank you for supporting KFPS."
                          : Theme.activeThemeName + " is active."
                    color: Theme.subtle
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(10.2)
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }

                KfpsSwitch {
                    Layout.fillWidth: true
                    visible: Theme.terminalMode
                    text: "Green terminal text"
                    checked: settings.terminalGreenText
                    toolTipText: "Switch Command Prompt text between white and phosphor green. This setting affects only the Command Prompt theme."
                    onToggled: settings.terminalGreenText = checked
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(1, Theme.px(1))
                    color: Theme.divider
                    opacity: 0.68
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(root.compactHeight ? 132 : 150)
                    soft: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(10)
                        spacing: Theme.px(6)

                        Text {
                            Layout.fillWidth: true
                            text: supporterService.activationStateLabel
                            color: supporterService.unlocked
                                   ? Theme.primaryBright
                                   : (supporterService.keyValid ? Theme.warning : Theme.muted)
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(12.2)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: supporterService.status
                                  + "\nOne-time anonymous registration sends no name, email, hardware details, artwork, or file paths. Activated devices need no recurring check."
                            color: supporterService.unlocked ? Theme.muted : Theme.subtle
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(9.8)
                            wrapMode: Text.Wrap
                            maximumLineCount: 4
                            elide: Text.ElideRight
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.px(7)

                            PrimaryButton {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                text: supporterService.unlocked ? "Replace Key" : "Add Supporter Key"
                                iconName: "settings"
                                toolTipText: "Choose a supporter key file. KFPS registers a valid key automatically when needed."
                                onClicked: {
                                    if (supporterService.importKey()) {
                                        settings.theme = supporterService.preferredTheme
                                    }
                                }
                            }

                            GhostButton {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                enabled: supporterService.keyValid
                                         && (supporterService.activationState !== "active"
                                             || supporterService.canDeactivate)
                                         && (!root.activationNeedsRepair || supporterService.canRepair)
                                text: supporterService.activationState === "active"
                                      ? (supporterService.canDeactivate ? "Release Device" : "Releasing...")
                                      : (root.activationNeedsRepair
                                         ? (supporterService.activationState === "deactivated" ? "Register Again" : "Retry")
                                         : "Remove")
                                toolTipText: supporterService.activationState === "active"
                                             ? "Release this device so the supporter key can be registered on another computer."
                                             : (root.activationNeedsRepair
                                                ? "Try the supporter-key registration again after checking the connection."
                                                : "Remove the supporter key from this KFPS installation.")
                                onClicked: {
                                    if (supporterService.activationState === "active") {
                                        supporterService.deactivateDevice()
                                    } else if (root.activationNeedsRepair) {
                                        supporterService.repairActivation()
                                    } else {
                                        supporterService.removeKey()
                                        settings.theme = Theme.defaultThemeName
                                    }
                                }
                            }
                        }
                    }
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? Theme.px(root.compactHeight ? 96 : 116) : 0
                    visible: Theme.activeThemeName === Theme.defaultThemeName
                             && supporterService.activationState === "no_key"
                    strong: true
                    glow: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(10)
                        spacing: Theme.px(6)

                        Text {
                            Layout.fillWidth: true
                            text: "Supporter extras"
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(12.4)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "One-click FH6 save-library exports and supporter themes are available with a supporter key."
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(9.6)
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }

                        PrimaryButton {
                            Layout.fillWidth: true
                            dense: root.compactHeight
                            text: "Get Supporter Key"
                            iconName: "heart"
                            toolTipText: "Open the KFPS supporter page in your web browser."
                            onClicked: desktop.openUrl("https://ko-fi.com/s/2d1507698d")
                        }
                    }
                }

                KfpsSwitch {
                    Layout.fillWidth: true
                    text: "Manual generator overrides"
                    checked: settings.manualOverrides
                    toolTipText: "Show advanced generator values on Create. Normal users should leave this off; presets fill these values automatically."
                    onToggled: settings.manualOverrides = checked
                }

                KfpsSwitch {
                    Layout.fillWidth: true
                    text: "Reduce nonessential motion"
                    checked: settings.reducedMotion
                    toolTipText: "Turn off decorative and nonessential animation while keeping all app functions available."
                    onToggled: settings.reducedMotion = checked
                }

                KfpsSwitch {
                    Layout.fillWidth: true
                    text: "Ambient background motion"
                    checked: settings.ambientMotion
                    enabled: !settings.reducedMotion
                    toolTipText: "Show or hide the current theme's quiet background animation."
                    onToggled: settings.ambientMotion = checked
                }

                KfpsSwitch {
                    Layout.fillWidth: true
                    text: "Glass shadows and effects"
                    checked: settings.glassEffects
                    toolTipText: "Enable or disable decorative glass shadows and effects. Turning them off may help slower graphics hardware."
                    onToggled: settings.glassEffects = checked
                }

                KfpsSwitch {
                    Layout.fillWidth: true
                    text: "Show live status ticker"
                    checked: settings.liveStatusVisible
                    toolTipText: "Show or hide the scrolling KFPS live-status message at the top of every page. Status checks continue while it is hidden."
                    onToggled: settings.liveStatusVisible = checked
                }

                Item { Layout.fillHeight: true }
            }
        }

        HoverCard {
            id: foldersCard
            Layout.fillWidth: true
            Layout.fillHeight: root.wide
            Layout.preferredHeight: root.wide
                                    ? -1
                                    : Math.max(Theme.px(350), foldersContent.implicitHeight + padding * 2)
            Layout.preferredWidth: root.wide ? Theme.px(520) : -1
            Layout.minimumWidth: root.wide ? Theme.px(420) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)

            ColumnLayout {
                id: foldersContent
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 5 : 7)

                SectionHeading {
                    Layout.fillWidth: true
                    title: "Folders"
                    subtitle: "Important local folders and shortcuts."
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
                                toolTipText: "Open the main KFPS installation folder in File Explorer."
                                onClicked: desktop.openRoot()
                            }

                            QuickActionRow {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                iconName: "images"
                                title: "Source images"
                                subtitle: desktop.sourceImagesFolder
                                toolTipText: "Open the folder where KFPS keeps copied source images."
                                onClicked: desktop.openSourceImages()
                            }

                            QuickActionRow {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                iconName: "json"
                                title: "Generated outputs"
                                subtitle: desktop.generatedFolder
                                toolTipText: "Open generated jobs, final JSON files, previews, checkpoints, and reports."
                                onClicked: desktop.openGenerated()
                            }

                            QuickActionRow {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                iconName: "transfer"
                                title: "Exported JSONs"
                                subtitle: desktop.exportedFolder
                                toolTipText: "Open JSON files exported from a running game or local game save."
                                onClicked: desktop.openExported()
                            }

                            QuickActionRow {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                iconName: "editor"
                                title: "Editor projects"
                                subtitle: desktop.editorProjectsFolder
                                toolTipText: "Open saved manual-editor project files."
                                onClicked: desktop.openProjects()
                            }

                            QuickActionRow {
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                iconName: "reports"
                                title: "Saved reports"
                                subtitle: desktop.reportsFolder
                                toolTipText: "Open locally saved diagnostic and feedback reports."
                                onClicked: desktop.openReports()
                            }
                        }
                    }
                }

            }
        }

        HoverCard {
            id: maintenanceCard
            Layout.fillWidth: true
            Layout.fillHeight: root.wide
            Layout.preferredHeight: root.wide
                                    ? -1
                                    : Math.max(Theme.px(210), maintenanceContent.implicitHeight + padding * 2)
            Layout.preferredWidth: root.wide ? Theme.px(390) : -1
            Layout.minimumWidth: root.wide ? Theme.px(330) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)
            strong: true

            ColumnLayout {
                id: maintenanceContent
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 8 : 10)

                SectionHeading {
                    Layout.fillWidth: true
                    title: "Maintenance"
                    subtitle: "Reports and logs stay out of the creation flow. Updates have their own tab."
                }

                GhostButton {
                    Layout.fillWidth: true
                    text: "Create Report"
                    iconName: "reports"
                    toolTipText: "Open the report builder to describe a bug or suggestion."
                    onClicked: appController.navigate("reports")
                }

                GhostButton {
                    Layout.fillWidth: true
                    text: "Open Logs"
                    iconName: "folder"
                    toolTipText: "Open the folder containing KFPS runtime log files."
                    onClicked: desktop.openRuntime()
                }

                GhostButton {
                    Layout.fillWidth: true
                    text: "Reset Editor Tutorial"
                    iconName: "help"
                    toolTipText: "Show the manual editor's first-run tutorial again the next time the editor opens."
                    onClicked: editorService.resetTutorial()
                }

                GhostButton {
                    Layout.fillWidth: true
                    text: jsonService.thumbnailRegenerating ? "Regenerating..." : "Regenerate Local Thumbnails"
                    iconName: "refresh"
                    enabled: !jsonService.thumbnailRegenerating
                    toolTipText: "Replace every Generated, Editor, Game Export, and Library thumbnail with the current renderer. JSON files, source artwork, and personal adjacent PNGs are not changed; KFPS-managed previews are replaced."
                    onClicked: jsonService.regenerateLocalThumbnails()
                }

                Text {
                    Layout.fillWidth: true
                    visible: jsonService.thumbnailStatus.length > 0
                    text: jsonService.thumbnailStatus
                    color: Theme.subtle
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(9.4)
                    wrapMode: Text.Wrap
                }

                Text {
                    Layout.fillWidth: true
                    visible: editorService.status.length > 0
                    text: "Editor: " + editorService.status
                    color: editorService.lastError.length > 0 ? Theme.danger : Theme.subtle
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(9.4)
                    wrapMode: Text.Wrap
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
    }
}
