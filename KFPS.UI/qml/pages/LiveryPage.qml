import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Dialogs 6.7
import QtQuick.Layouts 6.7
import QtWebEngine
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    objectName: "LiveryPage"
    anchors.fill: parent
    clip: true

    readonly property bool wide: Theme.logical(width) >= 1180
    readonly property bool compactHeight: Theme.logical(height) < 760
    property bool pageActive: true
    property bool wipNoticeAcknowledged: false
    property bool showGallery: true
    // WebEngine treats a repeated URL assignment as navigation. This string
    // changes only for a new session, unlike the service's shared status signal.
    readonly property string viewerSessionUrl: fullLiveryService.viewerUrl
    readonly property string viewerThemeJson: JSON.stringify(studioThemeContext())
    signal wipNoticeAccepted()

    function studioThemeContext() {
        // Qt serializes translucent colors as ARGB; CSS requires explicit RGBA.
        function color(value) {
            return "rgba(" + Math.round(value.r * 255) + "," + Math.round(value.g * 255)
                    + "," + Math.round(value.b * 255) + "," + value.a.toFixed(4) + ")"
        }
        const variables = {
            "--bg": Theme.backgroundA, "--shell": Theme.backgroundB,
            "--panel": Theme.surface, "--panel2": Theme.surfaceRaised, "--panel3": Theme.fieldSurface,
            "--text": Theme.text, "--muted": Theme.muted, "--soft": Theme.subtle,
            "--line": Theme.border, "--line2": Theme.borderStrong,
            "--accent": Theme.primary, "--accent2": Theme.signalSecondary,
            "--good": Theme.success, "--warn": Theme.warning, "--danger": Theme.danger,
            "--canvas-bg": Theme.previewSurfaceSoft, "--fabric-canvas-bg": Theme.previewSurface,
            "--editor-grid-line": Theme.borderSoft, "--editor-grid-axis": Theme.borderStrong,
            "--editor-guide-line": Theme.signalSecondary, "--editor-guide-selected": Theme.primaryBright,
            "--editor-guide-draft": Theme.primary, "--editor-notch-line": Theme.borderStrong,
            "--editor-notch-muted": Theme.muted, "--editor-notch-active": Theme.primaryBright,
            "--editor-selection-border": Theme.primary, "--editor-shape-outline": Theme.text,
            "--editor-selection-corner": Theme.primaryBright, "--editor-selection-corner-stroke": Theme.surfaceStrong,
            "--editor-skew-corner": Theme.warning, "--shape-tile-bg": Theme.fieldSurface,
            "--dialog-bg": Theme.surfaceStrong, "--dialog-header": Theme.surfaceRaised
        }
        Object.keys(variables).forEach(key => variables[key] = color(variables[key]))
        const fonts = []
        if (Theme.classicMode && Theme.classicFontFamily !== "Microsoft Sans Serif" && Theme.classicFontFamily !== "sans-serif")
            fonts.push({family: Theme.classicFontFamily, asset: "fonts/windows94/W95FA.otf"})
        else if (!Theme.terminalMode && Theme.loadedUiFontFamily.length && Theme.uiFontFile.length)
            fonts.push({family: Theme.loadedUiFontFamily, asset: Theme.uiFontFile})
        return {name: Theme.activeThemeName, variables: variables, fontFamily: Theme.fontFamily, fontAssets: fonts}
    }

    function openSelectedLivery() {
        if (fullLiveryService.selectedSource.length === 0 || fullLiveryService.gameFolder.length === 0)
            return
        showGallery = false
        fullLiveryService.previewSelectedSource()
    }

    function returnToGallery() {
        fullLiveryService.showSourceGrid()
        showGallery = true
    }

    onViewerSessionUrlChanged: {
        if (viewerSessionUrl.length > 0)
            showGallery = false
    }

    function dismissWipNotice() {
        wipNoticeAcknowledged = true
        wipNoticeAccepted()
    }

    Component.onCompleted: {
        fullLiveryService.setSourceSearch("")
        if (pageActive)
            fullLiveryService.activate()
    }

    onPageActiveChanged: {
        if (pageActive)
            fullLiveryService.activate()
        else {
            root.returnToGallery()
            fullLiveryService.deactivate()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.px(10)

        GlassPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: toolbarContent.implicitHeight + Theme.px(20)
            strong: true

            RowLayout {
                id: toolbarContent
                anchors.fill: parent
                anchors.margins: Theme.px(10)
                spacing: Theme.px(8)

                Icon {
                    name: "monitor"
                    iconSize: Theme.px(30)
                    glow: true
                    Layout.alignment: Qt.AlignVCenter
                }

                SectionHeading {
                    Layout.fillWidth: true
                    title: root.showGallery ? "Liveries" : "Full Livery Workshop"
                    subtitle: root.showGallery ? fullLiveryService.status : fullLiveryService.summary
                    HoverHandler { id: liveryStatusHover }
                    KfpsToolTip {
                        visible: liveryStatusHover.hovered
                        text: fullLiveryService.summary
                    }
                }

                KfpsComboBox {
                    dense: true
                    visible: !root.showGallery
                    Layout.preferredWidth: Theme.px(130)
                    model: ["Standard", "High"]
                    currentIndex: fullLiveryService.viewerQuality - 1
                    enabled: fullLiveryService.featureEnabled
                    onActivated: fullLiveryService.setViewerQuality(currentIndex + 1)
                    objectName: "LiveryVinylResolution"
                    toolTipText: "Vinyl resolution: Standard uses the previous High detail. High doubles width and height and uses more memory."
                    Accessible.name: "Vinyl resolution"
                }

                GhostButton {
                    objectName: "launchLiveryStudioButton"
                    dense: true
                    text: editorService.studioLaunching ? "Starting..." : "Livery Studio"
                    iconName: "editor"
                    enabled: !editorService.studioLaunching
                    toolTipText: editorService.studioStatus.length > 0 ? editorService.studioStatus : "Open the independent car and vinyl workspace."
                    onClicked: editorService.launchLiveryStudio(root.studioThemeContext())
                }

                GhostButton {
                    dense: true
                    text: fullLiveryService.gameFolder.length > 0 ? "FH6 Linked" : "FH6 Folder"
                    iconName: "folder"
                    enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                    toolTipText: fullLiveryService.gameFolder.length > 0
                                 ? "FH6 is linked at " + fullLiveryService.gameFolder + ". Choose this again to change it."
                                 : "Choose the local FH6 game or Content folder used to resolve car IDs and meshes."
                    onClicked: fullLiveryService.chooseGameFolder()
                }

                GhostButton {
                    dense: true
                    text: "Save Folder"
                    iconName: "folder"
                    enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                    toolTipText: "Choose the FH6 GameSave root if it was not found automatically."
                    onClicked: fullLiveryService.chooseSaveRoot()
                }

                GhostButton {
                    objectName: "clearFullLiveryCacheButton"
                    dense: true
                    text: "Clear Cache"
                    iconName: "refresh"
                    enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                    toolTipText: "Remove rebuilt full-livery previews, car meshes, and indexes. Saved liveries and packages are kept."
                    onClicked: fullLiveryService.clearFullLiveryCache()
                }

                GhostButton {
                    dense: true
                    text: "Diagnostics"
                    iconName: "reports"
                    enabled: !fullLiveryService.running
                    toolTipText: "Export privacy-scrubbed livery worker, cache, crash-recovery, and environment diagnostics."
                    onClicked: fullLiveryService.exportDiagnostics()
                }

                PrimaryButton {
                    dense: true
                    text: fullLiveryService.running ? "Working..." : "Scan Saves"
                    iconName: "refresh"
                    enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                    toolTipText: "Find unique full-car FH6 livery records without changing the save."
                    onClicked: fullLiveryService.scanSaves()
                }


                Text {
                    text: fullLiveryService.featureStage.toUpperCase()
                    color: fullLiveryService.featureStable ? Theme.success : Theme.warning
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.px(9.5)
                    font.weight: Font.DemiBold
                }
            }
        }

        Text {
            Layout.fillWidth: true
            visible: editorService.studioStatus.length > 0
            text: editorService.studioStatus
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(12)
            wrapMode: Text.Wrap
        }

        GridLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            columns: root.wide && !root.showGallery ? 3 : 2
            columnSpacing: Theme.px(10)
            rowSpacing: Theme.px(10)

            GlassPanel {
                Layout.fillHeight: true
                Layout.preferredWidth: Theme.px(330)
                Layout.minimumWidth: Theme.px(280)
                Layout.maximumWidth: Theme.px(390)
                soft: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.px(11)
                    spacing: Theme.px(7)

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: "Local FH6 liveries"
                            color: Theme.text
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(15)
                            font.weight: Font.DemiBold
                        }
                        Text {
                            text: liveryGrid.count
                            color: Theme.subtle
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.px(10)
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: fullLiveryService.selectedSource.length > 0 ? fullLiveryService.selectedTitle : "No livery selected"
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(12)
                        wrapMode: Text.Wrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                    }

                    Text {
                        Layout.fillWidth: true
                        visible: fullLiveryService.selectedSource.length > 0
                        text: fullLiveryService.selectedVehicle + "\n" + fullLiveryService.selectedCounts
                        textFormat: Text.PlainText
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(10.5)
                        wrapMode: Text.Wrap
                    }

                    PrimaryButton {
                        objectName: "openSelectedLiveryPreviewButton"
                        Layout.fillWidth: true
                        dense: true
                        text: "Open 3D Preview"
                        iconName: "monitor"
                        enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                                 && fullLiveryService.selectedSource.length > 0
                                 && fullLiveryService.gameFolder.length > 0
                        toolTipText: fullLiveryService.gameFolder.length > 0
                                     ? "Render the selected livery on its exact car."
                                     : "Link the FH6 game folder to enable 3D previews."
                        onClicked: root.openSelectedLivery()
                    }

                    GhostButton {
                        objectName: "returnToLiveryGridButton"
                        Layout.fillWidth: true
                        dense: true
                        visible: !root.showGallery
                        text: "Back to Liveries"
                        iconName: "chevron-left"
                        toolTipText: "Close the 3D preview and return to the livery grid without changing your selection."
                        onClicked: root.returnToGallery()
                    }

                    PrimaryButton {
                        Layout.fillWidth: true
                        dense: true
                        text: fullLiveryService.running ? "Packaging..." : "Export Selected"
                        iconName: "transfer"
                        enabled: !fullLiveryService.running
                                 && fullLiveryService.featureEnabled
                                 && fullLiveryService.selectedSource.length > 0
                                 && fullLiveryService.selectedSourceExportable
                        toolTipText: fullLiveryService.selectedSourceExportable
                                     ? "Create a verified shareable package and add it directly to Saved packages. Game meshes stay local."
                                     : fullLiveryService.selectedSourcePrivacyMessage
                        onClicked: fullLiveryService.exportSelected()
                    }

                    Text {
                        Layout.fillWidth: true
                        visible: fullLiveryService.selectedSource.length > 0
                                 && !fullLiveryService.selectedSourceExportable
                        text: fullLiveryService.selectedSourcePrivacyMessage
                        color: Theme.warning
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(10.5)
                        wrapMode: Text.WordWrap
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(1, Theme.px(1))
                        color: Theme.divider
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: "Saved packages"
                            color: Theme.text
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(15)
                            font.weight: Font.DemiBold
                        }
                        GhostButton {
                            objectName: "addFullLiveryPackageButton"
                            dense: true
                            text: "Add"
                            iconName: "folder"
                            enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                            toolTipText: "Validate and add a received .kfpslivery package to this KFPS instance."
                            onClicked: fullLiveryService.choosePackage()
                        }
                    }

                    Text {
                        objectName: "fullLiveryPackageAddError"
                        Layout.fillWidth: true
                        visible: fullLiveryService.packageAddError.length > 0
                        text: "Package not added: " + fullLiveryService.packageAddError
                        textFormat: Text.PlainText
                        color: Theme.danger
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(11)
                        wrapMode: Text.Wrap
                        maximumLineCount: 5
                        elide: Text.ElideRight
                        HoverHandler { id: packageAddErrorHover }
                        ToolTip.visible: visible && packageAddErrorHover.hovered
                        ToolTip.text: text
                    }

                    FastListView {
                        id: packages
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: Theme.px(150)
                        model: fullLiveryService.packageModel
                        spacing: Theme.px(3)
                        clip: true

                        delegate: Item {
                            id: packageDelegate
                            required property string title
                            required property string path
                            required property string modelCode
                            required property int placementCount
                            required property bool portableMesh
                            width: packages.width
                            height: packageRow.implicitHeight

                            Rectangle {
                                anchors.fill: parent
                                visible: packageDelegate.path === fullLiveryService.selectedPackage
                                radius: Theme.framedRadius(Theme.px(5))
                                color: Theme.rowSelectedSurface
                                border.width: Math.max(1, Theme.px(1))
                                border.color: Theme.primary
                            }

                            QuickActionRow {
                                id: packageRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                dense: true
                                iconName: "monitor"
                                title: packageDelegate.title
                                subtitle: packageDelegate.modelCode + " · " + packageDelegate.placementCount + " placements"
                                enabled: fullLiveryService.featureEnabled
                                toolTipText: packageDelegate.portableMesh
                                             ? "Open this development package in the interactive car inspector."
                                             : "Open this verified package using the matching car assets from your local FH6 installation."
                                onClicked: {
                                    root.showGallery = false
                                    fullLiveryService.selectPackage(packageDelegate.path)
                                }
                            }
                        }

                        ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
                    }

                    GhostButton {
                        Layout.fillWidth: true
                        dense: true
                        text: "Open Package Folder"
                        iconName: "folder"
                        toolTipText: "Open the folder containing shareable full-livery packages."
                        onClicked: fullLiveryService.openPackageFolder()
                    }
                }
            }

            GlassPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: Theme.px(470)
                strong: true
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.px(12)
                    visible: root.showGallery
                    spacing: Theme.px(10)
                    RowLayout {
                        Layout.fillWidth: true
                        KfpsTextField {
                            id: liverySearch
                            objectName: "liveryGridSearch"
                            Layout.fillWidth: true
                            placeholderText: "Search liveries, car models or IDs"
                            toolTipText: "Filter local liveries by name, car model or car ID."
                            onTextChanged: searchDebounce.restart()
                            Timer {
                                id: searchDebounce
                                interval: 150
                                onTriggered: fullLiveryService.setSourceSearch(liverySearch.text)
                            }
                        }
                        Text {
                            text: liveryGrid.count + " liveries"
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(11)
                        }
                    }
                    LiveryThumbnailGrid {
                        id: liveryGrid
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        model: fullLiveryService.sourceGridModel
                        selectedPath: fullLiveryService.selectedSource
                        enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                        loading: fullLiveryService.running
                        filtered: liverySearch.text.trim().length > 0
                        onLiverySelected: function(path) { fullLiveryService.browseSource(path) }
                        onLiveryOpened: function(path) {
                            fullLiveryService.browseSource(path)
                            root.openSelectedLivery()
                        }
                    }
                }

                Loader {
                    id: inspectorLoader
                    anchors.fill: parent
                    anchors.margins: Math.max(1, Theme.px(1))
                    active: root.pageActive && !root.showGallery && root.viewerSessionUrl.length > 0
                    sourceComponent: Component {
                        WebEngineView {
                            id: carView
                            url: root.viewerSessionUrl
                            // Chromium aborts on fractional backing alpha. Keep
                            // the theme RGB; translucency stays in the page CSS.
                            backgroundColor: Qt.rgba(Theme.previewSurface.r, Theme.previewSurface.g, Theme.previewSurface.b, 1)
                            function applyViewerTheme() {
                                runJavaScript("window.__kfpsReadonlyTheme?.(" + root.viewerThemeJson + ")")
                            }
                            Connections {
                                target: root
                                function onViewerThemeJsonChanged() { carView.applyViewerTheme() }
                            }
                            settings.localContentCanAccessRemoteUrls: false
                            settings.localContentCanAccessFileUrls: false
                            settings.javascriptCanOpenWindows: false
                            onRenderProcessPidChanged: fullLiveryService.viewerProcess(url.toString(), renderProcessPid)
                            onRenderProcessTerminated: function(terminationStatus, exitCode) {
                                fullLiveryService.viewerFailed(url.toString(), "The graphics renderer stopped (status " + terminationStatus + ", exit " + exitCode + ").")
                            }
                            onLoadingChanged: function(request) {
                                if (request.status === WebEngineView.LoadFailedStatus)
                                    fullLiveryService.viewerFailed(url.toString(), request.errorString)
                                else if (request.status === WebEngineView.LoadSucceededStatus)
                                    applyViewerTheme()
                            }
                            onJavaScriptConsoleMessage: function(level, message, lineNumber, sourceId) {
                                if (message.indexOf("KFPS_VIEWER:") === 0) {
                                    if (message.indexOf('"event":"ready"') >= 0 || message.indexOf('"event":"phase"') >= 0)
                                        applyViewerTheme()
                                    fullLiveryService.viewerProcess(url.toString(), renderProcessPid)
                                    fullLiveryService.viewerEvent(url.toString(), message.slice(12))
                                }
                            }
                            Timer {
                                interval: 5000
                                repeat: true
                                running: root.pageActive && root.viewerSessionUrl.length > 0
                                onTriggered: {
                                    const sessionUrl = carView.url.toString()
                                    fullLiveryService.viewerProcess(sessionUrl, carView.renderProcessPid)
                                    carView.runJavaScript("JSON.stringify({event:'sample',diagnostics:window.__kfpsViewerStatusDiagnostics?.()})", function(result) {
                                        if (typeof result === "string")
                                            fullLiveryService.viewerEvent(sessionUrl, result)
                                    })
                                }
                            }
                            Component.onDestruction: {
                                stop()
                                url = "about:blank"
                            }
                        }
                    }
                }

                Rectangle {
                    anchors.fill: parent
                    color: "#090b0e"
                    opacity: fullLiveryService.viewerReady ? 0 : 1
                    visible: !root.showGallery && opacity > 0
                    Behavior on opacity { NumberAnimation { duration: Theme.reducedMotion ? 0 : 160 } }
                }

                EmptyState {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - Theme.px(40), Theme.px(460))
                    visible: !root.showGallery && !fullLiveryService.viewerReady
                    iconName: "monitor"
                    title: fullLiveryService.running || fullLiveryService.selectedPackage.length > 0
                           ? fullLiveryService.status
                           : "Open a full-livery package"
                    message: fullLiveryService.running || fullLiveryService.selectedPackage.length > 0
                             ? fullLiveryService.summary
                             : "Select a saved package to inspect the resolved car, turn it freely, zoom in, and isolate projected livery sections."
                }
            }

            GlassPanel {
                visible: !root.showGallery
                Layout.fillHeight: true
                Layout.fillWidth: !root.wide
                Layout.preferredWidth: root.wide ? Theme.px(310) : -1
                Layout.minimumWidth: root.wide ? Theme.px(270) : 0
                Layout.maximumWidth: root.wide ? Theme.px(360) : -1
                Layout.columnSpan: root.wide ? 1 : 2
                Layout.preferredHeight: root.wide ? -1 : Theme.px(250)
                soft: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.px(11)
                    spacing: Theme.px(7)

                    Text {
                        Layout.fillWidth: true
                        text: fullLiveryService.selectedTitle
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.px(16)
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }

                    Text {
                        Layout.fillWidth: true
                        text: fullLiveryService.selectedVehicle + "\n" + fullLiveryService.selectedCounts
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(10.5)
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "FH6 package policy"
                        color: Theme.primaryBright
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.px(13)
                        font.weight: Font.DemiBold
                    }

                    FastListView {
                        id: decisions
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: Theme.px(130)
                        model: fullLiveryService.decisionModel
                        spacing: Theme.px(3)
                        clip: true

                        delegate: Item {
                            required property string action
                            required property string item
                            required property string detail
                            width: decisions.width
                            height: decisionColumn.implicitHeight + Theme.px(12)

                            Column {
                                id: decisionColumn
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: Theme.px(2)
                                Text {
                                    width: parent.width
                                    text: action + "  " + item
                                    color: action === "DISCARD" ? Theme.danger
                                           : (action === "CHANGE" ? Theme.warning
                                           : (action === "KEEP" ? Theme.success : Theme.primaryBright))
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.px(9.5)
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.WordWrap
                                }
                                Text {
                                    width: parent.width
                                    text: detail
                                    color: Theme.subtle
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(9)
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }

                        ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
                    }

                    PrimaryButton {
                        objectName: "installExactCarFullLiveryButton"
                        Layout.fillWidth: true
                        dense: true
                        text: fullLiveryService.running ? "Working..." : "Install in FH6 Save"
                        iconName: "transfer"
                        enabled: !fullLiveryService.running && fullLiveryService.selectedPackageInstallable
                        toolTipText: fullLiveryService.selectedPackageInstallable
                                     ? "Install this package as a new local livery for its exact FH6 car."
                                     : "Open a verified shareable package for its exact FH6 car first."
                        onClicked: installConfirm.open()
                    }

                    StatusRow {
                        Layout.fillWidth: true
                        dense: true
                        label: "Package state"
                        value: fullLiveryService.status
                        state: fullLiveryService.status.indexOf("failed") >= 0 || fullLiveryService.status.indexOf("rejected") >= 0 ? "bad"
                               : (fullLiveryService.running ? "warn" : "ok")
                    }
                }
            }
        }
    }

    MessageDialog {
        id: installConfirm
        title: "Install this FH6 livery?"
        text: "KFPS will verify the package against the exact car, create a recovery record, and add a new livery without replacing existing save entries. Different-car installation is blocked. FH6 may need to reload its save before the new livery appears."
        buttons: MessageDialog.Ok | MessageDialog.Cancel
        onAccepted: fullLiveryService.installSelectedPackage()
    }

    FocusScope {
        id: wipPreviewOverlay
        objectName: "liveryWipPreviewOverlay"
        anchors.fill: parent
        z: 1000
        visible: !root.wipNoticeAcknowledged
        focus: visible

        onVisibleChanged: {
            if (visible)
                Qt.callLater(function () { wipAcknowledgeButton.forceActiveFocus() })
        }

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0.01, 0.01, 0.018, 0.80)
        }

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
            preventStealing: true
            onWheel: function(wheel) { wheel.accepted = true }
        }

        GlassPanel {
            anchors.centerIn: parent
            width: Math.min(parent.width - Theme.px(40), Theme.px(650))
            height: wipNoticeContent.implicitHeight + Theme.px(56)
            strong: true

            ColumnLayout {
                id: wipNoticeContent
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: Theme.px(36)
                anchors.rightMargin: Theme.px(36)
                spacing: Theme.px(14)

                Text {
                    Layout.fillWidth: true
                    text: "WIP"
                    color: Theme.warning
                    font.family: Theme.displayFamily
                    font.pixelSize: Theme.px(root.compactHeight ? 54 : 72)
                    font.weight: Font.Black
                    horizontalAlignment: Text.AlignHCenter
                }

                Text {
                    Layout.fillWidth: true
                    text: "This page is a heavy work-in-progress preview, not a finished or dependable product. Expect incomplete behavior, rendering issues, and changes while it is being developed."
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(root.compactHeight ? 13 : 15)
                    font.weight: Font.Medium
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }

                PrimaryButton {
                    id: wipAcknowledgeButton
                    objectName: "liveryWipAcknowledgeButton"
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: Theme.px(180)
                    text: "OK"
                    iconName: "check"
                    toolTipText: "Acknowledge the livery preview warning for this KFPS session."
                    onClicked: root.dismissWipNotice()
                }
            }
        }
    }
}
