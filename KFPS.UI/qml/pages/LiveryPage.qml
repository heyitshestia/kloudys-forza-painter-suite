import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Dialogs 6.7
import QtQuick.Layouts 6.7
import QtWebEngine
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    objectName: "LiveryPage"
    anchors.fill: parent
    clip: true

    readonly property bool wide: Theme.logical(width) >= 1180
    readonly property bool compactHeight: Theme.logical(height) < 760

    Component.onCompleted: {
        fullLiveryService.refreshPackages()
        fullLiveryService.scanSaves()
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.px(10)

        GlassPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: toolbarContent.implicitHeight + Theme.px(20)
            strong: true

            RowLayout {
                id: toolbarContent
                anchors.fill: parent
                anchors.margins: Theme.px(10)
                spacing: Theme.px(8)

                Icon {
                    name: "monitor"
                    iconSize: Theme.px(30)
                    glow: true
                    Layout.alignment: Qt.AlignVCenter
                }

                SectionHeading {
                    Layout.fillWidth: true
                    title: "Full Livery Workshop"
                    subtitle: fullLiveryService.summary
                }

                GhostButton {
                    dense: true
                    text: fullLiveryService.gameFolder.length > 0 ? "FH6 Linked" : "FH6 Folder"
                    iconName: "folder"
                    enabled: !fullLiveryService.running
                    toolTipText: fullLiveryService.gameFolder.length > 0
                                 ? "FH6 is linked at " + fullLiveryService.gameFolder + ". Choose this again to change it."
                                 : "Choose the local FH6 game or Content folder used to resolve car IDs and meshes."
                    onClicked: fullLiveryService.chooseGameFolder()
                }

                GhostButton {
                    dense: true
                    text: "Save Folder"
                    iconName: "folder"
                    enabled: !fullLiveryService.running
                    toolTipText: "Choose the FH6 GameSave root if it was not found automatically."
                    onClicked: fullLiveryService.chooseSaveRoot()
                }

                GhostButton {
                    objectName: "clearFullLiveryCacheButton"
                    dense: true
                    text: "Clear Cache"
                    iconName: "refresh"
                    enabled: !fullLiveryService.running
                    toolTipText: "Remove rebuilt full-livery previews, car meshes, and indexes. Saved liveries and packages are kept."
                    onClicked: fullLiveryService.clearFullLiveryCache()
                }

                PrimaryButton {
                    dense: true
                    text: fullLiveryService.running ? "Working..." : "Scan Saves"
                    iconName: "refresh"
                    enabled: !fullLiveryService.running
                    toolTipText: "Find unique full-car FH6 livery records without changing the save."
                    onClicked: fullLiveryService.scanSaves()
                }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            columns: root.wide ? 3 : 2
            columnSpacing: Theme.px(10)
            rowSpacing: Theme.px(10)

            GlassPanel {
                Layout.fillHeight: true
                Layout.preferredWidth: Theme.px(330)
                Layout.minimumWidth: Theme.px(280)
                Layout.maximumWidth: Theme.px(390)
                soft: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.px(11)
                    spacing: Theme.px(7)

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: "Local FH6 liveries"
                            color: Theme.text
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(15)
                            font.weight: Font.DemiBold
                        }
                        Text {
                            text: localLiveries.count
                            color: Theme.subtle
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.px(10)
                        }
                    }

                    FastListView {
                        id: localLiveries
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: Theme.px(180)
                        model: fullLiveryService.sourceModel
                        spacing: Theme.px(3)
                        clip: true

                        delegate: Item {
                            id: sourceDelegate
                            required property string title
                            required property string path
                            required property int carId
                            required property string modelCode
                            required property int placementCount
                            required property bool exportable
                            required property string privacyDetail
                            width: localLiveries.width
                            height: sourceRow.implicitHeight

                            Rectangle {
                                anchors.fill: parent
                                visible: sourceDelegate.path === fullLiveryService.selectedSource
                                radius: Theme.framedRadius(Theme.px(5))
                                color: Theme.rowSelectedSurface
                                border.width: Math.max(1, Theme.px(1))
                                border.color: Theme.primary
                            }

                            QuickActionRow {
                                id: sourceRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                dense: true
                                iconName: "transfer"
                                title: sourceDelegate.title
                                subtitle: sourceDelegate.modelCode + " · " + sourceDelegate.placementCount + " placements · "
                                          + (sourceDelegate.exportable ? "ready to export" : "preview only")
                                toolTipText: sourceDelegate.exportable
                                             ? "Select this owned full-car livery for preview or export."
                                             : sourceDelegate.privacyDetail
                                onClicked: fullLiveryService.selectSource(sourceDelegate.path)
                            }
                        }

                        ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }

                        EmptyState {
                            anchors.centerIn: parent
                            visible: localLiveries.count === 0
                            iconName: "monitor"
                            title: fullLiveryService.running ? "Scanning saves" : "No liveries scanned"
                            message: "Scan the FH6 GameSave folder to list full-car livery records."
                        }
                    }

                    PrimaryButton {
                        Layout.fillWidth: true
                        dense: true
                        text: fullLiveryService.running ? "Packaging..." : "Export Selected"
                        iconName: "transfer"
                        enabled: !fullLiveryService.running
                                 && fullLiveryService.selectedSource.length > 0
                                 && fullLiveryService.selectedSourceExportable
                        toolTipText: fullLiveryService.selectedSourceExportable
                                     ? "Create a verified shareable package and add it directly to Saved packages. Game meshes stay local."
                                     : fullLiveryService.selectedSourcePrivacyMessage
                        onClicked: fullLiveryService.exportSelected()
                    }

                    Text {
                        Layout.fillWidth: true
                        visible: fullLiveryService.selectedSource.length > 0
                                 && !fullLiveryService.selectedSourceExportable
                        text: fullLiveryService.selectedSourcePrivacyMessage
                        color: Theme.warning
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(10.5)
                        wrapMode: Text.WordWrap
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(1, Theme.px(1))
                        color: Theme.divider
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: "Saved packages"
                            color: Theme.text
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(15)
                            font.weight: Font.DemiBold
                        }
                        GhostButton {
                            dense: true
                            text: "Add"
                            iconName: "folder"
                            toolTipText: "Validate and add a received .kfpslivery package to this KFPS instance."
                            onClicked: fullLiveryService.choosePackage()
                        }
                    }

                    FastListView {
                        id: packages
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: Theme.px(150)
                        model: fullLiveryService.packageModel
                        spacing: Theme.px(3)
                        clip: true

                        delegate: Item {
                            id: packageDelegate
                            required property string title
                            required property string path
                            required property string modelCode
                            required property int placementCount
                            required property bool portableMesh
                            width: packages.width
                            height: packageRow.implicitHeight

                            Rectangle {
                                anchors.fill: parent
                                visible: packageDelegate.path === fullLiveryService.selectedPackage
                                radius: Theme.framedRadius(Theme.px(5))
                                color: Theme.rowSelectedSurface
                                border.width: Math.max(1, Theme.px(1))
                                border.color: Theme.primary
                            }

                            QuickActionRow {
                                id: packageRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                dense: true
                                iconName: "monitor"
                                title: packageDelegate.title
                                subtitle: packageDelegate.modelCode + " · " + packageDelegate.placementCount + " placements"
                                toolTipText: packageDelegate.portableMesh
                                             ? "Open this development package in the interactive car inspector."
                                             : "Open this verified package using the matching car assets from your local FH6 installation."
                                onClicked: fullLiveryService.selectPackage(packageDelegate.path)
                            }
                        }

                        ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
                    }

                    GhostButton {
                        Layout.fillWidth: true
                        dense: true
                        text: "Open Package Folder"
                        iconName: "folder"
                        toolTipText: "Open the folder containing shareable full-livery packages."
                        onClicked: fullLiveryService.openPackageFolder()
                    }
                }
            }

            GlassPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: Theme.px(470)
                strong: true
                clip: true

                WebEngineView {
                    id: inspector
                    anchors.fill: parent
                    anchors.margins: Math.max(1, Theme.px(1))
                    visible: fullLiveryService.viewerUrl.length > 0
                    url: fullLiveryService.viewerUrl.length > 0
                         ? fullLiveryService.viewerUrl
                         : "about:blank"
                    backgroundColor: "#090b0e"
                    settings.localContentCanAccessRemoteUrls: false
                    settings.localContentCanAccessFileUrls: false
                    settings.javascriptCanOpenWindows: false
                }

                EmptyState {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - Theme.px(40), Theme.px(460))
                    visible: fullLiveryService.viewerUrl.length === 0
                    iconName: "monitor"
                    title: fullLiveryService.selectedPackage.length > 0
                           ? fullLiveryService.status
                           : "Open a full-livery package"
                    message: fullLiveryService.selectedPackage.length > 0
                             ? fullLiveryService.summary
                             : "Select a saved package to inspect the resolved car, turn it freely, zoom in, and isolate projected livery sections."
                }
            }

            GlassPanel {
                Layout.fillHeight: true
                Layout.fillWidth: !root.wide
                Layout.preferredWidth: root.wide ? Theme.px(310) : -1
                Layout.minimumWidth: root.wide ? Theme.px(270) : 0
                Layout.maximumWidth: root.wide ? Theme.px(360) : -1
                Layout.columnSpan: root.wide ? 1 : 2
                Layout.preferredHeight: root.wide ? -1 : Theme.px(250)
                soft: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.px(11)
                    spacing: Theme.px(7)

                    Text {
                        Layout.fillWidth: true
                        text: fullLiveryService.selectedTitle
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.px(16)
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }

                    Text {
                        Layout.fillWidth: true
                        text: fullLiveryService.selectedVehicle + "\n" + fullLiveryService.selectedCounts
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(10.5)
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "FH6 package policy"
                        color: Theme.primaryBright
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.px(13)
                        font.weight: Font.DemiBold
                    }

                    FastListView {
                        id: decisions
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: Theme.px(130)
                        model: fullLiveryService.decisionModel
                        spacing: Theme.px(3)
                        clip: true

                        delegate: Item {
                            required property string action
                            required property string item
                            required property string detail
                            width: decisions.width
                            height: decisionColumn.implicitHeight + Theme.px(12)

                            Column {
                                id: decisionColumn
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: Theme.px(2)
                                Text {
                                    width: parent.width
                                    text: action + "  " + item
                                    color: action === "DISCARD" ? Theme.danger
                                           : (action === "CHANGE" ? Theme.warning
                                           : (action === "KEEP" ? Theme.success : Theme.primaryBright))
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.px(9.5)
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.WordWrap
                                }
                                Text {
                                    width: parent.width
                                    text: detail
                                    color: Theme.subtle
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(9)
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }

                        ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
                    }

                    PrimaryButton {
                        objectName: "installExactCarFullLiveryButton"
                        Layout.fillWidth: true
                        dense: true
                        text: fullLiveryService.running ? "Working..." : "Install in FH6 Save"
                        iconName: "transfer"
                        enabled: !fullLiveryService.running && fullLiveryService.selectedPackageInstallable
                        toolTipText: fullLiveryService.selectedPackageInstallable
                                     ? "Install this package as a new local livery for its exact FH6 car."
                                     : "Open a verified shareable package for its exact FH6 car first."
                        onClicked: installConfirm.open()
                    }

                    StatusRow {
                        Layout.fillWidth: true
                        dense: true
                        label: "Package state"
                        value: fullLiveryService.status
                        state: fullLiveryService.status.indexOf("failed") >= 0 || fullLiveryService.status.indexOf("rejected") >= 0 ? "bad"
                               : (fullLiveryService.running ? "warn" : "ok")
                    }
                }
            }
        }
    }

    MessageDialog {
        id: installConfirm
        title: "Install this FH6 livery?"
        text: "KFPS will verify the package against the exact car, create a recovery record, and add a new livery without replacing existing save entries. Different-car installation is blocked. FH6 may need to reload its save before the new livery appears."
        buttons: MessageDialog.Ok | MessageDialog.Cancel
        onAccepted: fullLiveryService.installSelectedPackage()
    }
}
