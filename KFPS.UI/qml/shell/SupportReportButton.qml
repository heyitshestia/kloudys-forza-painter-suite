import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

GhostButton {
    id: root
    objectName: "OpenPrefilledSupportForm"
    property bool compact: false
    dense: true
    text: reportService.supportBusy ? "Preparing..." : (compact ? "Report a\nproblem" : "Report a problem")
    iconName: compact ? "" : "reports"
    minimumWidth: 0
    maximumTextWidth: compact ? Theme.px(74) : Theme.px(120)
    textPixelSize: Theme.px(compact ? 9.3 : 9.6)
    enabled: !reportService.supportBusy
    toolTipText: reportService.supportStatus || "Open a prefilled support form. Nothing is sent until you confirm."
    onClicked: reportService.openSupportForm(appController.currentPage)

    Connections {
        target: reportService
        function onChanged() {
            if (!reportService.supportBusy && (reportService.supportStatus.indexOf("Could not") === 0
                                                || reportService.supportStatus.indexOf("Report saved") === 0))
                failure.open()
        }
    }
    Popup {
        id: failure
        x: 0
        y: -height - Theme.px(6)
        width: Theme.px(300)
        padding: Theme.px(12)
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
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
                Layout.fillWidth: true
                text: "Saved reports"
                iconName: "folder"
                toolTipText: "Open saved support reports for review or manual submission."
                onClicked: { failure.close(); reportService.openSupportReports() }
            }
            GhostButton {
                Layout.fillWidth: true
                text: "Open Discord"
                iconName: "community"
                toolTipText: "Open the KFPS Support Discord server."
                onClicked: { failure.close(); reportService.openDiscord() }
            }
        }
    }
}
