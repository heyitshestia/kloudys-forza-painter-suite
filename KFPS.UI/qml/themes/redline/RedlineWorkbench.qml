import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../../components"

Item {
    id: root
    objectName: "RedlineWorkbench"
    property var session: null
    property int viewIndex: 0
    property bool showLog: false
    readonly property bool narrow: Theme.logical(width) < 1150
    readonly property string artwork: viewIndex === 0 ? sourceService.url : session ? session.generatedPreviewUrl : ""
    readonly property real leftWidth: Theme.px(narrow ? 180 : 220)
    readonly property real rightWidth: Theme.px(narrow ? 260 : 320)
    readonly property string sourceName: sourceService.path ? sourceService.path.replace(/\\/g, "/").split("/").pop() : "No image selected"

    RowLayout {
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.bottom: execution.top; anchors.bottomMargin: Theme.px(24)
        spacing: Theme.px(root.narrow ? 20 : 32)
        FastScrollView {
            id: slots
            Layout.preferredWidth: root.leftWidth; Layout.fillHeight: true
            contentWidth: availableWidth; clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ColumnLayout {
                width: slots.availableWidth; spacing: Theme.px(12)
                RedlineText { text: "LOADOUT"; heading: true; color: Theme.primary }
                RedlineButton {
                    objectName: "RedlineViewSource"; Layout.fillWidth: true
                    text: "SOURCE"; subtitle: sourceService.count ? sourceService.count + (sourceService.count === 1 ? " image" : " images") : "Empty slot"
                    thumbnail: sourceService.url
                    slotNumber: "01"; menuEntry: true; displayText: true; minimal: true
                    selected: root.viewIndex === 0 && !root.showLog
                    onClicked: { root.viewIndex = 0; root.showLog = false }
                }
                RedlineButton {
                    objectName: "RedlineViewOutput"; Layout.fillWidth: true
                    text: "OUTPUT"; subtitle: root.session && root.session.generatedPreviewUrl ? "Preview available" : "No output"
                    thumbnail: root.session ? root.session.generatedPreviewUrl : ""
                    slotNumber: "02"; menuEntry: true; displayText: true; minimal: true
                    selected: root.viewIndex === 1 && !root.showLog
                    onClicked: { root.viewIndex = 1; root.showLog = false }
                }
                RedlineButton { objectName: "RedlineChooseSource"; Layout.fillWidth: true; text: sourceService.count ? "CHANGE IMAGES" : "LOAD IMAGES"; iconName: "images"; minimal: true; onClicked: sourceService.choose() }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSoft }
                RedlineButton { objectName: "RedlineToggleLog"; Layout.fillWidth: true; text: "LIVE LOG"; iconName: "terminal"; minimal: true; selected: root.showLog; onClicked: root.showLog = !root.showLog }
                RedlineButton { objectName: "RedlineOpenOutputs"; Layout.fillWidth: true; text: "OPEN LIBRARY"; iconName: "json"; minimal: true; onClicked: appController.navigate("outputs") }
            }
        }
        Item {
            id: stage
            objectName: "RedlineStage"
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumWidth: Theme.px(180)
            RowLayout {
                id: stageHeader
                width: parent.width; height: Theme.px(48); spacing: Theme.px(8)
                RedlineText { Layout.fillWidth: true; text: root.showLog ? "LIVE LOG" : root.viewIndex ? "OUTPUT" : "SOURCE"; heading: true; font.pixelSize: Theme.px(26); color: Theme.primary; fontSizeMode: Text.Fit; minimumPixelSize: Theme.px(18) }
                RedlineButton { compact: true; text: ""; iconName: "refresh"; hint: "Refresh output preview"; onClicked: generationService.refreshPreview() }
            }
            Rectangle { anchors.top: stageHeader.bottom; width: parent.width; height: 1; color: Theme.borderSoft }
            Item {
                id: viewingArea
                anchors.left: parent.left; anchors.right: parent.right
                anchors.top: stageHeader.bottom; anchors.topMargin: Theme.px(20)
                anchors.bottom: filename.top; anchors.bottomMargin: Theme.px(16)
                Image {
                    objectName: "RedlineArtwork"
                    anchors.fill: parent
                    source: root.artwork
                    fillMode: Image.PreserveAspectFit; asynchronous: true; cache: false; mipmap: true
                }
                ColumnLayout {
                    visible: !root.artwork && !root.showLog
                    anchors.centerIn: parent; width: parent.width; spacing: Theme.px(16)
                    Icon { Layout.alignment: Qt.AlignHCenter; name: root.viewIndex ? "json" : "images"; iconSize: Theme.px(60); tint: Theme.primary }
                    RedlineText { Layout.fillWidth: true; text: root.viewIndex ? "NO OUTPUT" : "EMPTY SLOT"; heading: true; color: Theme.primary; horizontalAlignment: Text.AlignHCenter }
                    RedlineText { Layout.fillWidth: true; text: root.viewIndex ? generationService.status : root.sourceName; color: Theme.muted; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap }
                }
                Rectangle {
                    visible: root.showLog; anchors.fill: parent; color: Theme.surfaceStrong
                    FastScrollView {
                        anchors.fill: parent; clip: true
                        TextArea { objectName: "RedlineLog"; text: root.showLog ? generationService.liveLog : ""; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Theme.text; font.family: Theme.monoFamily; font.pixelSize: Theme.px(12); background: null }
                    }
                }
            }
            RedlineText {
                id: filename
                anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                height: Theme.px(22); font.family: Theme.monoFamily; font.pixelSize: Theme.px(11); color: Theme.subtle
                text: root.showLog ? "GENERATION / LOG" : root.viewIndex ? generationService.status : root.sourceName
            }
        }
        FastScrollView {
            id: setupScroll
            Layout.preferredWidth: root.rightWidth; Layout.fillHeight: true
            clip: true; contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ColumnLayout {
                width: setupScroll.availableWidth
                spacing: Theme.px(10)
                RedlineText { text: "GENERATION"; heading: true; color: Theme.primary; Layout.topMargin: Theme.px(7); Layout.bottomMargin: Theme.px(12) }
                RowLayout {
                    Layout.fillWidth: true
                    RedlineText { text: "IMAGES"; color: Theme.subtle; font.pixelSize: Theme.px(12) }
                    Item { Layout.fillWidth: true }
                    RedlineText { text: String(sourceService.count).padStart(2, "0"); heading: true; font.pixelSize: Theme.px(24) }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSoft }
                RedlineText { text: "PROFILE"; color: Theme.primary; font.pixelSize: Theme.px(12) }
                KfpsComboBox {
                    objectName: "RedlinePreset"; Layout.fillWidth: true; dense: true
                    model: generationService.presets; currentIndex: generationService.selectedPresetIndex
                    onActivated: generationService.setSelectedPresetIndex(currentIndex)
                }
                RowLayout {
                    Layout.fillWidth: true; spacing: Theme.px(12)
                    RedlineText { Layout.fillWidth: true; text: "SHAPE BUDGET"; color: Theme.primary; font.pixelSize: Theme.px(12) }
                    KfpsTextField {
                        objectName: "RedlineLayers"; Layout.preferredWidth: Theme.px(112)
                        text: root.session ? root.session.templateLayers : ""
                        font.family: Theme.displayFamily; font.pixelSize: Theme.px(22)
                        inputMethodHints: Qt.ImhDigitsOnly
                        toolTipText: "Maximum shapes, from 1 to 3000."
                        onTextEdited: root.session.templateLayers = text
                        onEditingFinished: { if (root.session && !root.session.checkpointsManual) root.session.checkpointValues = root.session.checkpointTextFor(text) }
                    }
                }
                RedlineText { text: "CHECKPOINTS"; font.pixelSize: Theme.px(12); color: Theme.primary }
                KfpsTextField {
                    objectName: "RedlineCheckpoints"; Layout.fillWidth: true; dense: true
                    text: root.session ? root.session.checkpointValues : ""
                    onTextEdited: { root.session.checkpointsManual = true; root.session.checkpointValues = text }
                }
                GridLayout {
                    Layout.fillWidth: true; columns: 2; columnSpacing: Theme.px(8); rowSpacing: 0
                    KfpsCheckBox { objectName: "RedlineDetail"; Layout.fillWidth: true; dense: true; text: "Detail"; checked: root.session ? root.session.detailEnabled : false; onToggled: root.session.detailEnabled = checked; toolTipText: root.session ? root.session.detailHeatmapTip : "" }
                    KfpsCheckBox { objectName: "RedlineLuma"; Layout.fillWidth: true; dense: true; text: "Luma"; checked: root.session ? root.session.lumaEnabled : false; onToggled: root.session.lumaEnabled = checked; toolTipText: root.session ? root.session.lumaPrepTip : "" }
                    KfpsCheckBox { objectName: "RedlineRepair"; Layout.fillWidth: true; dense: true; text: "Repair"; checked: root.session ? root.session.repairEnabled : false; onToggled: root.session.repairEnabled = checked; toolTipText: root.session ? root.session.edgeRepairTip : "" }
                    KfpsCheckBox { objectName: "RedlineBoost"; Layout.fillWidth: true; dense: true; text: "2x"; checked: root.session ? root.session.boostEnabled : false; onToggled: root.session.boostEnabled = checked; toolTipText: root.session ? root.session.sampleBoostTip : "" }
                }
                RedlineButton { objectName: "RedlineOpenOverrides"; Layout.fillWidth: true; text: "MANUAL OVERRIDES"; iconName: "settings"; minimal: true; enabled: settings.manualOverrides; hint: settings.manualOverrides ? "Manual generation overrides" : "Enable manual generator overrides in Settings"; onClicked: advanced.open() }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSoft }
                RedlineText { Layout.fillWidth: true; text: sourceService.path ? sourceService.reportTitle : "NO INPUT"; color: sourceService.severity === "red" ? Theme.danger : sourceService.severity === "yellow" ? Theme.warning : Theme.signalSecondary; wrapMode: Text.Wrap; font.pixelSize: Theme.px(13) }
                RedlineText { Layout.fillWidth: true; text: sourceService.path ? sourceService.metrics : "--"; font.family: Theme.monoFamily; font.pixelSize: Theme.px(11); wrapMode: Text.Wrap }
                RedlineButton { objectName: "RedlineSourceReport"; Layout.fillWidth: true; text: "SOURCE REPORT"; iconName: "source-check"; minimal: true; enabled: sourceService.count > 0; onClicked: sourceReport.open() }
            }
        }
    }
    Item {
        id: execution
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: Theme.px(50)
        Rectangle { anchors.fill: parent; color: "#401316"; border.width: 0 }
        Rectangle { width: parent.width; height: 2; color: Theme.primary }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: Theme.px(14); spacing: Theme.px(14)
            Icon { name: "generate"; iconSize: Theme.px(20); tint: Theme.primary }
            RedlineText { Layout.fillWidth: true; text: generationService.running ? generationService.queueStatus || generationService.status : generationService.status; font.pixelSize: Theme.px(13); color: Theme.text; maximumLineCount: 2; wrapMode: Text.Wrap }
            RedlineButton { objectName: "RedlineStopSafe"; text: "STOP"; compact: true; minimal: true; enabled: generationService.running; hint: "Stop safely and retain completed checkpoints"; onClicked: generationService.gracefulStop() }
            RedlineButton { objectName: "RedlineStopNow"; text: "ABORT"; compact: true; minimal: true; enabled: generationService.running; hint: "Stop immediately, with confirmation"; onClicked: root.session.requestForceStop() }
            RedlineButton { objectName: "RedlineGenerate"; Layout.preferredWidth: Theme.px(root.narrow ? 170 : 240); Layout.fillHeight: true; text: "GENERATE"; displayText: true; iconName: "generate"; primary: true; enabled: !!root.session && !generationService.running; onClicked: root.session.beginGeneration() }
        }
    }
    Dialog {
        id: sourceReport
        objectName: "RedlineSourceReportDialog"
        anchors.centerIn: parent; width: Math.min(root.width - Theme.px(30), Theme.px(580)); modal: true
        header: RedlineText { text: sourceService.reportTitle; padding: Theme.px(16); heading: true; color: Theme.primary; wrapMode: Text.Wrap }
        footer: Item { implicitHeight: Theme.px(52); RedlineButton { objectName: "RedlineReportClose"; anchors.right: parent.right; anchors.rightMargin: Theme.px(12); anchors.verticalCenter: parent.verticalCenter; text: "Close"; onClicked: sourceReport.close() } }
        background: Rectangle { color: Theme.surfaceStrong; border.color: Theme.primary }
        contentItem: RedlineText { text: sourceService.reportMessage + "\n\n" + sourceService.metrics; wrapMode: Text.Wrap; elide: Text.ElideNone }
    }
    Dialog {
        id: advanced
        objectName: "RedlineOverrides"
        anchors.centerIn: parent; width: Math.min(root.width - Theme.px(30), Theme.px(540)); modal: true
        header: RedlineText { text: "MANUAL OVERRIDES"; padding: Theme.px(16); heading: true; color: Theme.primary }
        footer: Item { implicitHeight: Theme.px(52); RedlineButton { objectName: "RedlineOverridesClose"; anchors.right: parent.right; anchors.rightMargin: Theme.px(12); anchors.verticalCenter: parent.verticalCenter; text: "Close"; onClicked: advanced.close() } }
        background: Rectangle { color: Theme.surfaceStrong; border.color: Theme.primary }
        contentItem: GridLayout {
            columns: 2; rowSpacing: Theme.px(12); columnSpacing: Theme.px(12)
            Repeater {
                model: [{label:"Max resolution",key:"maxResolution"},{label:"Random samples",key:"randomCount"},{label:"Mutated samples",key:"mutatedCount"},{label:"Seed",key:"seedValue"}]
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    RedlineText { text: modelData.label }
                    KfpsTextField { objectName: "RedlineOverride:" + modelData.key; Layout.fillWidth: true; text: root.session ? root.session[modelData.key] : ""; onTextEdited: root.session[modelData.key] = text }
                }
            }
        }
    }
}
