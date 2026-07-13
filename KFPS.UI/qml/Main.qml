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

    Component.onCompleted: supporterService.startActivation()

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
                onCreditsRequested: appController.navigate("credits")
                z: 10
            }

            Item {
                id: workspace
                anchors.left: sidebar.right
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                property real controlsTopMargin: announcementTicker.visible
                                                 ? Theme.px(window.shortWindow ? 42 : 54)
                                                 : Theme.px(window.shortWindow ? 10 : 16)
                readonly property bool pageHeaderAlignmentAvailable: Boolean(pageLoader.item && pageLoader.item.headerAlignmentAvailable)
                readonly property real headerSafeMargin: Theme.px(14)
                readonly property real headerRightReserve: Math.max(
                    headerControls.visible ? headerControls.width + Theme.px(30) : 0,
                    supporterPromo.visible ? supporterPromo.width + Theme.px(30) : 0
                )
                readonly property real headerRightLimit: Math.max(
                    headerSafeMargin,
                    width - headerRightReserve - headerSafeMargin
                )
                readonly property real headerFallbackBannerWidth: Math.max(
                    Theme.px(window.compactHeader ? 420 : 540),
                    Math.min(
                        Theme.px(supporterPromo.visible ? 760 : (window.compactHeader ? 720 : 900)),
                        width - Theme.px(window.compactHeader ? 320 : 680)
                    )
                )
                readonly property real headerFallbackBannerX: Theme.clamp(
                    (width - headerFallbackBannerWidth) / 2 + (supporterPromo.visible ? -Theme.px(220) : -Theme.px(80)),
                    Theme.px(12),
                    Math.max(Theme.px(12), width - headerFallbackBannerWidth - Theme.px(12))
                )
                readonly property real headerBannerLeft: pageHeaderX("headerBannerLeftX", headerFallbackBannerX)
                readonly property real headerRawBannerRight: pageHeaderX("headerBannerRightX", headerFallbackBannerX + headerFallbackBannerWidth)
                readonly property real headerBannerRight: pageHeaderAlignmentAvailable
                                                          ? Math.min(headerRawBannerRight, headerRightLimit)
                                                          : headerRawBannerRight
                readonly property real headerAlignedBannerWidth: Math.max(
                    Theme.px(window.compactHeader ? 420 : 540),
                    headerBannerRight - headerBannerLeft
                )
                readonly property real headerBannerWidth: pageHeaderAlignmentAvailable ? headerAlignedBannerWidth : headerFallbackBannerWidth
                readonly property real headerBannerX: pageHeaderAlignmentAvailable
                                                      ? Theme.clamp(headerBannerLeft + ((headerBannerRight - headerBannerLeft - headerBannerWidth) / 2),
                                                                    Theme.px(12),
                                                                    Math.max(Theme.px(12), width - headerBannerWidth - Theme.px(12)))
                                                      : headerFallbackBannerX
                readonly property real headerSourceCenterX: pageHeaderX("headerSourceCenterX", Math.max(headerSafeMargin, headerBannerX + headerBannerWidth * 0.28))
                readonly property real headerPreviewCenterX: pageHeaderX("headerPreviewCenterX", Math.max(headerSafeMargin, (window.width / 2) - workspace.x))

                function pageHeaderX(name, fallback) {
                    if (!pageHeaderAlignmentAvailable)
                        return fallback
                    var item = pageLoader.item
                    if (!item || item[name] === undefined)
                        return fallback
                    var value = Number(item[name])
                    if (!isFinite(value))
                        return fallback
                    return workspaceLayout.x + pageLoader.x + value
                }

                function centeredHeaderX(centerX, itemWidth) {
                    return Theme.clamp(centerX - itemWidth / 2,
                                       headerSafeMargin,
                                       Math.max(headerSafeMargin, width - headerRightReserve - itemWidth - headerSafeMargin))
                }

                AnnouncementTicker {
                    id: announcementTicker
                    compact: window.compactHeader
                    anchors.top: parent.top
                    anchors.topMargin: Theme.px(window.shortWindow ? 7 : 9)
                    x: workspace.headerBannerX + Theme.px(5)
                    width: Math.max(Theme.px(1), workspace.headerBannerWidth - Theme.px(10))
                    z: 24
                }

                HeaderControls {
                    id: headerControls
                    compact: window.compactHeader
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.topMargin: Theme.px(window.shortWindow ? 10 : 16)
                    anchors.rightMargin: Theme.px(16)
                    visible: !supporterPromo.visible
                    z: 20
                }

                VersionPill {
                    id: versionPill
                    compact: window.compactHeader
                    anchors.top: parent.top
                    anchors.topMargin: workspace.controlsTopMargin
                    x: workspace.pageHeaderAlignmentAvailable
                       ? workspace.centeredHeaderX(workspace.headerPreviewCenterX, width)
                       : Math.max(Theme.px(14), (window.width - width) / 2 - workspace.x)
                    z: 20
                }

                SupporterPill {
                    compact: window.compactHeader
                    anchors.top: parent.top
                    anchors.topMargin: workspace.controlsTopMargin + Theme.px(2)
                    x: workspace.pageHeaderAlignmentAvailable
                       ? workspace.centeredHeaderX(workspace.headerSourceCenterX, width)
                       : Math.max(
                             Theme.px(14),
                             Math.min(
                                 versionPill.x - width - Theme.px(14),
                                 Math.max(Theme.px(14), (versionPill.x - width) / 2)
                             )
                         )
                    z: 20
                }

                SupporterPromoToast {
                    id: supporterPromo
                    compact: window.compactHeader
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.topMargin: Theme.px(window.shortWindow ? -2 : 2)
                    anchors.rightMargin: Theme.px(16)
                    z: 80
                }

                SupporterActivationNotice {
                    id: activationNotice
                    compact: window.compactHeader
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.rightMargin: Theme.px(16)
                    anchors.bottomMargin: Theme.px(14)
                                          + (bottom.visible ? window.consoleHeight + Theme.px(10) : 0)
                    z: 120
                }

                ColumnLayout {
                    id: workspaceLayout
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
                            settings: "SettingsPage",
                            credits: "CreditsPage"
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
