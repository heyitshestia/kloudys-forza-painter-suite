import QtQuick 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Item {
    id: root
    objectName: "RedlineConsole"
    readonly property Item reportTarget: reportButton
    readonly property Item joinTarget: joinButton
    readonly property var groups: [
        {label:"CREATE",pages:[{page:"create",label:"Create"}]},
        {label:"LIBRARY",pages:[{page:"outputs",label:"Outputs"},{page:"liveries",label:"Garage"}]},
        {label:"COMMUNITY",pages:[{page:"community",label:"Community"}]},
        {label:"WORKSHOP",pages:[{page:"editor",label:"Editor"},{page:"tools",label:"Tools"}]},
        {label:"SYSTEM",pages:[{page:"settings",label:"Settings"},{page:"help",label:"Help"},{page:"support",label:"Support"},{page:"update",label:"Update"}]}
    ]
    function primaryPage(page) {
        if (["images","upscaler","background-remover"].indexOf(page) >= 0) return "tools"
        if (page === "reports" || page === "credits") return "settings"
        return page === "generate" ? "create" : page
    }
    function groupFor(page) {
        var primary = primaryPage(page)
        for (var i = 0; i < groups.length; ++i)
            for (var j = 0; j < groups[i].pages.length; ++j)
                if (groups[i].pages[j].page === primary) return i
        return 0
    }
    readonly property int currentGroup: groupFor(appController.currentPage)
    RedlineText {
        x: Theme.px(36); y: Theme.px(14); width: Theme.px(170); height: Theme.px(52)
        text: "KFPS"; heading: true; font.pixelSize: Theme.px(36); font.weight: Font.Black; color: Theme.primary
    }
    RowLayout {
        x: Theme.px(228); y: Theme.px(22); width: parent.width - x - Theme.px(36); height: Theme.px(34); spacing: Theme.px(4)
        Repeater {
            model: root.groups
            RedlineButton {
                required property var modelData
                required property int index
                objectName: "RedlineGroup:" + index
                Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.minimumWidth: 0; Layout.fillHeight: true
                text: modelData.label; displayText: true; minimal: true
                selected: root.currentGroup === index
                onClicked: appController.navigate(modelData.pages[0].page)
            }
        }
    }
    Rectangle { x: Theme.px(36); y: Theme.px(76); width: parent.width - Theme.px(72); height: 1; color: "#84401828" }
    RowLayout {
        x: Theme.px(36); y: Theme.px(86); width: parent.width - Theme.px(72); height: Theme.px(32); spacing: Theme.px(6)
        RedlineText { text: "0" + (root.currentGroup + 1); font.family: Theme.monoFamily; color: Theme.primary; Layout.rightMargin: Theme.px(12) }
        Repeater {
            model: root.groups[root.currentGroup].pages
            RedlineButton {
                required property var modelData
                objectName: "NavButton:" + modelData.label
                text: modelData.label.toUpperCase(); displayText: true; compact: true; minimal: true
                Layout.preferredWidth: Theme.px(152)
                selected: root.primaryPage(appController.currentPage) === modelData.page
                onClicked: appController.navigate(modelData.page)
            }
        }
        Item { Layout.fillWidth: true }
        RedlineText { text: generationService.running ? "PROCESSING" : "READY"; font.family: Theme.monoFamily; font.pixelSize: Theme.px(10); color: Theme.subtle }
    }
    RowLayout {
        x: Theme.px(36); y: parent.height - Theme.px(36); width: parent.width - Theme.px(72); height: Theme.px(24); spacing: Theme.px(12)
        RedlineText { text: "REDLINE / " + versionService.displayText; color: Theme.primary; font.family: Theme.monoFamily; font.pixelSize: Theme.px(10) }
        RedlineText { Layout.fillWidth: true; text: generationService.running ? generationService.queueStatus || generationService.status : settings.liveStatusVisible ? announcementService.displayText : ""; color: Theme.subtle; font.pixelSize: Theme.px(11) }
        RedlineButton { compact: true; minimal: true; text: ""; iconName: "heart"; hint: "Credits"; onClicked: appController.navigate("credits") }
        RedlineButton { id: reportButton; compact: true; minimal: true; text: ""; iconName: "help"; hint: "Report a problem"; enabled: !reportService.supportBusy; onClicked: reportService.openSupportForm(appController.currentPage) }
        RedlineButton { id: joinButton; text: "DISCORD"; compact: true; minimal: true; onClicked: reportService.openDiscord() }
    }
}
