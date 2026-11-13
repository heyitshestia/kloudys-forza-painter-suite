import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Popup {
    id: root
    objectName: "SupportReportRecovery"
    property Item targetItem: null
    parent: Overlay.overlay
    width: Math.min(Theme.px(320), parent ? parent.width - Theme.px(24) : Theme.px(320))
    padding: Theme.px(12)
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    readonly property point anchorPoint: targetItem && targetItem.visible && parent
        ? targetItem.mapToItem(parent, 0, 0) : Qt.point(Theme.px(12), Theme.px(12))
    x: Math.max(Theme.px(12), Math.min(anchorPoint.x, parent ? parent.width - width - Theme.px(12) : anchorPoint.x))
    y: Math.max(Theme.px(12), Math.min(anchorPoint.y > height + Theme.px(12)
        ? anchorPoint.y - height - Theme.px(6) : anchorPoint.y + (targetItem ? targetItem.height : 0) + Theme.px(6),
        parent ? parent.height - height - Theme.px(12) : Theme.px(12)))
    Connections {
        target: reportService
        function onChanged() {
            if (!reportService.supportBusy && (reportService.supportStatus.indexOf("Could not") === 0
                                               || reportService.supportStatus.indexOf("Report saved") === 0))
                root.open()
        }
    }
    background: KfpsPopupSurface { }
    contentItem: ColumnLayout {
        spacing: Theme.px(10)
        Text {
            Layout.fillWidth: true
            text: reportService.supportStatus
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(12)
        }
        GhostButton {
            objectName: "SupportSavedReports"
            Layout.fillWidth: true
            text: "Saved reports"
            iconName: "folder"
            onClicked: { root.close(); reportService.openSupportReports() }
        }
        GhostButton {
            objectName: "SupportOpenWebsite"
            Layout.fillWidth: true
            text: "Open support form"
            iconName: "external"
            onClicked: { root.close(); reportService.openSupportWebsite() }
        }
        GhostButton {
            objectName: "SupportOpenDiscord"
            Layout.fillWidth: true
            text: "Open Discord"
            iconName: "community"
            onClicked: { root.close(); reportService.openDiscord() }
        }
    }
}
