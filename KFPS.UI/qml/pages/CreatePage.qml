import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Dialogs 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    anchors.fill: parent
    clip: true

    property bool wide: Theme.logical(width) >= 1120
    property bool threeColumns: Theme.logical(width) >= 1180
    property bool compactHeight: Theme.logical(height) < 720
    property bool checkpointsManual: false
    readonly property bool headerAlignmentAvailable: threeColumns
                                                     && sourceSetupCard.width > 0
                                                     && previewCard.width > 0
    readonly property real headerSourceCenterX: sourceSetupCard.x + sourceSetupCard.width / 2
    readonly property real headerPreviewCenterX: previewCard.x + previewCard.width / 2
    readonly property real headerBannerLeftX: sourceSetupCard.x
    readonly property real headerBannerRightX: previewCard.x + previewCard.width
    readonly property string detailHeatmapTip: "Usually leave this off.\nKFPS automatically uses detail-focused processing when the preset or source needs it.\nManual use is mostly for controlled testing."
    readonly property string lumaPrepTip: "Usually leave this off.\nKFPS automatically prepares brightness and transparency when a preset benefits from it.\nTurning it on manually can make some images worse."
    readonly property string edgeRepairTip: "Usually leave this off.\nKFPS automatically handles cleanup when appropriate.\nManual edge repair is only for sources with obvious cutout holes or broken edges."
    readonly property string sampleBoostTip: "This is the only option most users should touch.\n2x mode makes the generator spend about twice as much work looking for better shape matches.\nIt can improve detail or smoother edges, but it takes longer."

    function checkpointTextFor(layerText) {
        var target = parseInt(layerText)
        if (!target || target < 1)
            target = 2000
        target = Math.max(1, Math.min(3000, target))
        var base = [500, 1000, 1250, 1500, 2000, 2500, 3000]
        var out = []
        var seen = {}
        for (var i = 0; i < base.length; ++i) {
            if (base[i] <= target) {
                out.push(base[i])
                seen[base[i]] = true
            }
        }
        if (!seen[target])
            out.push(target)
        out.sort(function(a, b) { return a - b })
        return out.join(",")
    }

    function sourceBorderColor() {
        if (sourceService.severity === "red") return Theme.danger
        if (sourceService.severity === "yellow") return Theme.warning
        if (sourceService.severity === "green") return Theme.success
        return Theme.borderStrong
    }

    Component.onCompleted: Qt.callLater(function () {
        root.forceActiveFocus(Qt.OtherFocusReason)
    })

    Connections {
        target: sourceService
        function onChanged() {
            if (sourceService.url && !generationService.running)
                generationService.clearPreview()
        }
    }

    GridLayout {
        id: pageGrid
        anchors.fill: parent
        columns: root.threeColumns ? 3 : 1
        columnSpacing: Theme.px(12)
        rowSpacing: Theme.px(12)

        HoverCard {
            id: sourceSetupCard
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.threeColumns ? Theme.px(390) : -1
            Layout.minimumWidth: root.threeColumns ? Theme.px(350) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)
            strong: true

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 7 : 9)

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(10)

                    Icon {
                        name: "generate"
                        iconSize: Theme.px(31)
                        glow: true
                        Layout.alignment: Qt.AlignVCenter
                    }

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "1. Source & setup"
                        subtitle: "Choose art, target, and generation options."
                    }
                }

                Label { text: "Source images" }

                PrimaryButton {
                    Layout.fillWidth: true
                    text: sourceService.count > 0 ? "Change source image(s)" : "Choose source image(s)"
                    iconName: "images"
                    onClicked: sourceService.choose()
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(root.compactHeight ? 54 : 62)
                    soft: true
                    border.color: sourceService.path ? Theme.borderStrong : Theme.borderSoft

                    Text {
                        anchors.fill: parent
                        anchors.margins: Theme.px(10)
                        text: sourceService.summary
                        color: sourceService.path ? Theme.muted : Theme.subtle
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.px(root.compactHeight ? 8.7 : 9.2)
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideMiddle
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                Label { text: "Preset" }

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
                    columnSpacing: Theme.px(9)
                    rowSpacing: Theme.px(5)

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.columnSpan: 2
                        spacing: Theme.px(3)
                        Label { text: "Template layers" }
                        KfpsTextField {
                            id: layers
                            Layout.fillWidth: true
                            text: "2000"
                            dense: root.compactHeight
                            placeholderText: "1–3000"
                            inputMethodHints: Qt.ImhDigitsOnly
                            onEditingFinished: if (!root.checkpointsManual) checkpoints.text = root.checkpointTextFor(text)
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(3)
                    Label { text: "Finalize checkpoints" }
                    KfpsTextField {
                        id: checkpoints
                        Layout.fillWidth: true
                        dense: root.compactHeight
                        text: "500,1000,1250,1500,2000"
                        placeholderText: "500,1000,1500,2000"
                        onTextEdited: root.checkpointsManual = true
                    }
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(root.compactHeight ? 92 : 112)
                    soft: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(10)
                        spacing: Theme.px(4)

                        Text {
                            Layout.fillWidth: true
                            text: "Generation options"
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(11.2)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            columns: 2
                            columnSpacing: Theme.px(6)
                            rowSpacing: Theme.px(1)

                            KfpsCheckBox { id: heat; Layout.fillWidth: true; text: "Detail heatmap"; dense: true; toolTipText: root.detailHeatmapTip }
                            KfpsCheckBox { id: luma; Layout.fillWidth: true; text: "Luma prep"; dense: true; toolTipText: root.lumaPrepTip }
                            KfpsCheckBox { id: repair; Layout.fillWidth: true; text: "Edge repair"; dense: true; toolTipText: root.edgeRepairTip }
                            KfpsCheckBox { id: boost; Layout.fillWidth: true; text: "2× mode"; dense: true; toolTipText: root.sampleBoostTip }
                        }
                    }
                }

                GlassPanel {
                    visible: settings.manualOverrides
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? Theme.px(root.compactHeight ? 112 : 128) : 0
                    soft: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(10)
                        spacing: Theme.px(5)

                        Text {
                            Layout.fillWidth: true
                            text: "Manual overrides"
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(11.2)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: Theme.px(6)
                            rowSpacing: Theme.px(5)
                            KfpsTextField { id: maxRes; Layout.fillWidth: true; dense: true; placeholderText: "Max res" }
                            KfpsTextField { id: randomSamples; Layout.fillWidth: true; dense: true; placeholderText: "Random" }
                            KfpsTextField { id: mutatedSamples; Layout.fillWidth: true; dense: true; placeholderText: "Mutated" }
                            KfpsTextField {
                                id: seed
                                Layout.fillWidth: true
                                dense: true
                                placeholderText: "Seed"
                                inputMethodHints: Qt.ImhDigitsOnly
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                PrimaryButton {
                    Layout.fillWidth: true
                    text: generationService.running ? "Generating…" : "Generate Final Vinyl"
                    iconName: "generate"
                    enabled: !generationService.running
                    onClicked: generationService.startQueue(sourceService.queuedPaths, preset.currentIndex, layers.text, checkpoints.text, luma.checked, heat.checked, repair.checked, boost.checked, settings.manualOverrides, settings.manualOverrides ? maxRes.text : "", settings.manualOverrides ? randomSamples.text : "", settings.manualOverrides ? mutatedSamples.text : "", settings.manualOverrides ? (parseInt(seed.text) || 0) : 0)
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: Theme.px(8)

                    GhostButton {
                        Layout.fillWidth: true
                        minimumWidth: 0
                        text: "Graceful stop"
                        enabled: generationService.running
                        onClicked: generationService.gracefulStop()
                    }

                    GhostButton {
                        Layout.fillWidth: true
                        minimumWidth: 0
                        text: "Force stop"
                        enabled: generationService.running
                        onClicked: forceDialog.open()
                    }
                }
            }
        }

        HoverCard {
            id: previewCard
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.threeColumns ? Theme.px(610) : -1
            Layout.minimumWidth: root.threeColumns ? Theme.px(460) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 7 : 9)

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(8)

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "2. Preview"
                        subtitle: generationService.running ? "Live output refreshes automatically." : "Source and latest generated output."
                    }

                    GhostButton {
                        text: "Refresh"
                        iconName: "refresh"
                        dense: true
                        minimumWidth: Theme.px(82)
                        onClicked: generationService.refreshPreview()
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: Theme.px(340)
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
                        anchors.margins: Theme.px(18)
                        source: generationService.previewUrl || sourceService.url
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        cache: false
                        smooth: true
                        mipmap: true
                    }

                    EmptyState {
                        visible: !(generationService.previewUrl || sourceService.url)
                        anchors.centerIn: parent
                        iconName: "images"
                        title: "Choose source art"
                        message: "Your selected source and generated previews will appear here."
                    }
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(root.compactHeight ? 54 : 62)
                    soft: true
                    border.color: generationService.running ? Theme.warning : Theme.borderStrong

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(10)
                        spacing: Theme.px(8)

                        Icon {
                            name: generationService.running ? "terminal" : "monitor"
                            iconSize: Theme.px(17)
                            glow: generationService.running
                            Layout.alignment: Qt.AlignVCenter
                        }

                        Text {
                            Layout.fillWidth: true
                            text: (generationService.queueStatus.length ? generationService.queueStatus + "  •  " : "") + generationService.status
                            color: generationService.running ? Theme.warning : Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(10.6)
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                }
            }
        }

        HoverCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: root.threeColumns ? Theme.px(380) : -1
            Layout.minimumWidth: root.threeColumns ? Theme.px(330) : 0
            padding: Theme.px(root.compactHeight ? 14 : 16)
            strong: true

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.px(root.compactHeight ? 8 : 10)

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(10)

                    Icon {
                        name: "source-check"
                        iconSize: Theme.px(29)
                        glow: sourceService.severity === "green" || sourceService.severity === "yellow" || sourceService.severity === "red"
                        glowColor: root.sourceBorderColor()
                        Layout.alignment: Qt.AlignVCenter
                    }

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "3. Source check"
                        subtitle: "Image suitability and next step."
                    }
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(root.compactHeight ? 82 : 98)
                    soft: true
                    border.color: root.sourceBorderColor()

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(12)
                        spacing: Theme.px(5)

                        Text {
                            Layout.fillWidth: true
                            text: sourceService.path ? sourceService.reportTitle : "No source selected"
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(12.7)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            text: sourceService.path ? sourceService.reportMessage : "Choose source art in step 1. KFPS will show resolution, visibility, and generation readiness here."
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(9.8)
                            wrapMode: Text.Wrap
                            elide: Text.ElideRight
                        }
                    }
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(root.compactHeight ? 92 : 108)
                    soft: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(12)
                        spacing: Theme.px(5)

                        Text {
                            Layout.fillWidth: true
                            text: "Image metrics"
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(12.2)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            text: sourceService.metrics
                            color: Theme.subtle
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.px(9.1)
                            wrapMode: Text.Wrap
                            elide: Text.ElideRight
                        }
                    }
                }

                GlassPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: Theme.px(root.compactHeight ? 160 : 200)
                    soft: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(12)
                        spacing: Theme.px(7)

                        Text {
                            Layout.fillWidth: true
                            text: "Live generation log"
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(13)
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        Flickable {
                            id: sideLiveLogScroll
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            contentWidth: width
                            contentHeight: Math.max(height, sideLiveLogText.height)

                            function pinToBottom() {
                                contentY = Math.max(0, contentHeight - height)
                            }

                            Timer {
                                id: sideLiveLogPinTimer
                                interval: 0
                                repeat: false
                                onTriggered: sideLiveLogScroll.pinToBottom()
                            }

                            TextEdit {
                                id: sideLiveLogText
                                width: sideLiveLogScroll.width
                                height: Math.max(contentHeight + Theme.px(10), sideLiveLogScroll.height)
                                text: generationService.liveLog
                                readOnly: true
                                selectByMouse: true
                                persistentSelection: true
                                wrapMode: TextEdit.Wrap
                                textFormat: TextEdit.PlainText
                                color: Theme.muted
                                selectedTextColor: Theme.primaryText
                                selectionColor: Theme.primary
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.px(10.8)

                                onTextChanged: sideLiveLogPinTimer.restart()
                            }

                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        }
                    }
                }

                PrimaryButton {
                    Layout.fillWidth: true
                    text: "Open Outputs"
                    iconName: "json"
                    showArrow: true
                    onClicked: appController.navigate("outputs")
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
}
