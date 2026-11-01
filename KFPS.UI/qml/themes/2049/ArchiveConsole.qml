import QtQuick 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../../components"

Item {
    id: root
    objectName: "ArchiveConsole"
    readonly property Item reportTarget: reportButton
    readonly property Item joinTarget: joinButton
    readonly property bool compact: Theme.logical(height) < 730
    readonly property var routes: [
        {page:"create", label:"Create", icon:"generate"}, {page:"outputs", label:"Outputs", icon:"json"},
        {page:"liveries", label:"Liveries", icon:"monitor"}, {page:"community", label:"Community", icon:"heart"},
        {page:"editor", label:"Editor", icon:"editor"}, {page:"tools", label:"Tools", icon:"tools"},
        {page:"support", label:"Support", icon:"heart"}, {page:"help", label:"Help", icon:"help"},
        {page:"update", label:"Update", icon:"update"}, {page:"settings", label:"Settings", icon:"settings"}
    ]
    function primaryPage(page) {
        if (["images", "upscaler", "background-remover"].indexOf(page) >= 0) return "tools"
        if (page === "reports") return "settings"
        if (page === "generate") return "create"
        return page
    }
    RowLayout {
        x: Theme.px(56); y: Theme.px(root.compact ? 12 : 20)
        width: parent.width - Theme.px(112); height: Theme.px(40)
        spacing: Theme.px(22)
        ArchiveText { text: "KFPS"; phosphor: true; font.pixelSize: Theme.px(32); color: Theme.primary }
        Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: Theme.px(30); color: Theme.border }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 0
            ArchiveText { Layout.fillWidth: true; text: appController.currentPage === "create" ? "IMAGE SYNTHESIS" : appController.currentPage.toUpperCase().replace(/-/g, " "); font.pixelSize: Theme.px(19); phosphor: true }
            ArchiveText { Layout.fillWidth: true; text: "2049 / " + (generationService.running ? generationService.queueStatus || generationService.status : "LOCAL WORKSPACE"); font.pixelSize: Theme.px(10); color: Theme.signalSecondary }
        }
        ArchiveText { text: generationService.running ? "PROCESSING" : "READY"; color: generationService.running ? Theme.warning : Theme.primary; font.pixelSize: Theme.px(16) }
        ArchiveButton { text: "Credits"; iconName: "heart"; Layout.preferredWidth: Theme.px(112); onClicked: appController.navigate("credits") }
        ArchiveButton { id: reportButton; text: "Report"; iconName: "help"; Layout.preferredWidth: Theme.px(108); hint: "Report a problem"; enabled: !reportService.supportBusy; onClicked: reportService.openSupportForm(appController.currentPage) }
    }
    Rectangle { x: Theme.px(56); y: Theme.px(root.compact ? 60 : 76); width: parent.width - Theme.px(112); height: 1; color: Theme.border }
    RowLayout {
        id: navigation
        x: Theme.px(56); width: parent.width - Theme.px(112)
        y: parent.height - Theme.px(135); height: Theme.px(54)
        spacing: Theme.px(8)
        Repeater {
            model: root.routes
            ArchiveButton {
                required property var modelData
                objectName: "NavButton:" + modelData.label
                Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.minimumWidth: 0; Layout.fillHeight: true
                text: modelData.label; iconName: modelData.icon; vertical: true
                selected: root.primaryPage(appController.currentPage) === modelData.page
                onClicked: appController.navigate(modelData.page)
            }
        }
    }
    RowLayout {
        x: Theme.px(56); width: parent.width - Theme.px(112)
        y: parent.height - Theme.px(70); height: Theme.px(27)
        spacing: Theme.px(16)
        ArchiveText { text: "SYSTEM / " + versionService.displayText; font.pixelSize: Theme.px(10); color: Theme.subtle }
        ArchiveText { Layout.fillWidth: true; visible: settings.liveStatusVisible; text: announcementService.displayText || "LOCAL SESSION"; font.pixelSize: Theme.px(10); color: Theme.signalSecondary }
        Item { Layout.fillWidth: true; visible: !settings.liveStatusVisible }
        ArchiveButton { id: joinButton; text: "Discord"; iconName: "heart"; Layout.preferredWidth: Theme.px(110); Layout.fillHeight: true; onClicked: reportService.openDiscord() }
    }
    Repeater {
        model: 2
        Item {
            required property int index
            x: index ? root.width - Theme.px(37) : Theme.px(21)
            y: Theme.px(80); width: Theme.px(16); height: root.height - Theme.px(205)
            Repeater {
                model: 25
                Rectangle {
                    required property int index
                    x: 0; y: index * (parent.height - 1) / 24
                    width: index % 4 === 0 ? parent.width : parent.width * 0.48
                    height: 1; color: index % 4 === 0 ? Theme.primary : Theme.signalSecondary
                    opacity: index % 4 === 0 ? 0.8 : 0.40
                }
            }
        }
    }
}
