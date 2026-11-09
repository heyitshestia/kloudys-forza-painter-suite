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
    property bool showGallery: true
    property int libraryTab: garage ? 2 : 0
    property bool pageReady: false
    property string garageLaunchTarget: ""
    readonly property var garage: typeof garageService !== "undefined" ? garageService : null
    onLibraryTabChanged: {
        detailsPopup.close()
        enterMyCars()
    }
    function enterMyCars() {
        if (pageReady && pageActive && showGallery && libraryTab === 2 && garage)
            garage.enter()
    }
    readonly property bool galleryHasSelection: libraryTab === 0
                                               ? fullLiveryService.selectedSource.length > 0
                                               : libraryTab === 1 && fullLiveryService.browsedPackage.length > 0
    readonly property var galleryDetails: libraryTab === 0 ? fullLiveryService.sourceDetails
                                                          : fullLiveryService.packageDetails
    readonly property bool hasStudioPackageStatus: showGallery && libraryTab === 1
                                                  && !fullLiveryService.running
                                                  && fullLiveryService.browsedPackage.length > 0
                                                  && editorService.studioPackagePath === fullLiveryService.browsedPackage
                                                  && editorService.studioStatus.length > 0
    readonly property bool canPreviewSelection: fullLiveryService.featureEnabled && !fullLiveryService.running
                                               && galleryHasSelection
                                               && (libraryTab === 1 || fullLiveryService.gameFolder.length > 0)
    readonly property bool packageFiltersActive: fullLiveryService.packageSearch.length > 0
                                                || fullLiveryService.packageCarId !== 0
    readonly property bool filtersActive: fullLiveryService.sourceSearch.length > 0
                                         || fullLiveryService.sourceCarId !== 0
                                         || fullLiveryService.sourceAvailability !== "all"
    readonly property var availabilityOptions: [
        {label: "All availability", value: "all"},
        {label: "Exportable", value: "exportable"},
        {label: "Preview only", value: "preview"}
    ]
    readonly property var sortOptions: [
        {label: "Newest first", value: "modified"},
        {label: "Title", value: "title"},
        {label: "Car ID", value: "car"},
        {label: "Most shapes", value: "placements"}
    ]
    readonly property var packageSortOptions: [
        {label: "Title", value: "title"},
        {label: "Car ID", value: "car"},
        {label: "Most shapes", value: "placements"}
    ]
    // WebEngine treats a repeated URL assignment as navigation. This string
    // changes only for a new session, unlike the service's shared status signal.
    readonly property string viewerSessionUrl: fullLiveryService.viewerUrl
    readonly property string viewerThemeJson: JSON.stringify(studioThemeContext())
    readonly property string garageStatus: garage && garage.busy ? garage.status
        : garageLaunchTarget === "studio" ? editorService.studioStatus
        : garageLaunchTarget === "preview" ? fullLiveryService.status : garage ? garage.status : ""

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
        if (libraryTab === 1) {
            if (!canPreviewSelection) return
            if (fullLiveryService.previewBrowsedPackage())
                showGallery = false
            return
        }
        if (fullLiveryService.selectedSource.length === 0 || fullLiveryService.gameFolder.length === 0)
            return
        showGallery = false
        fullLiveryService.previewSelectedSource()
    }

    function returnToGallery() {
        fullLiveryService.showSourceGrid()
        garageLaunchTarget = ""
        showGallery = true
    }

    onViewerSessionUrlChanged: {
        if (viewerSessionUrl.length > 0)
            showGallery = false
    }

    Component.onCompleted: {
        pageReady = true
        if (pageActive)
            fullLiveryService.activate()
        // Let CachedPageHost apply pageActive before a retained loader can enter.
        Qt.callLater(root.enterMyCars)
    }

    onPageActiveChanged: {
        if (pageActive) {
            fullLiveryService.activate()
            enterMyCars()
        } else {
            root.returnToGallery()
            fullLiveryService.deactivate()
        }
    }


    function optionIndex(options, value) {
        for (let i = 0; i < options.length; ++i) {
            if (options[i].value === value)
                return i
        }
        return 0
    }

    function scrollLibraryToBeginning() {
        Qt.callLater(function() { liveryGrid.positionViewAtBeginning() })
    }

    function scrollPackagesToBeginning() {
        Qt.callLater(function() { packages.positionViewAtBeginning() })
    }

    function retryPreview() {
        if (fullLiveryService.running) return
        if (fullLiveryService.hasGaragePreview)
            fullLiveryService.retryGaragePreview()
        else if (fullLiveryService.selectedSource.length > 0)
            fullLiveryService.previewSelectedSource()
        else if (fullLiveryService.browsedPackage.length > 0)
            fullLiveryService.previewBrowsedPackage()
        else if (fullLiveryService.selectedPackage.length > 0)
            fullLiveryService.selectPackage(fullLiveryService.selectedPackage)
    }

    onWideChanged: {
        if (wide)
            detailsPopup.close()
    }
    onShowGalleryChanged: {
        detailsPopup.close()
        enterMyCars()
    }

    Connections {
        target: root.garage
        function onChanged() {
            if (root.garage.busy) root.garageLaunchTarget = ""
        }
        function onPreviewRequested(identity, snapshot) {
            root.garageLaunchTarget = "preview"
            if (fullLiveryService.previewGarageBuild(identity, snapshot)) root.showGallery = false
        }
        function onStudioRequested(identity, snapshot, name) {
            root.garageLaunchTarget = "studio"
            editorService.launchGarageInLiveryStudio(identity, snapshot, name, root.studioThemeContext())
        }
        function onStockPreviewRequested(identity) {
            root.garageLaunchTarget = "preview"
            if (fullLiveryService.previewStockCar(identity)) root.showGallery = false
        }
        function onStockStudioRequested(identity) {
            root.garageLaunchTarget = "studio"
            editorService.launchStockInLiveryStudio(identity, root.studioThemeContext())
        }
        function onArtworkRequested(identity, snapshot, path, kind, expected) {
            root.garageLaunchTarget = "studio"
            editorService.launchGarageArtworkInLiveryStudio(identity, snapshot, path, kind, root.studioThemeContext(), expected)
        }
        function onProjectRequested(project) {
            root.garageLaunchTarget = "studio"
            editorService.launchLinkedProjectInLiveryStudio(project, root.studioThemeContext())
        }
        function onLiveryRequested(path) {
            root.libraryTab = 0
            fullLiveryService.resetSourceFilters()
            fullLiveryService.browseSource(path)
        }
    }
    Connections {
        target: root
        function onPageActiveChanged() {
            if (!root.pageActive) {
                detailsPopup.close()
                morePopup.close()
            }
        }
    }

    component PlainToolTip: KfpsToolTip {
        id: plainTip
        contentItem: Text {
            width: plainTip.preferredTextWidth
            text: plainTip.text
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(10.8)
            wrapMode: Text.Wrap
        }
    }

    component LibraryTab: TabButton {
        id: tabControl
        implicitHeight: Theme.px(34)
        padding: Theme.px(8)
        font.family: Theme.fontFamily
        font.pixelSize: Theme.px(12)
        contentItem: Text {
            text: tabControl.text
            font: tabControl.font
            color: tabControl.checked ? (Theme.classicMode ? Theme.primaryText : Theme.primaryBright) : Theme.muted
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            color: tabControl.checked ? Theme.rowSelectedSurface : Theme.surface
            radius: Theme.framedRadius(Theme.px(4))
            border.width: tabControl.activeFocus ? Math.max(1, Theme.px(1)) : 0
            border.color: Theme.focusColor
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: Theme.px(2)
                visible: tabControl.checked
                color: Theme.primary
            }
        }
        KfpsToolTip {
            visible: tabControl.hovered
            text: tabControl.text
        }
    }

    component SmallIconButton: ToolButton {
        id: iconButton
        property string iconName: "reports"
        property string fallbackText: "i"
        property string help: ""
        readonly property bool symbolsOnly: !Theme.iconGlyphsVisible || GraphicsInfo.api === GraphicsInfo.Software
        implicitWidth: Theme.px(34)
        implicitHeight: Theme.px(34)
        Layout.minimumWidth: implicitWidth
        Layout.maximumWidth: implicitWidth
        Layout.minimumHeight: implicitHeight
        hoverEnabled: true
        Accessible.name: help
        contentItem: Item {
            Icon {
                anchors.centerIn: parent
                visible: !iconButton.symbolsOnly
                name: iconButton.iconName
                iconSize: Theme.px(16)
                tint: iconButton.enabled ? Theme.text : Theme.subtle
            }
            Text {
                anchors.fill: parent
                visible: iconButton.symbolsOnly
                text: iconButton.fallbackText
                textFormat: Text.PlainText
                color: iconButton.enabled ? Theme.text : Theme.subtle
                font.family: Theme.monoFamily
                font.pixelSize: Theme.px(14)
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
        background: Rectangle {
            color: iconButton.down ? Theme.rowSelectedSurface
                                  : (iconButton.hovered ? Theme.rowHover : Theme.fieldSurface)
            radius: Theme.framedRadius(Theme.px(4))
            border.width: Math.max(1, Theme.px(1))
            border.color: iconButton.activeFocus ? Theme.focusColor : Theme.borderSoft
        }
        KfpsToolTip {
            visible: iconButton.hovered
            text: iconButton.help
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.px(8)

        RowLayout {
            id: pageHeader
            Layout.fillWidth: true
            Layout.minimumHeight: Theme.px(42)
            spacing: Theme.px(8)

            Icon {
                name: "monitor"
                iconSize: Theme.px(24)
            }
            Text {
                text: "Garage"
                color: Theme.text
                font.family: Theme.displayFamily
                font.pixelSize: Theme.px(20)
                font.weight: Font.DemiBold
            }
            Text {
                text: "Experimental"
                color: Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(10)
                HoverHandler { id: experimentalHover }
                KfpsToolTip {
                    visible: experimentalHover.hovered
                    text: "Experimental livery preview and package tools."
                }
            }
            Item { Layout.fillWidth: true }

            GhostButton {
                objectName: "launchLiveryStudioButton"
                dense: true
                text: editorService.studioLaunching ? "Starting..." : "Studio"
                iconName: "editor"
                enabled: !editorService.studioLaunching
                toolTipText: editorService.studioStatus.length > 0
                             ? editorService.studioStatus : "Open Livery Studio."
                onClicked: editorService.launchLiveryStudio(root.studioThemeContext())
            }
            PrimaryButton {
                objectName: "garageRefreshButton"
                dense: true
                text: root.libraryTab === 2 ? "Refresh" : fullLiveryService.running ? "Working..." : "Scan Saves"
                iconName: "refresh"
                enabled: root.libraryTab === 2 ? root.garage && !root.garage.busy && !root.garage.catalogueBusy
                                             : fullLiveryService.featureEnabled && !fullLiveryService.running
                toolTipText: root.libraryTab === 2 ? "Refresh the selected garage snapshot."
                                                  : "Find unique full-car FH6 livery records without changing the save."
                onClicked: root.libraryTab === 2 ? root.garage.refresh() : fullLiveryService.scanSaves()
            }
            GhostButton {
                id: moreButton
                objectName: "liveryMoreButton"
                dense: true
                text: "More"
                iconName: "tools"
                selected: morePopup.visible
                toolTipText: "Folders, cache and diagnostics."
                onClicked: morePopup.visible ? morePopup.close() : morePopup.open()
            }
        }

        Text {
            objectName: "liveryLibraryStatus"
            Layout.fillWidth: true
            text: root.libraryTab === 2 && root.garage ? root.garageStatus : root.hasStudioPackageStatus || (editorService.studioLaunching && editorService.studioStatus.length > 0)
                  ? editorService.studioStatus : fullLiveryService.status
            textFormat: Text.PlainText
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(11)
            elide: Text.ElideRight
            HoverHandler { id: statusHover }
            PlainToolTip {
                visible: statusHover.hovered
                text: root.libraryTab === 2 && root.garage ? (root.garageLaunchTarget === "preview" ? fullLiveryService.summary : root.garageStatus) : root.hasStudioPackageStatus || (editorService.studioLaunching && editorService.studioStatus.length > 0)
                      ? editorService.studioStatus : fullLiveryService.summary
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(1, Theme.px(1))
            color: Theme.divider
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.px(12)

            ColumnLayout {
                id: mainContent
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 0
                spacing: Theme.px(8)

                RowLayout {
                    visible: root.showGallery
                    Layout.fillWidth: true
                    spacing: Theme.px(8)

                    TabBar {
                        id: libraryTabs
                        objectName: "liveryLibraryTabs"
                        Layout.fillWidth: true
                        Layout.minimumWidth: Theme.px(240)
                        Layout.preferredWidth: Theme.px(390)
                        Layout.maximumWidth: Theme.px(390)
                        currentIndex: root.libraryTab
                        onCurrentIndexChanged: if (root.pageReady) root.libraryTab = currentIndex
                        background: Item {}
                        LibraryTab { objectName: "garageSavedLiveriesTab"; text: "Saved Liveries"; onClicked: root.libraryTab = 0 }
                        LibraryTab { objectName: "garagePackagesTab"; text: "Packages"; onClicked: root.libraryTab = 1 }
                        LibraryTab { objectName: "garageMyCarsTab"; text: "My Cars"; enabled: root.garage !== null; onClicked: root.libraryTab = 2 }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.libraryTab === 2 ? (root.garage ? root.garage.visibleCount + " / " + root.garage.browseTotal : "") : root.libraryTab === 0
                              ? fullLiveryService.visibleSourceCount + " / " + fullLiveryService.sourceCount
                              : fullLiveryService.visiblePackageCount + " / " + fullLiveryService.packageCount
                        color: Theme.muted
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.px(10)
                        elide: Text.ElideRight
                        HoverHandler { id: countHover }
                        KfpsToolTip {
                            visible: countHover.hovered
                            text: root.libraryTab === 2 && root.garage
                                  ? root.garage.visibleCount + " visible of " + root.garage.browseTotal + " cars"
                                  : root.libraryTab === 0
                                  ? fullLiveryService.visibleSourceCount + " visible of " + fullLiveryService.sourceCount + " saved liveries"
                                  : fullLiveryService.visiblePackageCount + " visible of " + fullLiveryService.packageCount + " saved packages"
                        }
                    }
                    GhostButton {
                        objectName: "addFullLiveryPackageButton"
                        visible: root.libraryTab !== 2
                        dense: true
                        text: "Add Package"
                        iconName: "folder"
                        enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                        toolTipText: "Validate and add a received .kfpslivery package."
                        onClicked: {
                            root.libraryTab = 1
                            fullLiveryService.choosePackage()
                        }
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
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    HoverHandler { id: packageAddErrorHover }
                    PlainToolTip {
                        visible: packageAddErrorHover.hovered
                        text: fullLiveryService.packageAddError
                    }
                }

                GridLayout {
                    id: filterToolbar
                    visible: root.showGallery && root.libraryTab === 0
                    Layout.fillWidth: true
                    columns: Theme.logical(width) >= 900 ? 5 : 4
                    columnSpacing: Theme.px(6)
                    rowSpacing: Theme.px(6)

                    KfpsTextField {
                        id: liverySearch
                        objectName: "liveryGridSearch"
                        Layout.fillWidth: true
                        Layout.minimumWidth: Theme.px(180)
                        Layout.columnSpan: filterToolbar.columns === 5 ? 1 : 4
                        dense: true
                        placeholderText: "Search liveries, models or IDs"
                        text: fullLiveryService.sourceSearch
                        toolTipText: "Search saved livery names, car models and IDs."
                        onTextChanged: {
                            if (text !== fullLiveryService.sourceSearch)
                                searchDebounce.restart()
                        }
                        onAccepted: {
                            searchDebounce.stop()
                            fullLiveryService.setSourceSearch(text)
                            root.scrollLibraryToBeginning()
                        }
                        Timer {
                            id: searchDebounce
                            interval: 150
                            onTriggered: {
                                fullLiveryService.setSourceSearch(liverySearch.text)
                                root.scrollLibraryToBeginning()
                            }
                        }
                    }
                    KfpsComboBox {
                        objectName: "liveryCarFilter"
                        Layout.fillWidth: true
                        Layout.preferredWidth: Theme.px(190)
                        dense: true
                        model: fullLiveryService.sourceCars
                        textRole: "label"
                        valueRole: "value"
                        currentIndex: root.optionIndex(fullLiveryService.sourceCars, fullLiveryService.sourceCarId)
                        onActivated: {
                            fullLiveryService.setSourceCar(currentValue)
                            root.scrollLibraryToBeginning()
                        }
                        toolTipText: "Filter by exact car ID."
                        Accessible.name: "Car filter"
                    }
                    KfpsComboBox {
                        objectName: "liveryAvailabilityFilter"
                        Layout.fillWidth: true
                        Layout.preferredWidth: Theme.px(155)
                        dense: true
                        model: root.availabilityOptions
                        textRole: "label"
                        valueRole: "value"
                        currentIndex: root.optionIndex(root.availabilityOptions, fullLiveryService.sourceAvailability)
                        onActivated: {
                            fullLiveryService.setSourceAvailability(currentValue)
                            root.scrollLibraryToBeginning()
                        }
                        toolTipText: "Show all liveries, exportable liveries or preview-only liveries."
                        Accessible.name: "Availability filter"
                    }
                    KfpsComboBox {
                        objectName: "liverySortOrder"
                        Layout.fillWidth: true
                        Layout.preferredWidth: Theme.px(150)
                        dense: true
                        model: root.sortOptions
                        textRole: "label"
                        valueRole: "value"
                        currentIndex: root.optionIndex(root.sortOptions, fullLiveryService.sourceSort)
                        onActivated: {
                            fullLiveryService.setSourceSort(currentValue)
                            root.scrollLibraryToBeginning()
                        }
                        toolTipText: "Sort saved liveries."
                        Accessible.name: "Livery sort order"
                    }
                    SmallIconButton {
                        objectName: "resetLiveryFiltersButton"
                        iconName: "refresh"
                        fallbackText: "x"
                        help: "Clear search and filters."
                        enabled: root.filtersActive
                        onClicked: {
                            searchDebounce.stop()
                            fullLiveryService.resetSourceFilters()
                            root.scrollLibraryToBeginning()
                        }
                    }
                }

                GridLayout {
                    id: packageFilters
                    visible: root.showGallery && root.libraryTab === 1
                    Layout.fillWidth: true
                    columns: Theme.logical(width) >= 720 ? 4 : 3
                    columnSpacing: Theme.px(6)
                    rowSpacing: Theme.px(6)
                    KfpsTextField {
                        id: packageSearch
                        objectName: "liveryPackageSearch"
                        Layout.fillWidth: true
                        Layout.minimumWidth: Theme.px(180)
                        Layout.columnSpan: packageFilters.columns === 4 ? 1 : 3
                        dense: true
                        placeholderText: "Search packages, models or IDs"
                        text: fullLiveryService.packageSearch
                        toolTipText: "Search indexed package names, models, car IDs and paths."
                        onTextChanged: {
                            if (text !== fullLiveryService.packageSearch)
                                packageSearchDebounce.restart()
                        }
                        onAccepted: {
                            packageSearchDebounce.stop()
                            fullLiveryService.setPackageSearch(text)
                            root.scrollPackagesToBeginning()
                        }
                        Timer {
                            id: packageSearchDebounce
                            interval: 150
                            onTriggered: {
                                fullLiveryService.setPackageSearch(packageSearch.text)
                                root.scrollPackagesToBeginning()
                            }
                        }
                    }
                    KfpsComboBox {
                        objectName: "liveryPackageCarFilter"
                        Layout.fillWidth: true
                        Layout.preferredWidth: Theme.px(190)
                        dense: true
                        model: fullLiveryService.packageCars
                        textRole: "label"
                        valueRole: "value"
                        currentIndex: root.optionIndex(fullLiveryService.packageCars, fullLiveryService.packageCarId)
                        onActivated: {
                            fullLiveryService.setPackageCar(currentValue)
                            root.scrollPackagesToBeginning()
                        }
                        Accessible.name: "Package car filter"
                        toolTipText: "Filter packages by exact car ID."
                    }
                    KfpsComboBox {
                        objectName: "liveryPackageSortOrder"
                        Layout.fillWidth: true
                        Layout.preferredWidth: Theme.px(160)
                        dense: true
                        model: root.packageSortOptions
                        textRole: "label"
                        valueRole: "value"
                        currentIndex: root.optionIndex(root.packageSortOptions, fullLiveryService.packageSort)
                        onActivated: {
                            fullLiveryService.setPackageSort(currentValue)
                            root.scrollPackagesToBeginning()
                        }
                        Accessible.name: "Package sort order"
                        toolTipText: "Sort the package library."
                    }
                    SmallIconButton {
                        objectName: "resetLiveryPackageFiltersButton"
                        iconName: "refresh"
                        fallbackText: "x"
                        help: "Clear package search and car filter."
                        enabled: root.packageFiltersActive
                        onClicked: {
                            packageSearchDebounce.stop()
                            fullLiveryService.resetPackageFilters()
                            root.scrollPackagesToBeginning()
                        }
                    }
                }

                RowLayout {
                    visible: !root.showGallery
                    Layout.fillWidth: true
                    spacing: Theme.px(8)

                    GhostButton {
                        objectName: "returnToLiveryGridButton"
                        dense: true
                        text: root.libraryTab === 2 ? "Back to Garage" : "Back to Liveries"
                        iconName: "chevron-left"
                        toolTipText: "Close the 3D preview and return to the library."
                        onClicked: root.returnToGallery()
                    }
                    Text {
                        Layout.fillWidth: true
                        text: fullLiveryService.selectedTitle
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(13)
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    KfpsComboBox {
                        objectName: "LiveryVinylResolution"
                        visible: !fullLiveryService.hasGaragePreview
                        dense: true
                        Layout.preferredWidth: Theme.px(130)
                        model: ["Standard", "High"]
                        currentIndex: fullLiveryService.viewerQuality - 1
                        enabled: fullLiveryService.featureEnabled
                        onActivated: fullLiveryService.setViewerQuality(currentIndex + 1)
                        toolTipText: "Vinyl resolution: Standard uses the previous High detail. High doubles width and height and uses more memory."
                        Accessible.name: "Vinyl resolution"
                    }
                    SmallIconButton {
                        visible: !root.wide && root.libraryTab !== 2
                        iconName: "reports"
                        help: "Preview details and compatibility."
                        onClicked: detailsPopup.open()
                    }
                }

                Item {
                    id: contentSurface
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: Theme.px(120)
                    clip: true

                    Loader {
                        anchors.fill: parent
                        active: root.pageActive && root.showGallery && root.libraryTab === 2 && root.garage !== null
                        sourceComponent: GarageBrowser {
                            service: root.garage
                            launchBusy: fullLiveryService.running || editorService.studioLaunching
                            onBuildRequested: root.garageLaunchTarget = ""
                        }
                    }

                    LiveryThumbnailGrid {
                        id: liveryGrid
                        objectName: "liveryThumbnailGrid"
                        anchors.fill: parent
                        visible: root.showGallery && root.libraryTab === 0
                        model: fullLiveryService.sourceGridModel
                        selectedPath: fullLiveryService.selectedSource
                        enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                        loading: fullLiveryService.running
                        filtered: root.filtersActive
                        onLiverySelected: function(path) { fullLiveryService.browseSource(path) }
                        onLiveryOpened: function(path) {
                            fullLiveryService.browseSource(path)
                            root.openSelectedLivery()
                        }
                    }

                    LiveryPackageList {
                        id: packages
                        objectName: "fullLiveryPackageList"
                        anchors.fill: parent
                        visible: root.showGallery && root.libraryTab === 1
                        model: fullLiveryService.packageGridModel
                        selectedPath: fullLiveryService.browsedPackage
                        filtered: root.packageFiltersActive
                        enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                        onPackageSelected: function(path) { fullLiveryService.browsePackage(path) }
                        onPackageOpened: function(path) {
                            fullLiveryService.browsePackage(path)
                            root.openSelectedLivery()
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
                        color: Theme.previewSurface
                        opacity: fullLiveryService.viewerReady ? 0 : 1
                        visible: !root.showGallery && opacity > 0
                        Behavior on opacity { NumberAnimation { duration: Theme.reducedMotion ? 0 : 160 } }
                    }
                    Column {
                        anchors.centerIn: parent
                        width: Math.min(parent.width - Theme.px(40), Theme.px(460))
                        visible: !root.showGallery && !fullLiveryService.viewerReady
                        spacing: Theme.px(10)
                        Icon {
                            anchors.horizontalCenter: parent.horizontalCenter
                            name: "monitor"
                            iconSize: Theme.px(28)
                        }
                        Text {
                            width: parent.width
                            objectName: "liveryPreviewStatus"
                            text: fullLiveryService.status
                            textFormat: Text.PlainText
                            color: Theme.text
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(16)
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            maximumLineCount: 3
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            objectName: "liveryPreviewSummary"
                            text: fullLiveryService.summary
                            textFormat: Text.PlainText
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(12)
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            maximumLineCount: 4
                            elide: Text.ElideRight
                            HoverHandler { id: previewSummaryHover }
                            PlainToolTip {
                                visible: previewSummaryHover.hovered
                                text: fullLiveryService.summary
                            }
                        }
                        GhostButton {
                            objectName: "retryLiveryPreviewButton"
                            anchors.horizontalCenter: parent.horizontalCenter
                            visible: !fullLiveryService.running
                            dense: true
                            text: "Retry Preview"
                            iconName: "refresh"
                            enabled: fullLiveryService.featureEnabled
                                     && (fullLiveryService.hasGaragePreview
                                         || (fullLiveryService.selectedSource.length > 0 && fullLiveryService.gameFolder.length > 0)
                                         || fullLiveryService.browsedPackage.length > 0
                                         || fullLiveryService.selectedPackage.length > 0)
                            toolTipText: "Retry the selected preview without changing the save or replacing artwork."
                            onClicked: root.retryPreview()
                        }
                    }
                }

                RowLayout {
                    visible: root.showGallery && !root.wide && root.libraryTab !== 2
                    Layout.fillWidth: true
                    spacing: Theme.px(8)
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        spacing: Theme.px(2)
                        Text {
                            Layout.fillWidth: true
                            text: root.galleryHasSelection ? (root.galleryDetails.title || "Untitled livery")
                                                           : (root.libraryTab === 0 ? "Select a livery" : "Select a package")
                            textFormat: Text.PlainText
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(12)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: root.galleryHasSelection
                                  ? (root.galleryDetails.modelCode || "Unresolved car") + " | Car "
                                    + (root.galleryDetails.carId || "?") + " | "
                                    + (root.galleryDetails.placementCount || 0) + " placements" : ""
                            textFormat: Text.PlainText
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(10)
                            elide: Text.ElideRight
                        }
                    }
                    GhostButton {
                        objectName: "compactLiveryPreviewButton"
                        dense: true
                        text: "Preview"
                        iconName: "monitor"
                        enabled: root.canPreviewSelection
                        toolTipText: root.libraryTab === 1 ? "Verify and open the selected package."
                                     : fullLiveryService.gameFolder.length > 0
                                     ? "Open the selected livery in 3D."
                                     : "Link the FH6 folder under More to enable 3D previews."
                        onClicked: root.openSelectedLivery()
                    }
                    GhostButton {
                        objectName: "liverySelectionDetailsButton"
                        dense: true
                        text: "Details"
                        iconName: "reports"
                        enabled: root.galleryHasSelection
                        toolTipText: "Selection details and available actions."
                        onClicked: detailsPopup.open()
                    }
                }
            }

            Rectangle {
                visible: root.wide && root.libraryTab !== 2
                Layout.fillHeight: true
                Layout.preferredWidth: Math.max(1, Theme.px(1))
                color: Theme.divider
            }
            Item {
                id: detailsHost
                visible: root.wide && root.libraryTab !== 2
                Layout.fillHeight: true
                Layout.preferredWidth: Theme.px(300)
                Layout.minimumWidth: Theme.px(300)
                Layout.maximumWidth: Theme.px(300)
            }
        }
    }

    LiveryPreviewDetails {
        id: selectionDetails
        parent: root.wide ? detailsHost : detailsPopup.contentItem
        anchors.fill: parent
        anchors.topMargin: root.wide ? 0 : Theme.px(40)
        visible: root.libraryTab !== 2 && (root.wide || detailsPopup.visible)
        viewingPreview: !root.showGallery
        sourceMode: root.showGallery ? root.libraryTab === 0 : fullLiveryService.selectedSource.length > 0
        onPreviewRequested: {
            detailsPopup.close()
            root.openSelectedLivery()
        }
        onStudioRequested: {
            detailsPopup.close()
            editorService.launchPackageInLiveryStudio(fullLiveryService.browsedPackage, root.studioThemeContext())
        }
        onInstallRequested: installConfirm.open()
    }

    Popup {
        id: detailsPopup
        objectName: "liveryDetailsPopup"
        parent: root
        modal: false
        dim: false
        focus: true
        padding: Theme.px(12)
        width: Math.min(root.width - Theme.px(16), Theme.px(380))
        height: Math.max(0, root.height - pageHeader.height - Theme.px(24))
        x: root.width - width - Theme.px(8)
        y: pageHeader.height + Theme.px(12)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: KfpsPopupSurface {
            surfaceColor: Qt.rgba(Theme.surfaceRaised.r, Theme.surfaceRaised.g, Theme.surfaceRaised.b, 1)
            cornerRadius: Theme.px(6)
        }
        contentItem: Item {
            RowLayout {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                Text {
                    Layout.fillWidth: true
                    text: "Details"
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: Theme.px(14)
                    font.weight: Font.DemiBold
                }
                SmallIconButton {
                    iconName: "chevron-right"
                    fallbackText: "x"
                    help: "Close details."
                    onClicked: detailsPopup.close()
                }
            }
        }
    }

    Popup {
        id: morePopup
        objectName: "liveryMorePopup"
        parent: root
        modal: false
        dim: false
        focus: true
        padding: Theme.px(8)
        width: Math.min(root.width - Theme.px(16), Theme.px(270))
        height: Math.min(moreActions.implicitHeight + padding * 2, root.height - Theme.px(16))
        x: root.width - width
        y: Math.min(pageHeader.height + Theme.px(6), root.height - height)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: KfpsPopupSurface {
            surfaceColor: Qt.rgba(Theme.surfaceRaised.r, Theme.surfaceRaised.g, Theme.surfaceRaised.b, 1)
            cornerRadius: Theme.px(6)
        }
        contentItem: Flickable {
            contentWidth: width
            contentHeight: moreActions.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            ColumnLayout {
                id: moreActions
                width: parent.width
                spacing: Theme.px(4)
                GhostButton {
                    Layout.fillWidth: true
                    dense: true
                    text: fullLiveryService.gameFolder.length > 0 ? "Change FH6 Folder" : "Link FH6 Folder"
                    iconName: "folder"
                    enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                    toolTipText: fullLiveryService.gameFolder.length > 0
                                 ? fullLiveryService.gameFolder : "Choose the local FH6 game or Content folder."
                    onClicked: {
                        morePopup.close()
                        fullLiveryService.chooseGameFolder()
                    }
                }
                GhostButton {
                    Layout.fillWidth: true
                    dense: true
                    text: "Save Folder"
                    iconName: "folder"
                    enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                    toolTipText: "Choose the FH6 GameSave root."
                    onClicked: {
                        morePopup.close()
                        fullLiveryService.chooseSaveRoot()
                    }
                }
                GhostButton {
                    Layout.fillWidth: true
                    dense: true
                    text: "Open Package Folder"
                    iconName: "folder"
                    toolTipText: "Open the folder containing shareable full-livery packages."
                    onClicked: {
                        morePopup.close()
                        fullLiveryService.openPackageFolder()
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(1, Theme.px(1))
                    color: Theme.divider
                }
                GhostButton {
                    objectName: "clearFullLiveryCacheButton"
                    Layout.fillWidth: true
                    dense: true
                    text: "Clear Cache"
                    iconName: "refresh"
                    enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                    toolTipText: "Remove rebuilt previews, meshes and indexes. Saved liveries and packages are kept."
                    onClicked: {
                        morePopup.close()
                        fullLiveryService.clearFullLiveryCache()
                    }
                }
                GhostButton {
                    Layout.fillWidth: true
                    dense: true
                    text: "Diagnostics"
                    iconName: "reports"
                    enabled: !fullLiveryService.running
                    toolTipText: "Export privacy-scrubbed livery diagnostics."
                    onClicked: {
                        morePopup.close()
                        fullLiveryService.exportDiagnostics()
                    }
                }
            }
            ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
        }
    }

    MessageDialog {
        id: installConfirm
        title: "Install this FH6 livery?"
        text: "KFPS will verify the package against the exact car, create a recovery record, and add a new livery without replacing existing save entries. Different-car installation is blocked. FH6 may need to reload its save before the new livery appears."
        buttons: MessageDialog.Ok | MessageDialog.Cancel
        onAccepted: fullLiveryService.installSelectedPackage()
    }
}
