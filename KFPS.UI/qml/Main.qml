import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "shell"
import "components"

ApplicationWindow {
    id: window

    width: Metrics.launchWidth
    height: Metrics.launchHeight
    minimumWidth: Metrics.minWidth
    minimumHeight: Metrics.minHeight
    visible: true
    color: Theme.backgroundA
    title: appController.windowTitle
    flags: Qt.Window | Qt.FramelessWindowHint

    onActiveChanged: {
        if (active) {
            supporterService.refresh()
        }
    }

    Timer {
        interval: 2500
        repeat: true
        running: true
        onTriggered: supporterService.refresh()
    }

    readonly property real viewportFitScale: Theme.clamp(
                                                Math.min(width / Metrics.launchWidth,
                                                         height / Metrics.launchHeight),
                                                0.72,
                                                1.75)
    property bool compactSidebar: Theme.logical(width) < 1240
    property bool shortWindow: Theme.logical(height) < 760
    property bool compactHeader: Theme.logical(width) < 1280
    property real sidebarWidth: Theme.px(compactSidebar ? Metrics.compactSidebar : Metrics.wideSidebar)
    property real headerHeight: Theme.px(shortWindow ? Metrics.compactHeaderHeight : Metrics.headerHeight)
    property real consoleExpandedHeight: Theme.px(shortWindow ? Metrics.compactConsoleHeight : Metrics.consoleHeight)
    property real consoleHeight: settings.consoleCollapsed
                                 ? Theme.px(Metrics.consoleCollapsedHeight)
                                 : consoleExpandedHeight
    property Item glassBackdropSource: backdropLayer
    property bool updateAutoOpened: false

    Binding { target: Theme; property: "viewportScale"; value: window.viewportFitScale }
    Binding { target: Theme; property: "uiScale"; value: settings.uiScale }
    Binding { target: Theme; property: "reducedMotion"; value: settings.reducedMotion }
    Binding { target: Theme; property: "ambientMotion"; value: settings.ambientMotion }
    Binding { target: Theme; property: "glassEffects"; value: settings.glassEffects }
    Binding { target: Theme; property: "themeName"; value: settings.theme }
    Binding { target: Theme; property: "supporterUnlocked"; value: supporterService.unlocked }

    Connections {
        target: versionService
        function onChanged() {
            if (versionService.updateAvailable && !window.updateAutoOpened) {
                window.updateAutoOpened = true
                appController.navigate("update")
            } else if (!versionService.updateAvailable) {
                window.updateAutoOpened = false
            }
        }
    }

    BlossomBackdrop {
        id: backdropLayer
        anchors.fill: parent
    }

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.width: Math.max(1, Theme.px(1))
        border.color: Theme.appBorder
        z: 200
    }

    Column {
        anchors.fill: parent
        spacing: 0

        AppTitleBar {
            id: titleBar
            width: parent.width
            window: window
            z: 50
        }

        Item {
            width: parent.width
            height: parent.height - titleBar.height

            Sidebar {
                id: sidebar
                compact: window.compactSidebar
                railWidth: window.sidebarWidth
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                onRoute: page => appController.navigate(page)
                z: 10
            }

            Item {
                id: workspace
                anchors.left: sidebar.right
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom

                HeaderControls {
                    compact: window.compactHeader
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.topMargin: Theme.px(window.shortWindow ? 10 : 16)
                    anchors.rightMargin: Theme.px(16)
                    z: 20
                }

                VersionPill {
                    id: versionPill
                    compact: window.compactHeader
                    anchors.top: parent.top
                    anchors.topMargin: Theme.px(window.shortWindow ? 10 : 16)
                    x: Math.max(Theme.px(14), (window.width - width) / 2 - workspace.x)
                    z: 20
                }

                SupporterPill {
                    compact: window.compactHeader
                    anchors.top: parent.top
                    anchors.topMargin: Theme.px(window.shortWindow ? 12 : 18)
                    x: Math.max(
                           Theme.px(14),
                           Math.min(
                               versionPill.x - width - Theme.px(14),
                               Math.max(Theme.px(14), (versionPill.x - width) / 2)
                           )
                       )
                    z: 20
                }

                ColumnLayout {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: Theme.px(12)
                    anchors.rightMargin: Theme.px(14)
                    anchors.topMargin: window.headerHeight
                    anchors.bottomMargin: Theme.px(11)
                    spacing: Theme.px(10)

                    Loader {
                        id: pageLoader
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: Theme.px(100)
                        clip: true
                        source: "pages/" + ({
                            create: "CreatePage",
                            dashboard: "CreatePage",
                            outputs: "JsonPage",
                            library: "JsonPage",
                            json: "JsonPage",
                            generate: "GeneratePage",
                            editor: "EditorPage",
                            images: "ImagesPage",
                            tools: "ToolsPage",
                            help: "HelpPage",
                            learn: "HelpPage",
                            reports: "ReportsPage",
                            update: "UpdatePage",
                            settings: "SettingsPage"
                        }[appController.currentPage]) + ".qml"
                        opacity: 1

                        onSourceChanged: {
                            if (!Theme.reducedMotion) {
                                opacity = 0
                                pageFade.restart()
                            }
                        }

                        NumberAnimation {
                            id: pageFade
                            target: pageLoader
                            property: "opacity"
                            from: 0
                            to: 1
                            duration: 190
                            easing.type: Easing.OutCubic
                        }
                    }

                    BottomPanel {
                        id: bottom
                        visible: appController.showBottomPanel
                        Layout.fillWidth: true
                        Layout.preferredHeight: visible ? window.consoleHeight : 0
                        Layout.minimumHeight: visible ? window.consoleHeight : 0
                        mode: appController.bottomMode
                        collapsed: settings.consoleCollapsed
                        onToggle: settings.consoleCollapsed = !settings.consoleCollapsed
                    }
                }
            }
        }
    }
}
