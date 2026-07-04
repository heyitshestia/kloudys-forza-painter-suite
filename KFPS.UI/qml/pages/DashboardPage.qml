import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    anchors.fill: parent
    property bool compactHeight: Theme.logical(height) < 520
    property bool threeColumns: Theme.logical(width) >= 900
    property real heroCardHeight: Theme.px(compactHeight ? 91 : 128)
    property real workflowCardHeight: Theme.px(compactHeight ? 154 : 170)
    property real lowerCardHeight: Theme.px(compactHeight ? 178 : 250)

    focus: true

    Component.onCompleted: Qt.callLater(function () {
        root.forceActiveFocus(Qt.OtherFocusReason);
        if (scroll.contentItem)
            scroll.contentItem.contentY = 0;
    })
    property real heroHeight: threeColumns ? heroCardHeight : heroCardHeight * 2 + Theme.px(10)
    property real workflowHeight: threeColumns ? workflowCardHeight : workflowCardHeight * 3 + Theme.px(20)
    property real lowerMinimum: threeColumns ? lowerCardHeight : lowerCardHeight * 3 + Theme.px(20)

    FastScrollView {
        id: scroll
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: contentItem.contentHeight > availableHeight ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff

        ColumnLayout {
            width: scroll.availableWidth
            height: Math.max(scroll.availableHeight, implicitHeight)
            spacing: Theme.px(10)

            GridLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: root.heroHeight
                columns: root.threeColumns ? 2 : 1
                columnSpacing: Theme.px(16)
                rowSpacing: Theme.px(10)

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: root.heroCardHeight
                    Layout.minimumHeight: root.heroCardHeight
                    Layout.preferredWidth: root.threeColumns ? (scroll.availableWidth - Theme.px(16)) / 2 : scroll.availableWidth

                    Row {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.px(11)

                        Icon {
                            name: "petal"
                            iconSize: Theme.px(root.compactHeight ? 20 : 27)
                            glow: true
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Column {
                            spacing: Theme.px(6)
                            Text {
                                text: "Welcome to KFPS"
                                color: Theme.text
                                font.family: Theme.displayFamily
                                font.pixelSize: Theme.px(root.compactHeight ? 25 : 30)
                                font.weight: Font.DemiBold
                            }
                            Text {
                                text: "Your all-in-one toolkit for image-to-vinyl workflows."
                                color: Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(root.compactHeight ? 11.5 : 13.5)
                            }
                        }
                    }
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: root.heroCardHeight
                    Layout.minimumHeight: root.heroCardHeight
                    Layout.preferredWidth: root.threeColumns ? (scroll.availableWidth - Theme.px(16)) / 2 : scroll.availableWidth
                    strong: true
                    padding: Theme.px(root.compactHeight ? 14 : 18)

                    RowLayout {
                        anchors.fill: parent
                        spacing: Theme.px(root.compactHeight ? 12 : 18)

                        Icon {
                            name: "coffee"
                            iconSize: Theme.px(root.compactHeight ? 48 : 68)
                            glow: true
                            Layout.alignment: Qt.AlignVCenter
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.px(5)
                            Text {
                                Layout.fillWidth: true
                                text: "Support KFPS"
                                color: Theme.primaryBright
                                font.family: Theme.displayFamily
                                font.pixelSize: Theme.px(root.compactHeight ? 14 : 17)
                                font.weight: Font.DemiBold
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "KFPS is free and made with passion. Optional support helps future development, testing, and documentation."
                                color: Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(root.compactHeight ? 9.5 : 11)
                                wrapMode: Text.Wrap
                                lineHeight: 1.24
                                maximumLineCount: root.compactHeight ? 2 : 3
                                elide: Text.ElideRight
                            }
                        }
                        PrimaryButton {
                            text: "Support on Ko-fi"
                            iconName: "heart"
                            minimumWidth: Theme.px(root.compactHeight ? 132 : 150)
                            Layout.alignment: Qt.AlignVCenter
                            onClicked: desktop.openUrl("https://ko-fi.com/kloudy1811")
                        }
                    }
                }
            }

            GridLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: root.workflowHeight
                columns: root.threeColumns ? 3 : 1
                columnSpacing: Theme.px(10)
                rowSpacing: Theme.px(10)

                WorkflowCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: root.workflowCardHeight
                    Layout.minimumHeight: root.workflowCardHeight
                    number: "1"
                    title: "Generate Vinyl"
                    description: "Start from a source image and build finalized JSON checkpoints with live previews."
                    iconName: "generate"
                    buttonText: "Open Generator"
                    onAction: appController.navigate("generate")
                }
                WorkflowCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: root.workflowCardHeight
                    Layout.minimumHeight: root.workflowCardHeight
                    number: "2"
                    title: "Edit by Hand"
                    description: "Fine-tune layers, masks, colors, text, guides, and deliberate cleanup in the Fabric editor."
                    iconName: "editor"
                    buttonText: "Launch Editor"
                    onAction: editorService.launch()
                }
                WorkflowCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: root.workflowCardHeight
                    Layout.minimumHeight: root.workflowCardHeight
                    number: "3"
                    title: "Import / Export"
                    description: "Select a JSON, import it into a prepared game template, or export an editable game group."
                    iconName: "transfer"
                    buttonText: "Open Import / Export"
                    onAction: appController.navigate("json")
                }
            }

            GridLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: root.lowerMinimum
                Layout.preferredHeight: root.lowerMinimum
                columns: root.threeColumns ? 3 : 1
                columnSpacing: Theme.px(10)
                rowSpacing: Theme.px(10)

                HoverCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: root.lowerCardHeight
                    Layout.preferredHeight: root.lowerCardHeight
                    padding: Theme.px(root.compactHeight ? 12 : 16)
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Theme.px(4)
                        RowLayout {
                            Layout.fillWidth: true
                            Icon {
                                name: "folder"
                                iconSize: Theme.px(17)
                                glow: true
                            }
                            Text {
                                text: "Recent JSON Projects"
                                color: Theme.primaryBright
                                font.family: Theme.displayFamily
                                font.pixelSize: Theme.px(14)
                                font.weight: Font.DemiBold
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                        }
                        ListView {
                            id: recent
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            model: jsonService.recentModel
                            clip: true
                            interactive: false
                            delegate: RecentJsonRow {
                                width: recent.width
                                fileName: name
                                folder: folder
                                age: age
                                dense: root.compactHeight
                                onClicked: {
                                    jsonService.selectPath(path);
                                    appController.navigate("json");
                                }
                            }
                        }
                        GhostButton {
                            Layout.alignment: Qt.AlignHCenter
                            text: "Open JSON Manager"
                            accentText: true
                            showArrow: true
                            dense: root.compactHeight
                            minimumWidth: Theme.px(root.compactHeight ? 146 : 168)
                            onClicked: appController.navigate("json")
                        }
                    }
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: root.lowerCardHeight
                    Layout.preferredHeight: root.lowerCardHeight
                    padding: Theme.px(root.compactHeight ? 12 : 16)
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0
                        RowLayout {
                            Layout.fillWidth: true
                            Icon {
                                name: "bolt"
                                iconSize: Theme.px(17)
                                glow: true
                            }
                            Text {
                                text: "Quick Actions"
                                color: Theme.primaryBright
                                font.family: Theme.displayFamily
                                font.pixelSize: Theme.px(14)
                                font.weight: Font.DemiBold
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                        }
                        QuickActionRow {
                            Layout.fillWidth: true
                            dense: root.compactHeight
                            iconName: "source-check"
                            title: "Source Image Check"
                            subtitle: "Inspect source size, alpha, and practical targets"
                            onClicked: appController.navigate("images")
                        }
                        QuickActionRow {
                            Layout.fillWidth: true
                            dense: root.compactHeight
                            iconName: "tools"
                            title: "Image Tools"
                            subtitle: "Background removal, upscaling, and compression"
                            onClicked: appController.navigate("tools")
                        }
                        QuickActionRow {
                            Layout.fillWidth: true
                            dense: root.compactHeight
                            iconName: "folder"
                            title: "Open Projects Folder"
                            subtitle: "Browse Fabric editor project files"
                            onClicked: desktop.openProjects()
                        }
                        QuickActionRow {
                            Layout.fillWidth: true
                            dense: root.compactHeight
                            iconName: "reports"
                            title: "Bug Report / Report"
                            subtitle: "Preview or save a private local report"
                            onClicked: appController.navigate("reports")
                        }
                    }
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: root.lowerCardHeight
                    Layout.preferredHeight: root.lowerCardHeight
                    padding: Theme.px(root.compactHeight ? 12 : 16)
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0
                        RowLayout {
                            Layout.fillWidth: true
                            Icon {
                                name: "monitor"
                                iconSize: Theme.px(17)
                                glow: true
                            }
                            Text {
                                text: "System Status"
                                color: Theme.primaryBright
                                font.family: Theme.displayFamily
                                font.pixelSize: Theme.px(14)
                                font.weight: Font.DemiBold
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                        }
                        StatusRow {
                            Layout.fillWidth: true
                            dense: root.compactHeight
                            label: "Python"
                            value: runtimeService.pythonText
                            state: runtimeService.ready ? "ok" : "warn"
                        }
                        StatusRow {
                            Layout.fillWidth: true
                            dense: root.compactHeight
                            label: "Dependencies"
                            value: runtimeService.dependenciesText
                            state: runtimeService.ready ? "ok" : "warn"
                        }
                        StatusRow {
                            Layout.fillWidth: true
                            dense: root.compactHeight
                            label: "Runtime"
                            value: runtimeService.runtimeText
                            state: runtimeService.ready ? "ok" : "warn"
                        }
                        StatusRow {
                            Layout.fillWidth: true
                            dense: root.compactHeight
                            label: "Last Update Check"
                            value: versionService.checking ? "Checking…" : "Just now"
                            state: versionService.updateAvailable ? "warn" : "ok"
                        }
                        Item {
                            Layout.fillHeight: true
                        }
                        GhostButton {
                            Layout.alignment: Qt.AlignHCenter
                            text: "Open Settings"
                            iconName: "settings"
                            dense: root.compactHeight
                            minimumWidth: Theme.px(root.compactHeight ? 124 : 142)
                            onClicked: appController.navigate("settings")
                        }
                    }
                }
            }
        }
    }
}
