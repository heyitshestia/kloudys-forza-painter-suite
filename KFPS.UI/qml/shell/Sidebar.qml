import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root

    property bool compact: false
    property real railWidth: Theme.px(compact ? Metrics.compactSidebar : Metrics.wideSidebar)
    property bool denseNavigation: Theme.logical(height) < 760
    readonly property var navItems: [
        { page: "create", label: "Create", icon: "generate" },
        { page: "outputs", label: "Outputs", icon: "json" },
        { page: "editor", label: "Editor", icon: "editor" },
        { page: "tools", label: "Tools", icon: "tools" },
        { page: "help", label: "Help", icon: "help" },
        { page: "update", label: "Update", icon: "update" },
        { page: "settings", label: "Settings", icon: "settings" }
    ]
    signal route(string page)
    property int logoTapCount: 0
    property bool insaneActive: false

    function primaryPage(page) {
        if (page === "outputs" || page === "json" || page === "library")
            return "outputs"
        if (page === "editor")
            return "editor"
        if (page === "tools" || page === "images")
            return "tools"
        if (page === "help" || page === "learn")
            return "help"
        if (page === "update")
            return "update"
        if (page === "settings" || page === "reports")
            return "settings"
        return "create"
    }

    function pageIndex(page) {
        var primary = primaryPage(page)
        for (let index = 0; index < navItems.length; ++index) {
            if (navItems[index].page === primary)
                return index
        }
        return 0
    }

    function registerLogoTap() {
        if (!Theme.supporterTheme)
            return
        logoTapReset.restart()
        logoTapCount += 1
        if (logoTapCount >= 10) {
            logoTapCount = 0
            insaneActive = true
            insaneTimer.restart()
        }
    }

    width: railWidth
    clip: true

    GlassPanel {
        anchors.fill: parent
        radius: 0
        strong: true
        panelOpacity: 0.97
        border.width: 0
    }

    Rectangle {
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        width: Math.max(1, Theme.px(1))
        color: Theme.border
        opacity: 0.58
    }

    Image {
        visible: Theme.backdropBranchesVisible
        source: assetRoot + "/" + Theme.backdropBranchBottomFile
        width: root.width * (root.compact ? 2.6 : 1.95)
        height: root.height * 0.37
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.leftMargin: -width * 0.28
        anchors.bottomMargin: Theme.px(28)
        fillMode: Image.PreserveAspectFit
        opacity: root.compact ? Theme.sidebarCompactBranchOpacity : Theme.sidebarBranchOpacity
        smooth: true
        mipmap: true
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.px(10)
        anchors.rightMargin: Theme.px(10)
        anchors.topMargin: Theme.px(8)
        anchors.bottomMargin: Theme.px(10)
        spacing: Theme.px(4)

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.px(root.denseNavigation ? (root.compact ? 74 : 82) : (root.compact ? 93 : 102))
            Layout.minimumHeight: Layout.preferredHeight

            Row {
                id: wideLogoContent
                visible: !root.compact
                anchors.centerIn: parent
                spacing: Theme.px(10)
                opacity: root.insaneActive ? 0 : 1
                y: root.insaneActive ? Theme.px(8) : 0
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                Behavior on y { enabled: !Theme.reducedMotion; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

                Rectangle {
                    width: Theme.px(root.denseNavigation ? 48 : 56)
                    height: width
                    radius: width / 2
                    color: Theme.logoCapsuleSurface
                    border.width: Math.max(1, Theme.px(1))
                    border.color: Theme.borderStrong

                    Image {
                        anchors.fill: parent
                        anchors.margins: Theme.px(3)
                        source: assetRoot + "/" + Theme.logoFile
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                        mipmap: true
                    }
                }

                Item {
                    anchors.verticalCenter: parent.verticalCenter
                    width: brandText.implicitWidth
                    height: parent.height

                    Text {
                        id: brandText
                        anchors.centerIn: parent
                        text: "KFPS"
                        color: Theme.primaryBright
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.px(root.denseNavigation ? 21 : 25)
                        font.weight: Font.DemiBold
                        font.letterSpacing: Theme.px(1.4)
                    }
                }
            }

            Column {
                id: compactLogoContent
                visible: root.compact
                anchors.centerIn: parent
                spacing: Theme.px(3)
                opacity: root.insaneActive ? 0 : 1
                y: root.insaneActive ? Theme.px(8) : 0
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                Behavior on y { enabled: !Theme.reducedMotion; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

                Rectangle {
                    width: Theme.px(root.denseNavigation ? 42 : 50)
                    height: width
                    radius: width / 2
                    color: Theme.logoCapsuleSurface
                    border.width: Math.max(1, Theme.px(1))
                    border.color: Theme.borderStrong

                    Image {
                        anchors.fill: parent
                        anchors.margins: Theme.px(3)
                        source: assetRoot + "/" + Theme.logoFile
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                    }
                }

                Text {
                    width: parent.width
                    text: "KFPS"
                    color: Theme.primaryBright
                    font.family: Theme.displayFamily
                    font.pixelSize: Theme.px(root.denseNavigation ? 12.5 : 14)
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    anchors.horizontalCenter: parent.horizontalCenter
                }
            }

            Text {
                visible: Theme.supporterTheme
                anchors.centerIn: parent
                width: parent.width - Theme.px(10)
                text: "CREATE INSANE"
                color: Theme.primaryBright
                opacity: root.insaneActive ? 1 : 0
                scale: root.insaneActive ? 1.0 : 0.72
                font.family: Theme.displayFamily
                font.pixelSize: Theme.px(root.compact ? 11.5 : 16)
                font.weight: Font.Black
                font.letterSpacing: Theme.px(root.compact ? 0.6 : 1.1)
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.NoWrap
                elide: Text.ElideRight
                fontSizeMode: Text.HorizontalFit
                minimumPixelSize: Theme.px(root.compact ? 8.5 : 11.5)
                Behavior on opacity { enabled: !Theme.reducedMotion; NumberAnimation { duration: 210; easing.type: Easing.OutCubic } }
                Behavior on scale { enabled: !Theme.reducedMotion; NumberAnimation { duration: 210; easing.type: Easing.OutBack } }
            }

            TapHandler {
                acceptedButtons: Qt.LeftButton
                enabled: Theme.supporterTheme
                onTapped: root.registerLogoTap()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(1, Theme.px(1))
            color: Theme.border
            opacity: 0.55
        }

        ListView {
            id: navList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: root.navItems
            currentIndex: root.pageIndex(appController.currentPage)
            spacing: Theme.px(4)
            boundsBehavior: Flickable.StopAtBounds
            keyNavigationEnabled: true

            delegate: NavButton {
                required property var modelData
                width: ListView.view.width
                text: modelData.label
                iconName: modelData.icon
                compact: root.compact
                dense: root.denseNavigation
                active: root.primaryPage(appController.currentPage) === modelData.page
                onClicked: root.route(modelData.page)
            }

            ScrollBar.vertical: ScrollBar {
                policy: navList.contentHeight > navList.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
            }

            onCurrentIndexChanged: Qt.callLater(function () {
                if (currentIndex >= 0)
                    positionViewAtIndex(currentIndex, ListView.Contain)
            })

            Component.onCompleted: Qt.callLater(function () {
                if (currentIndex >= 0)
                    positionViewAtIndex(currentIndex, ListView.Contain)
            })
        }

        GlassPanel {
            visible: !root.compact
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.px(root.denseNavigation ? 76 : 90)
            soft: true

            Column {
                anchors.fill: parent
                anchors.margins: Theme.px(11)
                spacing: Theme.px(4)

                Text {
                    width: parent.width
                    text: Theme.supporterSignatureVisible ? Theme.supporterSignatureText : "Single path per task"
                    color: Theme.primaryBright
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(Theme.supporterSignatureVisible ? 11.2 : 10.2)
                    font.weight: Theme.supporterSignatureVisible ? Font.DemiBold : Font.DemiBold
                    font.italic: Theme.supporterSignatureVisible
                    wrapMode: Theme.supporterSignatureVisible ? Text.WordWrap : Text.NoWrap
                    maximumLineCount: Theme.supporterSignatureVisible ? 2 : 1
                    lineHeight: Theme.supporterSignatureVisible ? 0.94 : 1.0
                    lineHeightMode: Text.ProportionalHeight
                    elide: Theme.supporterSignatureVisible ? Text.ElideNone : Text.ElideRight
                }

                Text {
                    width: parent.width
                    text: Theme.supporterSignatureVisible ? Theme.activeThemeName : "Folders and maintenance are in Settings."
                    color: Theme.subtle
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(10.2)
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
            }
        }
    }

    Timer {
        id: logoTapReset
        interval: 1600
        repeat: false
        onTriggered: root.logoTapCount = 0
    }

    Timer {
        id: insaneTimer
        interval: 5000
        repeat: false
        onTriggered: root.insaneActive = false
    }
}
