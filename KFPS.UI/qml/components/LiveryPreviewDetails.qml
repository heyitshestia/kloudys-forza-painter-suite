import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "liveryPreviewDetails"
    property bool viewingPreview: false
    property bool sourceMode: true
    property bool compatibilityExpanded: false
    readonly property bool hasSelection: sourceMode ? fullLiveryService.selectedSource.length > 0
                                                   : (viewingPreview ? fullLiveryService.selectedPackage.length > 0
                                                                     : fullLiveryService.browsedPackage.length > 0)
    readonly property var sourceData: fullLiveryService.sourceDetails || ({})
    readonly property var packageData: fullLiveryService.packageDetails || ({})
    readonly property var galleryData: sourceMode ? sourceData : packageData
    readonly property string selectionTitle: viewingPreview ? fullLiveryService.selectedTitle
                                                            : (galleryData.title || "Untitled livery")
    readonly property string selectionVehicle: viewingPreview ? fullLiveryService.selectedVehicle
                                                              : (galleryData.modelCode || "Unresolved car")
                                                                + " | Car " + (galleryData.carId || "?")
    readonly property string selectionCounts: viewingPreview ? fullLiveryService.selectedCounts
                                                             : (galleryData.placementCount || 0) + " placements"
    readonly property var evidence: fullLiveryService.previewEvidence || ({})
    signal previewRequested()
    signal studioRequested()
    signal installRequested()

    function display(value) {
        return value === null || value === undefined || value === "" ? "Unknown" : String(value)
    }

    function dimensions(value) {
        // QVariantList is a QML sequence, not necessarily a JavaScript Array.
        return value && value.length === 2
                && Number.isInteger(value[0]) && value[0] > 0
                && Number.isInteger(value[1]) && value[1] > 0
                ? value[0] + " x " + value[1] : "Unknown"
    }

    function evidenceColor(tone) {
        if (tone === "warning" || tone === "warn")
            return Theme.warning
        if (tone === "danger" || tone === "bad" || tone === "error")
            return Theme.danger
        if (tone === "success" || tone === "ok" || tone === "good")
            return Theme.success
        return Theme.muted
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

    component DetailLine: Item {
        property string label: ""
        property string value: ""
        property color valueColor: Theme.text
        id: line
        Layout.fillWidth: true
        implicitHeight: Math.max(detailLabel.implicitHeight, detailValue.implicitHeight)
        Text {
            id: detailLabel
            width: line.width * 0.44
            text: line.label
            textFormat: Text.PlainText
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(11)
            wrapMode: Text.Wrap
        }
        Text {
            id: detailValue
            x: detailLabel.width + Theme.px(10)
            width: Math.max(0, line.width - x)
            text: line.value
            textFormat: Text.PlainText
            color: line.valueColor
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(11)
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignRight
        }
    }

    component DetailHeading: Text {
        Layout.fillWidth: true
        Layout.topMargin: Theme.px(8)
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.displayFamily
        font.pixelSize: Theme.px(12)
        font.weight: Font.DemiBold
        wrapMode: Text.Wrap
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.px(8)

        Text {
            Layout.fillWidth: true
            text: root.hasSelection ? root.selectionTitle
                                    : (root.sourceMode ? "No livery selected" : "No package selected")
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.displayFamily
            font.pixelSize: Theme.px(16)
            font.weight: Font.DemiBold
            wrapMode: Text.Wrap
            maximumLineCount: 3
            elide: Text.ElideRight
            HoverHandler { id: titleHover }
            PlainToolTip {
                visible: titleHover.hovered && root.hasSelection
                text: root.selectionTitle
            }
        }
        Text {
            Layout.fillWidth: true
            visible: root.hasSelection
            text: root.selectionVehicle
            textFormat: Text.PlainText
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(11)
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
            HoverHandler { id: vehicleHover }
            PlainToolTip {
                visible: vehicleHover.hovered
                text: root.selectionVehicle
            }
        }
        Text {
            Layout.fillWidth: true
            visible: root.hasSelection
            text: root.selectionCounts
            textFormat: Text.PlainText
            color: Theme.subtle
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(11)
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }

        PrimaryButton {
            objectName: "openSelectedLiveryPreviewButton"
            Layout.fillWidth: true
            visible: !root.viewingPreview
            dense: true
            text: "Open 3D Preview"
            iconName: "monitor"
            enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                     && root.hasSelection
                     && (!root.sourceMode || fullLiveryService.gameFolder.length > 0)
            toolTipText: !root.sourceMode ? "Verify and open this package using the existing preview worker."
                         : fullLiveryService.gameFolder.length > 0
                         ? "Render the selected livery on its exact car."
                         : "Link the FH6 game folder to enable 3D previews."
            onClicked: root.previewRequested()
        }
        PrimaryButton {
            objectName: "openSelectedLiveryStudioButton"
            Layout.fillWidth: true
            visible: !root.viewingPreview && !root.sourceMode && root.hasSelection
            dense: true
            text: editorService.studioLaunching ? "Starting..." : "Open in Studio"
            iconName: "editor"
            enabled: fullLiveryService.featureEnabled && !fullLiveryService.running
                     && !editorService.studioLaunching
            toolTipText: "Open this package's artwork on its car in Studio. The original package is unchanged."
            onClicked: root.studioRequested()
        }
        Text {
            objectName: "liveryStudioPackageStatus"
            Layout.fillWidth: true
            visible: !root.viewingPreview && !root.sourceMode && root.hasSelection
                     && editorService.studioPackagePath === fullLiveryService.browsedPackage
                     && editorService.studioStatus.length > 0
            text: editorService.studioStatus
            textFormat: Text.PlainText
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(11)
            wrapMode: Text.Wrap
            maximumLineCount: 5
            elide: Text.ElideRight
            HoverHandler { id: studioStatusHover }
            PlainToolTip {
                visible: studioStatusHover.hovered
                text: editorService.studioStatus
            }
        }
        PrimaryButton {
            Layout.fillWidth: true
            visible: root.sourceMode
            dense: true
            text: fullLiveryService.running ? "Working..." : "Export Selected"
            iconName: "transfer"
            enabled: !fullLiveryService.running && fullLiveryService.featureEnabled
                     && fullLiveryService.selectedSource.length > 0
                     && fullLiveryService.selectedSourceExportable
            toolTipText: fullLiveryService.selectedSourceExportable
                         ? "Create a verified shareable package. Game meshes stay local."
                         : "This source cannot be exported. See the source details."
            onClicked: fullLiveryService.exportSelected()
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(1, Theme.px(1))
            color: Theme.divider
        }

        Flickable {
            id: detailsScroll
            objectName: "liveryDetailsScroll"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 0
            contentWidth: width
            contentHeight: detailContent.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            activeFocusOnTab: true
            Accessible.name: "Livery information"
            Accessible.description: "Scrollable source, preview and compatibility details"

            function reveal(item) {
                var top = item.mapToItem(detailContent, 0, 0).y
                if (top < contentY)
                    contentY = top
                else if (top + item.height > contentY + height)
                    contentY = top + item.height - height
                contentY = Math.max(0, Math.min(Math.max(0, contentHeight - height), contentY))
            }
            Keys.onPressed: event => {
                var next = contentY
                switch (event.key) {
                case Qt.Key_Up: next -= Theme.px(32); break
                case Qt.Key_Down: next += Theme.px(32); break
                case Qt.Key_PageUp: next -= height * 0.9; break
                case Qt.Key_PageDown: next += height * 0.9; break
                case Qt.Key_Home: next = 0; break
                case Qt.Key_End: next = contentHeight; break
                default: return
                }
                contentY = Math.max(0, Math.min(Math.max(0, contentHeight - height), next))
                event.accepted = true
            }
            Rectangle {
                x: detailsScroll.contentX
                y: detailsScroll.contentY
                width: detailsScroll.width
                height: detailsScroll.height
                z: 2
                visible: detailsScroll.activeFocus
                color: Theme.withAlpha(Theme.surface, 0)
                border.width: Math.max(1, Theme.px(1))
                border.color: Theme.focusColor
            }

            ColumnLayout {
                id: detailContent
                objectName: "liveryDetailsContent"
                width: Math.max(0, detailsScroll.width - detailsBar.implicitWidth - Theme.px(5))
                spacing: Theme.px(7)

                ColumnLayout {
                    visible: root.sourceMode && root.hasSelection
                    Layout.fillWidth: true
                    spacing: Theme.px(7)
                    DetailHeading { text: "Source details" }
                    DetailLine { label: "Modified"; value: root.display(root.sourceData.modified) }
                    DetailLine {
                        label: "Header"
                        value: root.sourceData.hasHeader === true ? "Present"
                               : (root.sourceData.hasHeader === false ? "Not present" : "Unknown")
                    }
                    DetailLine {
                        label: "Availability"
                        value: root.sourceData.exportable === true ? "Exportable"
                               : (root.sourceData.exportable === false ? "Preview only" : "Unknown")
                        valueColor: root.sourceData.exportable === false ? Theme.warning : Theme.text
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: root.sourceData.privacyDetail || fullLiveryService.selectedSourcePrivacyMessage
                        textFormat: Text.PlainText
                        color: Theme.warning
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(11)
                        wrapMode: Text.Wrap
                    }
                }

                ColumnLayout {
                    visible: !root.sourceMode && root.hasSelection && !root.viewingPreview
                    Layout.fillWidth: true
                    spacing: Theme.px(7)
                    DetailHeading { text: "Package details" }
                    DetailLine { label: "Created"; value: root.display(root.packageData.created) }
                    DetailLine {
                        label: "Portable mesh"
                        value: root.packageData.portableMesh === true ? "Declared" : "Not included"
                    }
                    DetailLine { label: "Verification"; value: "Pending open" }
                }

                ColumnLayout {
                    visible: root.viewingPreview
                    Layout.fillWidth: true
                    spacing: Theme.px(7)
                    DetailHeading { text: "Preview evidence" }
                    DetailLine {
                        label: "Quality scale"
                        value: root.evidence.quality_scale === null || root.evidence.quality_scale === undefined
                               ? "Unknown" : root.evidence.quality_scale + "x"
                    }
                    DetailLine { label: "Paint atlas"; value: root.dimensions(root.evidence.paint_size) }
                    DetailLine { label: "Mask atlas"; value: root.dimensions(root.evidence.mask_size) }
                    DetailLine {
                        label: "Mesh cache"
                        value: root.evidence.mesh_cache_hit === true ? "Reused"
                               : (root.evidence.mesh_cache_hit === false ? "Rebuilt" : "Unknown")
                    }
                    DetailLine { label: "Limitations"; value: root.display(root.evidence.limitation_count) }

                    DetailHeading {
                        visible: (root.evidence.geometry || []).length > 0
                        text: "Geometry"
                    }
                    Repeater {
                        model: root.evidence.geometry || []
                        delegate: DetailLine {
                            required property var modelData
                            label: root.display(modelData.label)
                            value: root.display(modelData.value)
                            valueColor: root.evidenceColor(modelData.tone)
                        }
                    }
                    DetailHeading {
                        visible: (root.evidence.materials || []).length > 0
                        text: "Materials"
                    }
                    Repeater {
                        model: root.evidence.materials || []
                        delegate: DetailLine {
                            required property var modelData
                            label: root.display(modelData.label)
                            value: root.display(modelData.value)
                            valueColor: root.evidenceColor(modelData.tone)
                        }
                    }
                    DetailHeading {
                        visible: (root.evidence.warnings || []).length > 0
                        text: "Warnings"
                    }
                    Repeater {
                        model: root.evidence.warnings || []
                        delegate: Text {
                            required property var modelData
                            Layout.fillWidth: true
                            text: String(modelData)
                            textFormat: Text.PlainText
                            color: Theme.warning
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(11)
                            wrapMode: Text.Wrap
                        }
                    }
                    DetailHeading {
                        visible: fullLiveryService.sectionDetails.length > 0
                        text: "Livery sections"
                    }
                    Repeater {
                        model: fullLiveryService.sectionDetails
                        delegate: DetailLine {
                            required property var modelData
                            label: root.display(modelData.name)
                            value: root.display(modelData.count) + " placements"
                        }
                    }
                    DetailHeading {
                        visible: (root.evidence.sections || []).length > 0
                        text: "Preview slots"
                    }
                    Repeater {
                        model: root.evidence.sections || []
                        delegate: DetailLine {
                            required property var modelData
                            label: root.display(modelData.name)
                            value: "Slot " + root.display(modelData.slot_index)
                        }
                    }

                    GhostButton {
                        id: compatibilityToggle
                        objectName: "liveryCompatibilityToggle"
                        Layout.fillWidth: true
                        Layout.topMargin: Theme.px(8)
                        dense: true
                        text: "Compatibility"
                        iconName: "source-check"
                        checkable: true
                        checked: root.compatibilityExpanded
                        onToggled: root.compatibilityExpanded = checked
                        onActiveFocusChanged: {
                            if (activeFocus)
                                Qt.callLater(() => detailsScroll.reveal(compatibilityToggle))
                        }
                        toolTipText: checked ? "Collapse package compatibility details." : "Expand package compatibility details."
                    }
                    ColumnLayout {
                        visible: root.compatibilityExpanded
                        Layout.fillWidth: true
                        spacing: Theme.px(7)
                        Repeater {
                            model: fullLiveryService.decisionModel
                            delegate: ColumnLayout {
                                id: decisionEntry
                                required property string action
                                required property string item
                                required property string detail
                                Layout.fillWidth: true
                                spacing: Theme.px(3)
                                Text {
                                    Layout.fillWidth: true
                                    text: decisionEntry.action + "  " + decisionEntry.item
                                    textFormat: Text.PlainText
                                    color: decisionEntry.action === "DISCARD" ? Theme.danger
                                           : (decisionEntry.action === "CHANGE" ? Theme.warning
                                           : (decisionEntry.action === "KEEP" ? Theme.success : Theme.primaryBright))
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.px(10)
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.Wrap
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: decisionEntry.detail
                                    textFormat: Text.PlainText
                                    color: Theme.muted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(11)
                                    wrapMode: Text.Wrap
                                }
                            }
                        }
                    }
                }
            }
            ScrollBar.vertical: KfpsScrollBar {
                id: detailsBar
                objectName: "liveryDetailsScrollBar"
                policy: ScrollBar.AsNeeded
            }
        }

        PrimaryButton {
            objectName: "installExactCarFullLiveryButton"
            Layout.fillWidth: true
            visible: root.viewingPreview
            dense: true
            text: fullLiveryService.running ? "Working..." : "Install in FH6 Save"
            iconName: "transfer"
            enabled: !fullLiveryService.running && fullLiveryService.selectedPackageInstallable
            toolTipText: fullLiveryService.selectedPackageInstallable
                         ? "Install this package as a new local livery for its exact FH6 car."
                         : "Open a verified shareable package for its exact FH6 car first."
            onClicked: root.installRequested()
        }
    }
}
