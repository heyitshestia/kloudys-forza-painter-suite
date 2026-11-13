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

}
