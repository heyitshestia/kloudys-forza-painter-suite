import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"
import "../themes/redline"

Item {
    id: root
    anchors.fill: parent
    clip: true

    function focusSetting(key) {
        var item = ({theme: themePreset, chrome: editorChromeToggle, motion: reducedMotionToggle,
                     folders: foldersCard, session: sessionToggle})[key]
        if (!item) return
        if (redlineInterface)
            selectedSection = key === "folders" ? 1 : key === "chrome" ? 2 : 0
        Qt.callLater(function() {
            var pos = item.mapToItem(pageScroll.contentItem, 0, 0)
            pageScroll.contentItem.contentY = Math.max(0, Math.min(
                pageScroll.contentItem.contentHeight - pageScroll.availableHeight,
                pageScroll.contentItem.contentY + pos.y - Theme.px(12)))
            item.forceActiveFocus()
        })
    }

    readonly property var session: typeof workspaceTools !== "undefined" ? workspaceTools.session : null
    readonly property bool redlineInterface: Theme.chromeMetric("redlineInterface", 0) > 0
    property int selectedSection: 0
    property bool wide: !redlineInterface && Theme.logical(width) >= 1120
    property bool compactHeight: Theme.logical(height) < 720
    readonly property bool headerAlignmentAvailable: root.wide
                                                     && interfaceCard.width > 0
                                                     && foldersCard.width > 0
    readonly property real headerSourceCenterX: interfaceCard.x + interfaceCard.width / 2
    readonly property real headerPreviewCenterX: foldersCard.x + foldersCard.width / 2
    readonly property real headerBannerLeftX: interfaceCard.x
    readonly property real headerBannerRightX: foldersCard.x + foldersCard.width

    Timer {
        interval: 2000
        repeat: true
        triggeredOnStart: true
        running: root.visible && (settings.editorUseChrome || settings.liveryUseChrome)
        onTriggered: desktop.refreshChromeStatus()
    }

    ColumnLayout {
        visible: root.redlineInterface
        width: Theme.px(210)
        spacing: Theme.px(12)
        RedlineText { text: "SETTINGS"; heading: true; color: Theme.primary; Layout.bottomMargin: Theme.px(12) }
        Repeater {
            model: ["INTERFACE", "FOLDERS", "MAINTENANCE"]
            RedlineButton {
                required property int index
                required property string modelData
                objectName: "RedlineSettingsSection:" + index
                Layout.fillWidth: true
                menuEntry: true; minimal: true; displayText: true
                text: modelData; slotNumber: "0" + (index + 1)
                selected: root.selectedSection === index
                onClicked: {
                    root.selectedSection = index
                    if (pageScroll.contentItem && pageScroll.contentItem.contentY !== undefined)
                        pageScroll.contentItem.contentY = 0
                }
            }
        }
    }

    FastScrollView {
        id: pageScroll
        anchors.fill: parent
        anchors.leftMargin: root.redlineInterface ? Theme.px(250) : 0
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

    GridLayout {
        width: root.redlineInterface ? Math.min(pageScroll.availableWidth, Theme.px(880)) : pageScroll.availableWidth
        height: root.wide ? Math.max(pageScroll.availableHeight, implicitHeight) : implicitHeight
        columns: root.wide ? 3 : 1
        columnSpacing: Theme.px(12)
        rowSpacing: Theme.px(12)

        HoverCard {
            id: interfaceCard
            visible: !root.redlineInterface || root.selectedSection === 0
            Layout.fillWidth: true
            Layout.fillHeight: root.wide
            Layout.minimumHeight: interfaceContent.implicitHeight + padding * 2
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

                KfpsSwitch {
                    id: sessionToggle
                    objectName: "WorkspaceSessionToggle"
                    Layout.fillWidth: true
                    visible: root.session !== null
                    text: qsTr("Reopen previous workspace")
                    checked: root.session ? root.session.restoreEnabled : false
                    toolTipText: qsTr("Restore saved tool tabs on startup. Tools load only when selected; unsaved recovery stays separate.")
                    onToggled: if (root.session) root.session.restoreEnabled = checked
                }
                GhostButton {
                    objectName: "WorkspaceSessionReopen"
                    Layout.fillWidth: true
                    visible: root.session !== null
                    enabled: root.session ? root.session.previousAvailable : false
                    text: qsTr("Reopen previous tabs")
                    iconName: "folder"
                    toolTipText: root.session ? root.session.status : ""
                    onClicked: if (root.session) root.session.restorePrevious()
                }

                Label { text: "Theme preset" }
                KfpsComboBox {
                    id: themePreset
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
                    font.pixelSize: Theme.textSize(10.2)
                    font.weight: Theme.bodyWeight
                    lineHeight: Theme.bodyLineHeight
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

                KfpsSwitch {
                    objectName: "Ps2IntroMuteSetting"
                    Layout.fillWidth: true
                    visible: Theme.activeThemeName === "Original PS2"
                    text: qsTr("Mute intro sound")
                    checked: settings.ps2StartupMuted
                    toolTipText: qsTr("Mute the PS2 startup animation. Saved for future launches.")
                    onToggled: settings.ps2StartupMuted = checked
                }

                KfpsSwitch {
                    objectName: "XboxIntroMuteSetting"
                    Layout.fillWidth: true
                    visible: Theme.activeThemeName === "Original Xbox"
                    text: qsTr("Mute intro sound")
                    checked: settings.xboxStartupMuted
                    toolTipText: qsTr("Mute the Xbox startup animation. Saved for future launches.")
                    onToggled: settings.xboxStartupMuted = checked
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(1, Theme.px(1))
                    color: Theme.divider
                    opacity: 0.68
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(Theme.px(root.compactHeight ? 132 : 150),
                                                     supporterKeyContent.implicitHeight + Theme.px(20))
                    soft: true

                    ColumnLayout {
                        id: supporterKeyContent
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
                            font.pixelSize: Theme.textSize(12.2)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: supporterService.status
                                  + "\nExisting keys unlock supporter themes locally. No PC binding or online activation."
                            color: supporterService.unlocked ? Theme.muted : Theme.subtle
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.textSize(9.8)
                            font.weight: Theme.bodyWeight
                            lineHeight: Theme.bodyLineHeight
                            wrapMode: Text.Wrap
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.px(7)

                            PrimaryButton {
                                objectName: "AddSupporterThemeKey"
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                text: supporterService.unlocked ? "Replace Key" : "Add Supporter Key"
                                iconName: "settings"
                                toolTipText: "Choose an existing signed supporter key to unlock the exclusive themes."
                                onClicked: {
                                    if (supporterService.importKey()) {
                                        settings.theme = supporterService.preferredTheme
                                    }
                                }
                            }

                            GhostButton {
                                objectName: "RemoveSupporterThemeKey"
                                Layout.fillWidth: true
                                dense: root.compactHeight
                                enabled: supporterService.keyValid
                                text: "Remove Key"
                                toolTipText: "Remove local theme-key files. Your Community Verified status and projects are unchanged."
                                onClicked: {
                                    supporterService.removeKey()
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
                            text: "Supporter themes"
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.textSize(12.4)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "Existing supporter keys unlock four exclusive themes. All local tools are free."
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.textSize(9.6)
                            font.weight: Theme.bodyWeight
                            lineHeight: Theme.bodyLineHeight
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }

                        PrimaryButton {
                            Layout.fillWidth: true
                            dense: root.compactHeight
                            text: "Support KFPS"
                            iconName: "heart"
                            toolTipText: "Open Ko-fi for an optional donation. Donations do not issue a key."
                            onClicked: desktop.openUrl("https://ko-fi.com/O7O020EQNQ")
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
                    id: reducedMotionToggle
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
            visible: !root.redlineInterface || root.selectedSection === 1
            Layout.fillWidth: true
            Layout.fillHeight: root.wide
            Layout.minimumHeight: foldersContent.implicitHeight + padding * 2
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
            visible: !root.redlineInterface || root.selectedSection === 2
            Layout.fillWidth: true
            Layout.fillHeight: root.wide
            Layout.minimumHeight: maintenanceContent.implicitHeight + padding * 2
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

                KfpsCheckBox {
                    objectName: "editorChromeToggle"
                    id: editorChromeToggle
                    Layout.fillWidth: true
                    dense: root.compactHeight
                    text: "Use Google Chrome for editor"
                    checked: settings.editorUseChrome
                    toolTipText: "Applies after closing and reopening the editor, including KFPS Editor.exe. Uses installed Google Chrome with a separate KFPS profile, not your personal tabs."
                    onToggled: settings.editorUseChrome = checked
                }

                Label {
                    objectName: "editorChromeStatus"
                    Layout.fillWidth: true
                    visible: settings.editorUseChrome || settings.liveryUseChrome
                    text: desktop.chromeInstalled ? "Google Chrome: installed" : "Google Chrome: not found"
                    wrapMode: Text.WordWrap
                }

                GhostButton {
                    objectName: "editorChromeDownload"
                    Layout.fillWidth: true
                    visible: (settings.editorUseChrome || settings.liveryUseChrome) && !desktop.chromeInstalled
                    text: "Install Google Chrome..."
                    iconName: "external"
                    toolTipText: "Open Google's official setup page. Complete installation there; KFPS detects it automatically. No silent install or default-browser change."
                    onClicked: desktop.openChromeInstallPage()
                }

                Label {
                    Layout.fillWidth: true
                    visible: (settings.editorUseChrome || settings.liveryUseChrome) && desktop.chromeInstallError !== ""
                    text: desktop.chromeInstallError
                    wrapMode: Text.WordWrap
                }

                KfpsCheckBox {
                    objectName: "liveryChromeToggle"
                    Layout.fillWidth: true
                    dense: root.compactHeight
                    text: "Use Google Chrome for Livery Studio"
                    checked: settings.liveryUseChrome
                    toolTipText: "Off opens a standalone native window. On uses installed Chrome with a separate Studio profile. Applies to Studio opened from KFPS, the editor, or the Studio shortcut after closing and reopening it."
                    onToggled: settings.liveryUseChrome = checked
                }

                Label { text: "Editor / Studio graphics (restart windows)"; enabled: !settings.editorUseChrome || !settings.liveryUseChrome }
                KfpsComboBox {
                    objectName: "editorGraphicsSelector"
                    Layout.fillWidth: true
                    dense: root.compactHeight
                    enabled: !settings.editorUseChrome || !settings.liveryUseChrome
                    model: ["Auto", "OpenGL", "Direct3D 11"]
                    currentIndex: ["auto", "opengl", "d3d11"].indexOf(settings.editorGraphics)
                    toolTipText: "Auto preserves OpenGL except for confirmed hardware and driver compatibility rules. Applies to native editor and Livery Studio windows after closing and reopening them. Chrome manages its own graphics."
                    onActivated: settings.editorGraphics = ["auto", "opengl", "d3d11"][currentIndex]
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
                    font.pixelSize: Theme.textSize(9.4)
                    font.weight: Theme.bodyWeight
                    lineHeight: Theme.bodyLineHeight
                    wrapMode: Text.Wrap
                }

                Text {
                    Layout.fillWidth: true
                    visible: editorService.status.length > 0
                    text: "Editor: " + editorService.status
                    color: editorService.lastError.length > 0 ? Theme.danger : Theme.subtle
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.textSize(9.4)
                    font.weight: Theme.bodyWeight
                    lineHeight: Theme.bodyLineHeight
                    wrapMode: Text.Wrap
                }

                ActivitySettings {
                    Layout.fillWidth: true
                    service: activityService
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
    }
}
