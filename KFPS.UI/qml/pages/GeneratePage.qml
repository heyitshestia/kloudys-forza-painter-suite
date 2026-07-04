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
        anchors.fill: parent
        sourceComponent: root.wide ? wideComp : compactComp
    }

    Component {
        id: wideComp
        GridLayout {
            columns: Theme.logical(root.width) >= 1060 ? 3 : 2
            columnSpacing: Theme.px(10)
            rowSpacing: Theme.px(10)

            HoverCard {
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
                                    Label {
                                        text: "Layers"
                                    }
                                    KfpsComboBox {
                                        id: layers
                                        Layout.fillWidth: true
                                        model: root.layerOptions
                                        currentIndex: 3
                                        onActivated: checkpoints.text = root.checkpointTextFor(currentText)
                                        onDoubleTapped: root.openCustomLayerDialog(layers, checkpoints)
                                    }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Label {
                                        text: "Seed"
                                    }
                                    KfpsTextField {
                                        id: seed
                                        Layout.fillWidth: true
                                        text: "0"
                                        inputMethodHints: Qt.ImhDigitsOnly
                                        placeholderText: "Random"
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
                                }
                                KfpsCheckBox {
                                    id: luma
                                    Layout.fillWidth: true
                                    text: "Luma Prep"
                                    checked: false
                                    dense: true
                                }
                                KfpsCheckBox {
                                    id: repair
                                    Layout.fillWidth: true
                                    text: "Edge Repair"
                                    checked: false
                                    dense: true
                                }
                                KfpsCheckBox {
                                    id: boost
                                    Layout.fillWidth: true
                                    text: "2x Mode"
                                    checked: false
                                    dense: true
                                }
                            }

                            ColumnLayout {
                                visible: settings.manualOverrides
                                Layout.fillWidth: true
                                Label {
                                    text: "Manual generator overrides"
                                }
                                KfpsTextField {
                                    id: maxRes
                                    Layout.fillWidth: true
                                    placeholderText: "Max resolution"
                                }
                                KfpsTextField {
                                    id: randomSamples
                                    Layout.fillWidth: true
                                    placeholderText: "Random samples"
                                }
                                KfpsTextField {
                                    id: mutatedSamples
                                    Layout.fillWidth: true
                                    placeholderText: "Mutated samples"
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.px(7)

                        PrimaryButton {
                            Layout.fillWidth: true
                            text: generationService.running ? "Generating…" : "Generate Final Vinyl"
                            iconName: "generate"
                            enabled: !generationService.running
                            onClicked: generationService.startQueue(sourceService.queuedPaths, preset.currentIndex, layers.currentText, checkpoints.text, luma.checked, heat.checked, repair.checked, boost.checked, settings.manualOverrides, settings.manualOverrides ? maxRes.text : "", settings.manualOverrides ? randomSamples.text : "", settings.manualOverrides ? mutatedSamples.text : "", parseInt(seed.text) || 0)
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            GhostButton {
                                Layout.fillWidth: true
                                text: "Graceful Stop"
                                minimumWidth: Theme.px(108)
                                enabled: generationService.running
                                onClicked: generationService.gracefulStop()
                            }
                            GhostButton {
                                Layout.fillWidth: true
                                text: "Force Stop"
                                minimumWidth: Theme.px(96)
                                enabled: generationService.running
                                onClicked: forceDialog.open()
                            }
                        }
                    }
                }
            }

            HoverCard {
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
                            text: "Refresh"
                            minimumWidth: Theme.px(82)
                            onClicked: generationService.refreshPreview()
                        }
                        GhostButton {
                            text: "Open Editor"
                            minimumWidth: Theme.px(104)
                            onClicked: editorService.launch()
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: Theme.px(10)
                        color: Theme.previewSurfaceSoft
                        border.width: Math.max(1, Theme.px(1))
                        border.color: Theme.borderSoft
                        Image {
                            anchors.fill: parent
                            anchors.margins: Theme.px(12)
                            source: generationService.previewUrl || sourceService.url
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            cache: false
                        }
                        EmptyState {
                            visible: !(generationService.previewUrl || sourceService.url)
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
                        radius: Theme.px(10)
                        color: Theme.previewSurface
                        border.width: Math.max(1, Theme.px(1))
                        border.color: Theme.borderSoft
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
                        Layout.preferredHeight: Theme.px(132)
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
                    Item {
                        Layout.fillHeight: true
                    }
                    GhostButton {
                        Layout.fillWidth: true
                        text: "Open generated folder"
                        iconName: "folder"
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
                    title: "Generate Final Vinyl"
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
                            onClicked: sourceService.choose()
                        }
                        KfpsComboBox {
                            id: cp
                            Layout.fillWidth: true
                            model: generationService.presets
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
                                model: root.layerOptions
                                currentIndex: 3
                                onActivated: cc.text = root.checkpointTextFor(currentText)
                                onDoubleTapped: root.openCustomLayerDialog(cl, cc)
                            }
                            KfpsTextField {
                                id: cseed
                                Layout.fillWidth: true
                                text: "0"
                                placeholderText: "Seed"
                            }
                        }
                        KfpsTextField {
                            id: cc
                            Layout.fillWidth: true
                            text: "500,1000,1250,1500,2000"
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            KfpsCheckBox {
                                id: cHeat
                                text: "Detail Heatmap"
                            }
                            KfpsCheckBox {
                                id: cLuma
                                text: "Luma Prep"
                            }
                            KfpsCheckBox {
                                id: cRepair
                                text: "Edge Repair"
                                checked: false
                            }
                            KfpsCheckBox {
                                id: cBoost
                                text: "2x Mode"
                                checked: false
                            }
                        }
                        ColumnLayout {
                            visible: settings.manualOverrides
                            Layout.fillWidth: true
                            KfpsTextField {
                                id: cMax
                                Layout.fillWidth: true
                                placeholderText: "Max resolution"
                            }
                            KfpsTextField {
                                id: cRandom
                                Layout.fillWidth: true
                                placeholderText: "Random samples"
                            }
                            KfpsTextField {
                                id: cMutated
                                Layout.fillWidth: true
                                placeholderText: "Mutated samples"
                            }
                        }
                        Item {
                            Layout.fillHeight: true
                        }
                        PrimaryButton {
                            Layout.fillWidth: true
                            text: generationService.running ? "Generating…" : "Generate Final Vinyl"
                            enabled: !generationService.running
                            onClicked: generationService.startQueue(sourceService.queuedPaths, cp.currentIndex, cl.currentText, cc.text, cLuma.checked, cHeat.checked, cRepair.checked, cBoost.checked, settings.manualOverrides, settings.manualOverrides ? cMax.text : "", settings.manualOverrides ? cRandom.text : "", settings.manualOverrides ? cMutated.text : "", parseInt(cseed.text) || 0)
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            GhostButton {
                                Layout.fillWidth: true
                                text: "Graceful Stop"
                                enabled: generationService.running
                                onClicked: generationService.gracefulStop()
                            }
                            GhostButton {
                                Layout.fillWidth: true
                                text: "Force Stop"
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
                        source: generationService.previewUrl || sourceService.url
                        fillMode: Image.PreserveAspectFit
                    }
                    EmptyState {
                        visible: !(generationService.previewUrl || sourceService.url)
                        anchors.centerIn: parent
                        title: "No preview"
                        message: "Choose a source or begin generation."
                    }
                }
            }
        }
    }

    MessageDialog {
        id: forceDialog
        title: "Force stop generation?"
        text: "Force Stop immediately terminates the process tree. Use it only if Graceful Stop does not work."
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
