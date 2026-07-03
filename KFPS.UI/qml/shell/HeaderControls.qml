import QtQuick 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

GlassPanel {
    id: root

    property bool compact: false

    function iconFor(page) {
        if (page === "create" || page === "generate") return "generate"
        if (page === "outputs" || page === "json" || page === "library") return "json"
        if (page === "editor") return "editor"
        if (page === "settings") return "settings"
        if (page === "help" || page === "learn") return "help"
        if (page === "tools") return "tools"
        if (page === "images") return "source-check"
        if (page === "reports") return "reports"
        if (page === "update") return "update"
        return "home"
    }

    width: Theme.px(compact ? 330 : 430)
    height: Theme.px(compact ? 50 : 58)
    radius: Theme.px(14)
    soft: true

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.px(14)
        anchors.rightMargin: Theme.px(14)
        spacing: Theme.px(10)

        Icon {
            name: root.iconFor(appController.currentPage)
            iconSize: Theme.px(root.compact ? 18 : 22)
            glow: true
            Layout.alignment: Qt.AlignVCenter
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: Theme.px(1)

            Text {
                Layout.fillWidth: true
                text: appController.pageTitle
                color: Theme.primaryBright
                font.family: Theme.displayFamily
                font.pixelSize: Theme.px(root.compact ? 12.5 : 14.5)
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: appController.pageSubtitle
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(root.compact ? 9.4 : 10.3)
                elide: Text.ElideRight
            }
        }
    }
}
