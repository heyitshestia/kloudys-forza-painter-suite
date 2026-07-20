import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Dialogs 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    anchors.fill: parent
    property bool wide: Theme.logical(width) >= 820
    property var layerOptions: ["500", "1000", "1500", "2000", "2500", "3000"]
    property var customLayerCombo: null
    property var customCheckpointField: null
    property int seenSourceRevision: sourceService.revision
    property int seenPreviewRevision: generationService.previewRevision
    property bool preferSourcePreview: false
    readonly property string generatedPreviewUrl: generationService.previewUrl
                                                   ? generationService.previewUrl
                                                     + (generationService.previewUrl.indexOf("?") >= 0 ? "&" : "?")
                                                     + "kfpsPreview=" + generationService.previewRevision
                                                   : ""
    property string activePreviewUrl: preferSourcePreview ? sourceService.url : (generatedPreviewUrl || sourceService.url)
    readonly property bool headerAlignmentAvailable: Boolean(pageLayoutLoader.item && pageLayoutLoader.item.headerAlignmentAvailable)
    readonly property real headerSourceCenterX: headerAlignmentAvailable ? pageLayoutLoader.item.headerSourceCenterX : 0
    readonly property real headerPreviewCenterX: headerAlignmentAvailable ? pageLayoutLoader.item.headerPreviewCenterX : 0
    readonly property real headerBannerLeftX: headerAlignmentAvailable ? pageLayoutLoader.item.headerBannerLeftX : 0
    readonly property real headerBannerRightX: headerAlignmentAvailable ? pageLayoutLoader.item.headerBannerRightX : 0
    readonly property string detailHeatmapTip: "Usually leave this off.\nKFPS automatically uses detail-focused processing when the preset or source needs it.\nManual use is mostly for controlled testing."
    readonly property string lumaPrepTip: "Usually leave this off.\nKFPS automatically prepares brightness and transparency when a preset benefits from it.\nTurning it on manually can make some images worse."
    readonly property string edgeRepairTip: "Usually leave this off.\nKFPS automatically handles cleanup when appropriate.\nManual edge repair is only for sources with obvious cutout holes or broken edges."
    readonly property string sampleBoostTip: "This is the only option most users should touch.\n2x mode makes the generator spend about twice as much work looking for better shape matches.\nIt can improve detail or smoother edges, but it takes longer."

    function notePreviewRevision() {
        if (seenPreviewRevision === generationService.previewRevision)
            return
        seenPreviewRevision = generationService.previewRevision
        preferSourcePreview = false
    }

    function noteSourceRevision() {
        if (seenSourceRevision === sourceService.revision)
            return
        seenSourceRevision = sourceService.revision
        preferSourcePreview = !!sourceService.url
    }

    function checkpointTextFor(layerText) {
        var target = parseInt(layerText)
        if (!target || target < 1)
            target = 2000
        var base = [500, 1000, 1250, 1500, 2000, 2500, 3000]
        var seen = {}
        var out = []
        for (var i = 0; i < base.length; ++i) {
            if (base[i] <= target) {
                seen[base[i]] = true
                out.push(base[i])
            }
        }
        if (!seen[target])
            out.push(target)
        out.sort(function(a, b) { return a - b })
        return out.join(",")
    }

    function setLayerValue(combo, checkpointField, value) {
        var target = parseInt(value)
        if (!target || target < 1)
            return
        target = Math.max(1, Math.min(3000, target))
        var text = String(target)
        var items = []
        var found = false
        for (var i = 0; i < combo.model.length; ++i) {
            var item = String(combo.model[i])
            if (item === text)
                found = true
            items.push(item)
        }
        if (!found)
            items.push(text)
        items.sort(function(a, b) { return parseInt(a) - parseInt(b) })
        combo.model = items
        combo.currentIndex = items.indexOf(text)
        checkpointField.text = checkpointTextFor(text)
    }

    function openCustomLayerDialog(combo, checkpointField) {
        customLayerCombo = combo
        customCheckpointField = checkpointField
        customLayerInput.text = combo.currentText || "2000"
        customLayerDialog.open()
        customLayerInput.forceActiveFocus()
        customLayerInput.selectAll()
    }

    Loader {
        id: pageLayoutLoader
        anchors.fill: parent
        sourceComponent: root.wide ? wideComp : compactComp
    }

    Connections {
        target: generationService
        function onChanged() {
            root.notePreviewRevision()
        }
    }

    Connections {
        target: sourceService
        function onChanged() {
            root.noteSourceRevision()
        }
    }

    Component.onCompleted: {
        root.seenSourceRevision = sourceService.revision
        root.seenPreviewRevision = generationService.previewRevision
    }

    Component {
        id: wideComp
        GridLayout {
            readonly property bool headerAlignmentAvailable: columns >= 2
                                                         && sourceControlsCard.width > 0
                                                         && livePreviewCard.width > 0
            readonly property real headerSourceCenterX: sourceControlsCard.x + sourceControlsCard.width / 2
            readonly property real headerPreviewCenterX: livePreviewCard.x + livePreviewCard.width / 2
            readonly property real headerBannerLeftX: sourceControlsCard.x
            readonly property real headerBannerRightX: livePreviewCard.x + livePreviewCard.width
            columns: Theme.logical(root.width) >= 1060 ? 3 : 2
            columnSpacing: Theme.px(10)
            rowSpacing: Theme.px(10)

            HoverCard {
                id: sourceControlsCard
                Layout.preferredWidth: Theme.px(286)
                Layout.fillHeight: true
                padding: Theme.px(16)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(8)

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "Source and run controls"
                        subtitle: "Choose one source, a preset, and the target game layer budget."
                    }

                    FastScrollView {
                        id: controlScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: availableWidth
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        ColumnLayout {
                            width: controlScroll.availableWidth
                            spacing: Theme.px(8)

                            Label {
                                text: "Source image"
                            }
                            PrimaryButton {
                                Layout.fillWidth: true
                                text: "Choose source image(s)"
                                iconName: "images"
                                toolTipText: "Choose one or more images to turn into Forza vinyl shapes. PNG files with a transparent background usually work best."
                                onClicked: sourceService.choose()
                            }
                            Text {
                                Layout.fillWidth: true
                                text: sourceService.summary
                                color: Theme.subtle
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.px(9.3)
                                elide: Text.ElideMiddle
                            }

                            Label {
                                text: "Preset"
                            }
                            KfpsComboBox {
                                id: preset
                                Layout.fillWidth: true
                                model: generationService.presets
                                toolTipText: "Choose how KFPS interprets the artwork. A suitable preset is selected automatically when you choose an image."
                                currentIndex: generationService.selectedPresetIndex
                                onActivated: generationService.setSelectedPresetIndex(currentIndex)
                                Component.onCompleted: currentIndex = generationService.selectedPresetIndex
                                Connections {
                                    target: generationService
                                    function onChanged() {
                                        if (preset.currentIndex !== generationService.selectedPresetIndex)
                                            preset.currentIndex = generationService.selectedPresetIndex
                                    }
                                }
                                Connections {
                                    target: sourceService
                                    function onChanged() {
                                        if (sourceService.path)
                                            generationService.autoSelectPresetForImage(sourceService.path)
                                    }
                                }
                            }

                            GridLayout {
                                Layout.fillWidth: true
                                columns: 2
                                columnSpacing: Theme.px(8)

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.columnSpan: 2
                                    Label {
                                        text: "Layers"
                                    }
                                    KfpsComboBox {
                                        id: layers
                                        Layout.fillWidth: true
                                        model: root.layerOptions
                                        toolTipText: "Choose the maximum number of shapes for the finished vinyl. Double-click to enter a custom count from 1 to 3000."
                                        currentIndex: 3
                                        onActivated: checkpoints.text = root.checkpointTextFor(currentText)
                                        onDoubleTapped: root.openCustomLayerDialog(layers, checkpoints)
                                    }
                                }
                            }

                            Label {
                                text: "Finalize checkpoints"
                            }
                            KfpsTextField {
                                id: checkpoints
                                Layout.fillWidth: true
                                text: "500,1000,1250,1500,2000"
                                toolTipText: "Enter comma-separated shape counts. KFPS saves a finished JSON and preview at each count it reaches."
                            }

                            Label {
                                text: "Options"
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 2
                                columnSpacing: Theme.px(6)
                                rowSpacing: Theme.px(2)

                                KfpsCheckBox {
                                    id: heat
                                    Layout.fillWidth: true
                                    text: "Automatic Detail Heatmap"
                                    checked: false
                                    dense: true
                                    toolTipText: root.detailHeatmapTip
                                }
                                KfpsCheckBox {
                                    id: luma
                                    Layout.fillWidth: true
                                    text: "Luma Prep"
                                    checked: false
                                    dense: true
                                    toolTipText: root.lumaPrepTip
                                }
                                KfpsCheckBox {
                                    id: repair
                                    Layout.fillWidth: true
                                    text: "Edge Repair"
                                    checked: false
                                    dense: true
                                    toolTipText: root.edgeRepairTip
                                }
                                KfpsCheckBox {
                                    id: boost
                                    Layout.fillWidth: true
                                    text: "2x Mode"
                                    checked: false
                                    dense: true
                                    toolTipText: root.sampleBoostTip
                                }
                            }

                            ColumnLayout {
                                visible: settings.manualOverrides
                                Layout.fillWidth: true
                                Label {
                                    text: "Manual generator overrides"
                                }
                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 2
                                    columnSpacing: Theme.px(6)
                                    rowSpacing: Theme.px(5)
                                    KfpsTextField {
                                        id: maxRes
                                        Layout.fillWidth: true
                                        placeholderText: "Max res"
                                        toolTipText: "Advanced: limit the working image resolution. Leave the preset value unless you are testing performance or fine detail."
                                    }
                                    KfpsTextField {
                                        id: randomSamples
                                        Layout.fillWidth: true
                                        placeholderText: "Random"
                                        toolTipText: "Advanced: set how many fresh shape candidates are tested per search step. Higher values take longer."
                                    }
                                    KfpsTextField {
                                        id: mutatedSamples
                                        Layout.fillWidth: true
                                        placeholderText: "Mutated"
                                        toolTipText: "Advanced: set how many variations of promising candidates are tested. Higher values take longer."
                                    }
                                    KfpsTextField {
                                        id: seed
                                        Layout.fillWidth: true
                                        inputMethodHints: Qt.ImhDigitsOnly
                                        placeholderText: "Seed"
                                        toolTipText: "Advanced: use the same number to repeat the same randomized search. Use 0 for the normal automatic seed."
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.px(7)

                        PrimaryButton {
                            Layout.fillWidth: true
                            text: generationService.running ? "Generating…" : "Generate Vinyl"
                            iconName: "generate"
                            toolTipText: "Start generating every queued image with the selected layer budget, checkpoints, and options."
                            enabled: !generationService.running
                            onClicked: generationService.startQueue(sourceService.queuedPaths, preset.currentIndex, layers.currentText, checkpoints.text, luma.checked, heat.checked, repair.checked, boost.checked, settings.manualOverrides, settings.manualOverrides ? maxRes.text : "", settings.manualOverrides ? randomSamples.text : "", settings.manualOverrides ? mutatedSamples.text : "", settings.manualOverrides ? (parseInt(seed.text) || 0) : 0)
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            GhostButton {
                                Layout.fillWidth: true
                                text: "Stop Safely"
                                toolTipText: "Finish the current work and save all completed checkpoints before stopping."
                                minimumWidth: Theme.px(108)
                                enabled: generationService.running
                                onClicked: generationService.gracefulStop()
                            }
                            GhostButton {
                                Layout.fillWidth: true
                                text: "Stop Now"
                                toolTipText: "End generation immediately. Completed checkpoints are kept, but the current unfinished step is lost."
                                minimumWidth: Theme.px(96)
                                enabled: generationService.running
                                onClicked: forceDialog.open()
                            }
                        }
                    }
                }
            }

            HoverCard {
                id: livePreviewCard
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: Theme.px(450)
                padding: Theme.px(16)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(8)

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "LIVE OUTPUT PREVIEW"
                            color: Theme.subtle
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(10)
                            font.weight: Font.DemiBold
                        }
                        Item {
                            Layout.fillWidth: true
                        }
                        GhostButton {
                            text: "Refresh Preview"
                            minimumWidth: Theme.px(82)
                            toolTipText: "Reload the source or latest generated preview from disk."
                            onClicked: generationService.refreshPreview()
                        }
                        GhostButton {
                            text: "Open Editor"
                            minimumWidth: Theme.px(104)
                            toolTipText: "Open the manual editor in a new browser window for detailed shape changes."
                            onClicked: editorService.launch()
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: Theme.corner(Theme.px(10))
                        color: Theme.previewSurfaceSoft
                        border.width: Math.max(1, Theme.px(1))
                        border.color: Theme.borderSoft
                        ClassicBevel {
                            anchors.fill: parent
                            sunken: true
                            z: 20
                        }
                        Image {
                            anchors.fill: parent
                            anchors.margins: Theme.px(12)
                            source: root.activePreviewUrl
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            cache: false
                        }
                        EmptyState {
                            visible: !root.activePreviewUrl
                            anchors.centerIn: parent
                            iconName: "images"
                            title: "No output selected"
                            message: "Choose a source image or start a generation."
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.px(18)
                        Layout.minimumHeight: Theme.px(18)
                        Layout.maximumHeight: Theme.px(18)

                        Text {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Status: " + generationService.status
                            color: generationService.running ? Theme.warning : Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(10.5)
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                            wrapMode: Text.NoWrap
                            clip: true
                        }
                    }

                    GlassPanel {
                        visible: Theme.logical(root.width) < 1060
                        Layout.fillWidth: true
                        Layout.preferredHeight: visible ? Theme.px(132) : 0
                        Layout.minimumHeight: visible ? Theme.px(118) : 0
                        soft: true

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.px(10)
                            spacing: Theme.px(6)

                            Text {
                                Layout.fillWidth: true
                                text: "Live generation log"
                                color: Theme.primaryBright
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(12)
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }

                            FastScrollView {
                                id: centerGenerationLiveLogScroll
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                contentWidth: availableWidth
                                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                                Timer {
                                    id: centerGenerationLiveLogPinTimer
                                    interval: 0
                                    repeat: false
                                    onTriggered: {
                                        if (centerGenerationLiveLogScroll.contentItem)
                                            centerGenerationLiveLogScroll.contentItem.contentY = Math.max(0, centerGenerationLiveLogScroll.contentItem.contentHeight - centerGenerationLiveLogScroll.contentItem.height)
                                    }
                                }

                                Text {
                                    width: centerGenerationLiveLogScroll.availableWidth
                                    text: generationService.liveLog
                                    color: Theme.muted
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.px(9.5)
                                    wrapMode: Text.Wrap
                                    onTextChanged: centerGenerationLiveLogPinTimer.restart()
                                }
                            }
                        }
                    }
                }
            }

            HoverCard {
                visible: Theme.logical(root.width) >= 1060
                Layout.preferredWidth: visible ? Theme.px(270) : 0
                Layout.fillHeight: true
                padding: Theme.px(16)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(9)

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "Source preview"
                        subtitle: "The selected input and source check stay visible while you work."
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.px(210)
                        radius: Theme.corner(Theme.px(10))
                        color: Theme.previewSurface
                        border.width: Math.max(1, Theme.px(1))
                        border.color: Theme.borderSoft
                        ClassicBevel {
                            anchors.fill: parent
                            sunken: true
                            z: 20
                        }
                        Image {
                            anchors.fill: parent
                            anchors.margins: Theme.px(8)
                            source: sourceService.url
                            fillMode: Image.PreserveAspectFit
                        }
                        EmptyState {
                            visible: !sourceService.url
                            anchors.centerIn: parent
                            iconName: "images"
                            title: "Choose a source"
                            message: "PNG, JPEG, WebP, or BMP"
                        }
                    }
                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.px(88)
                        soft: true
                        border.color: sourceService.severity === "red" ? Theme.danger : (sourceService.severity === "yellow" ? Theme.warning : (sourceService.severity === "green" ? Theme.success : Theme.border))
                        Column {
                            anchors.fill: parent
                            anchors.margins: Theme.px(12)
                            spacing: Theme.px(6)
                            Text {
                                text: sourceService.reportTitle
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(12.5)
                                font.weight: Font.DemiBold
                            }
                            Text {
                                width: parent.width
                                text: sourceService.reportMessage
                                color: Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(10.2)
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: Theme.px(122)
                        soft: true

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.px(10)
                            spacing: Theme.px(6)

                            Text {
                                Layout.fillWidth: true
                                text: "Live generation log"
                                color: Theme.primaryBright
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(12)
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }

                            FastScrollView {
                                id: generationLiveLogScroll
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                contentWidth: availableWidth
                                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                                Timer {
                                    id: generationLiveLogPinTimer
                                    interval: 0
                                    repeat: false
                                    onTriggered: {
                                        if (generationLiveLogScroll.contentItem)
                                            generationLiveLogScroll.contentItem.contentY = Math.max(0, generationLiveLogScroll.contentItem.contentHeight - generationLiveLogScroll.contentItem.height)
                                    }
                                }

                                Text {
                                    width: generationLiveLogScroll.availableWidth
                                    text: generationService.liveLog
                                    color: Theme.muted
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.px(9.5)
                                    wrapMode: Text.Wrap
                                    onTextChanged: generationLiveLogPinTimer.restart()
                                }
                            }
                        }
                    }
                    GhostButton {
                        Layout.fillWidth: true
                        text: "Open Generated Folder"
                        iconName: "folder"
                        toolTipText: "Open the folder that contains generated JSON files, previews, checkpoints, and reports."
                        onClicked: desktop.openGenerated()
                    }
                }
            }
        }
    }

    Component {
        id: compactComp
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
                    title: "Generate Vinyl"
                    subtitle: "Compact mode keeps every generator option available and scrollable."
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(455)
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Theme.px(8)
                        PrimaryButton {
                            Layout.fillWidth: true
                            text: "Choose source image(s)"
                            iconName: "images"
                            toolTipText: "Choose one or more images to turn into Forza vinyl shapes. PNG files with a transparent background usually work best."
                            onClicked: sourceService.choose()
                        }
                        KfpsComboBox {
                            id: cp
                            Layout.fillWidth: true
                            model: generationService.presets
                            toolTipText: "Choose how KFPS interprets the artwork. A suitable preset is selected automatically when you choose an image."
                            currentIndex: generationService.selectedPresetIndex
                            onActivated: generationService.setSelectedPresetIndex(currentIndex)
                            Component.onCompleted: currentIndex = generationService.selectedPresetIndex
                            Connections {
                                target: generationService
                                function onChanged() {
                                    if (cp.currentIndex !== generationService.selectedPresetIndex)
                                        cp.currentIndex = generationService.selectedPresetIndex
                                }
                            }
                            Connections {
                                target: sourceService
                                function onChanged() {
                                    if (sourceService.path)
                                        generationService.autoSelectPresetForImage(sourceService.path)
                                }
                            }
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            KfpsComboBox {
                                id: cl
                                Layout.fillWidth: true
                                Layout.columnSpan: 2
                                model: root.layerOptions
                                toolTipText: "Choose the maximum number of shapes for the finished vinyl. Double-click to enter a custom count from 1 to 3000."
                                currentIndex: 3
                                onActivated: cc.text = root.checkpointTextFor(currentText)
                                onDoubleTapped: root.openCustomLayerDialog(cl, cc)
                            }
                        }
                        KfpsTextField {
                            id: cc
                            Layout.fillWidth: true
                            text: "500,1000,1250,1500,2000"
                            toolTipText: "Enter comma-separated shape counts. KFPS saves a finished JSON and preview at each count it reaches."
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            KfpsCheckBox {
                                id: cHeat
                                text: "Detail Heatmap"
                                toolTipText: root.detailHeatmapTip
                            }
                            KfpsCheckBox {
                                id: cLuma
                                text: "Luma Prep"
                                toolTipText: root.lumaPrepTip
                            }
                            KfpsCheckBox {
                                id: cRepair
                                text: "Edge Repair"
                                checked: false
                                toolTipText: root.edgeRepairTip
                            }
                            KfpsCheckBox {
                                id: cBoost
                                text: "2x Mode"
                                checked: false
                                toolTipText: root.sampleBoostTip
                            }
                        }
                        ColumnLayout {
                            visible: settings.manualOverrides
                            Layout.fillWidth: true
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 2
                                columnSpacing: Theme.px(6)
                                rowSpacing: Theme.px(5)
                                KfpsTextField {
                                    id: cMax
                                    Layout.fillWidth: true
                                    placeholderText: "Max res"
                                    toolTipText: "Advanced: limit the working image resolution. Leave the preset value unless you are testing performance or fine detail."
                                }
                                KfpsTextField {
                                    id: cRandom
                                    Layout.fillWidth: true
                                    placeholderText: "Random"
                                    toolTipText: "Advanced: set how many fresh shape candidates are tested per search step. Higher values take longer."
                                }
                                KfpsTextField {
                                    id: cMutated
                                    Layout.fillWidth: true
                                    placeholderText: "Mutated"
                                    toolTipText: "Advanced: set how many variations of promising candidates are tested. Higher values take longer."
                                }
                                KfpsTextField {
                                    id: cseed
                                    Layout.fillWidth: true
                                    inputMethodHints: Qt.ImhDigitsOnly
                                    placeholderText: "Seed"
                                    toolTipText: "Advanced: use the same number to repeat the same randomized search. Use 0 for the normal automatic seed."
                                }
                            }
                        }
                        Item {
                            Layout.fillHeight: true
                        }
                        PrimaryButton {
                            Layout.fillWidth: true
                            text: generationService.running ? "Generating…" : "Generate Vinyl"
                            toolTipText: "Start generating every queued image with the selected layer budget, checkpoints, and options."
                            enabled: !generationService.running
                            onClicked: generationService.startQueue(sourceService.queuedPaths, cp.currentIndex, cl.currentText, cc.text, cLuma.checked, cHeat.checked, cRepair.checked, cBoost.checked, settings.manualOverrides, settings.manualOverrides ? cMax.text : "", settings.manualOverrides ? cRandom.text : "", settings.manualOverrides ? cMutated.text : "", settings.manualOverrides ? (parseInt(cseed.text) || 0) : 0)
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            GhostButton {
                                Layout.fillWidth: true
                                text: "Stop Safely"
                                toolTipText: "Finish the current work and save all completed checkpoints before stopping."
                                enabled: generationService.running
                                onClicked: generationService.gracefulStop()
                            }
                            GhostButton {
                                Layout.fillWidth: true
                                text: "Stop Now"
                                toolTipText: "End generation immediately. Completed checkpoints are kept, but the current unfinished step is lost."
                                enabled: generationService.running
                                onClicked: forceDialog.open()
                            }
                        }
                    }
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(390)
                    Image {
                        anchors.fill: parent
                        anchors.margins: Theme.px(12)
                        source: root.activePreviewUrl
                        fillMode: Image.PreserveAspectFit
                    }
                    EmptyState {
                        visible: !root.activePreviewUrl
                        anchors.centerIn: parent
                        title: "No preview"
                        message: "Choose a source or begin generation."
                    }
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(132)
                    soft: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(10)
                        spacing: Theme.px(6)

                        Text {
                            Layout.fillWidth: true
                            text: "Live generation log"
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(12)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        FastScrollView {
                            id: compactGenerationLiveLogScroll
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            contentWidth: availableWidth
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                            Timer {
                                id: compactGenerationLiveLogPinTimer
                                interval: 0
                                repeat: false
                                onTriggered: {
                                    if (compactGenerationLiveLogScroll.contentItem)
                                        compactGenerationLiveLogScroll.contentItem.contentY = Math.max(0, compactGenerationLiveLogScroll.contentItem.contentHeight - compactGenerationLiveLogScroll.contentItem.height)
                                }
                            }

                            Text {
                                width: compactGenerationLiveLogScroll.availableWidth
                                text: generationService.liveLog
                                color: Theme.muted
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.px(9.5)
                                wrapMode: Text.Wrap
                                onTextChanged: compactGenerationLiveLogPinTimer.restart()
                            }
                        }
                    }
                }
            }
        }
    }

    MessageDialog {
        id: forceDialog
        title: "Stop generation now?"
        text: "Stop Now ends the active Genesis search immediately, then preserves every completed checkpoint and preview. Use it only if Stop Safely does not work."
        buttons: MessageDialog.Ok | MessageDialog.Cancel
        onAccepted: generationService.forceStop()
    }

    Dialog {
        id: customLayerDialog
        modal: true
        title: "Custom layer count"
        standardButtons: Dialog.Ok | Dialog.Cancel
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        width: Theme.px(320)

        background: Rectangle {
            color: Theme.surface
            border.width: Theme.classicMode ? 0 : Math.max(1, Theme.px(1))
            border.color: Theme.borderStrong
            radius: Theme.corner(Theme.px(10))
            ClassicBevel { anchors.fill: parent }
        }

        ColumnLayout {
            width: parent.width
            spacing: Theme.px(10)
            Text {
                Layout.fillWidth: true
                text: "Enter a target layer count between 1 and 3000."
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(11)
                wrapMode: Text.Wrap
            }
            KfpsTextField {
                id: customLayerInput
                Layout.fillWidth: true
                inputMethodHints: Qt.ImhDigitsOnly
                placeholderText: "Layer count"
                toolTipText: "Enter the maximum number of shapes to generate, from 1 to 3000."
                validator: IntValidator { bottom: 1; top: 3000 }
                onAccepted: customLayerDialog.accept()
            }
        }

        onAccepted: {
            if (root.customLayerCombo && root.customCheckpointField)
                root.setLayerValue(root.customLayerCombo, root.customCheckpointField, customLayerInput.text)
        }
    }
}
