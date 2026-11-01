import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../../components"

Item {
    id: root
    objectName: "ArchiveWorkbench"
    property var session: null
    readonly property bool compact: Theme.logical(height) < 650
    property bool showLog: false
    readonly property real bankHeight: Theme.px(compact ? 204 : 234)

    FastScrollView {
    id: workbenchScroll
    objectName: "ArchiveWorkbenchScroll"
    anchors.fill: parent
    contentWidth: availableWidth
    contentHeight: workbenchSurface.height
    clip: true
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    Item {
    id: workbenchSurface
    width: workbenchScroll.availableWidth
    height: Math.max(root.height, Theme.px(410))
    RowLayout {
        id: viewports
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        height: Math.max(Theme.px(170), parent.height - root.bankHeight - Theme.px(18))
        spacing: Theme.px(22)
        Repeater {
            model: 2
            Item {
                id: bay
                required property int index
                readonly property string artwork: index === 0 ? sourceService.url : root.session ? root.session.generatedPreviewUrl : ""
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 1
                objectName: index === 0 ? "ArchiveSourceBay" : "ArchiveResultBay"
                ArchiveText { x: 0; y: 0; text: index === 0 ? "01 / SOURCE" : "02 / OUTPUT"; color: index === 0 ? Theme.signalSecondary : Theme.primary; phosphor: true; font.pixelSize: Theme.px(15) }
                ArchiveText { anchors.right: parent.right; anchors.rightMargin: bay.index ? Theme.px(42) : 0; y: 2; text: index === 0 ? String(sourceService.count).padStart(2, "0") + " FILES" : generationService.running ? "LIVE" : "STANDBY"; font.pixelSize: Theme.px(11); color: Theme.subtle }
                ArchiveButton { visible: bay.index === 1; anchors.right: parent.right; y: -Theme.px(4); width: Theme.px(32); height: Theme.px(24); text: ""; iconName: "refresh"; hint: "Refresh output preview"; onClicked: generationService.refreshPreview() }
                Rectangle {
                    id: viewingGlass
                    x: 0; y: Theme.px(30); width: parent.width; height: parent.height - y - Theme.px(23)
                    color: bay.artwork ? "#111719" : "transparent"
                    Image {
                        objectName: bay.index === 0 ? "ArchiveArtworkSource" : "ArchiveArtworkResult"
                        anchors.fill: parent; anchors.margins: 2
                        source: bay.artwork
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true; cache: false; mipmap: true
                    }
                    Repeater {
                        model: bay.artwork ? 0 : 3
                        Rectangle { required property int index; x: 1; y: (index + 1) * viewingGlass.height / 4; width: viewingGlass.width - 2; height: 1; color: "#103cadad" }
                    }
                    Repeater {
                        model: bay.artwork ? 0 : 3
                        Rectangle { required property int index; x: (index + 1) * viewingGlass.width / 4; y: 1; width: 1; height: viewingGlass.height - 2; color: "#103cadad" }
                    }
                    ColumnLayout {
                        visible: !bay.artwork
                        anchors.centerIn: parent
                        spacing: Theme.px(12)
                        ArchiveText { Layout.alignment: Qt.AlignHCenter; text: bay.index === 0 ? "NO SOURCE" : "AWAITING SYNTHESIS"; color: Theme.withAlpha(Theme.signalSecondary, 0.7); font.pixelSize: Theme.px(18) }
                        ArchiveButton { visible: bay.index === 0; Layout.alignment: Qt.AlignHCenter; text: "Load image"; iconName: "images"; objectName: "ArchiveChooseSource"; onClicked: sourceService.choose() }
                    }
                    Rectangle { x: 0; y: 0; width: parent.width; height: 1; color: Theme.signalSecondary; opacity: 0.25 }
                    Rectangle { x: 0; y: parent.height - 1; width: parent.width; height: 1; color: Theme.signalSecondary; opacity: 0.25 }
                    Repeater {
                        model: 4
                        Item {
                            required property int index
                            x: index % 2 ? viewingGlass.width - width : 0
                            y: index > 1 ? viewingGlass.height - height : 0
                            width: Theme.px(18); height: Theme.px(14)
                            Rectangle { y: index > 1 ? parent.height - 1 : 0; width: parent.width; height: 1; color: Theme.signalSecondary; opacity: 0.8 }
                            Rectangle { x: index % 2 ? parent.width - 1 : 0; width: 1; height: parent.height; color: Theme.signalSecondary; opacity: 0.8 }
                        }
                    }
                }
                ArchiveText { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; text: bay.index === 0 ? (sourceService.path ? sourceService.path.replace(/\\/g, "/").split("/").pop() : "INPUT / --") : generationService.status; color: Theme.subtle; font.pixelSize: Theme.px(10) }
            }
        }
    }

    Rectangle { x: 0; y: viewports.height + Theme.px(8); width: parent.width; height: 1; color: Theme.border }
    GridLayout {
        id: bank
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: root.bankHeight
        columns: 4; columnSpacing: Theme.px(24); rowSpacing: 0
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 1; spacing: Theme.px(8)
            ArchiveText { text: "01  SOURCE ANALYSIS"; color: Theme.signalSecondary; font.pixelSize: Theme.px(11) }
            ArchiveText { text: sourceService.count ? String(sourceService.count).padStart(2, "0") : "--"; phosphor: true; font.pixelSize: Theme.px(root.compact ? 28 : 40); color: Theme.primary }
            ArchiveText { Layout.fillWidth: true; text: sourceService.path ? sourceService.metrics : "FILES  / --\nRASTER / --\nALPHA  / --"; font.pixelSize: Theme.px(11); wrapMode: Text.Wrap; maximumLineCount: 4 }
            ArchiveText { Layout.fillWidth: true; text: sourceService.path ? sourceService.reportTitle : "NO INPUT"; color: sourceService.severity === "red" ? Theme.danger : sourceService.severity === "yellow" ? Theme.warning : Theme.signalSecondary; font.pixelSize: Theme.px(10) }
            Item { Layout.fillHeight: true }
            ArchiveButton { Layout.fillWidth: true; text: "Load images"; iconName: "images"; onClicked: sourceService.choose() }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 1; spacing: Theme.px(8)
            ArchiveText { text: "02  SYNTHESIS PROFILE"; color: Theme.signalSecondary; font.pixelSize: Theme.px(11) }
            KfpsComboBox {
                objectName: "ArchivePreset"
                Layout.fillWidth: true; dense: true
                model: generationService.presets
                currentIndex: generationService.selectedPresetIndex
                font.family: Theme.monoFamily
                background: ArchiveFieldSurface {}
                onActivated: generationService.setSelectedPresetIndex(currentIndex)
            }
            GridLayout {
                Layout.fillWidth: true; columns: 2; columnSpacing: 0; rowSpacing: 0
                KfpsCheckBox { Layout.fillWidth: true; dense: true; text: "Detail"; checked: root.session ? root.session.detailEnabled : false; onToggled: root.session.detailEnabled = checked; toolTipText: root.session ? root.session.detailHeatmapTip : "" }
                KfpsCheckBox { Layout.fillWidth: true; dense: true; text: "Luma"; checked: root.session ? root.session.lumaEnabled : false; onToggled: root.session.lumaEnabled = checked; toolTipText: root.session ? root.session.lumaPrepTip : "" }
                KfpsCheckBox { Layout.fillWidth: true; dense: true; text: "Repair"; checked: root.session ? root.session.repairEnabled : false; onToggled: root.session.repairEnabled = checked; toolTipText: root.session ? root.session.edgeRepairTip : "" }
                KfpsCheckBox { Layout.fillWidth: true; dense: true; text: "2x"; checked: root.session ? root.session.boostEnabled : false; onToggled: root.session.boostEnabled = checked; toolTipText: root.session ? root.session.sampleBoostTip : "" }
            }
            Item { Layout.fillHeight: true }
            ArchiveButton { objectName: "ArchiveSourceReport"; Layout.fillWidth: true; text: "Source report"; iconName: "source-check"; enabled: sourceService.count > 0; onClicked: sourceReport.open() }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 1; spacing: Theme.px(6)
            ArchiveText { text: "03  SHAPE BUDGET"; color: Theme.signalSecondary; font.pixelSize: Theme.px(11) }
            KfpsTextField {
                objectName: "ArchiveLayers"
                Layout.fillWidth: true; dense: true
                text: root.session ? root.session.templateLayers : ""
                font.family: Theme.monoFamily; font.pixelSize: Theme.px(root.compact ? 24 : 32)
                background: ArchiveFieldSurface {}
                inputMethodHints: Qt.ImhDigitsOnly
                toolTipText: "Maximum shapes, from 1 to 3000."
                onTextEdited: root.session.templateLayers = text
                onEditingFinished: { if (root.session && !root.session.checkpointsManual) root.session.checkpointValues = root.session.checkpointTextFor(text) }
            }
            ArchiveText { text: "CHECKPOINTS"; font.pixelSize: Theme.px(10); color: Theme.subtle }
            KfpsTextField {
                objectName: "ArchiveCheckpoints"; Layout.fillWidth: true; dense: true
                font.family: Theme.monoFamily
                background: ArchiveFieldSurface {}
                text: root.session ? root.session.checkpointValues : ""
                onTextEdited: { root.session.checkpointsManual = true; root.session.checkpointValues = text }
            }
            Item { Layout.fillHeight: true }
            ArchiveButton { objectName: "ArchiveOpenOverrides"; Layout.fillWidth: true; text: "Overrides"; iconName: "settings"; enabled: settings.manualOverrides; hint: settings.manualOverrides ? "Manual generation overrides" : "Enable manual generator overrides in Settings"; onClicked: advanced.open() }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 1; spacing: Theme.px(8)
            ArchiveText { text: "04  EXECUTION"; color: Theme.signalSecondary; font.pixelSize: Theme.px(11) }
            ArchiveText { Layout.fillWidth: true; text: generationService.running ? "RUNNING" : "STANDBY"; phosphor: true; font.pixelSize: Theme.px(root.compact ? 24 : 32); color: generationService.running ? Theme.warning : Theme.primary }
            ArchiveButton { objectName: "ArchiveGenerate"; Layout.fillWidth: true; text: "Generate"; iconName: "generate"; selected: true; enabled: !!root.session && !generationService.running; onClicked: root.session.beginGeneration() }
            RowLayout {
                Layout.fillWidth: true; spacing: Theme.px(6)
                ArchiveButton { objectName: "ArchiveStopSafe"; Layout.fillWidth: true; Layout.preferredWidth: 1; text: "Stop"; enabled: generationService.running; hint: "Stop safely and retain completed checkpoints"; onClicked: generationService.gracefulStop() }
                ArchiveButton { objectName: "ArchiveStopNow"; Layout.fillWidth: true; Layout.preferredWidth: 1; text: "Abort"; danger: true; enabled: generationService.running; hint: "Stop immediately, with confirmation"; onClicked: root.session.requestForceStop() }
            }
            Item { Layout.fillHeight: true }
            ArchiveButton { Layout.fillWidth: true; text: root.showLog ? "Close log" : "Live log"; iconName: "terminal"; selected: root.showLog; onClicked: root.showLog = !root.showLog }
        }
    }

    Rectangle {
        visible: root.showLog
        x: viewports.width / 2 + Theme.px(11); y: Theme.px(30)
        width: viewports.width / 2 - Theme.px(11); height: viewports.height - Theme.px(53)
        color: "#091712"; border.color: Theme.border; border.width: 1
        FastScrollView {
            anchors.fill: parent; anchors.margins: Theme.px(12); clip: true
            TextArea { text: root.showLog ? generationService.liveLog : ""; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Theme.text; font.family: Theme.monoFamily; font.pixelSize: Theme.px(12); background: null }
        }
    }
    }
    }
    Dialog {
        id: sourceReport
        objectName: "ArchiveSourceReportDialog"
        title: sourceService.reportTitle
        anchors.centerIn: parent
        width: Math.min(root.width - Theme.px(30), Theme.px(580))
        modal: true
        header: ArchiveText { text: sourceReport.title; padding: Theme.px(16); font.pixelSize: Theme.px(18); color: Theme.primary }
        footer: Item { implicitHeight: Theme.px(52); ArchiveButton { anchors.right: parent.right; anchors.rightMargin: Theme.px(12); anchors.verticalCenter: parent.verticalCenter; text: "Close"; iconName: "check"; onClicked: sourceReport.close() } }
        background: Rectangle { color: Theme.surfaceStrong; border.color: Theme.border }
        contentItem: ArchiveText { text: sourceService.reportMessage + "\n\n" + sourceService.metrics; wrapMode: Text.Wrap; elide: Text.ElideNone }
    }
    Dialog {
        id: advanced
        objectName: "ArchiveOverrides"
        title: "Manual overrides"
        anchors.centerIn: parent
        width: Math.min(root.width - Theme.px(30), Theme.px(540))
        modal: true
        header: ArchiveText { text: advanced.title; padding: Theme.px(16); font.pixelSize: Theme.px(18); color: Theme.primary }
        footer: Item { implicitHeight: Theme.px(52); ArchiveButton { objectName: "ArchiveOverridesClose"; anchors.right: parent.right; anchors.rightMargin: Theme.px(12); anchors.verticalCenter: parent.verticalCenter; text: "Close"; iconName: "check"; onClicked: advanced.close() } }
        background: Rectangle { color: Theme.surfaceStrong; border.color: Theme.border }
        contentItem: GridLayout {
            columns: 2; rowSpacing: Theme.px(12); columnSpacing: Theme.px(12)
            Repeater {
                model: [{label:"Max resolution", key:"maxResolution"}, {label:"Random samples", key:"randomCount"}, {label:"Mutated samples", key:"mutatedCount"}, {label:"Seed", key:"seedValue"}]
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    ArchiveText { text: modelData.label }
                    KfpsTextField {
                        objectName: "ArchiveOverride:" + modelData.key; Layout.fillWidth: true
                        font.family: Theme.monoFamily
                        background: ArchiveFieldSurface {}
                        text: root.session ? root.session[modelData.key] : ""
                        onTextEdited: root.session[modelData.key] = text
                    }
                }
            }
        }
    }
}
