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
        { page: "help", label: "Help", icon: "help" },
        { page: "settings", label: "Settings", icon: "settings" }
    ]
    signal route(string page)

    function primaryPage(page) {
        if (page === "outputs" || page === "json" || page === "library")
            return "outputs"
        if (page === "editor")
            return "editor"
        if (page === "help" || page === "learn")
            return "help"
        if (page === "settings" || page === "reports" || page === "update")
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
        source: assetRoot + "/branch-bottom.png"
        width: root.width * (root.compact ? 2.6 : 1.95)
        height: root.height * 0.37
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.leftMargin: -width * 0.28
        anchors.bottomMargin: Theme.px(28)
        fillMode: Image.PreserveAspectFit
        opacity: root.compact ? 0.30 : 0.40
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
                visible: !root.compact
                anchors.centerIn: parent
                spacing: Theme.px(10)

                Rectangle {
                    width: Theme.px(root.denseNavigation ? 48 : 56)
                    height: width
                    radius: width / 2
                    color: "#45160b22"
                    border.width: Math.max(1, Theme.px(1))
                    border.color: Theme.borderStrong

                    Image {
                        anchors.fill: parent
                        anchors.margins: Theme.px(3)
                        source: assetRoot + "/kfps-logo.png"
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                        mipmap: true
                    }
                }

                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Theme.px(1)

                    Text {
                        text: "KFPS"
                        color: Theme.primaryBright
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.px(root.denseNavigation ? 21 : 25)
                        font.weight: Font.DemiBold
                        font.letterSpacing: Theme.px(1.4)
                    }

                    Text {
                        text: "Create-first"
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(root.denseNavigation ? 8.8 : 9.5)
                    }

                    Text {
                        text: "Painter Suite"
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(root.denseNavigation ? 8.8 : 9.5)
                    }
                }
            }

            Column {
                visible: root.compact
                anchors.centerIn: parent
                spacing: Theme.px(3)

                Rectangle {
                    width: Theme.px(root.denseNavigation ? 42 : 50)
                    height: width
                    radius: width / 2
                    color: "#45160b22"
                    border.width: Math.max(1, Theme.px(1))
                    border.color: Theme.borderStrong

                    Image {
                        anchors.fill: parent
                        anchors.margins: Theme.px(3)
                        source: assetRoot + "/kfps-logo.png"
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
            Layout.preferredHeight: Theme.px(root.denseNavigation ? 58 : 68)
            soft: true

            Column {
                anchors.fill: parent
                anchors.margins: Theme.px(9)
                spacing: Theme.px(2)

                Text {
                    width: parent.width
                    text: "Single path per task"
                    color: Theme.primaryBright
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(10.2)
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Text {
                    width: parent.width
                    text: "Folders and maintenance are in Settings."
                    color: Theme.subtle
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(8.7)
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
            }
        }
    }
}
